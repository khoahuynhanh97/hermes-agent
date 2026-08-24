from __future__ import annotations

import json
from starlette.testclient import TestClient

from hermes_personal.application.app import create_application
from hermes_personal.application.events_api import ArtifactRecord, EventsAPI, InMemoryEventStore
from hermes_personal.application.health_api import HealthAPI
from hermes_personal.contracts.events import AgentEvent
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.runtime.readiness import ReadinessProbe
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus


def test_fastapi_health_routes():
    health_api = HealthAPI()
    app = create_application(health_api=health_api)
    client = TestClient(app)

    # 1. Live
    res = client.get("/health/live")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "live": True}

    # 2. Ready without probe -> 503
    res = client.get("/health/ready")
    assert res.status_code == 503
    assert res.json()["status"] == "not_ready"

    # 3. Setup ready probe
    ready_report = StartupReport(
        overall_status=StartupStepStatus.COMPLETED,
        steps=(
            StartupStepRecord(
                name="ingress_ready",
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
    health_report = HealthReport.from_components(
        components=(ComponentHealth(name="gateway", required=True, status="healthy"),),
        checked_at=100.0,
    )
    probe = ReadinessProbe(
        get_health_report=lambda: health_report,
        check_capability_snapshot=lambda: True,
        check_dependency_probes=lambda: True,
    )
    probe.set_startup_report(ready_report)
    health_api.set_readiness_probe(probe)

    res = client.get("/health/ready")
    assert res.status_code == 200
    assert res.json()["status"] == "ready"
    assert res.json()["ready"] is True

    # 4. Component health
    res = client.get("/health/components/gateway")
    assert res.status_code == 200
    assert res.json() == {"component": "gateway", "status": "healthy"}


def test_fastapi_events_and_replay_routes():
    store = InMemoryEventStore()
    events_api = EventsAPI(
        event_store=store,
        auth_validator=lambda token, owner: token == f"token_{owner}",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    event1 = AgentEvent(
        event_type="text_delta",
        principal_id="user_alice",
        session_id="sess_1",
        turn_id="turn_1",
        sequence=1,
        data={"delta": "Hello "},
    )
    event2 = AgentEvent(
        event_type="text_delta",
        principal_id="user_alice",
        session_id="sess_1",
        turn_id="turn_1",
        sequence=2,
        data={"delta": "world!"},
    )
    event_bob = AgentEvent(
        event_type="text_delta",
        principal_id="user_bob",
        session_id="sess_2",
        turn_id="turn_2",
        sequence=1,
        data={"delta": "Bob private"},
    )
    store.save_event(event1)
    store.save_event(event2)
    store.save_event(event_bob)

    # 1. Replay JSON route with owner isolation and cursor resume
    res = client.get(
        "/api/events/replay?owner_id=user_alice&after_seq=0",
        headers={"Authorization": "Bearer token_user_alice"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["count"] == 2
    assert data["next_cursor"] == 2
    assert [e["sequence"] for e in data["events"]] == [1, 2]

    # Replay after_seq=1
    res = client.get(
        "/api/events/replay?owner_id=user_alice&after_seq=1",
        headers={"Authorization": "Bearer token_user_alice"},
    )
    assert res.status_code == 200
    assert res.json()["count"] == 1
    assert res.json()["events"][0]["sequence"] == 2

    # Unauthorized access rejected
    res = client.get(
        "/api/events/replay?owner_id=user_alice&after_seq=0",
        headers={"Authorization": "Bearer wrong_token"},
    )
    assert res.status_code == 403

    # 2. SSE Streaming route
    res = client.get(
        "/api/events?owner_id=user_alice&after_seq=0",
        headers={"Authorization": "Bearer token_user_alice"},
    )
    assert res.status_code == 200
    assert "text/event-stream" in res.headers["content-type"]
    sse_body = res.text
    assert "id: 1\n" in sse_body
    assert "id: 2\n" in sse_body
    assert "event: heartbeat\n" in sse_body


def test_fastapi_operator_command_and_artifact_routes():
    handled = []
    events_api = EventsAPI(
        command_handler=lambda cmd: handled.append(cmd) or {"executed": True},
        auth_validator=lambda token, owner: token == "valid_token",
    )
    app = create_application(events_api=events_api)
    client = TestClient(app)

    # 1. Operator command submission
    res = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer valid_token"},
        json={
            "owner_id": "op_admin",
            "command_type": "approve",
            "target_id": "wf_123",
            "expected_version": 1,
            "payload": {"approved": True},
        },
    )
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    assert len(handled) == 1
    assert handled[0].command_type == "approve"
    assert handled[0].target_id == "wf_123"

    # Operator command forbidden
    res = client.post(
        "/api/operator/command",
        headers={"Authorization": "Bearer bad_token"},
        json={
            "owner_id": "op_admin",
            "command_type": "approve",
            "target_id": "wf_123",
            "expected_version": 1,
        },
    )
    assert res.status_code == 403

    # 2. Artifact metadata route
    art = ArtifactRecord(
        artifact_id="art_video_001",
        owner_user_id="user_alice",
        artifact_type="video_render",
        version=1,
        digest="sha256:abc123digest",
        delivery_ref="/storage/artifacts/art_video_001.mp4",
        metadata={"duration_sec": 45},
    )
    events_api.add_artifact(art)

    # Alice queries artifact
    res = client.get(
        "/api/artifacts/art_video_001?owner_id=user_alice",
        headers={"Authorization": "Bearer valid_token"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["artifact_id"] == "art_video_001"
    assert data["digest"] == "sha256:abc123digest"
    assert data["delivery_ref"] == "/storage/artifacts/art_video_001.mp4"

    # Foreign user Bob forbidden
    res = client.get(
        "/api/artifacts/art_video_001?owner_id=user_bob",
        headers={"Authorization": "Bearer valid_token"},
    )
    assert res.status_code == 403

    # Unknown artifact -> 404
    res = client.get(
        "/api/artifacts/unknown_artifact?owner_id=user_alice",
        headers={"Authorization": "Bearer valid_token"},
    )
    assert res.status_code == 404
