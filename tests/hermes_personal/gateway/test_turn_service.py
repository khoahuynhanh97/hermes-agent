from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pytest

from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import IdentityRepository
from hermes_personal.orchestration import (
    AgentOutput,
    AuthorizationError,
    HermesTurnService,
    UpstreamAIAgentAdapter,
)
from hermes_personal.orchestration.event_repository import (
    EventRepository,
    IdempotencyConflict,
    TurnInProgress,
)
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


@dataclass
class FakeTranscript:
    events: list[AgentEvent] = field(default_factory=list)
    user_turns: list[str] = field(default_factory=list)
    event_persisted: list[bool] = field(default_factory=list)
    initial_history: list[Mapping[str, Any]] = field(default_factory=list)

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        user_msgs = [{"role": "user", "content": text} for text in self.user_turns]
        return tuple(self.initial_history + user_msgs)

    def append_user_turn(self, text: str) -> None:
        self.user_turns.append(text)

    def append_event(self, event: AgentEvent) -> None:
        self.events.append(event)
        self.event_persisted.append(False)


@dataclass
class FakeTranscriptFactory:
    transcript: FakeTranscript = field(default_factory=FakeTranscript)
    session_ids: list[str] = field(default_factory=list)

    def for_session(self, session_id: str) -> FakeTranscript:
        self.session_ids.append(session_id)
        return self.transcript


@dataclass
class FakeAgent:
    output: list[AgentOutput] = field(default_factory=list)
    failure: Exception | None = None
    calls: list[tuple[AgentTurnRequest, tuple[Mapping[str, Any], ...]]] = field(
        default_factory=list
    )

    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        self.calls.append((request, history))
        yield from self.output
        if self.failure is not None:
            raise self.failure


class StartFailureAgent:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        raise self._error


class SlowIterator:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.finished = threading.Event()
        self.closed = threading.Event()
        self._emitted = False

    def __iter__(self) -> SlowIterator:
        return self

    def __next__(self) -> AgentOutput:
        self.started.set()
        try:
            time.sleep(0.1)
            if self._emitted:
                raise StopIteration
            self._emitted = True
            return AgentOutput("completed", {})
        finally:
            self.finished.set()

    def close(self) -> None:
        if self.started.is_set() and not self.finished.is_set():
            raise RuntimeError("iterator closed while advancing")
        self.closed.set()


class SlowAgent:
    def __init__(self) -> None:
        self.iterator = SlowIterator()

    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        return self.iterator


@dataclass
class PublicAIAgentSpy:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_conversation(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        return {
            "final_response": "upstream response",
            "messages": [],
            "completed": True,
        }


def build_service(identities, sessions, transcript_factory, agent):
    return HermesTurnService(
        identities,
        sessions,
        EventRepository(sessions._connection),
        transcript_factory,
        agent,
    )


@pytest.fixture
def turn_environment(tmp_path):
    connection = connect(tmp_path / "turn-service.sqlite")
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    identities.link(owner.owner_user_id, "telegram", "actor:1")
    identities.link(owner.owner_user_id, "cli", "actor:1")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    transcript_factory = FakeTranscriptFactory()
    agent = FakeAgent()
    service = build_service(identities, sessions, transcript_factory, agent)
    try:
        yield service, identities, sessions, owner, session, transcript_factory, agent
    finally:
        connection.close()


@pytest.fixture
def request_factory(turn_environment):
    _, _, _, owner, session, _, _ = turn_environment

    def create(
        *,
        owner_user_id: str | None = None,
        channel: str = "telegram",
        session_id: str | None = None,
        workflow_id: str | None = None,
    ) -> AgentTurnRequest:
        return AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="actor:1",
                owner_user_id=owner_user_id or owner.owner_user_id,
                channel=channel,  # type: ignore[arg-type]
                session_id=session_id or session.session_id,
            ),
            message="Xin chao",
            workflow_id=workflow_id,
        )

    return create


@pytest.mark.asyncio
async def test_turn_rejects_principal_session_owner_mismatch(
    turn_environment, request_factory
):
    service, _, _, _, _, _, agent = turn_environment

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request_factory(owner_user_id="user:other"))]

    assert agent.calls == []
    assert (
        turn_environment[2]._connection.execute(
            "SELECT COUNT(*) AS count FROM turn_execution"
        ).fetchone()["count"]
        == 0
    )


@pytest.mark.asyncio
async def test_turn_rejects_principal_session_channel_mismatch(
    turn_environment, request_factory
):
    service, _, _, _, _, _, agent = turn_environment

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request_factory(channel="cli"))]

    assert agent.calls == []


@pytest.mark.asyncio
async def test_turn_allows_workflow_handoff_owned_by_principal(
    turn_environment, request_factory
):
    service, _, sessions, owner, source, _, agent = turn_environment
    target = sessions.get_or_create(owner.owner_user_id, "cli", "terminal:1")
    sessions.create_handoff(owner.owner_user_id, "wf_7", source.session_id, target.session_id)
    agent.output = [AgentOutput("completed", {})]

    events = [
        event
        async for event in service.handle(
            request_factory(session_id=target.session_id, channel="cli", workflow_id="wf_7")
        )
    ]

    assert [event.event_type for event in events] == ["completed"]
    assert agent.calls[0][0].workflow_id == "wf_7"


@pytest.mark.asyncio
async def test_turn_rejects_workflow_without_owned_handoff(
    turn_environment, request_factory
):
    service, _, sessions, owner, source, _, agent = turn_environment
    target = sessions.get_or_create(owner.owner_user_id, "cli", "terminal:1")
    sessions.create_handoff(owner.owner_user_id, "wf_7", source.session_id, target.session_id)

    with pytest.raises(AuthorizationError):
        [
            event
            async for event in service.handle(
                request_factory(session_id=target.session_id, channel="cli", workflow_id="wf_8")
            )
        ]

    assert agent.calls == []
    assert (
        sessions._connection.execute(
            "SELECT COUNT(*) AS count FROM turn_execution"
        ).fetchone()["count"]
        == 0
    )


@pytest.mark.asyncio
async def test_turn_persists_each_event_before_yield(
    turn_environment, request_factory
):
    service, _, sessions, owner, session, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("text_delta", {"text": "Xin chao"})]

    async for event in service.handle(request_factory()):
        assert event == transcript_factory.transcript.events[event.sequence]
        stored = sessions._connection.execute(
            "SELECT event_id FROM turn_event WHERE turn_id = ? AND sequence = ?",
            (event.turn_id, event.sequence),
        ).fetchone()
        assert stored["event_id"] == event.event_id
        transcript_factory.transcript.event_persisted[event.sequence] = True

    assert transcript_factory.session_ids == [session.session_id]
    assert all(transcript_factory.transcript.event_persisted)
    assert transcript_factory.transcript.user_turns == ["Xin chao"]
    assert agent.calls[0][1] == ()
    assert transcript_factory.transcript.events[0].principal_id == owner.owner_user_id


@pytest.mark.asyncio
async def test_terminal_event_is_marked_before_yield_and_stops_stream(
    turn_environment, request_factory
):
    service, _, sessions, _, _, transcript_factory, agent = turn_environment
    agent.output = [
        AgentOutput("completed", {"text": "done"}),
        AgentOutput("warning", {"text": "must not follow terminal"}),
    ]

    events = []
    async for event in service.handle(request_factory()):
        events.append(event)
        status = sessions._connection.execute(
            "SELECT status FROM turn_execution WHERE turn_id = ?", (event.turn_id,)
        ).fetchone()["status"]
        assert status == "completed"

    assert [event.event_type for event in events] == ["completed"]
    assert transcript_factory.transcript.events == events


@pytest.mark.asyncio
async def test_terminal_duplicate_replays_exact_events_without_transcript_or_agent_call(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.output = [
        AgentOutput("text_delta", {"text": "Xin"}),
        AgentOutput("completed", {"text": "Xin chao"}),
    ]
    request = request_factory()

    original = [event async for event in service.handle(request)]
    replay = [
        event
        async for event in service.handle(
            replace(
                request,
                turn_id="turn_retry",
                occurred_at=request.occurred_at + timedelta(minutes=1),
            )
        )
    ]

    assert replay == original
    assert [event.event_id for event in replay] == [
        event.event_id for event in original
    ]
    assert len(agent.calls) == 1
    assert transcript_factory.session_ids == [request.session_id]
    assert transcript_factory.transcript.user_turns == [request.message]
    assert transcript_factory.transcript.events == original


@pytest.mark.asyncio
async def test_same_idempotency_key_with_changed_request_fails_before_side_effects(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("completed", {})]
    request = request_factory()
    [event async for event in service.handle(request)]

    with pytest.raises(IdempotencyConflict):
        [event async for event in service.handle(replace(request, message="changed"))]

    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_in_progress_duplicate_is_typed_and_does_not_call_agent_again(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("text_delta", {"text": "partial"})]
    request = request_factory()
    [event async for event in service.handle(request)]

    with pytest.raises(TurnInProgress):
        [
            event
            async for event in service.handle(
                replace(request, turn_id="turn_concurrent")
            )
        ]

    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_failed_duplicate_replays_stored_failure_without_second_agent_call(
    turn_environment, request_factory
):
    service, _, sessions, _, _, transcript_factory, agent = turn_environment
    agent.failure = RuntimeError("agent unavailable")
    request = request_factory()

    original = [event async for event in service.handle(request)]
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"
    assert replay == original
    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_passes_prior_history_once_and_current_message_only_as_user_input(
    turn_environment, request_factory
):
    _, identities, sessions, owner, _, transcript_factory, _ = turn_environment
    transcript_factory.transcript.user_turns.append("prior turn")
    upstream = PublicAIAgentSpy()
    service = build_service(
        identities, sessions, transcript_factory, UpstreamAIAgentAdapter(upstream)
    )

    events = [event async for event in service.handle(request_factory())]

    assert upstream.calls[0]["conversation_history"] == [
        {"role": "user", "content": "prior turn"}
    ]
    assert upstream.calls[0]["user_message"] == "Xin chao"
    assert transcript_factory.transcript.user_turns == ["prior turn", "Xin chao"]
    assert [event.event_type for event in events] == ["text_delta", "completed"]


@pytest.mark.asyncio
async def test_turn_emits_exactly_one_persisted_failed_event_for_agent_failure(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.failure = RuntimeError("agent unavailable")

    events = [event async for event in service.handle(request_factory())]

    assert [event.event_type for event in events] == ["failed"]
    assert events == transcript_factory.transcript.events


@pytest.mark.asyncio
async def test_turn_streams_monotonic_events_from_one_agent(
    turn_environment, request_factory
):
    service, _, _, _, _, _, agent = turn_environment
    agent.output = [AgentOutput("text_delta", {"text": "Xin chao"}), AgentOutput("completed", {})]

    events = [event async for event in service.handle(request_factory())]

    assert [event.sequence for event in events] == [0, 1]
    assert all(event.event_id.startswith("evt_") for event in events)
    assert agent.calls[0][0].workflow_id is None


def test_agent_output_copies_and_recursively_freezes_data():
    source = {"text": "before", "nested": {"items": ["one"]}}

    output = AgentOutput("text_delta", source)
    source["text"] = "after"
    source["nested"]["items"].append("two")

    assert output.data == {"text": "before", "nested": {"items": ("one",)}}
    with pytest.raises(TypeError):
        output.data["text"] = "mutated"
    with pytest.raises(TypeError):
        output.data["nested"]["items"] = ()
    with pytest.raises(AttributeError):
        output.data["nested"]["items"].append("mutated")


@pytest.mark.asyncio
@dataclass
class FailingTranscript(FakeTranscript):
    fail_on_event_types: set[str] = field(default_factory=lambda: {"completed", "failed"})

    def append_event(self, event: AgentEvent) -> None:
        if event.event_type in self.fail_on_event_types:
            raise RuntimeError("transcript disk full")
        super().append_event(event)


@pytest.mark.asyncio
async def test_turn_terminal_status_is_committed_atomically_even_if_transcript_append_fails(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, _, _ = turn_environment
    failing_transcript = FailingTranscript()
    agent = FakeAgent(output=[AgentOutput("completed", {"text": "done"})])
    service = build_service(
        identities,
        sessions,
        FakeTranscriptFactory(failing_transcript),
        agent,
    )
    request = request_factory()

    events = [event async for event in service.handle(request)]
    assert len(events) == 1
    assert events[0].event_type == "completed"

    # Execution status in SQLite was committed as completed atomically
    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "completed"

    stored_events = sessions._connection.execute(
        "SELECT event_id, sequence FROM turn_event WHERE turn_id = ?", (request.turn_id,)
    ).fetchall()
    assert len(stored_events) == 1

    # Retry replays exact stored events without second agent call or duplicate user turns
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert replay == events
    assert len(agent.calls) == 1
    assert failing_transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_rejects_agent_workflow_when_request_has_no_workflow(
    turn_environment, request_factory
):
    service, _, sessions, _, _, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("workflow_state", {}, workflow_id="wf_7")]
    request = request_factory()

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request)]

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"
    assert len(transcript_factory.transcript.events) == 1
    assert transcript_factory.transcript.events[0].event_type == "failed"

    # Replay returns stored failed event without second agent call
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert [e.event_type for e in replay] == ["failed"]
    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_rejects_agent_workflow_that_differs_from_authorized_request(
    turn_environment, request_factory
):
    service, _, sessions, _, session, transcript_factory, agent = turn_environment
    sessions.link_workflow(session.session_id, "wf_7")
    agent.output = [AgentOutput("workflow_state", {}, workflow_id="wf_other")]
    request = request_factory(workflow_id="wf_7")

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request)]

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"
    assert len(transcript_factory.transcript.events) == 1
    assert transcript_factory.transcript.events[0].event_type == "failed"

    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert [e.event_type for e in replay] == ["failed"]
    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_preserves_optional_correlation_for_authorized_workflow(
    turn_environment, request_factory
):
    service, _, sessions, _, session, _, agent = turn_environment
    sessions.link_workflow(session.session_id, "wf_7")
    agent.output = [
        AgentOutput(
            "workflow_state",
            {"state": "running"},
            workflow_id="wf_7",
            job_id="job_7",
            approval_id="approval_7",
            tool_call_id="tool_7",
        )
    ]

    events = [
        event async for event in service.handle(request_factory(workflow_id="wf_7"))
    ]

    assert (
        events[0].workflow_id,
        events[0].job_id,
        events[0].approval_id,
        events[0].tool_call_id,
    ) == ("wf_7", "job_7", "approval_7", "tool_7")


@pytest.mark.asyncio
async def test_turn_propagates_agent_start_authorization_error_with_persisted_failed_state(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    start_failure_agent = StartFailureAgent(AuthorizationError("agent start denied"))
    service = build_service(
        identities,
        sessions,
        FakeTranscriptFactory(transcript_factory.transcript),
        start_failure_agent,
    )
    request = request_factory()

    with pytest.raises(AuthorizationError, match="agent start denied"):
        [event async for event in service.handle(request)]

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"
    assert len(transcript_factory.transcript.events) == 1
    assert transcript_factory.transcript.events[0].event_type == "failed"

    # Retry returns replayed failed event without second agent call
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert [e.event_type for e in replay] == ["failed"]
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_propagates_agent_advance_authorization_error_with_persisted_failed_state(
    turn_environment, request_factory
):
    service, _, sessions, _, _, transcript_factory, agent = turn_environment
    agent.failure = AuthorizationError("agent advance denied")
    request = request_factory()

    with pytest.raises(AuthorizationError, match="agent advance denied"):
        [event async for event in service.handle(request)]

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"
    assert len(transcript_factory.transcript.events) == 1
    assert transcript_factory.transcript.events[0].event_type == "failed"

    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert [e.event_type for e in replay] == ["failed"]
    assert len(agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]



@pytest.mark.asyncio
async def test_turn_allows_concurrent_progress_while_slow_iterator_advances(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    slow_agent = SlowAgent()
    service = build_service(identities, sessions, transcript_factory, slow_agent)
    progressed = asyncio.Event()

    async def mark_progress() -> None:
        await asyncio.sleep(0.01)
        progressed.set()

    marker = asyncio.create_task(mark_progress())
    stream = service.handle(request_factory())
    event = await anext(stream)

    assert progressed.is_set()
    assert event.event_type == "completed"
    await marker
    await stream.aclose()
    assert await asyncio.to_thread(slow_agent.iterator.closed.wait, 0.5)


@pytest.mark.asyncio
async def test_turn_closes_slow_iterator_when_consumer_is_cancelled(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    slow_agent = SlowAgent()
    service = build_service(identities, sessions, transcript_factory, slow_agent)
    request = request_factory()
    stream = service.handle(request)
    pending = asyncio.create_task(anext(stream))

    assert await asyncio.to_thread(slow_agent.iterator.started.wait, 0.5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    assert await asyncio.to_thread(slow_agent.iterator.closed.wait, 0.5)

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"

    # Subsequent request with same idempotency key replays stored failed cancellation event
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert len(replay) == 1
    assert replay[0].event_type == "failed"
    assert replay[0].data.get("cancelled") is True


class ControlledBlockingAgent:
    def __init__(self) -> None:
        self.started = threading.Event()
        self.unblock = threading.Event()
        self.calls: list[tuple[AgentTurnRequest, tuple[Mapping[str, Any], ...]]] = []

    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        self.calls.append((request, history))
        self.started.set()
        yield AgentOutput("text_delta", {"text": "part1"})
        self.unblock.wait(timeout=5.0)
        yield AgentOutput("completed", {"text": "done"})


@pytest.mark.asyncio
async def test_live_blocked_worker_with_stale_timestamp_rejects_retry_without_split_brain(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    blocking_agent = ControlledBlockingAgent()
    service = build_service(identities, sessions, transcript_factory, blocking_agent)
    request = request_factory()

    stream1 = service.handle(request)
    first_event = await anext(stream1)
    assert first_event.event_type == "text_delta"
    assert blocking_agent.started.is_set()

    # Force updated_at timestamp in SQLite to be stale (> 60 seconds ago) while worker is still alive
    stale_time = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
    sessions._connection.execute(
        "UPDATE turn_execution SET updated_at = ? WHERE turn_id = ?",
        (stale_time, request.turn_id),
    )
    sessions._connection.commit()

    # A retry attempt during active execution MUST raise TurnInProgress (no split-brain takeover)
    retry_request = replace(
        request,
        turn_id="turn_concurrent_retry",
        occurred_at=datetime.now(timezone.utc),
    )
    with pytest.raises(TurnInProgress) as raised:
        [event async for event in service.handle(retry_request)]
    assert raised.value.turn_id == request.turn_id

    # Verify agent was called exactly once, transcript was appended once, partial events preserved
    assert len(blocking_agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]
    stored_events_in_progress = sessions._connection.execute(
        "SELECT sequence, event_id FROM turn_event WHERE turn_id = ?",
        (request.turn_id,),
    ).fetchall()
    assert len(stored_events_in_progress) == 1
    assert stored_events_in_progress[0]["event_id"] == first_event.event_id

    # Unblock original worker and let it finish cleanly
    blocking_agent.unblock.set()
    second_event = await anext(stream1)
    assert second_event.event_type == "completed"

    with pytest.raises(StopAsyncIteration):
        await anext(stream1)

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "completed"

    # Terminal replay returns stored events without second agent call or transcript append
    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_replay"))
    ]
    assert replay == [first_event, second_event]
    assert len(blocking_agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_closes_stream_before_first_event_persists_failed_cancellation(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    slow_agent = SlowAgent()
    service = build_service(identities, sessions, transcript_factory, slow_agent)
    request = request_factory()
    stream = service.handle(request)

    # Start stream and wait until worker is started, then cancel task before receiving first event
    task = asyncio.create_task(anext(stream))
    assert await asyncio.to_thread(slow_agent.iterator.started.wait, 0.5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    await stream.aclose()
    assert await asyncio.to_thread(slow_agent.iterator.closed.wait, 0.5)

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"

    events = sessions._connection.execute(
        "SELECT sequence, payload_json FROM turn_event WHERE turn_id = ?",
        (request.turn_id,),
    ).fetchall()
    assert len(events) == 1
    assert events[0]["sequence"] == 0

    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert len(replay) == 1
    assert replay[0].event_type == "failed"
    assert replay[0].sequence == 0
    assert replay[0].data.get("cancelled") is True


@pytest.mark.asyncio
async def test_turn_closes_stream_after_one_delta_persists_failed_cancellation_with_contiguous_sequence(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    blocking_agent = ControlledBlockingAgent()
    service = build_service(identities, sessions, transcript_factory, blocking_agent)
    request = request_factory()
    stream = service.handle(request)

    first_event = await anext(stream)
    assert first_event.event_type == "text_delta"
    assert first_event.sequence == 0

    # Close stream after reading one delta
    await stream.aclose()

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "failed"

    events = sessions._connection.execute(
        "SELECT sequence, payload_json FROM turn_event WHERE turn_id = ? ORDER BY sequence",
        (request.turn_id,),
    ).fetchall()
    assert len(events) == 2
    assert [e["sequence"] for e in events] == [0, 1]

    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert len(replay) == 2
    assert replay[0].event_type == "text_delta"
    assert replay[0].sequence == 0
    assert replay[1].event_type == "failed"
    assert replay[1].sequence == 1
    assert replay[1].data.get("cancelled") is True
    assert len(blocking_agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]


@pytest.mark.asyncio
async def test_turn_closes_stream_after_terminal_completion_leaves_completed_status(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    blocking_agent = ControlledBlockingAgent()
    service = build_service(identities, sessions, transcript_factory, blocking_agent)
    request = request_factory()
    stream = service.handle(request)

    first_event = await anext(stream)
    blocking_agent.unblock.set()
    second_event = await anext(stream)
    assert second_event.event_type == "completed"

    # Close stream after consuming terminal event
    await stream.aclose()

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "completed"

    events = sessions._connection.execute(
        "SELECT sequence, payload_json FROM turn_event WHERE turn_id = ? ORDER BY sequence",
        (request.turn_id,),
    ).fetchall()
    assert len(events) == 2
    assert [e["sequence"] for e in events] == [0, 1]

    replay = [
        event
        async for event in service.handle(replace(request, turn_id="turn_retry"))
    ]
    assert replay == [first_event, second_event]
    assert len(blocking_agent.calls) == 1


@pytest.mark.asyncio
async def test_canonical_history_preserves_chronological_order_across_multiple_turns_with_projection_failures(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, _, _ = turn_environment
    failing_transcript = FailingTranscript(fail_on_event_types={"completed"})
    agent = FakeAgent()
    service = build_service(
        identities,
        sessions,
        FakeTranscriptFactory(failing_transcript),
        agent,
    )

    # Turn 1: projection fails on completed event
    agent.output = [AgentOutput("completed", {"text": "assistant1"})]
    req1 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user1",
        turn_id="turn_1",
        idempotency_key="key:1",
    )
    [e async for e in service.handle(req1)]

    # Turn 2: projection succeeds
    failing_transcript.fail_on_event_types = set()
    agent.output = [AgentOutput("completed", {"text": "assistant2"})]
    req2 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user2",
        turn_id="turn_2",
        idempotency_key="key:2",
    )
    [e async for e in service.handle(req2)]

    # Turn 3: check history passed to agent
    agent.output = [AgentOutput("completed", {"text": "assistant3"})]
    req3 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user3",
        turn_id="turn_3",
        idempotency_key="key:3",
    )
    [e async for e in service.handle(req3)]

    turn3_history = agent.calls[2][1]
    assert turn3_history == (
        {"role": "user", "content": "user1"},
        {"role": "assistant", "content": "assistant1"},
        {"role": "user", "content": "user2"},
        {"role": "assistant", "content": "assistant2"},
    )


@pytest.mark.asyncio
async def test_canonical_history_does_not_collapse_identical_assistant_replies_across_turns(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    agent = FakeAgent()
    service = build_service(identities, sessions, transcript_factory, agent)

    # Turn 1: outputs "Xin chao"
    agent.output = [AgentOutput("completed", {"text": "Xin chao"})]
    req1 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user1",
        turn_id="turn_1",
        idempotency_key="key:1",
    )
    [e async for e in service.handle(req1)]

    # Turn 2: outputs "Xin chao" (identical response text)
    agent.output = [AgentOutput("completed", {"text": "Xin chao"})]
    req2 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user2",
        turn_id="turn_2",
        idempotency_key="key:2",
    )
    [e async for e in service.handle(req2)]

    # Turn 3: check history passed to agent
    agent.output = [AgentOutput("completed", {"text": "reply3"})]
    req3 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="user3",
        turn_id="turn_3",
        idempotency_key="key:3",
    )
    [e async for e in service.handle(req3)]

    turn3_history = agent.calls[2][1]
    assert turn3_history == (
        {"role": "user", "content": "user1"},
        {"role": "assistant", "content": "Xin chao"},
        {"role": "user", "content": "user2"},
        {"role": "assistant", "content": "Xin chao"},
    )


@pytest.mark.asyncio
async def test_canonical_history_survives_sqlite_restart(tmp_path):
    db_path = tmp_path / "restart-test.sqlite"
    connection = connect(db_path)
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    identities.link(owner.owner_user_id, "telegram", "actor:1")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    transcript_factory = FakeTranscriptFactory()
    agent = FakeAgent()
    service = build_service(identities, sessions, transcript_factory, agent)

    def make_req(msg: str, turn_id: str, key: str) -> AgentTurnRequest:
        return AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="actor:1",
                owner_user_id=owner.owner_user_id,
                channel="telegram",  # type: ignore[arg-type]
                session_id=session.session_id,
            ),
            turn_id=turn_id,
            idempotency_key=key,
            message=msg,
        )

    # Turn 1
    agent.output = [AgentOutput("completed", {"text": "reply1"})]
    [e async for e in service.handle(make_req("user1", "turn_1", "key:1"))]

    # Turn 2
    agent.output = [AgentOutput("completed", {"text": "reply2"})]
    [e async for e in service.handle(make_req("user2", "turn_2", "key:2"))]
    connection.close()

    # Simulate restart by reconnecting to the database
    reopened = connect(db_path)
    try:
        reopened_identities = IdentityRepository(reopened)
        reopened_sessions = SessionRepository(reopened)
        reopened_events = EventRepository(reopened)
        reopened_agent = FakeAgent()
        reopened_service = HermesTurnService(
            reopened_identities,
            reopened_sessions,
            reopened_events,
            transcript_factory,
            reopened_agent,
        )

        reopened_agent.output = [AgentOutput("completed", {"text": "reply3"})]
        [e async for e in reopened_service.handle(make_req("user3", "turn_3", "key:3"))]

        turn3_history = reopened_agent.calls[0][1]
        assert turn3_history == (
            {"role": "user", "content": "user1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "user2"},
            {"role": "assistant", "content": "reply2"},
        )
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_database_migration_from_legacy_schema_without_user_message_column(tmp_path):
    db_path = tmp_path / "legacy-schema.sqlite"
    raw_conn = connect_raw = sqlite3.connect(db_path)
    connect_raw.row_factory = sqlite3.Row
    connect_raw.execute("PRAGMA foreign_keys = ON")
    connect_raw.executescript(
        """
        CREATE TABLE global_user_identity (
          owner_user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE channel_identity (
          channel TEXT NOT NULL, external_subject TEXT NOT NULL,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id), created_at TEXT NOT NULL,
          PRIMARY KEY (channel, external_subject)
        );
        CREATE TABLE conversation_session (
          session_id TEXT PRIMARY KEY,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          channel TEXT NOT NULL, external_conversation_id TEXT NOT NULL, active_workflow_id TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner_user_id, channel, external_conversation_id)
        );
        CREATE TABLE turn_execution (
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, turn_id TEXT NOT NULL UNIQUE,
          session_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY (owner_user_id, idempotency_key)
        );
        CREATE TABLE turn_event (
          turn_id TEXT NOT NULL REFERENCES turn_execution(turn_id),
          sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
          PRIMARY KEY (turn_id, sequence)
        );
        """
    )
    # Populate legacy records
    now = datetime.now(timezone.utc).isoformat()
    connect_raw.execute("INSERT INTO global_user_identity VALUES ('usr_1', 'Legacy User', ?)", (now,))
    connect_raw.execute("INSERT INTO channel_identity VALUES ('telegram', 'act_1', 'usr_1', ?)", (now,))
    connect_raw.execute("INSERT INTO conversation_session VALUES ('sess_1', 'usr_1', 'telegram', 'chat_1', NULL, ?, ?)", (now, now))
    connect_raw.execute("INSERT INTO turn_execution VALUES ('usr_1', 'key_old', 'digest', 'turn_old', 'sess_1', 'completed', ?, ?)", (now, now))
    connect_raw.execute(
        "INSERT INTO turn_event VALUES ('turn_old', 0, 'evt_old', ?)",
        (json.dumps({
            "event_type": "completed", "principal_id": "act_1", "session_id": "sess_1",
            "turn_id": "turn_old", "sequence": 0, "schema_version": 1, "data": {"text": "Old assistant reply"},
            "workflow_id": None, "job_id": None, "approval_id": None, "tool_call_id": None,
            "occurred_at": now, "event_id": "evt_old"
        }),)
    )
    connect_raw.commit()
    connect_raw.close()

    # Now open with current connection factory (triggers migration)
    conn = connect(db_path)
    try:
        columns = [r["name"] for r in conn.execute("PRAGMA table_info(turn_execution)").fetchall()]
        assert "user_message" in columns

        identities = IdentityRepository(conn)
        sessions = SessionRepository(conn)
        events = EventRepository(conn)
        agent = FakeAgent()
        transcript_factory = FakeTranscriptFactory()
        transcript_factory.transcript.user_turns = ["Old user turn"]
        service = HermesTurnService(identities, sessions, events, transcript_factory, agent)

        req = AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="act_1", owner_user_id="usr_1", channel="telegram", session_id="sess_1"  # type: ignore[arg-type]
            ),
            turn_id="turn_new", idempotency_key="key_new", message="New question"
        )
        agent.output = [AgentOutput("completed", {"text": "New reply"})]

        # Executing new turn MUST NOT fail with missing column error
        results = [e async for e in service.handle(req)]
        assert len(results) == 1
        assert results[0].event_type == "completed"

        history = agent.calls[0][1]
        assert history == (
            {"role": "user", "content": "Old user turn"},
            {"role": "assistant", "content": "Old assistant reply"},
        )
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_canonical_history_preserves_tool_calls_and_results_without_duplicates(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    agent = FakeAgent()
    service = build_service(identities, sessions, transcript_factory, agent)

    # Turn 1 emits tool_call and tool_result
    tool_call_dict = {"id": "call_42", "type": "function", "function": {"name": "search", "arguments": "{}"}}
    tool_result_msg = {"role": "tool", "tool_call_id": "call_42", "content": "found result"}
    agent.output = [
        AgentOutput("tool_activity", {"kind": "tool_call", "tool_call": tool_call_dict}, tool_call_id="call_42"),
        AgentOutput("tool_activity", {"kind": "tool_result", "message": tool_result_msg}, tool_call_id="call_42"),
        AgentOutput("completed", {"text": "Search complete"}),
    ]

    req1 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="Search query",
        turn_id="turn_1",
        idempotency_key="key:1",
    )
    [e async for e in service.handle(req1)]

    # Turn 2
    agent.output = [AgentOutput("completed", {"text": "Follow up answer"})]
    req2 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="Follow up question",
        turn_id="turn_2",
        idempotency_key="key:2",
    )
    [e async for e in service.handle(req2)]

    turn2_history = agent.calls[1][1]
    assert len(turn2_history) == 4
    assert turn2_history[0] == {"role": "user", "content": "Search query"}
    assert turn2_history[1] == {
        "role": "assistant",
        "content": None,
        "tool_calls": (tool_call_dict,),
    }
    assert turn2_history[2] == tool_result_msg
    assert turn2_history[3] == {"role": "assistant", "content": "Search complete"}

    # Test upstream adapter _new_tool_outputs duplicate suppression using reconstructed history
    from hermes_personal.orchestration.upstream_agent import _new_tool_outputs
    result_messages = [
        {"role": "assistant", "tool_calls": [tool_call_dict]},
        tool_result_msg,
    ]
    suppressed_outputs = list(_new_tool_outputs(result_messages, turn2_history, None))
    assert len(suppressed_outputs) == 0


@pytest.mark.asyncio
async def test_system_prompt_and_legacy_transcript_retention(
    turn_environment, request_factory
):
    _, identities, sessions, _, session, transcript_factory, _ = turn_environment
    transcript_factory.transcript.initial_history = [
        {"role": "system", "content": "You are Hermes Assistant"},
    ]
    agent = FakeAgent()
    service = build_service(identities, sessions, transcript_factory, agent)

    agent.output = [AgentOutput("completed", {"text": "Reply 1"})]
    req1 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="Hello",
        turn_id="turn_1",
        idempotency_key="key:1",
    )
    [e async for e in service.handle(req1)]

    turn1_history = agent.calls[0][1]
    assert len(turn1_history) == 1
    assert turn1_history[0] == {"role": "system", "content": "You are Hermes Assistant"}

    # Turn 2
    agent.output = [AgentOutput("completed", {"text": "Reply 2"})]
    req2 = replace(
        request_factory(channel="telegram", session_id=session.session_id),
        message="Follow up",
        turn_id="turn_2",
        idempotency_key="key:2",
    )
    [e async for e in service.handle(req2)]

    turn2_history = agent.calls[1][1]
    assert len(turn2_history) == 3
    assert turn2_history[0] == {"role": "system", "content": "You are Hermes Assistant"}
    assert turn2_history[1] == {"role": "user", "content": "Hello"}
    assert turn2_history[2] == {"role": "assistant", "content": "Reply 1"}


class FakeUpstreamAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_conversation(
        self,
        *,
        user_message: Any,
        conversation_history: list[Mapping[str, Any]],
        task_id: str,
        stream_callback: Callable[[str | None], None],
        persist_user_message: Any,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "user_message": user_message,
                "history": conversation_history,
                "task_id": task_id,
            }
        )
        # Stream text delta first
        stream_callback("Searching...")
        tool_call_dict = {
            "id": "call_1",
            "type": "function",
            "function": {"name": "search", "arguments": "{}"},
        }
        tool_result_msg = {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "result_text",
        }
        return {
            "completed": True,
            "failed": False,
            "interrupted": False,
            "final_response": "done",
            "messages": [
                {"role": "user", "content": user_message},
                {
                    "role": "assistant",
                    "content": "Searching...",
                    "tool_calls": [tool_call_dict],
                },
                tool_result_msg,
                {"role": "assistant", "content": "done"},
            ],
        }


@pytest.mark.asyncio
async def test_real_upstream_streamed_tool_turn_reconstruction_and_deduplication(
    tmp_path,
):
    db_path = tmp_path / "streamed-tool.sqlite"
    connection = connect(db_path)
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    events = EventRepository(connection)
    owner = identities.create_owner("primary")
    identities.link(owner.owner_user_id, "telegram", "actor:1")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    transcript_factory = FakeTranscriptFactory()

    upstream_agent = FakeUpstreamAgent()
    adapter = UpstreamAIAgentAdapter(upstream_agent)
    service = HermesTurnService(
        identities, sessions, events, transcript_factory, adapter
    )

    def make_req(msg: str, turn_id: str, key: str) -> AgentTurnRequest:
        return AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="actor:1",
                owner_user_id=owner.owner_user_id,
                channel="telegram",  # type: ignore[arg-type]
                session_id=session.session_id,
            ),
            turn_id=turn_id,
            idempotency_key=key,
            message=msg,
        )

    # Turn 1
    events1 = [
        e async for e in service.handle(make_req("Search query", "turn_1", "key:1"))
    ]
    # Assert events emitted in Turn 1 include text_delta, tool_activity call, tool_activity result, completed
    event_types1 = [e.event_type for e in events1]
    assert event_types1 == ["text_delta", "tool_activity", "tool_activity", "text_delta", "completed"]

    # Turn 2
    events2 = [
        e async for e in service.handle(make_req("Follow up query", "turn_2", "key:2"))
    ]

    # Inspect history received by upstream agent in Turn 2
    turn2_history = upstream_agent.calls[1]["history"]
    assert len(turn2_history) == 4
    assert turn2_history[0] == {"role": "user", "content": "Search query"}
    tool_call_dict = {
        "id": "call_1",
        "type": "function",
        "function": {"name": "search", "arguments": "{}"},
    }
    assert turn2_history[1]["role"] == "assistant"
    assert turn2_history[1]["content"] == "Searching..."
    assert turn2_history[1]["tool_calls"] == (tool_call_dict,)
    assert turn2_history[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "result_text",
    }
    assert turn2_history[3] == {"role": "assistant", "content": "done"}

    # Verify zero duplicate tool_activity events yielded in Turn 2 for call_1
    turn2_tool_events = [e for e in events2 if e.event_type == "tool_activity"]
    assert len(turn2_tool_events) == 0

    connection.close()

    # Restart database connection with an empty transcript adapter
    reopened = connect(db_path)
    try:
        reopened_identities = IdentityRepository(reopened)
        reopened_sessions = SessionRepository(reopened)
        reopened_events = EventRepository(reopened)
        empty_transcript_factory = FakeTranscriptFactory()
        reopened_upstream_agent = FakeUpstreamAgent()
        reopened_adapter = UpstreamAIAgentAdapter(reopened_upstream_agent)
        reopened_service = HermesTurnService(
            reopened_identities,
            reopened_sessions,
            reopened_events,
            empty_transcript_factory,
            reopened_adapter,
        )

        [
            e
            async for e in reopened_service.handle(
                make_req("Turn 3 query", "turn_3", "key:3")
            )
        ]

        turn3_history = reopened_upstream_agent.calls[0]["history"]
        assert len(turn3_history) == 8  # 4 from Turn 1 + 4 from Turn 2
        assert turn3_history[0] == {"role": "user", "content": "Search query"}
        assert turn3_history[3] == {"role": "assistant", "content": "done"}
        assert turn3_history[4] == {"role": "user", "content": "Follow up query"}
        assert turn3_history[7] == {"role": "assistant", "content": "done"}
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_legacy_migration_restart_without_transcript_and_repeated_text(tmp_path):
    db_path = tmp_path / "legacy-repeat.sqlite"
    raw_conn = sqlite3.connect(db_path)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA foreign_keys = ON")
    raw_conn.executescript(
        """
        CREATE TABLE global_user_identity (
          owner_user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE channel_identity (
          channel TEXT NOT NULL, external_subject TEXT NOT NULL,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id), created_at TEXT NOT NULL,
          PRIMARY KEY (channel, external_subject)
        );
        CREATE TABLE conversation_session (
          session_id TEXT PRIMARY KEY,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          channel TEXT NOT NULL, external_conversation_id TEXT NOT NULL, active_workflow_id TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner_user_id, channel, external_conversation_id)
        );
        CREATE TABLE turn_execution (
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, turn_id TEXT NOT NULL UNIQUE,
          session_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY (owner_user_id, idempotency_key)
        );
        CREATE TABLE turn_event (
          turn_id TEXT NOT NULL REFERENCES turn_execution(turn_id),
          sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
          PRIMARY KEY (turn_id, sequence)
        );
        """
    )

    now = datetime.now(timezone.utc).isoformat()
    raw_conn.execute("INSERT INTO global_user_identity VALUES ('usr_1', 'Legacy User', ?)", (now,))
    raw_conn.execute("INSERT INTO channel_identity VALUES ('telegram', 'act_1', 'usr_1', ?)", (now,))
    raw_conn.execute("INSERT INTO conversation_session VALUES ('sess_1', 'usr_1', 'telegram', 'chat_1', NULL, ?, ?)", (now, now))
    raw_conn.execute("INSERT INTO turn_execution VALUES ('usr_1', 'key_old', 'digest', 'turn_old', 'sess_1', 'completed', ?, ?)", (now, now))
    raw_conn.execute(
        "INSERT INTO turn_event VALUES ('turn_old', 0, 'evt_old', ?)",
        (
            json.dumps(
                {
                    "event_type": "completed",
                    "principal_id": "act_1",
                    "session_id": "sess_1",
                    "turn_id": "turn_old",
                    "sequence": 0,
                    "schema_version": 1,
                    "data": {"text": "Old answer"},
                    "workflow_id": None,
                    "job_id": None,
                    "approval_id": None,
                    "tool_call_id": None,
                    "occurred_at": now,
                    "event_id": "evt_old",
                }
            ),
        ),
    )
    raw_conn.commit()
    raw_conn.close()

    # Step 1: Open with current connect() and pass legacy transcript containing repeated text 'repeat'
    conn1 = connect(db_path)
    identities1 = IdentityRepository(conn1)
    sessions1 = SessionRepository(conn1)
    events1 = EventRepository(conn1)
    tf1 = FakeTranscriptFactory()
    tf1.transcript.user_turns = ["repeat"]
    agent1 = FakeAgent()
    service1 = HermesTurnService(identities1, sessions1, events1, tf1, agent1)

    # Perform history load to trigger migration & durable backfill
    history1 = events1.load_session_history("sess_1", tf1.transcript.history)
    assert history1 == (
        {"role": "user", "content": "repeat"},
        {"role": "assistant", "content": "Old answer"},
    )
    conn1.close()

    # Step 2: Reopen database with an EMPTY transcript adapter (simulating transcript loss/restart)
    reopened = connect(db_path)
    try:
        reopened_identities = IdentityRepository(reopened)
        reopened_sessions = SessionRepository(reopened)
        reopened_events = EventRepository(reopened)
        reopened_agent = FakeAgent()
        empty_tf = FakeTranscriptFactory()
        reopened_service = HermesTurnService(
            reopened_identities, reopened_sessions, reopened_events, empty_tf, reopened_agent
        )

        # Executing new turn with repeated user message 'repeat'
        req = AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="act_1",
                owner_user_id="usr_1",
                channel="telegram",  # type: ignore[arg-type]
                session_id="sess_1",
            ),
            turn_id="turn_new",
            idempotency_key="key_new",
            message="repeat",
        )
        reopened_agent.output = [AgentOutput("completed", {"text": "New answer"})]

        [e async for e in reopened_service.handle(req)]

        turn_new_history = reopened_agent.calls[0][1]
        assert len(turn_new_history) == 2
        assert turn_new_history[0] == {"role": "user", "content": "repeat"}
        assert turn_new_history[1] == {"role": "assistant", "content": "Old answer"}
    finally:
        reopened.close()


class RealContractFakeUpstreamAgent:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def run_conversation(
        self,
        *,
        user_message: Any,
        conversation_history: list[Mapping[str, Any]],
        task_id: str,
        stream_callback: Callable[[str | None], None],
        persist_user_message: Any,
    ) -> Mapping[str, Any]:
        self.calls.append(
            {
                "user_message": user_message,
                "history": conversation_history,
                "task_id": task_id,
            }
        )
        stream_callback(f"Thinking for {user_message}...")
        turn_num = len(self.calls)
        tool_call_dict = {
            "id": f"call_{turn_num}",
            "type": "function",
            "function": {"name": "search", "arguments": "{}"},
        }
        tool_result_msg = {
            "role": "tool",
            "tool_call_id": f"call_{turn_num}",
            "content": f"result_{turn_num}",
        }
        current_messages = [
            {"role": "user", "content": user_message},
            {
                "role": "assistant",
                "content": f"Thinking for {user_message}...",
                "tool_calls": [tool_call_dict],
            },
            tool_result_msg,
            {"role": "assistant", "content": f"Answer for {user_message}"},
        ]
        # Real NousResearch contract: cumulative messages = conversation_history + current_messages
        cumulative_messages = list(conversation_history) + current_messages
        return {
            "completed": True,
            "failed": False,
            "interrupted": False,
            "final_response": f"Answer for {user_message}",
            "messages": cumulative_messages,
        }


@pytest.mark.asyncio
async def test_real_contract_cumulative_upstream_result_has_linear_payload_growth_and_no_duplicates(
    tmp_path,
):
    db_path = tmp_path / "cumulative-upstream.sqlite"
    connection = connect(db_path)
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    events = EventRepository(connection)
    owner = identities.create_owner("primary")
    identities.link(owner.owner_user_id, "telegram", "actor:1")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")
    transcript_factory = FakeTranscriptFactory()

    upstream_agent = RealContractFakeUpstreamAgent()
    adapter = UpstreamAIAgentAdapter(upstream_agent)
    service = HermesTurnService(
        identities, sessions, events, transcript_factory, adapter
    )

    def make_req(msg: str, turn_id: str, key: str) -> AgentTurnRequest:
        return AgentTurnRequest(
            principal=PrincipalContext(
                actor_id="actor:1",
                owner_user_id=owner.owner_user_id,
                channel="telegram",  # type: ignore[arg-type]
                session_id=session.session_id,
            ),
            turn_id=turn_id,
            idempotency_key=key,
            message=msg,
        )

    # Turn 1
    [e async for e in service.handle(make_req("Question 1", "turn_1", "key:1"))]

    # Turn 2
    [e async for e in service.handle(make_req("Question 2", "turn_2", "key:2"))]

    # Turn 3
    [e async for e in service.handle(make_req("Question 3", "turn_3", "key:3"))]

    # Verify history received by upstream agent in Turn 3
    turn3_history = upstream_agent.calls[2]["history"]
    # 4 messages per turn * 2 turns = 8 prior history messages
    assert len(turn3_history) == 8
    assert turn3_history[0] == {"role": "user", "content": "Question 1"}
    assert turn3_history[3] == {"role": "assistant", "content": "Answer for Question 1"}
    assert turn3_history[4] == {"role": "user", "content": "Question 2"}
    assert turn3_history[7] == {"role": "assistant", "content": "Answer for Question 2"}

    # Verify linear per-turn payload growth in turn_event completed data
    for tid in ["turn_1", "turn_2", "turn_3"]:
        row = connection.execute(
            """
            SELECT payload_json FROM turn_event
            WHERE turn_id = ? AND sequence = (SELECT MAX(sequence) FROM turn_event WHERE turn_id = ?)
            """,
            (tid, tid),
        ).fetchone()
        payload = json.loads(row["payload_json"])
        stored_turn_msgs = payload["data"]["turn_messages"]
        # Stored turn_messages must contain ONLY the 4 current-turn messages (not cumulative history)
        assert len(stored_turn_msgs) == 4

    connection.close()

    # Restart database connection with an empty transcript adapter
    reopened = connect(db_path)
    try:
        reopened_identities = IdentityRepository(reopened)
        reopened_sessions = SessionRepository(reopened)
        reopened_events = EventRepository(reopened)
        reopened_upstream_agent = RealContractFakeUpstreamAgent()
        reopened_adapter = UpstreamAIAgentAdapter(reopened_upstream_agent)
        reopened_service = HermesTurnService(
            reopened_identities,
            reopened_sessions,
            reopened_events,
            FakeTranscriptFactory(),
            reopened_adapter,
        )

        [
            e
            async for e in reopened_service.handle(
                make_req("Question 4", "turn_4", "key:4")
            )
        ]

        turn4_history = reopened_upstream_agent.calls[0]["history"]
        # 3 turns * 4 messages = 12 historical messages
        assert len(turn4_history) == 12
        assert turn4_history[0] == {"role": "user", "content": "Question 1"}
        assert turn4_history[4] == {"role": "user", "content": "Question 2"}
        assert turn4_history[8] == {"role": "user", "content": "Question 3"}
        assert turn4_history[11] == {"role": "assistant", "content": "Answer for Question 3"}
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_durable_identity_cutover_with_multiple_legacy_and_canonical_turns(tmp_path):
    db_path = tmp_path / "legacy-identity-cutover.sqlite"
    raw_conn = sqlite3.connect(db_path)
    raw_conn.row_factory = sqlite3.Row
    raw_conn.execute("PRAGMA foreign_keys = ON")
    raw_conn.executescript(
        """
        CREATE TABLE global_user_identity (
          owner_user_id TEXT PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE channel_identity (
          channel TEXT NOT NULL, external_subject TEXT NOT NULL,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id), created_at TEXT NOT NULL,
          PRIMARY KEY (channel, external_subject)
        );
        CREATE TABLE conversation_session (
          session_id TEXT PRIMARY KEY,
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          channel TEXT NOT NULL, external_conversation_id TEXT NOT NULL, active_workflow_id TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          UNIQUE(owner_user_id, channel, external_conversation_id)
        );
        CREATE TABLE turn_execution (
          owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
          idempotency_key TEXT NOT NULL, request_digest TEXT NOT NULL, turn_id TEXT NOT NULL UNIQUE,
          session_id TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
          PRIMARY KEY (owner_user_id, idempotency_key)
        );
        CREATE TABLE turn_event (
          turn_id TEXT NOT NULL REFERENCES turn_execution(turn_id),
          sequence INTEGER NOT NULL, event_id TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
          PRIMARY KEY (turn_id, sequence)
        );
        """
    )

    now = datetime.now(timezone.utc).isoformat()
    raw_conn.execute("INSERT INTO global_user_identity VALUES ('usr_1', 'Legacy User', ?)", (now,))
    raw_conn.execute("INSERT INTO channel_identity VALUES ('telegram', 'act_1', 'usr_1', ?)", (now,))
    raw_conn.execute("INSERT INTO conversation_session VALUES ('sess_1', 'usr_1', 'telegram', 'chat_1', NULL, ?, ?)", (now, now))
    # Insert pre-existing canonical turn_execution without user_message column
    raw_conn.execute("INSERT INTO turn_execution VALUES ('usr_1', 'key_c1', 'digest_c1', 'turn_c1', 'sess_1', 'completed', ?, ?)", (now, now))
    raw_conn.execute(
        "INSERT INTO turn_event VALUES ('turn_c1', 0, 'evt_c1', ?)",
        (
            json.dumps(
                {
                    "event_type": "completed",
                    "principal_id": "act_1",
                    "session_id": "sess_1",
                    "turn_id": "turn_c1",
                    "sequence": 0,
                    "schema_version": 1,
                    "data": {"text": "Canonical Answer 1"},
                    "workflow_id": None,
                    "job_id": None,
                    "approval_id": None,
                    "tool_call_id": None,
                    "occurred_at": now,
                    "event_id": "evt_c1",
                }
            ),
        ),
    )
    raw_conn.commit()
    raw_conn.close()

    # Step 1: Open via connect() with legacy transcript containing 2 legacy turns + 1 canonical turn linked by turn_id
    conn1 = connect(db_path)
    events1 = EventRepository(conn1)
    transcript_messages = [
        {"role": "system", "content": "System Prompt"},
        {"role": "user", "content": "Legacy Question 1"},
        {"role": "assistant", "content": "Legacy Answer 1"},
        {"role": "user", "content": "Legacy Question 2"},
        {"role": "assistant", "content": "Legacy Answer 2"},
        {"role": "user", "content": "Canonical Question 1"},
        {
            "role": "assistant",
            "content": "Canonical Answer 1",
            "event_metadata": {"turn_id": "turn_c1"},
        },
    ]

    history1 = events1.load_session_history("sess_1", transcript_messages)
    assert len(history1) == 7
    assert history1[0] == {"role": "system", "content": "System Prompt"}
    assert history1[1] == {"role": "user", "content": "Legacy Question 1"}
    assert history1[2] == {"role": "assistant", "content": "Legacy Answer 1"}
    assert history1[3] == {"role": "user", "content": "Legacy Question 2"}
    assert history1[4] == {"role": "assistant", "content": "Legacy Answer 2"}
    assert history1[5] == {"role": "user", "content": "Canonical Question 1"}
    assert history1[6] == {"role": "assistant", "content": "Canonical Answer 1"}
    conn1.close()

    # Step 2: Reopen database connection with an EMPTY transcript adapter (transcript lost/deleted)
    reopened = connect(db_path)
    try:
        reopened_events = EventRepository(reopened)
        reopened_history = reopened_events.load_session_history("sess_1", [])
        assert len(reopened_history) == 7
        assert reopened_history[0] == {"role": "system", "content": "System Prompt"}
        assert reopened_history[1] == {"role": "user", "content": "Legacy Question 1"}
        assert reopened_history[2] == {"role": "assistant", "content": "Legacy Answer 1"}
        assert reopened_history[3] == {"role": "user", "content": "Legacy Question 2"}
        assert reopened_history[4] == {"role": "assistant", "content": "Legacy Answer 2"}
        assert reopened_history[5] == {"role": "user", "content": "Canonical Question 1"}
        assert reopened_history[6] == {"role": "assistant", "content": "Canonical Answer 1"}
    finally:
        reopened.close()


def test_corrupt_legacy_cutover_json_raises_migration_error(tmp_path):

    from hermes_personal.orchestration.event_repository import MigrationError

    db_path = tmp_path / "corrupt-cutover.sqlite"
    conn = connect(db_path)
    identities = IdentityRepository(conn)
    sessions = SessionRepository(conn)
    events = EventRepository(conn)
    owner = identities.create_owner("primary")
    session = sessions.get_or_create(owner.owner_user_id, "telegram", "chat:1")

    # Manually insert invalid JSON into legacy_session_cutover
    conn.execute(
        "INSERT INTO legacy_session_cutover VALUES (?, 'turn_1', 'corrupt_json{', ?)",
        (session.session_id, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()

    with pytest.raises(MigrationError, match="corrupt legacy cutover JSON"):
        events.load_session_history(session.session_id, [])

    conn.close()
