from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
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
    service = HermesTurnService(identities, sessions, transcript_factory, agent)
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


@pytest.mark.asyncio
async def test_turn_persists_each_event_before_yield(
    turn_environment, request_factory
):
    service, _, _, owner, session, transcript_factory, agent = turn_environment
    agent.output = [AgentOutput("text_delta", {"text": "Xin chao"})]

    async for event in service.handle(request_factory()):
        assert event == transcript_factory.transcript.events[event.sequence]
        transcript_factory.transcript.event_persisted[event.sequence] = True

    assert transcript_factory.session_ids == [session.session_id]
    assert all(transcript_factory.transcript.event_persisted)
    assert transcript_factory.transcript.user_turns == ["Xin chao"]
    assert agent.calls[0][1] == ()
    assert transcript_factory.transcript.events[0].principal_id == owner.owner_user_id


@pytest.mark.asyncio
async def test_turn_passes_prior_history_once_and_current_message_only_as_user_input(
    turn_environment, request_factory
):
    _, identities, sessions, owner, _, transcript_factory, _ = turn_environment
    transcript_factory.transcript.user_turns.append("prior turn")
    upstream = PublicAIAgentSpy()
    service = HermesTurnService(
        identities,
        sessions,
        transcript_factory,
        UpstreamAIAgentAdapter(upstream),
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
    service = HermesTurnService(
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
    service = HermesTurnService(identities, sessions, transcript_factory, slow_agent)
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
    _, identities, sessions, _, _, transcript_factory, _ = turn_environment
    slow_agent = SlowAgent()
    service = HermesTurnService(identities, sessions, transcript_factory, slow_agent)
    stream = service.handle(request_factory())
    pending = asyncio.create_task(anext(stream))

    assert await asyncio.to_thread(slow_agent.iterator.started.wait, 0.5)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending

    assert await asyncio.to_thread(slow_agent.iterator.closed.wait, 0.5)
