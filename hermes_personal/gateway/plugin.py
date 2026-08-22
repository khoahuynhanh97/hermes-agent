from __future__ import annotations

from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext
    from hermes_personal.orchestration import HermesTurnService


class TurnServiceRegistry:
    """Process-local services keyed by profile, separate from durable plugin state."""

    def __init__(self) -> None:
        self._services: dict[str, HermesTurnService] = {}
        self._lock = RLock()

    def register(self, profile_name: str, service: HermesTurnService) -> None:
        self._validate_profile_name(profile_name)
        with self._lock:
            self._services[profile_name] = service

    def get(self, profile_name: str) -> HermesTurnService | None:
        self._validate_profile_name(profile_name)
        with self._lock:
            return self._services.get(profile_name)

    def clear(self, profile_name: str) -> None:
        self._validate_profile_name(profile_name)
        with self._lock:
            self._services.pop(profile_name, None)

    @staticmethod
    def _validate_profile_name(profile_name: str) -> None:
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ValueError("profile_name must not be blank")


_TURN_SERVICES = TurnServiceRegistry()


def register_turn_service(profile_name: str, service: HermesTurnService) -> None:
    """Bind the profile's live turn service for a future ingress adapter."""
    _TURN_SERVICES.register(profile_name, service)


def get_turn_service(profile_name: str) -> HermesTurnService | None:
    """Return the profile's live service without persisting it."""
    return _TURN_SERVICES.get(profile_name)


def register(ctx: PluginContext) -> None:
    """Register durable metadata and lifecycle cleanup without route cutover."""
    profile_name = ctx.profile_name
    ctx.state.set(
        "gateway.registration",
        {
            "profile_name": profile_name,
            "registry": "hermes_personal.gateway.turn_service",
            "schema_version": 1,
        },
    )
    ctx.on_unload(lambda: _TURN_SERVICES.clear(profile_name))
