from __future__ import annotations

import asyncio
import time
from typing import Any, Iterator, Mapping

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import CapabilityPolicyEvaluator
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import IdentityRepository
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.orchestration import AgentOutput, HermesTurnService
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.runtime.config import RuntimeConfig
from hermes_personal.runtime.processes import ProcessSpec, build_process_topology
from hermes_personal.runtime.readiness import ReadinessProbe
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus
from hermes_personal.runtime.supervisor import ChildProcess, ProcessRunner, Supervisor
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import WorkflowRepository


class SmokeChildProcess(ChildProcess):
    def __init__(self, name: str, terminated_list: list[str], pid: int = 4000):
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


class SmokeRunner(ProcessRunner):
    def __init__(self):
        self.spawned: list[str] = []
        self.killed: list[str] = []
        self.active_processes: dict[str, SmokeChildProcess] = {}

    def start(self, spec: ProcessSpec) -> ChildProcess:
        self.spawned.append(spec.name)
        proc = SmokeChildProcess(name=spec.name, terminated_list=self.killed, pid=4000 + len(self.spawned))
        self.active_processes[spec.name] = proc
        return proc

    def stop(self, child: ChildProcess) -> None:
        child.terminate()


class FakeAgent:
    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        yield AgentOutput(
            event_type="text_delta",
            data={"delta": "Generated response for Web turn"},
        )
        yield AgentOutput(
            event_type="completed",
            data={"text": f"Successfully finished Web turn: {request.message}"},
        )


class FakeTranscript:
    def __init__(self):
        self.events: list[AgentEvent] = []
        self.user_turns: list[str] = []

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple({"role": "user", "content": t} for t in self.user_turns)

    def append_user_turn(self, text: str) -> None:
        self.user_turns.append(text)

    def append_event(self, event: AgentEvent) -> None:
        self.events.append(event)


class FakeTranscriptFactory:
    def __init__(self):
        self.transcripts: dict[str, FakeTranscript] = {}

    def for_session(self, session_id: str) -> FakeTranscript:
        if session_id not in self.transcripts:
            self.transcripts[session_id] = FakeTranscript()
        return self.transcripts[session_id]


def test_full_fake_provider_local_runtime_smoke_cycle():
    """Prove end-to-end fake-provider local runtime lifecycle:

    1. Process topology built from runtime config
    2. Supervisor starts all processes
    3. Readiness probe evaluates to READY
    4. Web Agent Turn executed via HermesTurnService producing real durable AgentEvents
    5. Clean supervisor shutdown with zero orphan processes
    """
    # 1. Topology & Supervisor setup
    config = RuntimeConfig(mode="development", app_api_port=8000, enable_mcp=True, enable_workers=True)
    topology = build_process_topology(config=config)
    runner = SmokeRunner()

    supervisor = Supervisor(specs=topology, runner=runner)
    supervisor.start_all()

    # All processes started
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is True

    # 2. Readiness Evaluation
    probe = ReadinessProbe(
        get_health_report=lambda: HealthReport.from_components((
            ComponentHealth(name="gateway", required=True, status="healthy"),
            ComponentHealth(name="app_api", required=True, status="healthy"),
            ComponentHealth(name="mcp_discovery", required=True, status="healthy"),
        )),
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: True,
    )
    probe.set_startup_report(
        StartupReport(
            overall_status=StartupStepStatus.COMPLETED,
            steps=(
                StartupStepRecord(name="db", status=StartupStepStatus.COMPLETED, start_time=0.0, end_time=0.01, latency_ms=10.0),
            ),
            started_at=0.0,
            completed_at=0.01,
            total_latency_ms=10.0,
        )
    )
    readiness_result = probe.evaluate()
    assert readiness_result.is_ready is True

    # 3. Web Agent Turn via HermesTurnService
    conn = connect(":memory:")
    identity_repo = IdentityRepository(conn)
    session_repo = SessionRepository(conn)
    event_repo = EventRepository(conn)
    snap_repo = CapabilitySnapshotRepository(conn)

    bindings = tuple(
        ImplementationBinding(
            capability_id=spec.capability_id,
            wire_name=spec.capability_id.replace(".", "_"),
            source="builtin",
            provider=spec.owner,
            implementation_version="1.0.0",
            input_schema_version=spec.input_schema_version,
            output_schema_version=spec.output_schema_version,
            schema_digest=f"sha256:{spec.capability_id}",
            health="healthy",
        )
        for spec in INITIAL_CAPABILITIES.values()
    )
    snap_repo.save_and_activate(bindings)

    catalog_service = CapabilityCatalogService(
        snapshot_repository=snap_repo,
        policy_evaluator=CapabilityPolicyEvaluator(),
    )
    transcript_factory = FakeTranscriptFactory()
    agent = FakeAgent()

    owner = identity_repo.create_owner("Smoke Operator")
    identity_repo.link(owner.owner_user_id, "web", "web_smoke_user")
    session = session_repo.get_or_create(owner.owner_user_id, "web", "conv_web_smoke")

    service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=agent,
        catalog_service=catalog_service,
    )

    ctx = PrincipalContext(
        actor_id="web_smoke_user",
        owner_user_id=owner.owner_user_id,
        channel="web",
        session_id=session.session_id,
    )
    req = AgentTurnRequest(
        principal=ctx,
        message="Smoke test: render video outline",
        idempotency_key="idem_smoke_001",
    )

    async def _run_turn():
        evts = []
        async for e in service.handle(req):
            evts.append(e)
        return evts

    emitted_events = asyncio.run(_run_turn())
    assert len(emitted_events) >= 2
    types = [e.event_type for e in emitted_events]
    assert "text_delta" in types
    assert "completed" in types

    # Verify event store durability
    stored_rows = conn.execute("SELECT * FROM turn_event WHERE turn_id = ?", (req.turn_id,)).fetchall()
    assert len(stored_rows) >= 2

    # 4. Clean Shutdown & Zero Orphans
    supervisor.stop_all()
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is False
    assert len(runner.killed) >= len(topology)
