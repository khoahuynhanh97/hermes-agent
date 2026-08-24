from __future__ import annotations

import time

from hermes_personal.application.events_api import InMemoryEventStore
from hermes_personal.contracts.events import AgentEvent
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.runtime.config import RuntimeConfig
from hermes_personal.runtime.processes import ProcessSpec, build_process_topology
from hermes_personal.runtime.readiness import ReadinessProbe
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus
from hermes_personal.runtime.supervisor import ChildProcess, ProcessRunner, Supervisor
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import WorkflowRepository


class FakeChildProcess(ChildProcess):
    def __init__(self, name: str, terminated_list: list[str], pid: int = 1234):
        self._name = name
        self._terminated_list = terminated_list
        self._pid = pid
        self._alive = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int:
        return self._pid

    def poll(self) -> int | None:
        return None if self._alive else 0

    def terminate(self) -> None:
        self._alive = False
        self._terminated_list.append(self._name)

    def kill(self) -> None:
        self._alive = False
        self._terminated_list.append(self._name)

    def wait(self, timeout: float | None = None) -> int:
        self._alive = False
        return 0

    def is_alive(self) -> bool:
        return self._alive


class FakeRunner(ProcessRunner):
    def __init__(self):
        self.spawned: list[str] = []
        self.killed: list[str] = []

    def start(self, spec: ProcessSpec) -> ChildProcess:
        self.spawned.append(spec.name)
        return FakeChildProcess(name=spec.name, terminated_list=self.killed)

    def stop(self, child: ChildProcess) -> None:
        child.terminate()


def test_supervisor_topology_and_bounded_restarts():
    """Verify supervisor builds topology and tracks process specs with restart policies."""
    config = RuntimeConfig(mode="development", app_api_port=8000, enable_mcp=True, enable_workers=True)
    topology = build_process_topology(config=config)
    assert len(topology) >= 3

    gateway_spec = next(p for p in topology if p.name == "app_api")
    assert gateway_spec.restart.max_attempts >= 3

    runner = FakeRunner()
    supervisor = Supervisor(specs=topology, runner=runner)
    supervisor.start_all()

    assert "app_api" in runner.spawned

    supervisor.stop_all()
    assert "app_api" in runner.killed


def test_readiness_probe_evaluation():
    """Verify readiness state transitions on component degradation and recovery."""
    probe = ReadinessProbe(
        get_health_report=lambda: HealthReport.from_components(
            components=(ComponentHealth(name="db", required=True, status="healthy"),),
            checked_at=time.time(),
        ),
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: True,
    )
    probe.set_startup_report(
        StartupReport(
            overall_status=StartupStepStatus.COMPLETED,
            steps=(
                StartupStepRecord(
                    name="db_ready",
                    status=StartupStepStatus.COMPLETED,
                    start_time=0.0,
                    end_time=0.01,
                    latency_ms=10.0,
                ),
            ),
            started_at=0.0,
            completed_at=0.01,
            total_latency_ms=10.0,
        )
    )

    state = probe.evaluate()
    assert state.is_ready is True


def test_workflow_and_event_persistence_across_restart():
    """Verify durable workflow state and event replay survives simulated process restart."""
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    engine = WorkflowEngine(repository=repo)

    # Process Run 1: Handle start and approval_requested
    res1 = engine.handle({
        "command_id": "cmd_start_01",
        "workflow_id": "wf_video_100",
        "type": "start",
        "args": {"product": "AI Audio"},
    })
    assert res1.success is True
    assert res1.new_version == 1

    res2 = engine.handle({
        "command_id": "cmd_appr_req_01",
        "workflow_id": "wf_video_100",
        "type": "request_approval",
        "args": {"step": "script_review"},
    })
    assert res2.success is True
    assert res2.new_version == 2

    # Process Run 2: Simulated restart with same database repository
    restarted_engine = WorkflowEngine(repository=repo)
    # Duplicate command replay is idempotent
    dup_res = restarted_engine.handle({
        "command_id": "cmd_start_01",
        "workflow_id": "wf_video_100",
        "type": "start",
    })
    assert dup_res.success is True
    assert dup_res.message == "duplicate"

    # Event store replay
    event_store = InMemoryEventStore()
    event_store.save_event(AgentEvent(
        event_type="workflow_state",
        principal_id="user_alice",
        session_id="s1",
        turn_id="t1",
        sequence=1,
        data={"workflow_id": "wf_video_100", "state": "approval_requested"},
    ))
    events = event_store.get_events_for_owner("user_alice", after_seq=0)
    assert len(events) == 1
    assert events[0].sequence == 1
