from __future__ import annotations

from fastapi import FastAPI

from hermes_personal.application.events_api import EventsAPI, create_events_router
from hermes_personal.application.health_api import HealthAPI, create_health_router


def create_application(
    health_api: HealthAPI | None = None,
    events_api: EventsAPI | None = None,
) -> FastAPI:
    """Create and configure the canonical Hermes personal application FastAPI instance."""
    app = FastAPI(
        title="Hermes Personal Application API",
        version="1.0.0",
        description="Unified Health, Events Stream, Operator Commands, and Artifact Metadata API",
    )

    health_router = create_health_router(health_api)
    events_router = create_events_router(events_api)

    app.include_router(health_router)
    app.include_router(events_router)

    return app
