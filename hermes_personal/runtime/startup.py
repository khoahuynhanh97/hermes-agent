from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from hermes_personal.runtime.config import RuntimeConfig


class StartupStep(str, Enum):
    """Ordered startup steps that must complete before ingress is ready."""

    CONFIG_VALIDATION = "config_validation"
    DB_MIGRATION = "db_migration"
    STALE_LEASE_RECOVERY = "stale_lease_recovery"
    WORKFLOW_APPROVAL_RECOVERY = "workflow_approval_recovery"
    MCP_DISCOVERY = "mcp_discovery"
    CAPABILITY_SNAPSHOT_ACTIVATION = "capability_snapshot_activation"
    MANDATORY_DEPENDENCY_PROBES = "mandatory_dependency_probes"
    INGRESS_READY = "ingress_ready"


class StartupStepStatus(str, Enum):
    """Status of a startup step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StartupErrorCode:
    CONFIG_VALIDATION_FAILED = "CONFIG_VALIDATION_FAILED"
    DB_MIGRATION_FAILED = "DB_MIGRATION_FAILED"
    STALE_LEASE_RECOVERY_FAILED = "STALE_LEASE_RECOVERY_FAILED"
    WORKFLOW_RECOVERY_FAILED = "WORKFLOW_RECOVERY_FAILED"
    MCP_DISCOVERY_FAILED = "MCP_DISCOVERY_FAILED"
    CAPABILITY_ACTIVATION_FAILED = "CAPABILITY_ACTIVATION_FAILED"
    DEPENDENCY_PROBE_FAILED = "DEPENDENCY_PROBE_FAILED"
    INGRESS_READY_FAILED = "INGRESS_READY_FAILED"


@dataclass(frozen=True)
class StartupStepRecord:
    """Record / result of a single startup step execution."""

    name: str
    status: StartupStepStatus
    start_time: float
    end_time: float
    latency_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "latency_ms": self.latency_ms,
            "details": self.details,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


# Alias for backward compatibility
StartupStepResult = StartupStepRecord


@dataclass(frozen=True)
class StartupReport:
    """Consolidated report of the Hermes startup sequence."""

    overall_status: StartupStepStatus
    steps: tuple[StartupStepRecord, ...]
    started_at: float
    completed_at: float
    total_latency_ms: float
    failure_code: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.overall_status == StartupStepStatus.COMPLETED

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status.value,
            "is_ready": self.is_ready,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_latency_ms": self.total_latency_ms,
            "failure_code": self.failure_code,
            "steps": [s.as_dict() for s in self.steps],
        }


class StartupFailure(Exception):
    """Raised when a mandatory startup step fails."""

    def __init__(self, step: StartupStep, message: str, failure_code: str):
        super().__init__(f"Startup failed at {step.value}: {message}")
        self.step = step
        self.failure_code = failure_code


class StartupCoordinator:
    """Coordinates the ordered startup sequence and gates ingress on exact readiness order.

    Startup order (strict):
    1. config_validation
    2. db_migration
    3. stale_lease_recovery (requeue only expired leases)
    4. workflow_approval_recovery (leave pending approvals intact, resume outbox)
    5. mcp_discovery
    6. capability_snapshot_activation
    7. mandatory_dependency_probes
    8. ingress_ready (never mark ready from process existence alone)

    Each step is idempotent - rerun after partial success continues gracefully.
    """

    _STEP_DEFS: list[tuple[StartupStep, str]] = [
        (StartupStep.CONFIG_VALIDATION, StartupErrorCode.CONFIG_VALIDATION_FAILED),
        (StartupStep.DB_MIGRATION, StartupErrorCode.DB_MIGRATION_FAILED),
        (StartupStep.STALE_LEASE_RECOVERY, StartupErrorCode.STALE_LEASE_RECOVERY_FAILED),
        (StartupStep.WORKFLOW_APPROVAL_RECOVERY, StartupErrorCode.WORKFLOW_RECOVERY_FAILED),
        (StartupStep.MCP_DISCOVERY, StartupErrorCode.MCP_DISCOVERY_FAILED),
        (StartupStep.CAPABILITY_SNAPSHOT_ACTIVATION, StartupErrorCode.CAPABILITY_ACTIVATION_FAILED),
        (StartupStep.MANDATORY_DEPENDENCY_PROBES, StartupErrorCode.DEPENDENCY_PROBE_FAILED),
        (StartupStep.INGRESS_READY, StartupErrorCode.INGRESS_READY_FAILED),
    ]

    def __init__(
        self,
        config: RuntimeConfig | None = None,
        env: dict[str, str] | None = None,
        config_validator: Callable[[], None] | None = None,
        migration_runner: Callable[[], None] | None = None,
        lease_recovery: Callable[[], int] | None = None,
        workflow_recovery: Callable[[], tuple[int, int] | int] | None = None,
        mcp_discoverer: Callable[[], Any] | None = None,
        snapshot_activator: Callable[[], Any] | None = None,
        dependency_prober: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._env = env or {}
        self._config_validator = config_validator
        self._migration_runner = migration_runner
        self._lease_recovery = lease_recovery
        self._workflow_recovery = workflow_recovery
        self._mcp_discoverer = mcp_discoverer
        self._snapshot_activator = snapshot_activator
        self._dependency_prober = dependency_prober
        self._clock = clock
        self._completed_steps: set[StartupStep] = set()

    def _execute_step_logic(self, step: StartupStep) -> dict[str, Any]:
        details: dict[str, Any] = {}

        if step == StartupStep.CONFIG_VALIDATION:
            if self._config is not None:
                self._config.validate()
                self._config.validate_secrets_presence(self._env)
                details["config_validated"] = True
            if self._config_validator is not None:
                self._config_validator()
                details["validator_called"] = True

        elif step == StartupStep.DB_MIGRATION:
            if self._migration_runner is not None:
                self._migration_runner()
                details["db_migrated"] = True

        elif step == StartupStep.STALE_LEASE_RECOVERY:
            if self._lease_recovery is not None:
                rec = self._lease_recovery()
                details["expired_leases_requeued"] = rec

        elif step == StartupStep.WORKFLOW_APPROVAL_RECOVERY:
            if self._workflow_recovery is not None:
                res = self._workflow_recovery()
                if isinstance(res, tuple):
                    details["workflows_recovered"] = res[0]
                    details["pending_approvals_preserved"] = res[1]
                else:
                    details["workflows_recovered"] = res
                    details["pending_approvals_preserved"] = True

        elif step == StartupStep.MCP_DISCOVERY:
            if self._mcp_discoverer is not None:
                self._mcp_discoverer()
                details["mcp_discovered"] = True

        elif step == StartupStep.CAPABILITY_SNAPSHOT_ACTIVATION:
            if self._snapshot_activator is not None:
                self._snapshot_activator()
                details["snapshot_activated"] = True

        elif step == StartupStep.MANDATORY_DEPENDENCY_PROBES:
            if self._dependency_prober is not None:
                healthy = self._dependency_prober()
                if not healthy:
                    raise StartupFailure(
                        step,
                        "Mandatory dependency probe failed",
                        StartupErrorCode.DEPENDENCY_PROBE_FAILED,
                    )
                details["probes_healthy"] = True

        elif step == StartupStep.INGRESS_READY:
            details["ingress_ready"] = True

        return details

    def prepare(self) -> StartupReport:
        """Execute ordered startup sequence and gate ingress on overall readiness."""
        started_at = self._clock()
        records: list[StartupStepRecord] = []

        for step, err_code in self._STEP_DEFS:
            # Idempotent skip if previously completed
            if step in self._completed_steps and step != StartupStep.INGRESS_READY:
                records.append(
                    StartupStepRecord(
                        name=step.value,
                        status=StartupStepStatus.SKIPPED,
                        start_time=started_at,
                        end_time=started_at,
                        latency_ms=0.0,
                        details={"note": "already completed in previous run"},
                    )
                )
                continue

            step_start = self._clock()
            try:
                details = self._execute_step_logic(step)
                step_end = self._clock()
                record = StartupStepRecord(
                    name=step.value,
                    status=StartupStepStatus.COMPLETED,
                    start_time=step_start,
                    end_time=step_end,
                    latency_ms=(step_end - step_start) * 1000.0,
                    details=details,
                )
                records.append(record)
                self._completed_steps.add(step)

            except StartupFailure as sf:
                step_end = self._clock()
                record = StartupStepRecord(
                    name=step.value,
                    status=StartupStepStatus.FAILED,
                    start_time=step_start,
                    end_time=step_end,
                    latency_ms=(step_end - step_start) * 1000.0,
                    error_code=sf.failure_code,
                    error_message=str(sf),
                )
                records.append(record)
                total_latency = (step_end - started_at) * 1000.0
                return StartupReport(
                    overall_status=StartupStepStatus.FAILED,
                    steps=tuple(records),
                    started_at=started_at,
                    completed_at=step_end,
                    total_latency_ms=total_latency,
                    failure_code=sf.failure_code,
                )

            except Exception as ex:
                step_end = self._clock()
                record = StartupStepRecord(
                    name=step.value,
                    status=StartupStepStatus.FAILED,
                    start_time=step_start,
                    end_time=step_end,
                    latency_ms=(step_end - step_start) * 1000.0,
                    error_code=err_code,
                    error_message=str(ex),
                )
                records.append(record)
                total_latency = (step_end - started_at) * 1000.0
                return StartupReport(
                    overall_status=StartupStepStatus.FAILED,
                    steps=tuple(records),
                    started_at=started_at,
                    completed_at=step_end,
                    total_latency_ms=total_latency,
                    failure_code=err_code,
                )

        completed_at = self._clock()
        return StartupReport(
            overall_status=StartupStepStatus.COMPLETED,
            steps=tuple(records),
            started_at=started_at,
            completed_at=completed_at,
            total_latency_ms=(completed_at - started_at) * 1000.0,
            failure_code=None,
        )