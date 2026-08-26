from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping
from starlette.testclient import TestClient

from hermes_personal.application.app import create_application
from hermes_personal.application.events_api import ArtifactRecord, EventsAPI, InMemoryEventStore
from hermes_personal.application.health_api import HealthAPI
from hermes_personal.application.turn_api import StaticBearerAuthenticator
from hermes_personal.contracts import AgentTurnRequest
from hermes_personal.contracts.events import AgentEvent
from hermes_personal.gateway.normalizers import ChannelTurnNormalizer
from hermes_personal.identity import IdentityRepository
from hermes_personal.observability.health import ComponentHealth, HealthReport
from hermes_personal.orchestration import AgentOutput, EventRepository, HermesTurnService
from hermes_personal.runtime.readiness import ReadinessProbe
from hermes_personal.runtime.startup import StartupReport, StartupStepRecord, StartupStepStatus
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


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


def test_events_api_is_fail_closed_without_auth_configuration():
    app = create_application(events_api=EventsAPI())
    client = TestClient(app)

    response = client.get(
        "/api/events/replay?owner_id=user_alice&after_seq=0",
        headers={"Authorization": "Bearer any-non-empty-token"},
    )

    assert response.status_code == 403


def test_event_replay_uses_owner_cursor_not_per_turn_sequence():
    store = InMemoryEventStore()
    for turn_id in ("turn_1", "turn_2"):
        store.save_event(
            AgentEvent(
                event_type="completed",
                principal_id="user_alice",
                session_id="session_1",
                turn_id=turn_id,
                sequence=0,
                data={"turn": turn_id},
            )
        )
    api = EventsAPI(
        event_store=store,
        auth_validator=lambda token, owner: token == "valid" and owner == "user_alice",
    )

    status, first = api.get_events("user_alice", after_seq=0, limit=1, auth_token="valid")
    status_2, second = api.get_events(
        "user_alice", after_seq=first["next_cursor"], limit=1, auth_token="valid"
    )

    assert status == status_2 == 200
    assert first["events"][0]["sequence"] == 0
    assert first["events"][0]["cursor"] == 1
    assert second["events"][0]["sequence"] == 0
    assert second["events"][0]["cursor"] == 2


@dataclass
class _Transcript:
    messages: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def history(self):
        return tuple(self.messages)

    def append_user_turn(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def append_event(self, event: AgentEvent) -> None:
        return None


@dataclass
class _TranscriptFactory:
    transcripts: dict[str, _Transcript] = field(default_factory=dict)

    def for_session(self, session_id: str) -> _Transcript:
        return self.transcripts.setdefault(session_id, _Transcript())


class _FakeAgent:
    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        yield AgentOutput("text_delta", {"text": f"echo:{request.message}"})
        yield AgentOutput("completed", {"text": "done"})


def test_http_turn_routes_execute_canonical_service_and_bind_authenticated_owner(tmp_path):
    conn = connect(tmp_path / "turn-api.sqlite3")
    identities = IdentityRepository(conn)
    sessions = SessionRepository(conn)
    owner = identities.create_owner("Alice")
    identities.link(owner.owner_user_id, "web", "alice")
    identities.link(owner.owner_user_id, "omni", "alice")
    service = HermesTurnService(
        identities,
        sessions,
        EventRepository(conn),
        _TranscriptFactory(),
        _FakeAgent(),
    )
    app = create_application(
        turn_service=service,
        turn_normalizers={
            "web": ChannelTurnNormalizer("web", identities, sessions),
            "omni": ChannelTurnNormalizer("omni", identities, sessions),
        },
        turn_authenticator=StaticBearerAuthenticator(
            "runtime-key", owner.owner_user_id, "alice"
        ),
    )
    client = TestClient(app)

    denied = client.post(
        "/api/turn",
        json={"conversation_id": "chat-1", "message": "hello"},
        headers={"Authorization": "Bearer wrong"},
    )
    forged = client.post(
        "/api/turn",
        json={
            "owner_id": "another-owner",
            "conversation_id": "chat-1",
            "message": "hello",
        },
        headers={"Authorization": "Bearer runtime-key"},
    )
    response = client.post(
        "/api/turn",
        json={"conversation_id": "chat-1", "message": "hello"},
        headers={
            "Authorization": "Bearer runtime-key",
            "Idempotency-Key": "web-turn-1",
        },
    )

    assert denied.status_code == 401
    assert forged.status_code == 403
    assert response.status_code == 200
    events = [json.loads(line) for line in response.text.splitlines()]
    assert [event["event_type"] for event in events] == ["text_delta", "completed"]
    assert all(event["principal_id"] == owner.owner_user_id for event in events)


def test_http_turn_route_returns_503_without_service():
    client = TestClient(create_application())

    response = client.post(
        "/api/turn",
        json={"conversation_id": "chat-1", "message": "hello"},
        headers={"Authorization": "Bearer configured-looking-token"},
    )

    assert response.status_code == 503


def test_compute_and_verify_static_bundle_digest(tmp_path):
    from hermes_personal.api.server import (
        compute_static_bundle_digest,
        create_proxy_application,
        verify_static_bundle_digest,
    )

    static_dir = tmp_path / "web_dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><html><head></head><body>Hermes</body></html>", encoding="utf-8")
    (static_dir / "app.js").write_text("console.log('hermes app');", encoding="utf-8")
    assets_dir = static_dir / "assets"
    assets_dir.mkdir()
    (assets_dir / "style.css").write_text("body { margin: 0; }", encoding="utf-8")

    digest = compute_static_bundle_digest(static_dir)
    assert digest.startswith("sha256:")
    assert len(digest) == 71  # "sha256:" (7) + 64 hex chars

    # Verification passes with the computed digest
    verify_static_bundle_digest(static_dir, digest)

    # Proxy application successfully creates with verified bundle
    app = create_proxy_application(
        "http://127.0.0.1:8642",
        static_dir=static_dir,
        static_digest=digest,
    )
    client = TestClient(app)
    res = client.get("/")
    assert res.status_code == 200
    assert "Hermes" in res.text


def test_static_bundle_digest_rejects_tampered_files_and_drift(tmp_path):
    import pytest
    from hermes_personal.api.server import (
        compute_static_bundle_digest,
        create_proxy_application,
        verify_static_bundle_digest,
    )

    static_dir = tmp_path / "web_dist_tamper"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<!doctype html><html><head></head><body>Original</body></html>", encoding="utf-8")
    (static_dir / "app.js").write_text("console.log('original');", encoding="utf-8")

    original_digest = compute_static_bundle_digest(static_dir)

    # 1. Tamper existing file content
    (static_dir / "app.js").write_text("console.log('tampered');", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_static_bundle_digest(static_dir, original_digest)

    with pytest.raises(ValueError, match="digest mismatch"):
        create_proxy_application(
            "http://127.0.0.1:8642",
            static_dir=static_dir,
            static_digest=original_digest,
        )

    # Restore app.js
    (static_dir / "app.js").write_text("console.log('original');", encoding="utf-8")
    verify_static_bundle_digest(static_dir, original_digest)

    # 2. Add extra unexpected file
    (static_dir / "extra.js").write_text("alert('injected');", encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_static_bundle_digest(static_dir, original_digest)

    # 3. Delete a file
    (static_dir / "extra.js").unlink()
    (static_dir / "app.js").unlink()
    with pytest.raises(ValueError, match="digest mismatch"):
        verify_static_bundle_digest(static_dir, original_digest)


def test_static_bundle_digest_rejects_missing_dir_and_malformed_digest(tmp_path):
    import pytest
    from hermes_personal.api.server import verify_static_bundle_digest

    missing_dir = tmp_path / "nonexistent"
    valid_digest_format = "sha256:" + "0" * 64

    # Missing directory
    with pytest.raises(ValueError, match="does not exist"):
        verify_static_bundle_digest(missing_dir, valid_digest_format)

    # Missing index.html
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    with pytest.raises(ValueError, match="missing index.html"):
        verify_static_bundle_digest(empty_dir, valid_digest_format)

    # Malformed digest formats
    (empty_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    for bad_digest in ("", "digest123", "sha256:short", "sha256:" + "G" * 64, "md5:abc"):
        with pytest.raises(ValueError, match="Malformed static digest"):
            verify_static_bundle_digest(empty_dir, bad_digest)
