from __future__ import annotations

import time
from typing import Any, Callable

from hermes_personal.runtime.readiness import StartupReport, StartupStepRecord


class StartupErrorCode:
    CONFIG_VALIDATION_FAILED = "CONFIG_VALIDATION_FAILED"
    DB_MIGRATION_FAILED = "DB_MIGRATION_FAILED"
    STALE_LEASE_RECOVERY_FAILED = "STALE_LEASE_RECOVERY_FAILED"
    WORKFLOW_RECOVERY_FAILED = "WORKFLOW_RECOVERY_FAILED"
    MCP_DISCOVERY_FAILED = "MCP_DISCOVERY_FAILED"
    CAPABILITY_ACTIVATION_FAILED = "CAPABILITY_ACTIVATION_FAILED"
    DEPENDENCY_PROBE_FAILED = "DEPENDENCY_PROBE_FAILED"
    INGRESS_READY_FAILED = "INGRESS_READY_FAILED"


class StartupCoordinator:
    """Coordinates runtime startup sequence and gates ingress on exact readiness order."""

    def __init__(
        self,
        config_validator: Callable[[], None] | None = None,
        migration_runner: Callable[[], None] | None = None,
        lease_recovery: Callable[[], int] | None = None,
        workflow_recovery: Callable[[], int] | None = None,
        mcp_discoverer: Callable[[], Any] | None = None,
        snapshot_activator: Callable[[], Any] | None = None,
        dependency_prober: Callable[[], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config_validator = config_validator
        self._migration_runner = migration_runner
        self._lease_recovery = lease_recovery
        self._workflow_recovery = workflow_recovery
        self._mcp_discoverer = mcp_discoverer
        self._snapshot_activator = snapshot_activator
        self._dependency_prober = dependency_prober
        self._clock = clock

    def _run_step(
        self,
        name: str,
        error_code: str,
        fn: Callable[[], Any] | None,
        is_probe: bool = False,
    ) -> StartupStepRecord:
        record = StartupStepRecord(name=name, status="running")
        start = self._clock()
        record.start_time = start

        if fn is None:
            end = self._clock()
            record.end_time = end
            record.latency_ms = (end - start) * 1000.0
            record.status = "succeeded"
            return record

        try:
            res = fn()
            end = self._clock()
            record.end_time = end
            record.latency_ms = (end - start) * 1000.0

            if is_probe and res is False:
                record.status = "failed"
                record.error_code = error_code
                record.error_message = "Mandatory dependency probe returned unhealthy (False)"
            else:
                record.status = "succeeded"
        except Exception as ex:
            end = self._clock()
            record.end_time = end
            record.latency_ms = (end - start) * 1000.0
            record.status = "failed"
            record.error_code = error_code
            record.error_message = str(ex)

        return record

    def prepare(self) -> StartupReport:
        """Execute exact ordered startup sequence:
        1. config_validation
        2. db_migration
        3. stale_lease_recovery
        4. workflow_approval_recovery
        5. mcp_discovery
        6. capability_snapshot_activation
        7. mandatory_dependency_probes
        8. ingress_ready
        """
        report = StartupReport(status="preparing")
        overall_start = self._clock()

        steps_definitions: list[tuple[str, str, Callable[[], Any] | None, bool]] = [
            ("config_validation", StartupErrorCode.CONFIG_VALIDATION_FAILED, self._config_validator, False),
            ("db_migration", StartupErrorCode.DB_MIGRATION_FAILED, self._migration_runner, False),
            ("stale_lease_recovery", StartupErrorCode.STALE_LEASE_RECOVERY_FAILED, self._lease_recovery, False),
            ("workflow_approval_recovery", StartupErrorCode.WORKFLOW_RECOVERY_FAILED, self._workflow_recovery, False),
            ("mcp_discovery", StartupErrorCode.MCP_DISCOVERY_FAILED, self._mcp_discoverer, False),
            (
                "capability_snapshot_activation",
                StartupErrorCode.CAPABILITY_ACTIVATION_FAILED,
                self._snapshot_activator,
                False,
            ),
            (
                "mandatory_dependency_probes",
                StartupErrorCode.DEPENDENCY_PROBE_FAILED,
                self._dependency_prober,
                True,
            ),
        ]

        for step_name, err_code, step_fn, is_probe in steps_definitions:
            record = self._run_step(step_name, err_code, step_fn, is_probe=is_probe)
            report.steps.append(record)
            if record.status == "failed":
                report.status = "failed"
                report.failure_code = record.error_code
                report.total_latency_ms = (self._clock() - overall_start) * 1000.0
                return report

        # All preliminary steps succeeded -> mark ingress ready
        ingress_step = StartupStepRecord(
            name="ingress_ready",
            status="succeeded",
            start_time=self._clock(),
            end_time=self._clock(),
            latency_ms=0.0,
        )
        report.steps.append(ingress_step)
        report.status = "ready"
        report.total_latency_ms = (self._clock() - overall_start) * 1000.0
        return report
