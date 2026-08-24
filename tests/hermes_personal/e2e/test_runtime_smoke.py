from __future__ import annotations

import json
from typing import Any, Mapping
from starlette.testclient import TestClient

from hermes_personal.application.app import create_application
from hermes_personal.application.events_api import ArtifactRecord, EventsAPI, InMemoryEventStore
from hermes_personal.application.health_api import HealthAPI
from hermes_personal.contracts.events import AgentEvent
from hermes_personal.contracts.operator import OperatorCommand, OperatorCommandType
from hermes_personal.contracts.principal import PrincipalContext
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.runtime.config import RuntimeConfig
from hermes_personal.runtime.processes import ProcessSpec, build_process_topology
from hermes_personal.runtime.readiness import ReadinessProbe
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus
from hermes_personal.runtime.supervisor import ChildProcess, ProcessRunner, Supervisor
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.storage.sqlite import connect


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


def test_production_http_surface_runtime_smoke_cycle():
    """Prove end-to-end fake-provider local runtime lifecycle over production HTTP API routes:

    1. Process topology built and started via Supervisor
    2. Readiness probe evaluates to READY -> HTTP GET /health/ready returns 200
    3. Web/Operator command submitted via HTTP POST /api/operator/command
    4. Real durable AgentEvents recorded and retrieved via HTTP GET /api/events/replay
    5. Artifact metadata retrieved via HTTP GET /api/artifacts/{id} with owner verification
    6. Clean supervisor shutdown with zero orphan child processes
    """
    # 1. Process topology & Supervisor
    config = RuntimeConfig(mode="development", app_api_port=8000, enable_mcp=True, enable_workers=True)
    topology = build_process_topology(config=config)
    runner = SmokeRunner()

    supervisor = Supervisor(specs=topology, runner=runner)
    supervisor.start_all()
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is True

    # 2. Readiness probe & Health API
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
                StartupStepRecord(name="capabilities", status=StartupStepStatus.COMPLETED, start_time=0.01, end_time=0.02, latency_ms=10.0),
            ),
            started_at=0.0,
            completed_at=0.02,
            total_latency_ms=20.0,
        )
    )

    health_api = HealthAPI(readiness_probe=probe)
    event_store = InMemoryEventStore()

    # Setup command handler connected to workflow engine
    conn = connect(":memory:")
    wf_repo = WorkflowRepository(conn)
    wf_engine = WorkflowEngine(repository=wf_repo)

    # Pre-seed workflow into approval_requested state (version 2)
    wf_engine.handle({
        "command_id": "cmd_seed_01",
        "workflow_id": "wf_web_smoke_01",
        "type": "start",
        "args": {"title": "Hermes Product Launch"},
    })
    wf_engine.handle({
        "command_id": "cmd_seed_02",
        "workflow_id": "wf_web_smoke_01",
        "type": "request_approval",
        "args": {"step": "script_review"},
    })

    def _handle_operator_command(cmd: OperatorCommand) -> dict[str, Any]:
        if cmd.command_type == "approve":
            res = wf_engine.handle({
                "command_id": cmd.command_id,
                "workflow_id": cmd.target_id,
                "type": "approve",
                "args": dict(cmd.payload),
            })
            evt = AgentEvent(
                event_type="workflow_state",
                principal_id=cmd.principal.owner_user_id,
                session_id="session_smoke_01",
                turn_id="turn_smoke_01",
                sequence=1,
                workflow_id=cmd.target_id,
                data={"state": "approved", "version": int(res.new_version)},
            )
            event_store.save_event(evt)
            return {"success": bool(res.success), "workflow_id": str(cmd.target_id), "version": int(res.new_version)}
        return {"success": True}

    events_api = EventsAPI(
        event_store=event_store,
        command_handler=_handle_operator_command,
        auth_validator=lambda token, owner: True,
    )

    artifact = ArtifactRecord(
        artifact_id="art_video_script_01",
        owner_user_id="user_owner_01",
        artifact_type="video_script",
        version=1,
        digest="sha256:script_digest_01",
        delivery_ref="file:///tmp/script.md",
        metadata={"title": "Product Launch Video"},
    )
    events_api.add_artifact(artifact)

    app = create_application(health_api=health_api, events_api=events_api)
    client = TestClient(app)

    # 3. HTTP Health Endpoints
    live_resp = client.get("/health/live")
    assert live_resp.status_code == 200
    assert live_resp.json()["status"] == "ok"

    ready_resp = client.get("/health/ready")
    assert ready_resp.status_code == 200
    ready_data = ready_resp.json()
    assert ready_data["status"] == "ready"
    assert ready_data["ready"] is True

    # 4. HTTP Operator Command (Web Ingress)
    cmd_payload = {
        "command_id": "cmd_web_turn_01",
        "command_type": "approve",
        "target_id": "wf_web_smoke_01",
        "owner_id": "user_owner_01",
        "expected_version": 2,
        "payload": {"reason": "Approved by Web Operator"},
    }
    cmd_resp = client.post(
        "/api/operator/command",
        json=cmd_payload,
        headers={"Authorization": "Bearer fake_token"},
    )
    assert cmd_resp.status_code == 200
    assert cmd_resp.json()["status"] == "ok"

    # 5. HTTP Durable Event Replay
    replay_resp = client.get(
        "/api/events/replay?after_seq=0&owner_id=user_owner_01",
        headers={"Authorization": "Bearer fake_token"},
    )
    assert replay_resp.status_code == 200
    replay_data = replay_resp.json()
    events = replay_data["events"]
    assert len(events) >= 1
    assert events[0]["event_type"] == "workflow_state"
    assert events[0]["sequence"] == 1

    # 6. HTTP Artifact Access
    art_resp = client.get(
        "/api/artifacts/art_video_script_01?owner_id=user_owner_01",
        headers={"Authorization": "Bearer fake_token"},
    )
    assert art_resp.status_code == 200
    assert art_resp.json()["artifact_id"] == "art_video_script_01"

    # Cross-owner forbidden access (403)
    art_forbidden = client.get(
        "/api/artifacts/art_video_script_01?owner_id=unauthorized_user",
        headers={"Authorization": "Bearer fake_token"},
    )
    assert art_forbidden.status_code == 403

    # 7. Clean supervisor shutdown with zero orphan processes
    supervisor.stop_all()
    for spec in topology:
        assert runner.active_processes[spec.name].is_alive() is False
    assert len(runner.killed) >= len(topology)
