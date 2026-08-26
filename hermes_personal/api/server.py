from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask
from starlette.staticfiles import StaticFiles

DIGEST_REGEX = re.compile(r"^sha256:[0-9a-f]{64}$")


def compute_static_bundle_digest(directory: Path) -> str:
    """Compute deterministic SHA-256 digest over all static assets.

    Scans the directory recursively, sorts relative POSIX paths stably, and computes
    a SHA-256 digest over the path and contents of each file. Rejects missing directories
    and directories missing an index.html file.
    """
    if not directory.exists() or not directory.is_dir():
        raise ValueError(f"Static bundle directory does not exist or is not a directory: {directory}")
    index_file = directory / "index.html"
    if not index_file.exists() or not index_file.is_file():
        raise ValueError(f"Static bundle directory is missing index.html: {directory}")

    entries: list[tuple[str, bytes]] = []
    for path in directory.rglob("*"):
        if path.is_file():
            rel_posix = path.relative_to(directory).as_posix()
            entries.append((rel_posix, path.read_bytes()))

    entries.sort(key=lambda item: item[0])
    hasher = hashlib.sha256()
    for rel_path, file_bytes in entries:
        hasher.update(rel_path.encode("utf-8"))
        hasher.update(b"\x00")
        hasher.update(file_bytes)
        hasher.update(b"\x00")
    return f"sha256:{hasher.hexdigest()}"


def verify_static_bundle_digest(directory: Path, expected_digest: str) -> None:
    """Verify static bundle digest against expected value using constant-time comparison."""
    if not isinstance(expected_digest, str) or not DIGEST_REGEX.match(expected_digest):
        raise ValueError(
            f"Malformed static digest '{expected_digest}': must be sha256:<64 lowercase hex>"
        )
    actual_digest = compute_static_bundle_digest(directory)
    if not hmac.compare_digest(actual_digest, expected_digest):
        raise ValueError(
            f"Static bundle digest mismatch: expected '{expected_digest}', computed '{actual_digest}'"
        )


def create_proxy_application(
    gateway_url: str,
    static_dir: Path | None = None,
    api_key: str = "",
    owner_user_id: str = "local-owner",
    browser_session_token: str | None = None,
    static_digest: str | None = None,
) -> FastAPI:
    if static_dir is not None and static_digest is not None:
        verify_static_bundle_digest(static_dir, static_digest)
    app = FastAPI(title="Hermes Application API", version="1.0.0")
    base_url = gateway_url.rstrip("/")
    session_token = browser_session_token or secrets.token_urlsafe(32)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def bootstrap() -> HTMLResponse:
        script = (
            "<script>"
            f"window.__HERMES_SESSION_TOKEN__={json.dumps(session_token)};"
            f"window.__HERMES_OWNER_ID__={json.dumps(owner_user_id)};"
            f"document.cookie='hermes_session={session_token}; SameSite=Strict; Path=/';"
            "window.__HERMES_DASHBOARD_EMBEDDED_CHAT__=true;"
            "</script>"
        )
        if static_dir is None:
            return HTMLResponse(f"<!doctype html><html><head>{script}</head></html>")
        html = (static_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("</head>", f"{script}</head>", 1))

    def authenticated(request: Request) -> bool:
        authorization = request.headers.get("authorization", "")
        header_token = authorization.removeprefix("Bearer ").strip()
        cookie_token = request.cookies.get("hermes_session", "")
        supplied = header_token or cookie_token
        return bool(supplied) and hmac.compare_digest(supplied, session_token)

    def upstream_request_parts(
        request: Request,
    ) -> tuple[dict[str, str], dict[str, str]]:
        params = dict(request.query_params)
        params.pop("auth_token", None)
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() in {"content-type", "idempotency-key"}
        }
        headers["authorization"] = f"Bearer {api_key}"
        return params, headers

    @app.get("/health/live")
    @app.get("/healthz", include_in_schema=False)
    async def live() -> dict[str, bool]:
        return {"live": True}

    @app.get("/health/ready")
    async def ready() -> JSONResponse:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base_url}/health/ready")
        except httpx.HTTPError:
            return JSONResponse(status_code=503, content={"ready": False})
        return JSONResponse(status_code=response.status_code, content=response.json())

    async def proxy_stream(request: Request, upstream_path: str):
        if not authenticated(request):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        client = httpx.AsyncClient(timeout=None)
        params, headers = upstream_request_parts(request)
        upstream = client.build_request(
            request.method,
            f"{base_url}{upstream_path}",
            params=params,
            headers=headers,
            content=await request.body(),
        )
        response = await client.send(upstream, stream=True)
        if response.status_code >= 400:
            content = await response.aread()
            await response.aclose()
            await client.aclose()
            return Response(
                content=content,
                status_code=response.status_code,
                media_type=response.headers.get("content-type"),
            )

        async def close_upstream() -> None:
            await response.aclose()
            await client.aclose()

        return StreamingResponse(
            response.aiter_raw(),
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            background=BackgroundTask(close_upstream),
        )

    async def proxy_buffered(request: Request, upstream_path: str) -> Response:
        if not authenticated(request):
            return JSONResponse(status_code=401, content={"error": "unauthorized"})
        params, headers = upstream_request_parts(request)
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    request.method,
                    f"{base_url}{upstream_path}",
                    params=params,
                    headers=headers,
                    content=await request.body(),
                )
        except httpx.HTTPError:
            return JSONResponse(
                status_code=503, content={"error": "gateway_unavailable"}
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
        )

    @app.post("/api/turn")
    async def turn(request: Request):
        return await proxy_stream(request, "/api/turn")

    @app.post("/api/omni/turn")
    async def omni_turn(request: Request):
        return await proxy_stream(request, "/api/omni/turn")

    @app.api_route("/api/events", methods=["GET"])
    @app.api_route("/api/events/replay", methods=["GET"])
    @app.api_route("/api/operator/command", methods=["POST"])
    async def events(request: Request):
        return await proxy_buffered(request, request.url.path)

    @app.get("/api/artifacts/{artifact_id}")
    async def artifact(artifact_id: str, request: Request):
        return await proxy_buffered(request, f"/api/artifacts/{artifact_id}")

    if static_dir is not None:
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="web")
    return app


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Hermes public application API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--gateway-port", type=int, default=8642)
    parser.add_argument("--static-dir", default=None)
    parser.add_argument("--static-digest", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    app = create_proxy_application(
        f"http://127.0.0.1:{args.gateway_port}",
        Path(args.static_dir) if args.static_dir else None,
        api_key=os.environ.get("HERMES_API_KEY", ""),
        owner_user_id=os.environ.get("HERMES_OWNER_ID", "local-owner"),
        static_digest=args.static_digest,
    )
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
