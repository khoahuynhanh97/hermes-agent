from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from hermes_personal.observability.health import HealthReport, HealthStatus
from hermes_personal.runtime.startup import StartupReport, StartupStepStatus


@dataclass(frozen=True)
class ReadinessState:
    """Immutable readiness state for the Hermes runtime ingress gateway.

    Ingress is gated on:
    - StartupReport.is_ready == True (all 8 startup steps completed)
    - All required components healthy
    - Capability snapshot active
    - Mandatory dependency probes passing
    """

    startup_report: StartupReport
    health_report: HealthReport
    capability_snapshot_active: bool
    dependency_probes_healthy: bool
    checked_at: float = field(default_factory=time.time)

    @property
    def is_ready(self) -> bool:
        """Ingress ready only when all conditions are met."""
        return (
            self.startup_report.is_ready
            and self.health_report.ready
            and self.capability_snapshot_active
            and self.dependency_probes_healthy
        )

    @property
    def is_live(self) -> bool:
        """Liveness check - process is running (not stopped)."""
        return self.health_report.live

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.is_ready,
            "live": self.is_live,
            "startup": self.startup_report.as_dict(),
            "health": self.health_report.as_dict(),
            "capability_snapshot_active": self.capability_snapshot_active,
            "dependency_probes_healthy": self.dependency_probes_healthy,
            "checked_at": self.checked_at,
        }


class ReadinessProbe:
    """Evaluates readiness state from startup report and live health."""

    def __init__(
        self,
        get_health_report: Callable[[], HealthReport],
        check_capability_snapshot: Callable[[], bool],
        check_dependency_probes: Callable[[], bool],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._get_health_report = get_health_report
        self._check_capability_snapshot = check_capability_snapshot
        self._check_dependency_probes = check_dependency_probes
        self._clock = clock
        self._last_startup_report: StartupReport | None = None

    def set_startup_report(self, report: StartupReport) -> None:
        """Set the startup report from StartupCoordinator.prepare()."""
        self._last_startup_report = report

    def evaluate(self) -> ReadinessState:
        """Evaluate current readiness state."""
        if self._last_startup_report is None:
            return ReadinessState(
                startup_report=StartupReport(
                    overall_status=StartupStepStatus.PENDING,
                    steps=(),
                    started_at=self._clock(),
                    completed_at=self._clock(),
                    total_latency_ms=0.0,
                    failure_code="NO_STARTUP_REPORT",
                ),
                health_report=self._get_health_report(),
                capability_snapshot_active=False,
                dependency_probes_healthy=False,
                checked_at=self._clock(),
            )

        health_report = self._get_health_report()
        capability_active = self._check_capability_snapshot()
        deps_healthy = self._check_dependency_probes()

        return ReadinessState(
            startup_report=self._last_startup_report,
            health_report=health_report,
            capability_snapshot_active=capability_active,
            dependency_probes_healthy=deps_healthy,
            checked_at=self._clock(),
        )

    def evaluate_component(self, component_name: str) -> HealthStatus:
        """Get health status of a specific component."""
        health_report = self._get_health_report()
        for comp in health_report.components:
            if comp.name == component_name:
                return comp.status
        return "unavailable"


def create_readiness_probe(
    startup_report: StartupReport,
    get_health_report: Callable[[], HealthReport],
    check_capability_snapshot: Callable[[], bool],
    check_dependency_probes: Callable[[], bool],
) -> ReadinessProbe:
    """Factory to create a configured ReadinessProbe with startup report."""
    probe = ReadinessProbe(
        get_health_report=get_health_report,
        check_capability_snapshot=check_capability_snapshot,
        check_dependency_probes=check_dependency_probes,
    )
    probe.set_startup_report(startup_report)
    return probe