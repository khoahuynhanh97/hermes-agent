from __future__ import annotations

from dataclasses import dataclass
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext
    from hermes_personal.orchestration import HermesTurnService


@dataclass(frozen=True)
class TurnServiceLease:
    """Immutable ownership of one profile-scoped service generation."""

    profile_name: str
    generation: int
    service: HermesTurnService


class TurnServiceRegistry:
    """Process-local services keyed by profile, separate from durable plugin state."""

    def __init__(self) -> None:
        self._services: dict[str, TurnServiceLease] = {}
        self._next_generation: dict[str, int] = {}
        self._lock = RLock()

    def register(
        self, profile_name: str, service: HermesTurnService
    ) -> TurnServiceLease:
        self._validate_profile_name(profile_name)
        with self._lock:
            generation = self._next_generation.get(profile_name, 0) + 1
            self._next_generation[profile_name] = generation
            lease = TurnServiceLease(profile_name, generation, service)
            self._services[profile_name] = lease
            return lease

    def get(self, profile_name: str) -> HermesTurnService | None:
        self._validate_profile_name(profile_name)
        with self._lock:
            lease = self._services.get(profile_name)
            return lease.service if lease is not None else None

    def current_lease(self, profile_name: str) -> TurnServiceLease | None:
        self._validate_profile_name(profile_name)
        with self._lock:
            return self._services.get(profile_name)

    def release(self, lease: TurnServiceLease) -> bool:
        if not isinstance(lease, TurnServiceLease):
            raise ValueError("lease must be TurnServiceLease")
        with self._lock:
            if self._services.get(lease.profile_name) is not lease:
                return False
            self._services.pop(lease.profile_name)
            return True

    @staticmethod
    def _validate_profile_name(profile_name: str) -> None:
        if not isinstance(profile_name, str) or not profile_name.strip():
            raise ValueError("profile_name must not be blank")


_TURN_SERVICES = TurnServiceRegistry()


def register_turn_service(
    profile_name: str, service: HermesTurnService
) -> TurnServiceLease:
    """Bind the profile's live turn service for a future ingress adapter."""
    return _TURN_SERVICES.register(profile_name, service)


def get_turn_service(profile_name: str) -> HermesTurnService | None:
    """Return the profile's live service without persisting it."""
    return _TURN_SERVICES.get(profile_name)


def register(ctx: PluginContext) -> None:
    """Register durable metadata and lifecycle cleanup without route cutover."""
    profile_name = ctx.profile_name
    lease = _TURN_SERVICES.current_lease(profile_name)
    ctx.state.set(
        "gateway.registration",
        {
            "profile_name": profile_name,
            "registry": "hermes_personal.gateway.turn_service",
            "schema_version": 1,
            "generation": lease.generation if lease is not None else None,
        },
    )
    ctx.on_unload(
        lambda: _TURN_SERVICES.release(lease) if lease is not None else None
    )
