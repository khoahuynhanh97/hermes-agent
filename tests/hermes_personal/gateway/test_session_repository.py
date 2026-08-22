from datetime import datetime, timezone

import pytest

from hermes_personal.contracts import AgentEvent
from hermes_personal.sessions import (
    OwnerMismatchError,
    SessionRepository,
    UpstreamTranscriptAdapter,
)
from hermes_personal.storage.sqlite import connect


@pytest.fixture
def session_repository(tmp_path):
    connection = connect(tmp_path / "sessions.sqlite")
    repository = SessionRepository(connection)
    try:
        yield repository
    finally:
        connection.close()


def test_sessions_are_separate_per_channel(session_repository):
    telegram = session_repository.get_or_create("user:42", "telegram", "chat:1")
    web = session_repository.get_or_create("user:42", "web", "browser:1")

    assert telegram.session_id != web.session_id
    assert telegram.owner_user_id == web.owner_user_id


def test_workflow_is_visible_only_after_explicit_handoff(session_repository):
    source = session_repository.get_or_create("user:42", "telegram", "chat:1")
    target = session_repository.get_or_create("user:42", "cli", "terminal:1")

    session_repository.link_workflow(source.session_id, "wf_7")

    assert session_repository.resolve_handoff(target.session_id, "wf_7") is None

    handoff = session_repository.create_handoff(
        "user:42", "wf_7", source.session_id, target.session_id
    )

    assert session_repository.resolve_handoff(target.session_id, "wf_7") == handoff


def test_handoff_rejects_sessions_owned_by_different_users(session_repository):
    source = session_repository.get_or_create("user:42", "telegram", "chat:1")
    target = session_repository.get_or_create("user:99", "cli", "terminal:1")

    with pytest.raises(OwnerMismatchError):
        session_repository.create_handoff(
            "user:42", "wf_7", source.session_id, target.session_id
        )


class PublicTranscriptStore:
    def __init__(self) -> None:
        self.transcripts = {
            "telegram-session": [{"role": "user", "content": "before"}]
        }
        self.loaded_session_ids: list[str] = []
        self.appended: list[tuple[str, dict[str, object], bool]] = []

    @property
    def _entries(self):
        raise AssertionError("adapter must not read private SessionStore state")

    @property
    def _db(self):
        raise AssertionError("adapter must not read private SessionStore state")

    def load_transcript(self, session_id: str) -> list[dict[str, object]]:
        self.loaded_session_ids.append(session_id)
        return self.transcripts.get(session_id, [])

    def append_to_transcript(
        self, session_id: str, message: dict[str, object], skip_db: bool = False
    ) -> None:
        self.appended.append((session_id, dict(message), skip_db))


def test_transcript_adapter_uses_public_api_and_keeps_history_immutable():
    store = PublicTranscriptStore()
    adapter = UpstreamTranscriptAdapter(store, "telegram-session")
    history = adapter.history
    event = AgentEvent(
        event_type="tool_activity",
        principal_id="user:42",
        session_id="cli-session",
        turn_id="turn_7",
        sequence=2,
        workflow_id="wf_7",
        tool_call_id="tool_7",
        data={"text": "checking source", "tool_name": "web_search"},
        occurred_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )

    store.transcripts["telegram-session"][0]["content"] = "changed upstream"
    with pytest.raises(TypeError):
        history[0]["content"] = "mutated"

    adapter.append_user_turn("continue workflow")
    adapter.append_event(event)

    assert history[0]["content"] == "before"
    assert store.loaded_session_ids == ["telegram-session"]
    assert store.appended == [
        (
            "telegram-session",
            {"role": "user", "content": "continue workflow"},
            False,
        ),
        (
            "telegram-session",
            {
                "role": "assistant",
                "content": "checking source",
                "timestamp": "2026-08-22T00:00:00+00:00",
                "event_metadata": {
                    "event_id": event.event_id,
                    "event_type": "tool_activity",
                    "turn_id": "turn_7",
                    "sequence": 2,
                    "workflow_id": "wf_7",
                    "job_id": None,
                    "approval_id": None,
                    "tool_call_id": "tool_7",
                    "data": {"text": "checking source", "tool_name": "web_search"},
                },
            },
            False,
        ),
    ]
