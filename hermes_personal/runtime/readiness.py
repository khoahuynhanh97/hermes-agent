from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ReadinessState = Literal["not_ready", "preparing", "ready", "failed"]
StepStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]


@dataclass
class StartupStepRecord:
    """Record of a single startup sequence step."""

    name: str
    status: StepStatus = "pending"
    start_time: float = 0.0
    end_time: float = 0.0
    latency_ms: float = 0.0
    error_code: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_ms": self.latency_ms,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass
class StartupReport:
    """Consolidated report of the Hermes startup sequence."""

    status: ReadinessState = "not_ready"
    total_latency_ms: float = 0.0
    steps: list[StartupStepRecord] = field(default_factory=list)
    failure_code: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "is_ready": self.is_ready,
            "total_latency_ms": self.total_latency_ms,
            "failure_code": self.failure_code,
            "steps": [s.as_dict() for s in self.steps],
        }
