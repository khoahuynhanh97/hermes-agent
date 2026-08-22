from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import pytest

from hermes_personal.contracts import AgentEvent, AgentTurnRequest, OperatorCommand
from hermes_personal.gateway import ChannelTurnNormalizer
from hermes_personal.identity import IdentityRepository
from hermes_personal.orchestration import (
    EventRepository,
    HermesTurnService,
    UpstreamAIAgentAdapter,
)
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect


@dataclass
class RecordingTranscript:
    user_turns: list[str] = field(default_factory=list)
    events: list[AgentEvent] = field(default_factory=list)

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            {"role": "user", "content": message} for message in self.user_turns
        )

    def append_user_turn(self, text: str) -> None:
        self.user_turns.append(text)

    def append_event(self, event: AgentEvent) -> None:
        self.events.append(event)


@dataclass
class RecordingTranscriptFactory:
    transcripts: dict[str, RecordingTranscript] = field(default_factory=dict)
    requested_session_ids: list[str] = field(default_factory=list)

    def for_session(self, session_id: str) -> RecordingTranscript:
        self.requested_session_ids.append(session_id)
        return self.transcripts.setdefault(session_id, RecordingTranscript())


@dataclass
class FakePublicAIAgent:
    workflow_id: str | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def run_conversation(self, **kwargs: Any) -> Mapping[str, Any]:
        self.calls.append(kwargs)
        kwargs["stream_callback"]("upstream ")
        return {
            "final_response": "upstream response",
            "messages": [],
            "completed": True,
            "workflow_id": self.workflow_id,
        }


@pytest.mark.asyncio
async def test_four_channel_normalizers_reach_one_agent_with_distinct_sessions_and_replay(
    tmp_path,
):
    connection = connect(tmp_path / "acceptance.sqlite")
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    channels = ("telegram", "cli", "web", "omni")
    for channel in channels:
        identities.link(owner.owner_user_id, channel, "actor:primary")

    public_agent = FakePublicAIAgent()
    transcripts = RecordingTranscriptFactory()
    service = HermesTurnService(
        identities,
        sessions,
        EventRepository(connection),
        transcripts,
        UpstreamAIAgentAdapter(public_agent),
    )
    requests = []
    emitted_by_channel = {}
    try:
        for channel in channels:
            normalizer = ChannelTurnNormalizer(channel, identities, sessions)
            request = normalizer.normalize(
                external_subject="actor:primary",
                external_conversation_id=f"conversation:{channel}",
                message="Cung mot yeu cau",
                authenticated_idempotency_key=f"{channel}:transport:7",
            )
            requests.append(request)
            emitted_by_channel[channel] = [
                event async for event in service.handle(request)
            ]

        telegram_retry = ChannelTurnNormalizer(
            "telegram", identities, sessions
        ).normalize(
            external_subject="actor:primary",
            external_conversation_id="conversation:telegram",
            message="Cung mot yeu cau",
            authenticated_idempotency_key="telegram:transport:7",
        )
        replay = [event async for event in service.handle(telegram_retry)]
    finally:
        connection.close()

    assert all(type(request) is AgentTurnRequest for request in requests)
    assert {request.principal.owner_user_id for request in requests} == {
        owner.owner_user_id
    }
    assert len({request.session_id for request in requests}) == 4
    assert len(public_agent.calls) == 4
    assert {call["user_message"] for call in public_agent.calls} == {
        "Cung mot yeu cau"
    }
    assert all(call["conversation_history"] == [] for call in public_agent.calls)
    assert all(
        [event.sequence for event in events] == list(range(len(events)))
        for events in emitted_by_channel.values()
    )
    assert replay == emitted_by_channel["telegram"]
    assert transcripts.requested_session_ids == [
        request.session_id for request in requests
    ]
    assert all(
        transcripts.transcripts[request.session_id].user_turns
        == ["Cung mot yeu cau"]
        for request in requests
    )


@pytest.mark.asyncio
async def test_explicit_wf_7_handoff_is_allowed_and_other_owner_is_denied(tmp_path):
    connection = connect(tmp_path / "handoff-acceptance.sqlite")
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    other_owner = identities.create_owner("other")
    identities.link(owner.owner_user_id, "telegram", "actor:primary")
    identities.link(owner.owner_user_id, "cli", "actor:primary")
    identities.link(other_owner.owner_user_id, "web", "actor:other")

    telegram = ChannelTurnNormalizer("telegram", identities, sessions)
    cli = ChannelTurnNormalizer("cli", identities, sessions)
    web = ChannelTurnNormalizer("web", identities, sessions)
    source_request = telegram.normalize(
        external_subject="actor:primary",
        external_conversation_id="source:7",
        message="start",
    )
    target_request = cli.normalize(
        external_subject="actor:primary",
        external_conversation_id="target:7",
        message="prepare",
    )
    other_request = web.normalize(
        external_subject="actor:other",
        external_conversation_id="other:7",
        message="prepare",
    )
    sessions.link_workflow(source_request.session_id, "wf_7")
    sessions.create_handoff(
        owner.owner_user_id,
        "wf_7",
        source_request.session_id,
        target_request.session_id,
    )
    handoff_request = cli.normalize(
        external_subject="actor:primary",
        external_conversation_id="target:7",
        message="continue",
        workflow_id="wf_7",
    )
    agent = FakePublicAIAgent(workflow_id="wf_7")
    service = HermesTurnService(
        identities,
        sessions,
        EventRepository(connection),
        RecordingTranscriptFactory(),
        UpstreamAIAgentAdapter(agent),
    )
    try:
        events = [event async for event in service.handle(handoff_request)]
        with pytest.raises(PermissionError, match="workflow is not authorized"):
            web.normalize(
                external_subject="actor:other",
                external_conversation_id="other:7",
                message="continue",
                workflow_id="wf_7",
            )
    finally:
        connection.close()

    assert other_request.principal.owner_user_id == other_owner.owner_user_id
    assert handoff_request.workflow_id == "wf_7"
    assert [event.sequence for event in events] == list(range(len(events)))
    assert events[-1].event_type == "completed"
    assert events[-1].workflow_id == "wf_7"
    assert len(agent.calls) == 1


def test_natural_language_normalizer_does_not_construct_operator_commands(tmp_path):
    connection = connect(tmp_path / "controls.sqlite")
    identities = IdentityRepository(connection)
    sessions = SessionRepository(connection)
    owner = identities.create_owner("primary")
    identities.link(owner.owner_user_id, "web", "actor:primary")
    try:
        request = ChannelTurnNormalizer("web", identities, sessions).normalize(
            external_subject="actor:primary",
            external_conversation_id="browser:7",
            message="approve artifact_7",
        )
        command = OperatorCommand(
            principal=request.principal,
            command_type="approve",
            target_id="artifact_7",
            expected_version=1,
        )
    finally:
        connection.close()

    assert type(request) is AgentTurnRequest
    assert not isinstance(request, OperatorCommand)
    assert type(command) is OperatorCommand
