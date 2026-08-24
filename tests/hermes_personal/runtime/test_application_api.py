from __future__ import annotations

import json
from datetime import datetime, timezone
import pytest

from hermes_personal.application.events_api import ArtifactRecord, EventsAPI
from hermes_personal.application.health_api import HealthAPI
from hermes_personal.contracts.events import AgentEvent
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.runtime.readiness import ReadinessProbe, ReadinessState
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus


def test_health_api_live_and_ready():
    health_api = HealthAPI()
    code, res = health_api.handle_live()
    assert code == 200
    assert res["status"] == "ok"
    assert res["live"] is True

    # Ready without probe returns 503
    code, res = health_api.handle_ready()
    assert code == 503
    assert res["status"] == "not_ready"

    # Setup ready probe
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
    code, res = health_api.handle_ready()
    assert code == 200
    assert res["status"] == "ready"
    assert res["ready"] is True


def test_events_api_resume_and_isolation():
    api = EventsAPI(
        auth_validator=lambda token, owner: token == f"token_{owner}",
    )
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
    api.add_event(event1)
    api.add_event(event2)
    api.add_event(event_bob)

    # Alice fetches her events from sequence 0
    code, res = api.get_events(owner_id="user_alice", after_seq=0, auth_token="token_user_alice")
    assert code == 200
    assert res["count"] == 2
    assert res["next_cursor"] == 2
    assert [e["sequence"] for e in res["events"]] == [1, 2]

    # Alice resumes from sequence 1 (only receives sequence 2)
    code, res = api.get_events(owner_id="user_alice", after_seq=1, auth_token="token_user_alice")
    assert code == 200
    assert res["count"] == 1
    assert res["events"][0]["sequence"] == 2

    # Unauthorized access rejected
    code, res = api.get_events(owner_id="user_alice", after_seq=0, auth_token="wrong_token")
    assert code == 403


def test_events_sse_formatting_and_heartbeat():
    api = EventsAPI()
    event = AgentEvent(
        event_type="cost_update",
        principal_id="user_alice",
        session_id="sess_1",
        turn_id="turn_1",
        sequence=42,
        data={"cost_usd": 0.005},
    )
    sse_text = api.format_sse_event(event)
    assert "id: 42\n" in sse_text
    assert "event: cost_update\n" in sse_text
    assert '"cost_usd": 0.005' in sse_text

    hb_text = api.format_sse_heartbeat()
    assert "event: heartbeat\n" in hb_text
    assert "timestamp" in hb_text


def test_operator_command_submission():
    handled_commands = []
    api = EventsAPI(
        command_handler=lambda cmd: handled_commands.append(cmd) or {"executed": True},
        auth_validator=lambda token, owner: token == "valid_operator_token",
    )

    code, res = api.handle_operator_command(
        auth_token="valid_operator_token",
        owner_id="op_admin",
        command_type="approve",
        target_id="workflow_123",
        expected_version=1,
        payload={"reason": "verified by human"},
    )
    assert code == 200
    assert res["status"] == "ok"
    assert len(handled_commands) == 1
    assert handled_commands[0].command_type == "approve"
    assert handled_commands[0].target_id == "workflow_123"

    # Unauthenticated rejected
    code, res = api.handle_operator_command(
        auth_token="invalid_token",
        owner_id="op_admin",
        command_type="reject",
        target_id="workflow_123",
        expected_version=1,
    )
    assert code == 403


def test_artifact_metadata_endpoint():
    api = EventsAPI(
        auth_validator=lambda token, owner: token == "tok",
    )
    art = ArtifactRecord(
        artifact_id="art_video_001",
        owner_user_id="user_alice",
        artifact_type="video_render",
        version=1,
        digest="sha256:abc123digest",
        delivery_ref="/storage/artifacts/art_video_001.mp4",
        metadata={"duration_sec": 45},
    )
    api.add_artifact(art)

    # Alice fetches her artifact
    code, res = api.get_artifact("art_video_001", owner_id="user_alice", auth_token="tok")
    assert code == 200
    assert res["artifact_id"] == "art_video_001"
    assert res["digest"] == "sha256:abc123digest"
    assert res["delivery_ref"] == "/storage/artifacts/art_video_001.mp4"

    # Foreign user Bob rejected with 403
    code, res = api.get_artifact("art_video_001", owner_id="user_bob", auth_token="tok")
    assert code == 403

    # Unknown artifact returns 404
    code, res = api.get_artifact("art_unknown", owner_id="user_alice", auth_token="tok")
    assert code == 404
