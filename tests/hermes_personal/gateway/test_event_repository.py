from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import IdentityRepository
from hermes_personal.orchestration.event_repository import (
    EventRepository,
    IdempotencyConflict,
    TurnInProgress,
)
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


@pytest.fixture
def repository_environment(tmp_path):
    database_path = tmp_path / "events.sqlite"
    connection = connect(database_path)
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    other_owner = identities.create_owner("other")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    other_session = sessions.get_or_create(
        other_owner.owner_user_id, "telegram", "chat:other"
    )
    repository = EventRepository(connection)
    try:
        yield database_path, connection, repository, owner, session, other_session
    finally:
        connection.close()


def make_request(
    owner_user_id: str,
    session_id: str,
    *,
    idempotency_key: str = "transport:7",
    message: str = "Xin chao",
    turn_id: str = "turn_original",
    occurred_at: datetime = datetime(2026, 8, 22, tzinfo=timezone.utc),
) -> AgentTurnRequest:
    return AgentTurnRequest(
        principal=PrincipalContext(
            actor_id="actor:1",
            owner_user_id=owner_user_id,
            channel="telegram",
            session_id=session_id,
            roles=("owner",),
        ),
        message=message,
        idempotency_key=idempotency_key,
        turn_id=turn_id,
        occurred_at=occurred_at,
    )


def make_event(
    request: AgentTurnRequest,
    sequence: int,
    event_type="text_delta",
    event_id: str | None = None,
):
    return AgentEvent(
        event_type=event_type,
        principal_id=request.principal.owner_user_id,
        session_id=request.session_id,
        turn_id=request.turn_id,
        sequence=sequence,
        data={"text": f"part {sequence}", "nested": {"items": ["one"]}},
        occurred_at=datetime(2026, 8, 22, 1, sequence, tzinfo=timezone.utc),
        event_id=event_id or f"evt_{request.turn_id}_{sequence}",
    )


def test_event_schema_has_execution_event_keys_and_foreign_keys(
    repository_environment,
):
    _, connection, _, _, _, _ = repository_environment

    execution_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(turn_execution)")
    }
    event_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(turn_event)")
    }
    execution_foreign_tables = {
        row["table"]
        for row in connection.execute("PRAGMA foreign_key_list(turn_execution)")
    }
    event_foreign_tables = {
        row["table"] for row in connection.execute("PRAGMA foreign_key_list(turn_event)")
    }

    assert execution_columns >= {
        "owner_user_id",
        "idempotency_key",
        "request_digest",
        "turn_id",
        "session_id",
        "status",
    }
    assert event_columns >= {"turn_id", "sequence", "event_id", "payload_json"}
    assert execution_foreign_tables == {
        "global_user_identity",
        "conversation_session",
    }
    assert event_foreign_tables == {"turn_execution"}


def test_first_claim_persists_canonical_execution(repository_environment):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)

    assert repository.claim(request) is None

    row = connection.execute(
        "SELECT * FROM turn_execution WHERE owner_user_id = ? AND idempotency_key = ?",
        (owner.owner_user_id, request.idempotency_key),
    ).fetchone()
    assert row["turn_id"] == request.turn_id
    assert row["session_id"] == request.session_id
    assert row["status"] == "in_progress"
    assert len(row["request_digest"]) == 64


def test_same_digest_ignores_retry_turn_identity_and_time(repository_environment):
    _, _, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    retry = replace(
        request,
        turn_id="turn_retry",
        occurred_at=request.occurred_at + timedelta(minutes=5),
    )
    repository.claim(request)

    with pytest.raises(TurnInProgress) as raised:
        repository.claim(retry)

    assert raised.value.turn_id == request.turn_id


def test_same_key_with_different_digest_fails_closed(repository_environment):
    _, _, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)

    with pytest.raises(IdempotencyConflict) as raised:
        repository.claim(replace(request, message="Khac noi dung"))

    assert raised.value.idempotency_key == request.idempotency_key


def test_claim_enforces_owner_session_foreign_key_and_rolls_back(
    repository_environment,
):
    _, connection, repository, owner, _, other_session = repository_environment
    request = make_request(owner.owner_user_id, other_session.session_id)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repository.claim(request)

    count = connection.execute(
        "SELECT COUNT(*) AS count FROM turn_execution"
    ).fetchone()["count"]
    assert count == 0


def test_event_requires_claimed_turn_and_failed_insert_rolls_back(
    repository_environment,
):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)

    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY constraint failed"):
        repository.append_event(make_event(request, 0))

    count = connection.execute("SELECT COUNT(*) AS count FROM turn_event").fetchone()[
        "count"
    ]
    assert count == 0


def test_event_sequence_and_event_id_are_unique(repository_environment):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)
    repository.append_event(make_event(request, 0))

    with pytest.raises(sqlite3.IntegrityError):
        repository.append_event(replace(make_event(request, 0), event_id="evt_other"))
    with pytest.raises(sqlite3.IntegrityError):
        repository.append_event(replace(make_event(request, 1), event_id=f"evt_{request.turn_id}_0"))

    rows = connection.execute("SELECT event_id FROM turn_event").fetchall()
    assert [row["event_id"] for row in rows] == [f"evt_{request.turn_id}_0"]


@pytest.mark.parametrize(
    ("event_type", "terminal_status"),
    (("completed", "completed"), ("failed", "failed")),
)
def test_terminal_replay_survives_sqlite_reopen_with_exact_immutable_events(
    repository_environment, event_type, terminal_status
):
    database_path, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    first = make_event(request, 0)
    terminal = make_event(request, 1, event_type)
    repository.claim(request)
    repository.append_event(first)
    repository.append_event(terminal)
    repository.mark_terminal(request.turn_id, terminal_status)
    connection.close()

    reopened = connect(database_path)
    try:
        replay = EventRepository(reopened).claim(
            replace(
                request,
                turn_id="turn_retry",
                occurred_at=request.occurred_at + timedelta(hours=1),
            )
        )
    finally:
        reopened.close()

    assert replay is not None
    assert [event.event_id for event in replay] == [
        f"evt_{request.turn_id}_0",
        f"evt_{request.turn_id}_1",
    ]
    assert [event.sequence for event in replay] == [0, 1]
    assert [event.turn_id for event in replay] == [request.turn_id, request.turn_id]
    assert [event.occurred_at for event in replay] == [
        first.occurred_at,
        terminal.occurred_at,
    ]
    assert replay[1].event_type == event_type
    with pytest.raises(TypeError):
        replay[0].data["nested"]["items"] = ()
    with pytest.raises(AttributeError):
        replay[0].data["nested"]["items"].append("mutated")


def test_owner_event_cursor_is_global_ordered_and_survives_sqlite_reopen(
    repository_environment,
):
    database_path, connection, repository, owner, session, _ = repository_environment
    first_request = make_request(owner.owner_user_id, session.session_id)
    second_request = replace(
        first_request,
        idempotency_key="transport:8",
        turn_id="turn_second",
    )
    repository.claim(first_request)
    repository.claim(second_request)
    repository.append_event(make_event(first_request, 0))
    repository.append_event(make_event(second_request, 0))
    connection.close()

    reopened = connect(database_path)
    try:
        records = EventRepository(reopened).get_event_records_for_owner(
            owner.owner_user_id, after_cursor=0, limit=10
        )
    finally:
        reopened.close()

    assert [cursor for cursor, _ in records] == [1, 2]
    assert [event.turn_id for _, event in records] == ["turn_original", "turn_second"]


def test_concurrent_same_claim_has_one_winner_and_typed_in_progress_duplicate(
    repository_environment,
):
    database_path, _, _, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    barrier = Barrier(2)

    def claim_from_new_connection():
        connection = connect(database_path)
        try:
            barrier.wait(timeout=5)
            try:
                EventRepository(connection).claim(request)
            except TurnInProgress:
                return "in_progress"
            return "claimed"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: claim_from_new_connection(), range(2)))

    assert sorted(results) == ["claimed", "in_progress"]


def test_mark_terminal_rejects_non_terminal_status(repository_environment):
    _, _, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)

    with pytest.raises(ValueError, match="terminal status"):
        repository.mark_terminal(request.turn_id, "in_progress")


def test_mark_terminal_rejects_without_events(repository_environment):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)

    with pytest.raises(RuntimeError, match="cannot mark terminal without a stored terminal event"):
        repository.mark_terminal(request.turn_id, "completed")

    status = connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "in_progress"


def test_mark_terminal_rejects_when_latest_event_is_not_terminal(
    repository_environment,
):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)
    repository.append_event(make_event(request, 0, "text_delta"))

    with pytest.raises(RuntimeError, match="latest stored event does not match terminal status"):
        repository.mark_terminal(request.turn_id, "completed")

    status = connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "in_progress"


@pytest.mark.parametrize(
    ("event_type", "terminal_status"),
    (("completed", "failed"), ("failed", "completed")),
)
def test_mark_terminal_rejects_mismatched_terminal_event_and_status(
    repository_environment, event_type, terminal_status
):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)
    repository.append_event(make_event(request, 0, event_type))

    with pytest.raises(RuntimeError, match="latest stored event does not match terminal status"):
        repository.mark_terminal(request.turn_id, terminal_status)

    status = connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == event_type


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_append_event_rejects_after_turn_is_terminal(repository_environment, status):
    _, connection, repository, owner, session, _ = repository_environment
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)
    repository.append_event(make_event(request, 0, status))
    repository.mark_terminal(request.turn_id, status)

    with pytest.raises(RuntimeError, match="cannot append event to terminal turn"):
        repository.append_event(make_event(request, 1, "text_delta"))

    rows = connection.execute(
        "SELECT sequence, event_id FROM turn_event WHERE turn_id = ?", (request.turn_id,)
    ).fetchall()
    assert len(rows) == 1
    current_status = connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert current_status == status


def test_claim_rejects_in_progress_execution_and_preserves_events(
    repository_environment,
):
    _, connection, repository, owner, session, _ = repository_environment
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    request = make_request(owner.owner_user_id, session.session_id)
    repository.claim(request)
    repository.append_event(make_event(request, 0, "text_delta"))

    connection.execute(
        "UPDATE turn_execution SET updated_at = ? WHERE turn_id = ?",
        (stale_time, request.turn_id),
    )
    connection.commit()

    retry_request = replace(
        request,
        turn_id="turn_retry",
        occurred_at=datetime.now(timezone.utc),
    )
    with pytest.raises(TurnInProgress) as raised:
        repository.claim(retry_request)
    assert raised.value.turn_id == request.turn_id

    events = connection.execute(
        "SELECT * FROM turn_event WHERE turn_id = ?", (request.turn_id,)
    ).fetchall()
    assert len(events) == 1
    assert events[0]["sequence"] == 0


def test_load_session_events_returns_all_terminal_events_in_session(
    repository_environment,
):
    _, _, repository, owner, session, _ = repository_environment
    req1 = make_request(owner.owner_user_id, session.session_id, idempotency_key="key:1", turn_id="turn_1")
    repository.claim(req1)
    repository.append_event(make_event(req1, 0, "text_delta"))
    repository.append_event(make_event(req1, 1, "completed"))

    req2 = make_request(owner.owner_user_id, session.session_id, idempotency_key="key:2", turn_id="turn_2")
    repository.claim(req2)
    repository.append_event(make_event(req2, 0, "completed"))

    session_events = repository.load_session_events(session.session_id)
    assert len(session_events) == 3
    assert [e.turn_id for e in session_events] == ["turn_1", "turn_1", "turn_2"]
    assert [e.event_type for e in session_events] == ["text_delta", "completed", "completed"]
