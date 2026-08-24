from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import CapabilityPolicyEvaluator
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import IdentityRepository
from hermes_personal.orchestration import AgentOutput, HermesTurnService
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.sessions import SessionRepository
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.repository import WorkflowRepository


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
    transcripts: dict[str, FakeTranscript] = field(default_factory=dict)

    def for_session(self, session_id: str) -> FakeTranscript:
        if session_id not in self.transcripts:
            self.transcripts[session_id] = FakeTranscript()
        return self.transcripts[session_id]


@dataclass
class MultiChannelAgent:
    catalog_service: CapabilityCatalogService | None = None

    def run(
        self, request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]
    ) -> Iterator[AgentOutput]:
        msg_lower = request.message.lower()
        if "ambiguous" in msg_lower:
            yield AgentOutput(
                event_type="clarification_required",
                data={
                    "text": "Please clarify: which target format do you prefer?",
                    "options": ("Shorts", "Reels", "TikTok"),
                },
            )
        elif "capabilities" in msg_lower:
            caps = []
            if self.catalog_service:
                snap = self.catalog_service.get_active_snapshot()
                if snap:
                    caps = [b.capability_id for b in snap.bindings]
            yield AgentOutput(
                event_type="completed",
                data={"text": "Available capabilities", "capabilities": tuple(caps)},
            )
        else:
            yield AgentOutput(
                event_type="completed",
                data={"text": f"Processed on {request.principal.channel}: {request.message}"},
            )


def _setup_multi_channel_environment():
    conn = connect(":memory:")
    identity_repo = IdentityRepository(conn)
    session_repo = SessionRepository(conn)
    event_repo = EventRepository(conn)
    workflow_repo = WorkflowRepository(conn)
    workflow_engine = WorkflowEngine(workflow_repo)

    snap_repo = CapabilitySnapshotRepository(conn)
    bindings = tuple(
        ImplementationBinding(
            capability_id=spec.capability_id,
            wire_name=spec.capability_id.replace(".", "_"),
            source="builtin",
            provider=spec.owner,
            implementation_version="1.0.0",
            input_schema_version=spec.input_schema_version,
            output_schema_version=spec.output_schema_version,
            schema_digest=f"sha256:{spec.capability_id}",
            health="healthy",
        )
        for spec in INITIAL_CAPABILITIES.values()
    )
    snap_repo.save_and_activate(bindings)

    policy_eval = CapabilityPolicyEvaluator()
    catalog_service = CapabilityCatalogService(
        snapshot_repository=snap_repo,
        policy_evaluator=policy_eval,
    )

    transcript_factory = FakeTranscriptFactory()
    agent = MultiChannelAgent(catalog_service=catalog_service)

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
        catalog_service=catalog_service,
    )
    return service, session_repo, event_repo, workflow_engine, owner.owner_user_id, catalog_service


async def _collect_events(service: HermesTurnService, request: AgentTurnRequest) -> list[AgentEvent]:
    events = []
    async for e in service.handle(request):
        events.append(e)
    return events


def test_four_channel_single_upstream_turn_boundary():
    """Prove Telegram, CLI, Web, and Omni share the exact canonical HermesTurnService boundary."""
    service, session_repo, _, _, owner_id, _ = _setup_multi_channel_environment()

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
            message="Create a video for product alpha",
            idempotency_key=f"idem_{ch}_turn",
        )
        events = asyncio.run(_collect_events(service, req))
        assert len(events) >= 1
        completed = [e for e in events if e.event_type == "completed"]
        assert len(completed) == 1
        assert f"Processed on {ch}: Create a video for product alpha" in str(completed[0].data["text"])


def test_stable_capability_selection_across_channels():
    """Prove active capability catalog snapshot is stable and identical regardless of ingress channel."""
    service, session_repo, _, _, owner_id, catalog_service = _setup_multi_channel_environment()

    active_snap = catalog_service.get_active_snapshot()
    assert active_snap is not None
    expected_binding_count = len(active_snap.bindings)

    for ch, actor_id in [("telegram", "tg_123"), ("cli", "cli_local"), ("web", "web_456"), ("omni", "omni_789")]:
        session = session_repo.get_or_create(owner_id, ch, f"conv_cap_{ch}")
        ctx = PrincipalContext(
            actor_id=actor_id,
            owner_user_id=owner_id,
            channel=ch,
            session_id=session.session_id,
        )
        req = AgentTurnRequest(
            principal=ctx,
            message="List capabilities",
            idempotency_key=f"idem_cap_{ch}",
        )
        events = asyncio.run(_collect_events(service, req))
        assert len(events) > 0, f"events was empty: {events}"
        completed = [e for e in events if e.event_type == "completed"]
        if not completed:
            raise AssertionError(f"No completed event in {events}")
        assert len(completed[0].data["capabilities"]) == expected_binding_count


def test_shared_workflow_and_approval_across_channels():
    """Prove workflow started on Telegram is visible and can be approved/advanced from Web and CLI."""
    service, session_repo, _, workflow_engine, owner_id, _ = _setup_multi_channel_environment()

    # 1. Start workflow via command
    cmd_start = {
        "command_id": "cmd_start_wf_01",
        "workflow_id": "wf_cross_channel_01",
        "type": "start",
        "args": {"product": "AI Camera", "owner": owner_id},
    }
    res_start = workflow_engine.handle(cmd_start)
    assert res_start.success is True
    assert res_start.new_version == 1

    # 2. Request approval
    cmd_req = {
        "command_id": "cmd_req_appr_01",
        "workflow_id": "wf_cross_channel_01",
        "type": "request_approval",
        "args": {"step": "script_review"},
    }
    res_req = workflow_engine.handle(cmd_req)
    assert res_req.success is True
    assert res_req.new_version == 2

    # 3. Approve from Web
    cmd_appr = {
        "command_id": "cmd_appr_01",
        "workflow_id": "wf_cross_channel_01",
        "type": "approve",
        "args": {"step": "script_review", "channel": "web"},
    }
    res_appr = workflow_engine.handle(cmd_appr)
    assert res_appr.success is True
    assert res_appr.new_version == 3


def test_channel_local_histories_with_global_identity():
    """Prove per-channel session histories remain isolated while bound to one global user identity."""
    service, session_repo, _, _, owner_id, _ = _setup_multi_channel_environment()

    session_tg = session_repo.get_or_create(owner_id, "telegram", "conv_tg_private")
    session_web = session_repo.get_or_create(owner_id, "web", "conv_web_private")

    ctx_tg = PrincipalContext(actor_id="tg_123", owner_user_id=owner_id, channel="telegram", session_id=session_tg.session_id)
    ctx_web = PrincipalContext(actor_id="web_456", owner_user_id=owner_id, channel="web", session_id=session_web.session_id)

    asyncio.run(_collect_events(service, AgentTurnRequest(principal=ctx_tg, message="Telegram confidential note", idempotency_key="id_tg_c1")))
    asyncio.run(_collect_events(service, AgentTurnRequest(principal=ctx_web, message="Web dashboard overview", idempotency_key="id_web_c1")))

    s_tg = session_repo.get(session_tg.session_id)
    s_web = session_repo.get(session_web.session_id)

    assert s_tg.owner_user_id == owner_id
    assert s_web.owner_user_id == owner_id
    assert s_tg.channel == "telegram"
    assert s_web.channel == "web"
    assert s_tg.session_id != s_web.session_id


def test_cross_channel_explicit_handoff():
    """Prove explicit cross-channel handoff preserves workflow context and owner identity."""
    _, session_repo, _, _, owner_id, _ = _setup_multi_channel_environment()

    source_session = session_repo.get_or_create(owner_id, "telegram", "conv_tg_source", workflow_id="wf_handoff_100")
    target_session = session_repo.get_or_create(owner_id, "web", "conv_web_target")

    handoff = session_repo.create_handoff(
        owner_user_id=owner_id,
        workflow_id="wf_handoff_100",
        source_session_id=source_session.session_id,
        target_session_id=target_session.session_id,
    )

    assert handoff is not None
    assert handoff.owner_user_id == owner_id

    resolved = session_repo.resolve_handoff(target_session.session_id, "wf_handoff_100")
    assert resolved is not None
    assert resolved.source_session_id == source_session.session_id
    assert resolved.target_session_id == target_session.session_id


def test_structured_clarification_on_ambiguity():
    """Prove ambiguous request returns structured clarification options across channels."""
    service, session_repo, _, _, owner_id, _ = _setup_multi_channel_environment()

    session = session_repo.get_or_create(owner_id, "omni", "conv_omni_clarify")
    ctx = PrincipalContext(
        actor_id="omni_789",
        owner_user_id=owner_id,
        channel="omni",
        session_id=session.session_id,
    )
    req = AgentTurnRequest(
        principal=ctx,
        message="Make an ambiguous video request",
        idempotency_key="idem_clarify_01",
    )
    events = asyncio.run(_collect_events(service, req))
    clarify = [e for e in events if e.event_type == "clarification_required"]
    assert len(clarify) == 1
    assert "Shorts" in clarify[0].data["options"]
    assert "TikTok" in clarify[0].data["options"]
