from __future__ import annotations

import pytest

from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.runtime.config import RuntimeConfig
from hermes_personal.runtime.readiness import (
    ReadinessProbe,
    ReadinessState,
    create_readiness_probe,
)
from hermes_personal.runtime.startup import (
    StartupCoordinator,
    StartupErrorCode,
    StartupReport,
    StartupStep,
    StartupStepRecord,
    StartupStepStatus,
)


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_successful_startup_order_and_readiness(tmp_path):
    clock = FakeClock()
    execution_order: list[str] = []

    def config_step():
        execution_order.append("config_validation")
        clock.advance(0.01)

    def migration_step():
        execution_order.append("db_migration")
        clock.advance(0.02)

    def lease_step():
        execution_order.append("stale_lease_recovery")
        clock.advance(0.01)
        return 3  # recovered 3 leases

    def workflow_step():
        execution_order.append("workflow_approval_recovery")
        clock.advance(0.01)
        return (2, 5)  # 2 workflows recovered, 5 pending approvals left intact

    def mcp_step():
        execution_order.append("mcp_discovery")
        clock.advance(0.03)

    def snapshot_step():
        execution_order.append("capability_snapshot_activation")
        clock.advance(0.01)

    def probe_step():
        execution_order.append("mandatory_dependency_probes")
        clock.advance(0.02)
        return True

    coordinator = StartupCoordinator(
        config=RuntimeConfig(mode="development", repo_root=tmp_path),
        env={"HERMES_TELEGRAM_TOKEN": "token_val", "HERMES_API_KEY": "key_val"},
        config_validator=config_step,
        migration_runner=migration_step,
        lease_recovery=lease_step,
        workflow_recovery=workflow_step,
        mcp_discoverer=mcp_step,
        snapshot_activator=snapshot_step,
        dependency_prober=probe_step,
        clock=clock.time,
    )

    report = coordinator.prepare()

    expected_order = [
        "config_validation",
        "db_migration",
        "stale_lease_recovery",
        "workflow_approval_recovery",
        "mcp_discovery",
        "capability_snapshot_activation",
        "mandatory_dependency_probes",
    ]
    assert execution_order == expected_order
    assert report.is_ready is True
    assert report.overall_status == StartupStepStatus.COMPLETED
    assert report.failure_code is None
    assert len(report.steps) == 8
    assert report.steps[-1].name == "ingress_ready"
    assert report.steps[-1].status == StartupStepStatus.COMPLETED
    assert report.total_latency_ms > 0


def test_mandatory_step_failure_stops_before_ready():
    clock = FakeClock()
    execution_order: list[str] = []

    def config_step():
        execution_order.append("config_validation")

    def migration_step():
        execution_order.append("db_migration")
        raise RuntimeError("database unreachable")

    def lease_step():
        execution_order.append("stale_lease_recovery")

    coordinator = StartupCoordinator(
        config_validator=config_step,
        migration_runner=migration_step,
        lease_recovery=lease_step,
        clock=clock.time,
    )

    report = coordinator.prepare()

    assert execution_order == ["config_validation", "db_migration"]
    assert report.is_ready is False
    assert report.overall_status == StartupStepStatus.FAILED
    assert report.failure_code == StartupErrorCode.DB_MIGRATION_FAILED
    failed_step = next(s for s in report.steps if s.name == "db_migration")
    assert failed_step.status == StartupStepStatus.FAILED
    assert "database unreachable" in (failed_step.error_message or "")


def test_dependency_probe_failure_blocks_readiness():
    clock = FakeClock()

    coordinator = StartupCoordinator(
        dependency_prober=lambda: False,  # unhealthy probe
        clock=clock.time,
    )

    report = coordinator.prepare()

    assert report.is_ready is False
    assert report.overall_status == StartupStepStatus.FAILED
    assert report.failure_code == StartupErrorCode.DEPENDENCY_PROBE_FAILED


def test_rerun_after_partial_success_is_idempotent():
    clock = FakeClock()
    attempts = {"count": 0}

    def flaky_migration():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient migration lock")

    coordinator = StartupCoordinator(
        migration_runner=flaky_migration,
        clock=clock.time,
    )

    # First run fails
    report1 = coordinator.prepare()
    assert report1.is_ready is False
    assert report1.failure_code == StartupErrorCode.DB_MIGRATION_FAILED

    # Second run succeeds and skips already completed steps
    report2 = coordinator.prepare()
    assert report2.is_ready is True
    assert report2.overall_status == StartupStepStatus.COMPLETED


def test_recovery_contract_requeues_leases_and_preserves_approvals():
    requeued_leases = []
    preserved_approvals = []

    def custom_lease_recovery():
        requeued_leases.append("lease_exp_1")
        return len(requeued_leases)

    def custom_workflow_recovery():
        preserved_approvals.append("appr_pending_1")
        return (1, len(preserved_approvals))

    coordinator = StartupCoordinator(
        lease_recovery=custom_lease_recovery,
        workflow_recovery=custom_workflow_recovery,
    )

    report = coordinator.prepare()
    assert report.is_ready is True
    assert requeued_leases == ["lease_exp_1"]
    assert preserved_approvals == ["appr_pending_1"]


def test_readiness_probe_integration():
    clock = FakeClock()
    coordinator = StartupCoordinator(clock=clock.time)
    report = coordinator.prepare()

    health_report = HealthReport.from_components(
        components=(
            ComponentHealth(name="gateway", required=True, status="healthy"),
            ComponentHealth(name="telegram", required=False, status="degraded"),
        ),
        checked_at=clock.time(),
    )

    probe = create_readiness_probe(
        startup_report=report,
        get_health_report=lambda: health_report,
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: True,
    )

    state = probe.evaluate()
    assert state.is_ready is True
    assert state.is_live is True
    assert state.as_dict()["ready"] is True
    assert probe.evaluate_component("gateway") == "healthy"
    assert probe.evaluate_component("telegram") == "degraded"
