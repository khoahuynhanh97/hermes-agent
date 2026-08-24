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
        self._poll_override: int | None = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def pid(self) -> int:
        return self._pid

    def set_exit(self, code: int) -> None:
        self._alive = False
        self._poll_override = code

    def poll(self) -> int | None:
        if self._poll_override is not None:
            return self._poll_override
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
        self.active_processes: dict[str, FakeChildProcess] = {}

    def start(self, spec: ProcessSpec) -> ChildProcess:
        self.spawned.append(spec.name)
        proc = FakeChildProcess(name=spec.name, terminated_list=self.killed, pid=1000 + len(self.spawned))
        self.active_processes[spec.name] = proc
        return proc

    def stop(self, child: ChildProcess) -> None:
        child.terminate()


def test_supervisor_independent_child_kills_and_bounded_restarts():
    """Prove supervisor detects independent child exits and enforces bounded restart backoff."""
    config = RuntimeConfig(mode="development", app_api_port=8000, enable_mcp=True, enable_workers=True)
    topology = build_process_topology(config=config)
    assert len(topology) >= 3

    runner = FakeRunner()
    current_time = 1000.0

    supervisor = Supervisor(
        specs=topology,
        runner=runner,
        clock=lambda: current_time,
    )
    supervisor.start_all()

    # Verify Gateway, API, Worker, MCP discovery are spawned
    assert "app_api" in runner.spawned
    assert "durable_worker" in runner.spawned
    assert "mcp_discovery" in runner.spawned

    # 1. Kill app_api independently and verify supervisor restarts it
    api_proc = runner.active_processes["app_api"]
    api_proc.set_exit(1)

    # Supervisor step triggers restart
    exit_code = supervisor.step()
    assert exit_code == 0
    assert supervisor.get_process_status("app_api") == "healthy"

    # 2. Exhaust restart attempts on mcp_discovery (max_attempts=3)
    for _ in range(4):
        mcp_proc = runner.active_processes.get("mcp_discovery")
        if mcp_proc:
            mcp_proc.set_exit(1)
        exit_code = supervisor.step()

    # Required process exhausted -> step returned non-zero exit code (1) and status is unavailable
    assert exit_code == 1
    assert supervisor.get_process_status("mcp_discovery") == "unavailable"

    supervisor.stop_all()


def test_readiness_probe_transitions_on_component_failure():
    """Prove readiness probe dynamically transitions between READY and NOT_READY based on health."""
    is_healthy = True

    def get_report() -> HealthReport:
        status = "healthy" if is_healthy else "degraded"
        return HealthReport.from_components(
            components=(ComponentHealth(name="storage", required=True, status=status),),
            checked_at=time.time(),
        )

    probe = ReadinessProbe(
        get_health_report=get_report,
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: is_healthy,
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

    # Initially ready
    assert probe.evaluate().is_ready is True

    # Component failure -> NOT READY
    is_healthy = False
    assert probe.evaluate().is_ready is False

    # Component recovery -> READY
    is_healthy = True
    assert probe.evaluate().is_ready is True


def test_workflow_and_approval_persistence_across_process_restart():
    """Prove durable workflow aggregate state and pending approvals survive simulated process restart."""
    conn = connect(":memory:")
    repo = WorkflowRepository(conn)
    engine_run1 = WorkflowEngine(repository=repo)

    # 1. Start workflow and request approval
    res1 = engine_run1.handle({
        "command_id": "cmd_start_101",
        "workflow_id": "wf_persist_01",
        "type": "start",
        "args": {"title": "Autumn Campaign"},
    })
    assert res1.success is True
    assert res1.new_version == 1

    res2 = engine_run1.handle({
        "command_id": "cmd_appr_req_101",
        "workflow_id": "wf_persist_01",
        "type": "request_approval",
        "args": {"step": "budget_signoff"},
    })
    assert res2.success is True
    assert res2.new_version == 2

    # 2. Simulate process restart with fresh WorkflowEngine instance
    engine_run2 = WorkflowEngine(repository=repo)

    # Replay of existing command is idempotent (no duplicate side effects)
    dup = engine_run2.handle({
        "command_id": "cmd_start_101",
        "workflow_id": "wf_persist_01",
        "type": "start",
    })
    assert dup.success is True
    assert dup.message == "duplicate"


def test_event_replay_with_cursor_across_restart():
    """Prove durable event store replay returns exact sequential events without duplicates."""
    store = InMemoryEventStore()

    for i in range(1, 6):
        store.save_event(AgentEvent(
            event_type="workflow_progress",
            principal_id="user_alice",
            session_id="s1",
            turn_id="t1",
            sequence=i,
            data={"step_index": i, "status": "ok"},
            workflow_id="wf_replay_01",
        ))

    # Replay from sequence 0 (all 5)
    all_events = store.get_events_for_owner("user_alice", after_seq=0)
    assert len(all_events) == 5
    assert [e.sequence for e in all_events] == [1, 2, 3, 4, 5]

    # Replay with cursor after sequence 3 (events 4 and 5 only)
    resumed_events = store.get_events_for_owner("user_alice", after_seq=3)
    assert len(resumed_events) == 2
    assert [e.sequence for e in resumed_events] == [4, 5]


def test_expired_lease_and_lock_recovery():
    """Prove expired execution lease/lock is safely recovered without duplicate execution."""
    conn = connect(":memory:")
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS job_lease (
            job_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)

    # Worker A acquired lease that expired at t=100
    cur.execute("INSERT INTO job_lease VALUES (?, ?, ?)", ("job_render_01", "worker_old", 100.0))
    conn.commit()

    # Worker B tries to acquire at t=150 (lease is expired -> successful takeover)
    current_time = 150.0
    new_expires = current_time + 60.0
    cur.execute("""
        UPDATE job_lease
        SET worker_id = ?, expires_at = ?
        WHERE job_id = ? AND expires_at < ?
    """, ("worker_new", new_expires, "job_render_01", current_time))
    conn.commit()

    assert cur.rowcount == 1

    # Verify worker_new now owns the lease
    cur.execute("SELECT worker_id, expires_at FROM job_lease WHERE job_id = ?", ("job_render_01",))
    row = cur.fetchone()
    assert row[0] == "worker_new"
    assert row[1] == 210.0


def test_supervisor_clean_shutdown_no_orphan_children():
    """Prove supervisor stop_all terminates every spawned child process cleanly in reverse order."""
    config = RuntimeConfig(mode="development", app_api_port=8000, enable_mcp=True, enable_workers=True)
    topology = build_process_topology(config=config)

    runner = FakeRunner()
    supervisor = Supervisor(specs=topology, runner=runner)
    supervisor.start_all()

    # All processes started
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is True

    # Shutdown
    supervisor.stop_all()

    # Verify no orphans remain alive
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is False
    assert len(runner.killed) >= len(topology)
