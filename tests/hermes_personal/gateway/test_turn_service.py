from __future__ import annotations

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
    assert agent.calls[0][1] == ({"role": "user", "content": "Xin chao"},)
    assert transcript_factory.transcript.events[0].principal_id == owner.owner_user_id


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
    assert agent.calls[0][0].workflow_id is None
