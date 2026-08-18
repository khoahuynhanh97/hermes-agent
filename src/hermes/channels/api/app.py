from __future__ import annotations

from typing import Any
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from hermes.channels.cli.env_loader import load_hermes_dotenv
load_hermes_dotenv()

from hermes.security.principal import set_current_principal, current_principal, PrincipalContext
from hermes.security.ingress import build_api_principal, build_gui_principal, build_local_cli_principal
from hermes.channels.api.dependencies import get_authenticated_principal_context
from hermes.channels.api.routes import projects, jobs, prompt_studio, product_research, assets, video_factory, omni_chat, knowledge, compliance, analytics, publishing
from hermes.channels.api.sse import router as sse_router


class APIPrincipalIngressMiddleware(BaseHTTPMiddleware):
    """Canonical ASGI Middleware for Authenticated Principal Ingress.

    1. Authenticates/resolves server-side PrincipalContext at request ingress.
    2. Binds PrincipalContext into ContextVar (current_principal) for the request scope.
    3. Guarantees context cleanup in a finally block so principal never leaks across requests.
    4. Fails closed with HTTP 401 Unauthorized if principal cannot be resolved at ingress.
    """
    UNAUTHENTICATED_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/noop"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.UNAUTHENTICATED_PATHS:
            return await call_next(request)

        # Authenticate / resolve server-side principal at ingress
        principal = (
            build_api_principal()
            or build_gui_principal()
            or build_local_cli_principal()
        )

        if principal is None or not principal.owner_user_id:
            return JSONResponse(
                status_code=401,
                content={"status": "error", "detail": "UNAUTHENTICATED_PRINCIPAL: Session principal context missing at API ingress"}
            )

        token = set_current_principal(principal)
        try:
            response = await call_next(request)
            return response
        finally:
            current_principal.reset(token)


app = FastAPI(title="Hermes Web API", version="1.0.0")

app.add_middleware(APIPrincipalIngressMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(prompt_studio.router, prefix="/api", tags=["prompt_studio"])
app.include_router(product_research.router, prefix="/api/products", tags=["product_research"])
app.include_router(assets.router, prefix="/api/assets", tags=["assets"])
app.include_router(video_factory.router, prefix="/api", tags=["video-factory"])
app.include_router(omni_chat.router, prefix="/api", tags=["omni-chat"])
app.include_router(sse_router, prefix="/api", tags=["events"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(compliance.router, prefix="/api/compliance", tags=["compliance"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(publishing.router, prefix="/api/publish", tags=["publishing"])


@app.get("/api/session")
def get_session(principal: PrincipalContext = Depends(get_authenticated_principal_context)) -> dict[str, Any]:
    return {
        "status": "ok",
        "principal": {
            "actor_id": principal.actor_id,
            "owner_user_id": principal.owner_user_id,
            "platform": principal.platform,
            "session_id": principal.session_id,
            "roles": list(principal.roles),
        },
    }


@app.get("/health")
def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "Hermes Web Operator API",
        "version": "1.0.0",
        "capabilities": [
            "mcp_video_factory",
            "mcp_product_intelligence",
            "durable_job_worker",
            "product_resource_binding",
        ],
    }


@app.get("/noop")
def noop() -> dict[str, Any]:
    return {"status": "ok", "message": "noop"}