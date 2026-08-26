from __future__ import annotations

import json

from fastapi.testclient import TestClient

from hermes_personal.api.server import create_proxy_application
from hermes_personal.runtime.gateway_server import create_gateway_application


def test_fake_gateway_runs_canonical_turn_and_durable_replay(tmp_path):
    app = create_gateway_application(
        database_path=tmp_path / "runtime.sqlite3",
        api_key="test-runtime-key",
        provider_mode="fake",
    )

    with TestClient(app) as client:
        ready = client.get("/health/ready")
        turn = client.post(
            "/api/turn",
            json={"conversation_id": "smoke", "message": "xin chao"},
            headers={
                "Authorization": "Bearer test-runtime-key",
                "Idempotency-Key": "smoke-1",
            },
        )
        events = [json.loads(line) for line in turn.text.splitlines()]
        replay = client.get(
            "/api/events/replay",
            params={"owner_id": "local-owner"},
            headers={"Authorization": "Bearer test-runtime-key"},
        )

    assert ready.status_code == 200
    assert turn.status_code == 200
    assert [event["event_type"] for event in events] == ["text_delta", "completed"]
    assert replay.status_code == 200
    assert replay.json()["count"] == 2
    assert [event["cursor"] for event in replay.json()["events"]] == [1, 2]


def test_app_api_bootstrap_uses_ephemeral_browser_token_not_gateway_secret():
    client = TestClient(
        create_proxy_application(
            "http://127.0.0.1:1",
            api_key="gateway-secret",
            owner_user_id="owner-7",
            browser_session_token="browser-session-key",
        )
    )

    response = client.get("/")

    assert response.status_code == 200
    assert 'window.__HERMES_SESSION_TOKEN__="browser-session-key"' in response.text
    assert 'window.__HERMES_OWNER_ID__="owner-7"' in response.text
    assert "hermes_session=browser-session-key" in response.text
    assert "gateway-secret" not in response.text


class _RecordingAgent:
    def __init__(self):
        self.calls = []

    def run(self, request, history):
        self.calls.append((request.message, history))
        text = f"echo:{request.message}"
        from hermes_personal.orchestration import AgentOutput

        yield AgentOutput("text_delta", {"text": text})
        yield AgentOutput("completed", {"text": text, "provider_mode": "test"})


def test_gateway_multi_turn_history_and_restart_persistence(tmp_path):
    db_path = tmp_path / "runtime-restart.sqlite3"
    agent1 = _RecordingAgent()
    app1 = create_gateway_application(
        database_path=db_path,
        api_key="test-restart-key",
        owner_user_id="local-owner",
        provider_mode="fake",
        agent=agent1,
    )

    with TestClient(app1) as client1:
        # Turn 1
        turn1 = client1.post(
            "/api/turn",
            json={"conversation_id": "session-1", "message": "Turn 1 question"},
            headers={
                "Authorization": "Bearer test-restart-key",
                "Idempotency-Key": "turn-1",
            },
        )
        assert turn1.status_code == 200
        assert len(agent1.calls) == 1
        assert agent1.calls[0][1] == ()

        # Turn 2 in same session
        turn2 = client1.post(
            "/api/turn",
            json={"conversation_id": "session-1", "message": "Turn 2 question"},
            headers={
                "Authorization": "Bearer test-restart-key",
                "Idempotency-Key": "turn-2",
            },
        )
        assert turn2.status_code == 200
        assert len(agent1.calls) == 2
        # Turn 2 must have history of Turn 1
        turn2_history = agent1.calls[1][1]
        assert len(turn2_history) == 2
        assert turn2_history[0]["role"] == "user"
        assert turn2_history[0]["content"] == "Turn 1 question"
        assert turn2_history[1]["role"] == "assistant"
        assert turn2_history[1]["content"] == "echo:Turn 1 question"

    # Simulate Gateway process restart with same database
    agent2 = _RecordingAgent()
    app2 = create_gateway_application(
        database_path=db_path,
        api_key="test-restart-key",
        owner_user_id="local-owner",
        provider_mode="fake",
        agent=agent2,
    )

    with TestClient(app2) as client2:
        # Turn 3 after restart in same session
        turn3 = client2.post(
            "/api/turn",
            json={"conversation_id": "session-1", "message": "Turn 3 question"},
            headers={
                "Authorization": "Bearer test-restart-key",
                "Idempotency-Key": "turn-3",
            },
        )
        assert turn3.status_code == 200
        assert len(agent2.calls) == 1
        # Turn 3 must receive committed history from Turn 1 and Turn 2 across restart
        turn3_history = agent2.calls[0][1]
        assert len(turn3_history) == 4
        assert turn3_history[0]["role"] == "user"
        assert turn3_history[0]["content"] == "Turn 1 question"
        assert turn3_history[1]["role"] == "assistant"
        assert turn3_history[1]["content"] == "echo:Turn 1 question"
        assert turn3_history[2]["role"] == "user"
        assert turn3_history[2]["content"] == "Turn 2 question"
        assert turn3_history[3]["role"] == "assistant"
        assert turn3_history[3]["content"] == "echo:Turn 2 question"

        # Check full replay across restart: monotonic owner cursor 1..6
        replay = client2.get(
            "/api/events/replay",
            params={"owner_id": "local-owner"},
            headers={"Authorization": "Bearer test-restart-key"},
        )
        assert replay.status_code == 200
        data = replay.json()
        assert data["count"] == 6
        assert [e["cursor"] for e in data["events"]] == [1, 2, 3, 4, 5, 6]


def test_gateway_auth_and_owner_isolation(tmp_path):
    app = create_gateway_application(
        database_path=tmp_path / "auth.sqlite3",
        api_key="secret-key-123",
        owner_user_id="owner-alice",
        external_subject="owner-alice",
        provider_mode="fake",
    )

    with TestClient(app) as client:
        # Invalid API key
        res = client.post(
            "/api/turn",
            json={"conversation_id": "c1", "message": "hi"},
            headers={"Authorization": "Bearer wrong-key"},
        )
        assert res.status_code == 401

        # Forged owner_id
        res = client.post(
            "/api/turn",
            json={"conversation_id": "c1", "message": "hi", "owner_id": "owner-bob"},
            headers={"Authorization": "Bearer secret-key-123"},
        )
        assert res.status_code == 403

        # Replay for wrong owner_id rejected
        res = client.get(
            "/api/events/replay",
            params={"owner_id": "owner-bob"},
            headers={"Authorization": "Bearer secret-key-123"},
        )
        assert res.status_code == 403

