from __future__ import annotations

import time
import threading
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp


class RequestBodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Rejects request bodies exceeding maximum byte limit with HTTP 413 Payload Too Large."""

    def __init__(self, app: ASGIApp, max_body_bytes: int = 10 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_body_bytes = max_body_bytes

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    return JSONResponse(
                        {"error": "Payload Too Large", "max_bytes": self.max_body_bytes},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)


class TokenBucketRateLimiter:
    """Thread-safe in-memory token bucket rate limiter."""

    def __init__(self, rate_per_minute: float = 120.0, burst: int = 60) -> None:
        self.rate_per_second = rate_per_minute / 60.0
        self.capacity = float(burst)
        self._buckets: dict[str, tuple[float, float]] = {}  # key -> (tokens, last_update_time)
        self._lock = threading.Lock()

    def allow(self, key: str, cost: float = 1.0, now: float | None = None) -> tuple[bool, float]:
        """Check if request is allowed under rate limit.

        Returns (is_allowed, retry_after_seconds).
        """
        now_ts = time.monotonic() if now is None else now
        with self._lock:
            if key not in self._buckets:
                tokens = self.capacity - cost
                self._buckets[key] = (tokens, now_ts)
                return True, 0.0

            tokens, last_update = self._buckets[key]
            elapsed = max(0.0, now_ts - last_update)
            tokens = min(self.capacity, tokens + elapsed * self.rate_per_second)

            if tokens >= cost:
                tokens -= cost
                self._buckets[key] = (tokens, now_ts)
                return True, 0.0

            deficit = cost - tokens
            retry_after = deficit / self.rate_per_second if self.rate_per_second > 0 else 1.0
            self._buckets[key] = (tokens, now_ts)
            return False, retry_after

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Enforces rate limits by client IP or Bearer token, returning HTTP 429 Too Many Requests."""

    def __init__(
        self,
        app: ASGIApp,
        limiter: TokenBucketRateLimiter | None = None,
        rate_per_minute: float = 120.0,
        burst: int = 60,
        exclude_paths: tuple[str, ...] = ("/health", "/health/live", "/health/ready"),
    ) -> None:
        super().__init__(app)
        self.limiter = limiter or TokenBucketRateLimiter(rate_per_minute=rate_per_minute, burst=burst)
        self.exclude_paths = exclude_paths

    def _extract_client_key(self, request: Request) -> str:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token:
                return f"token:{token[:16]}"
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    async def dispatch(self, request: Request, call_next: Callable[[Request], Response]) -> Response:
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        client_key = self._extract_client_key(request)
        allowed, retry_after = self.limiter.allow(client_key)
        if not allowed:
            return JSONResponse(
                {
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Please retry after {int(retry_after) + 1} seconds.",
                },
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        return await call_next(request)


def configure_security_middleware(
    app: Any,
    max_body_bytes: int = 10 * 1024 * 1024,
    rate_per_minute: float = 120.0,
    burst: int = 60,
    cors_allowed_origins: list[str] | None = None,
    rate_limiter: TokenBucketRateLimiter | None = None,
) -> None:
    """Attaches standard security and edge middlewares to FastAPI app."""
    origins = cors_allowed_origins or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestBodySizeLimitMiddleware, max_body_bytes=max_body_bytes)
    app.add_middleware(
        RateLimitMiddleware,
        limiter=rate_limiter,
        rate_per_minute=rate_per_minute,
        burst=burst,
    )
