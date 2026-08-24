from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

HealthStatus = Literal["starting", "healthy", "degraded", "unavailable", "stopping", "stopped"]


@dataclass(frozen=True)
class ComponentHealth:
    """Health status and metadata for a discrete runtime component or dependency."""

    name: str
    required: bool
    status: HealthStatus
    details: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "required": self.required,
            "status": self.status,
            "details": self.details,
            "metadata": dict(self.metadata),
            "checked_at": self.checked_at,
        }


@dataclass(frozen=True)
class HealthReport:
    """Aggregate health and readiness report for the Hermes runtime."""

    ready: bool
    live: bool
    components: tuple[ComponentHealth, ...]
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def from_components(
        cls,
        components: Iterable[ComponentHealth],
        checked_at: str | None = None,
    ) -> HealthReport:
        comp_tuple = tuple(components)
        # Ready: all required components must be 'healthy'
        ready = all(c.status == "healthy" for c in comp_tuple if c.required)
        # Live: required components must not be 'stopping' or 'stopped'
        live = not any(c.status in ("stopping", "stopped") for c in comp_tuple if c.required)
        return cls(
            ready=ready,
            live=live,
            components=comp_tuple,
            checked_at=checked_at or datetime.now(timezone.utc).isoformat(),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "live": self.live,
            "checked_at": self.checked_at,
            "components": [c.as_dict() for c in self.components],
        }
