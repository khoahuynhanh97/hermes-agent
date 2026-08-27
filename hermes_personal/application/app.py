from __future__ import annotations

from fastapi import FastAPI

from hermes_personal.application.events_api import EventsAPI, create_events_router
from hermes_personal.application.health_api import HealthAPI, create_health_router
from hermes_personal.application.middleware import (
    TokenBucketRateLimiter,
    configure_security_middleware,
)
from hermes_personal.application.turn_api import TurnAuthenticator, create_turn_router
from hermes_personal.gateway.normalizers import ChannelTurnNormalizer
from hermes_personal.orchestration import HermesTurnService


def create_application(
    health_api: HealthAPI | None = None,
    events_api: EventsAPI | None = None,
    turn_service: HermesTurnService | None = None,
    turn_normalizers: dict[str, ChannelTurnNormalizer] | None = None,
    turn_authenticator: TurnAuthenticator | None = None,
    max_body_bytes: int = 10 * 1024 * 1024,
    rate_per_minute: float = 120.0,
    burst: int = 60,
    cors_allowed_origins: list[str] | None = None,
    rate_limiter: TokenBucketRateLimiter | None = None,
    enable_security_middleware: bool = True,
) -> FastAPI:
    """Create and configure the canonical Hermes personal application FastAPI instance."""
    app = FastAPI(
        title="Hermes Personal Application API",
        version="1.0.0",
        description="Unified Health, Events Stream, Operator Commands, and Artifact Metadata API",
    )

    if enable_security_middleware:
        configure_security_middleware(
            app=app,
            max_body_bytes=max_body_bytes,
            rate_per_minute=rate_per_minute,
            burst=burst,
            cors_allowed_origins=cors_allowed_origins,
            rate_limiter=rate_limiter,
        )

    health_router = create_health_router(health_api)
    events_router = create_events_router(events_api)
    turn_router = create_turn_router(
        turn_service=turn_service,
        normalizers=turn_normalizers,
        authenticator=turn_authenticator,
    )

    app.include_router(health_router)
    app.include_router(events_router)
    app.include_router(turn_router)

    return app
