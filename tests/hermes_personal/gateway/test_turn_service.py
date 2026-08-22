from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import timedelta
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

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            {"role": "user", "content": text} for text in self.user_turns
        )

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
async def test_turn_rejects_agent_workflow_when_request_has_no_workflow(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("workflow_state", {}, workflow_id="wf_7")]

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request_factory())]

    assert transcript_factory.transcript.events == []


@pytest.mark.asyncio
async def test_turn_rejects_agent_workflow_that_differs_from_authorized_request(
    turn_environment, request_factory
):
    service, _, sessions, _, session, transcript_factory, agent = turn_environment
    sessions.link_workflow(session.session_id, "wf_7")
    agent.output = [AgentOutput("workflow_state", {}, workflow_id="wf_other")]

    with pytest.raises(AuthorizationError):
        [event async for event in service.handle(request_factory(workflow_id="wf_7"))]

    assert transcript_factory.transcript.events == []


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
async def test_turn_propagates_agent_start_authorization_error_without_failed_event(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    service = build_service(
        identities,
        sessions,
        FakeTranscriptFactory(transcript_factory.transcript),
        StartFailureAgent(AuthorizationError("agent start denied")),
    )

    with pytest.raises(AuthorizationError, match="agent start denied"):
        [event async for event in service.handle(request_factory())]

    assert transcript_factory.transcript.events == []


@pytest.mark.asyncio
async def test_turn_propagates_agent_advance_authorization_error_without_failed_event(
    turn_environment, request_factory
):
    service, _, _, _, _, transcript_factory, agent = turn_environment
    agent.failure = AuthorizationError("agent advance denied")

    with pytest.raises(AuthorizationError, match="agent advance denied"):
        [event async for event in service.handle(request_factory())]

    assert transcript_factory.transcript.events == []


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
    assert status == "in_progress"

    # Subsequent request with same idempotency key fails with TurnInProgress
    with pytest.raises(TurnInProgress) as raised:
        [event async for event in service.handle(replace(request, turn_id="turn_retry"))]
    assert raised.value.turn_id == request.turn_id


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
async def test_overlapping_turn_duplicate_fails_in_progress_then_replays_after_terminal(
    turn_environment, request_factory
):
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    blocking_agent = ControlledBlockingAgent()
    service = build_service(identities, sessions, transcript_factory, blocking_agent)
    request = request_factory()

    stream1 = service.handle(request)
    first_event = await anext(stream1)
    assert first_event.event_type == "text_delta"
    assert first_event.sequence == 0
    assert blocking_agent.started.is_set()

    # While turn 1 is active and blocked before terminal output,
    # a duplicate with the same idempotency key and changed turn_id/timestamp raises TurnInProgress
    retry_request = replace(
        request,
        turn_id="turn_concurrent_retry",
        occurred_at=request.occurred_at + timedelta(seconds=10),
    )
    with pytest.raises(TurnInProgress) as raised:
        [event async for event in service.handle(retry_request)]
    assert raised.value.turn_id == request.turn_id

    # Verify agent was called exactly once, transcript was appended once, no duplicate events
    assert len(blocking_agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]
    stored_events_in_progress = sessions._connection.execute(
        "SELECT sequence, event_id FROM turn_event WHERE turn_id = ?",
        (request.turn_id,),
    ).fetchall()
    assert len(stored_events_in_progress) == 1
    assert stored_events_in_progress[0]["event_id"] == first_event.event_id

    # Unblock agent and finish turn 1
    blocking_agent.unblock.set()
    second_event = await anext(stream1)
    assert second_event.event_type == "completed"
    assert second_event.sequence == 1

    with pytest.raises(StopAsyncIteration):
        await anext(stream1)

    original_events = [first_event, second_event]
    assert transcript_factory.transcript.events == original_events

    status = sessions._connection.execute(
        "SELECT status FROM turn_execution WHERE turn_id = ?", (request.turn_id,)
    ).fetchone()["status"]
    assert status == "completed"

    # Now that turn 1 is terminal, a retry request replays exact stored events without another agent or transcript call
    replay_request = replace(
        request,
        turn_id="turn_replay_retry",
        occurred_at=request.occurred_at + timedelta(minutes=5),
    )
    replay_events = [event async for event in service.handle(replay_request)]

    assert replay_events == original_events
    assert [event.event_id for event in replay_events] == [
        event.event_id for event in original_events
    ]
    assert [event.occurred_at for event in replay_events] == [
        event.occurred_at for event in original_events
    ]
    assert [event.turn_id for event in replay_events] == [
        request.turn_id,
        request.turn_id,
    ]
    assert [event.data for event in replay_events] == [
        event.data for event in original_events
    ]

    # Still only 1 agent call and 1 user turn in transcript
    assert len(blocking_agent.calls) == 1
    assert transcript_factory.transcript.user_turns == [request.message]
    assert transcript_factory.transcript.events == original_events
