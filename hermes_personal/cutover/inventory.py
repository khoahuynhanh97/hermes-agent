from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RouteClassification = Literal[
    "natural_language",
    "operator_command",
    "health_static",
    "prohibited_direct_provider",
]


class RouteInventoryError(Exception):
    """Raised when an entry path is unclassified or violates boundary rules."""


@dataclass(frozen=True)
class RouteEntry:
    path: str
    method: str
    channel: str
    classification: RouteClassification
    target_service: str
    description: str = ""


class RouteInventory:
    """Canonical inventory of production entry paths for Telegram, CLI, Web, and Omni."""

    def __init__(self, routes: list[RouteEntry] | None = None) -> None:
        self._routes: list[RouteEntry] = list(routes or [])

    @property
    def routes(self) -> tuple[RouteEntry, ...]:
        return tuple(self._routes)

    def register_route(self, route: RouteEntry) -> None:
        self._routes.append(route)

    def validate(self) -> None:
        """Validate that all entry paths are classified and natural-language paths terminate at turn service."""
        for route in self._routes:
            if not route.classification:
                raise RouteInventoryError(f"Unclassified route: {route.method} {route.path}")

            if route.classification == "prohibited_direct_provider":
                raise RouteInventoryError(
                    f"Prohibited direct provider route detected: {route.method} {route.path} -> {route.target_service}"
                )

            if route.classification == "natural_language":
                if "HermesTurnService" not in route.target_service and "turn" not in route.target_service.lower():
                    raise RouteInventoryError(
                        f"Natural language route {route.method} {route.path} ({route.channel}) "
                        f"must terminate at HermesTurnService, but targets '{route.target_service}'"
                    )


def get_default_production_inventory() -> RouteInventory:
    """Build the canonical production route inventory for Telegram, CLI, Web, and Omni."""
    inventory = RouteInventory()

    # Telegram
    inventory.register_route(RouteEntry(
        path="telegram://updates/message",
        method="EVENT",
        channel="telegram",
        classification="natural_language",
        target_service="HermesTurnService",
        description="Telegram incoming user message ingress",
    ))
    inventory.register_route(RouteEntry(
        path="telegram://updates/callback_query",
        method="EVENT",
        channel="telegram",
        classification="operator_command",
        target_service="OperatorCommandDispatcher",
        description="Telegram inline button approval callback",
    ))

    # CLI
    inventory.register_route(RouteEntry(
        path="cli://interactive/turn",
        method="CALL",
        channel="cli",
        classification="natural_language",
        target_service="HermesTurnService",
        description="CLI prompt conversation loop",
    ))
    inventory.register_route(RouteEntry(
        path="cli://subcommand/start",
        method="CLI_EXEC",
        channel="cli",
        classification="health_static",
        target_service="StartupCoordinator",
        description="CLI runtime startup command",
    ))

    # Web & Omni HTTP
    inventory.register_route(RouteEntry(
        path="/api/turn",
        method="POST",
        channel="web",
        classification="natural_language",
        target_service="HermesTurnService",
        description="Web Chat turn endpoint",
    ))
    inventory.register_route(RouteEntry(
        path="/api/omni/turn",
        method="POST",
        channel="omni",
        classification="natural_language",
        target_service="HermesTurnService",
        description="Omni unified ingress turn endpoint",
    ))
    inventory.register_route(RouteEntry(
        path="/api/events",
        method="GET",
        channel="web",
        classification="health_static",
        target_service="EventsAPI",
        description="Durable event stream (SSE)",
    ))
    inventory.register_route(RouteEntry(
        path="/api/operator/command",
        method="POST",
        channel="web",
        classification="operator_command",
        target_service="OperatorCommandDispatcher",
        description="Authenticated operator action submission",
    ))
    inventory.register_route(RouteEntry(
        path="/health/live",
        method="GET",
        channel="web",
        classification="health_static",
        target_service="HealthAPI",
        description="Runtime liveness check",
    ))
    inventory.register_route(RouteEntry(
        path="/health/ready",
        method="GET",
        channel="web",
        classification="health_static",
        target_service="HealthAPI",
        description="Runtime readiness check",
    ))

    return inventory
