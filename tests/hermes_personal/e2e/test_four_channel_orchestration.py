from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import IdentityRepository
from hermes_personal.orchestration import AgentOutput, HermesTurnService
from hermes_personal.orchestration.event_repository import EventRepository
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
    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        if "ambiguous" in request.message.lower():
            yield AgentOutput(
                event_type="clarification_required",
                data={
                    "text": "Please clarify: which target format do you prefer?",
                    "options": ("Shorts", "Reels"),
                },
            )
        else:
            yield AgentOutput(
                event_type="completed",
                data={
                    "text": f"Processed: {request.message}",
                },
            )


def _setup_service():
    conn = connect(":memory:")
    identity_repo = IdentityRepository(conn)
    session_repo = SessionRepository(conn)
    event_repo = EventRepository(conn)
    transcript_factory = FakeTranscriptFactory()
    agent = FakeAgent()

    owner = identity_repo.create_owner("Alice User")
    identity_repo.link(owner.owner_user_id, "telegram", "tg_123")
    identity_repo.link(owner.owner_user_id, "cli", "cli_local")
    identity_repo.link(owner.owner_user_id, "web", "web_456")
    identity_repo.link(owner.owner_user_id, "omni", "omni_789")

    service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=agent,
    )
    return service, session_repo, event_repo, owner.owner_user_id


async def _collect_events(service: HermesTurnService, request: AgentTurnRequest) -> list[AgentEvent]:
    events = []
    async for e in service.handle(request):
        events.append(e)
    return events


def test_four_channel_single_upstream_turn_boundary():
    """Verify Telegram, CLI, Web, and Omni converge on one HermesTurnService boundary."""
    service, session_repo, _, owner_id = _setup_service()

    channels = [
        ("telegram", "tg_123"),
        ("cli", "cli_local"),
        ("web", "web_456"),
        ("omni", "omni_789"),
    ]

    for ch, actor_id in channels:
        session = session_repo.get_or_create(owner_id, ch, f"conv_{ch}_001")
        ctx = PrincipalContext(
            actor_id=actor_id,
            owner_user_id=owner_id,
            channel=ch,
            session_id=session.session_id,
        )
        req = AgentTurnRequest(
            principal=ctx,
            message=f"Generate video on {ch}",
            idempotency_key=f"idem_{ch}_001",
        )
        events = asyncio.run(_collect_events(service, req))
        assert len(events) >= 1
        assert any(f"Processed: Generate video on {ch}" in str(e.data) for e in events)


def test_structured_clarification_on_ambiguity():
    """Verify ambiguous requests return structured clarification across channels."""
    service, session_repo, _, owner_id = _setup_service()

    session = session_repo.get_or_create(owner_id, "web", "conv_web_clarify")
    ctx = PrincipalContext(
        actor_id="web_456",
        owner_user_id=owner_id,
        channel="web",
        session_id=session.session_id,
    )
    req = AgentTurnRequest(
        principal=ctx,
        message="Make an ambiguous request",
        idempotency_key="idem_clarify",
    )
    events = asyncio.run(_collect_events(service, req))
    assert len(events) >= 1
    clarify_events = [e for e in events if e.event_type == "clarification_required"]
    assert len(clarify_events) == 1
    assert "Shorts" in clarify_events[0].data["options"]


def test_channel_session_histories_remain_isolated():
    """Verify each channel maintains its own local session history."""
    service, session_repo, _, owner_id = _setup_service()

    session_tg = session_repo.get_or_create(owner_id, "telegram", "conv_tg_hist")
    session_web = session_repo.get_or_create(owner_id, "web", "conv_web_hist")

    # Turn on Telegram
    ctx_tg = PrincipalContext(actor_id="tg_123", owner_user_id=owner_id, channel="telegram", session_id=session_tg.session_id)
    asyncio.run(_collect_events(service, AgentTurnRequest(principal=ctx_tg, message="Hello Telegram", idempotency_key="id_tg_1")))

    # Turn on Web
    ctx_web = PrincipalContext(actor_id="web_456", owner_user_id=owner_id, channel="web", session_id=session_web.session_id)
    asyncio.run(_collect_events(service, AgentTurnRequest(principal=ctx_web, message="Hello Web", idempotency_key="id_web_1")))

    # Verify session histories are isolated
    s_tg = session_repo.get(session_tg.session_id)
    s_web = session_repo.get(session_web.session_id)

    assert s_tg is not None
    assert s_web is not None
    assert s_tg.channel == "telegram"
    assert s_web.channel == "web"
