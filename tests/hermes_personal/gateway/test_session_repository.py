import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Barrier

import pytest

from hermes_personal.contracts import AgentEvent, to_primitive
from hermes_personal.identity import IdentityRepository
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
    identity_repository = IdentityRepository(connection)
    owner = identity_repository.create_owner("primary")
    other_owner = identity_repository.create_owner("other")
    try:
        yield repository, owner, other_owner
    finally:
        connection.close()


def test_sessions_are_separate_per_channel(session_repository):
    repository, owner, _ = session_repository
    telegram = repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    web = repository.get_or_create(owner.owner_user_id, "web", "browser:1")

    assert telegram.session_id != web.session_id
    assert telegram.owner_user_id == web.owner_user_id


def test_get_returns_a_session_by_its_public_identifier(session_repository):
    repository, owner, _ = session_repository
    session = repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")

    assert repository.get(session.session_id) == session


def test_workflow_is_visible_only_after_explicit_handoff(session_repository):
    repository, owner, _ = session_repository
    source = repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    target = repository.get_or_create(owner.owner_user_id, "cli", "terminal:1")

    repository.link_workflow(source.session_id, "wf_7")

    assert repository.resolve_handoff(target.session_id, "wf_7") is None

    handoff = repository.create_handoff(
        owner.owner_user_id, "wf_7", source.session_id, target.session_id
    )

    assert repository.resolve_handoff(target.session_id, "wf_7") == handoff


def test_handoff_rejects_sessions_owned_by_different_users(session_repository):
    repository, owner, other_owner = session_repository
    source = repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    target = repository.get_or_create(other_owner.owner_user_id, "cli", "terminal:1")

    with pytest.raises(OwnerMismatchError):
        repository.create_handoff(
            owner.owner_user_id, "wf_7", source.session_id, target.session_id
        )


def test_session_foreign_key_rejects_unknown_owner_and_rolls_back(session_repository):
    repository, _, _ = session_repository

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        with repository._connection:
            repository._connection.execute(
                """
                INSERT INTO conversation_session (
                  session_id, owner_user_id, channel, external_conversation_id,
                  active_workflow_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "orphan-session",
                    "missing-owner",
                    "telegram",
                    "chat:orphan",
                    None,
                    "2026-08-22T00:00:00+00:00",
                    "2026-08-22T00:00:00+00:00",
                ),
            )

    row = repository._connection.execute(
        "SELECT COUNT(*) AS count FROM conversation_session"
    ).fetchone()
    assert row["count"] == 0


@pytest.mark.parametrize("invalid_reference", ["owner", "source", "target"])
def test_handoff_foreign_keys_reject_orphans_and_roll_back(
    session_repository, invalid_reference
):
    repository, owner, _ = session_repository
    source = repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    target = repository.get_or_create(owner.owner_user_id, "cli", "terminal:1")
    owner_user_id = owner.owner_user_id
    source_session_id = source.session_id
    target_session_id = target.session_id
    if invalid_reference == "owner":
        owner_user_id = "missing-owner"
    elif invalid_reference == "source":
        source_session_id = "missing-source"
    else:
        target_session_id = "missing-target"

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        with repository._connection:
            repository._connection.execute(
                """
                INSERT INTO workflow_handoff (
                  handoff_id, owner_user_id, workflow_id, source_session_id,
                  target_session_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"orphan-{invalid_reference}",
                    owner_user_id,
                    "wf_7",
                    source_session_id,
                    target_session_id,
                    "2026-08-22T00:00:00+00:00",
                ),
            )

    row = repository._connection.execute(
        "SELECT COUNT(*) AS count FROM workflow_handoff"
    ).fetchone()
    assert row["count"] == 0


class RacingSessionRepository(SessionRepository):
    def __init__(self, connection, barrier: Barrier) -> None:
        super().__init__(connection)
        self._barrier = barrier

    def _find_by_channel(self, owner_user_id, channel, external_conversation_id):
        session = super()._find_by_channel(
            owner_user_id, channel, external_conversation_id
        )
        if session is None:
            self._barrier.wait(timeout=5)
        return session


def test_get_or_create_is_idempotent_across_two_connections(tmp_path):
    database_path = tmp_path / "race.sqlite"
    owner_connection = connect(database_path)
    owner = IdentityRepository(owner_connection).create_owner("primary")
    owner_connection.close()
    barrier = Barrier(2)

    def get_session():
        connection = connect(database_path)
        repository = RacingSessionRepository(connection, barrier)
        try:
            return repository.get_or_create(owner.owner_user_id, "telegram", "chat:1")
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(get_session)
        second = executor.submit(get_session)
        sessions = [first.result(), second.result()]

    verification_connection = connect(database_path)
    try:
        row = verification_connection.execute(
            "SELECT COUNT(*) AS count FROM conversation_session"
        ).fetchone()
    finally:
        verification_connection.close()

    assert sessions[0].session_id == sessions[1].session_id
    assert row["count"] == 1


class PublicTranscriptStore:
    def __init__(self) -> None:
        self.transcripts = {
            "telegram-session": [
                {
                    "role": "user",
                    "content": "before",
                    "tool_calls": [
                        {"function": {"arguments": {"query": "before"}}}
                    ],
                    "metadata": {"labels": ["important"]},
                }
            ]
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
                "event_metadata": to_primitive(event),
            },
            False,
        ),
    ]
    assert store.appended[1][0] == "telegram-session"
    assert store.appended[1][1]["event_metadata"]["session_id"] == "cli-session"
    assert store.appended[1][1]["event_metadata"]["principal_id"] == "user:42"
    assert store.appended[1][1]["event_metadata"]["schema_version"] == 1


def test_transcript_history_recursively_freezes_nested_containers():
    store = PublicTranscriptStore()
    history = UpstreamTranscriptAdapter(store, "telegram-session").history

    assert history[0]["tool_calls"] == (
        {"function": {"arguments": {"query": "before"}}},
    )
    with pytest.raises(AttributeError):
        history[0]["tool_calls"].append({"function": {}})
    with pytest.raises(TypeError):
        history[0]["tool_calls"][0]["function"]["arguments"]["query"] = "mutated"
    with pytest.raises(TypeError):
        history[0]["metadata"]["labels"][0] = "mutated"

    assert store.transcripts["telegram-session"][0]["tool_calls"] == [
        {"function": {"arguments": {"query": "before"}}}
    ]
