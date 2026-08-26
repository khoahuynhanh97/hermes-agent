from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.discovery import (
    DEFAULT_WIRE_BINDING_RULES,
    CapabilityDiscovery,
)
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import (
    CapabilityPolicyEvaluator,
    PolicyRequestContext,
)
from hermes_personal.capabilities.search import GovernedCapabilitySearch
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.contracts import AgentEvent, AgentTurnRequest, PrincipalContext
from hermes_personal.identity import GlobalUserIdentity
from hermes_personal.orchestration import AgentOutput
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.orchestration.turn_service import HermesTurnService
from hermes_personal.sessions import ConversationSession
from hermes_personal.storage.sqlite import connect


def _create_database() -> sqlite3.Connection:
    connection = connect(":memory:")
    # Full DDL is initialized by storage.sqlite.connect, including capability tables
    return connection


def _make_full_fake_registry() -> dict[str, dict]:
    registry = {}
    for rule in DEFAULT_WIRE_BINDING_RULES:
        wire_name = rule.accepted_wire_names[0]
        registry[wire_name] = {
            "type": "function",
            "function": {
                "name": wire_name,
                "description": f"Tool for {rule.capability_id}",
                "parameters": {"type": "object", "properties": {"input_query": {"type": "string"}}},
                "returns": {"type": "object"},
            },
        }
    return registry


# Exit Criterion 1: Exactly 10 stable capability IDs; note.create is absent
def test_exit_criterion_1_exactly_ten_capabilities_and_no_note_create():
    assert len(INITIAL_CAPABILITIES) == 10
    assert "note.create" not in INITIAL_CAPABILITIES
    expected_ids = {
        "product.research",
        "product.resource_pack.build",
        "product.resource_pack.lock",
        "video.brief.create",
        "video.scene_plan.create",
        "video.storyboard.create",
        "video.render",
        "video.export",
        "knowledge.candidate.create",
        "knowledge.retrieve",
    }
    assert set(INITIAL_CAPABILITIES.keys()) == expected_ids


# Exit Criterion 2: Immutable snapshot singleton & atomic activation
def test_exit_criterion_2_snapshot_singleton_and_atomic_activation():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)

    snapshot1 = service.reload()
    assert snapshot1 is not None

    active1 = service.get_active_snapshot()
    assert active1.snapshot_id == snapshot1.snapshot_id

    # Reloading with identical bindings keeps identical deterministic snapshot ID, and updates active pointer
    snapshot2 = service.reload()
    assert snapshot2.snapshot_id == snapshot1.snapshot_id

    active2 = repo.get_active()
    assert active2 is not None
    assert active2.snapshot_id == snapshot1.snapshot_id


# Exit Criterion 3: Official ToolRegistry discovery API usage
def test_exit_criterion_3_official_tool_registry_discovery():
    fake_registry = _make_full_fake_registry()
    discovery = CapabilityDiscovery(rules=DEFAULT_WIRE_BINDING_RULES)

    class MockToolRegistry:
        def get_all_tool_names(self):
            return list(fake_registry.keys())

        def get_definitions(self, tool_names, quiet=False):
            return [fake_registry[name] for name in tool_names if name in fake_registry]

        def get_schema(self, name):
            return fake_registry.get(name)

        def get_toolset_for_tool(self, name):
            return "mock_set"

    mock_reg = MockToolRegistry()
    result = discovery.scan(registry=mock_reg)
    assert len(result.bindings) == 10
    assert len(result.diagnostics) == 0


# Exit Criterion 4: Governed capability search & lazy schema resolution
def test_exit_criterion_4_governed_search_and_lazy_schema():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)
    snapshot = service.reload()

    evaluator = CapabilityPolicyEvaluator()
    search_adapter = GovernedCapabilitySearch(
        snapshot=snapshot,
        policy_evaluator=evaluator,
        registry=fake_registry,
    )

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    search_result = search_adapter.search(query="product research", context=context)
    assert len(search_result.matches) > 0
    top = search_result.matches[0]
    assert not hasattr(top, "wire_name")
    assert not hasattr(top, "provider")

    desc = search_adapter.describe(top.capability_id, context=context)
    assert desc.capability_id == top.capability_id
    assert desc.input_schema is not None


# Exit Criterion 5: Governed domain skill metadata and boundaries
def test_exit_criterion_5_domain_skill_governance_contracts():
    skills_dir = Path(__file__).resolve().parents[3] / ".agents" / "skills"
    skill_paths = [
        skills_dir / "hermes-personal-product-research" / "SKILL.md",
        skills_dir / "hermes-personal-product-video-production" / "SKILL.md",
        skills_dir / "hermes-personal-knowledge-learning" / "SKILL.md",
    ]

    for p in skill_paths:
        content = p.read_text(encoding="utf-8")
        assert "allowed-capabilities:" in content
        assert "allowed-tools:" in content
        assert "AgentTurnRuntime" in content or "Orchestrator" in content
        if "knowledge-learning" in p.name:
            assert "auto-approve" in content.lower() or "human approval" in content.lower()


# Exit Criterion 6: Structured CapabilityError failed-event payloads
def test_exit_criterion_6_structured_capability_error_failed_events():
    principal = PrincipalContext(actor_id="usr_01", session_id="ses_01", owner_user_id="usr_01", channel="cli")
    request = AgentTurnRequest(
        principal=principal,
        message="Search KB",
        workflow_id="knowledge_learning",
    )

    cap_error = CapabilityError(
        code="unauthorized_skill",
        message="Skill is not permitted to execute this capability",
        retryable=False,
        capability_id="knowledge.retrieve",
        actionable_recovery="Request explicit skill permission",
    )

    failed_event = HermesTurnService._failed_event(request, sequence=0, error=cap_error)
    assert failed_event.event_type == "failed"
    assert failed_event.data["code"] == "unauthorized_skill"
    assert failed_event.data["message"] == "Skill is not permitted to execute this capability"
    assert failed_event.data["retryable"] is False
    assert failed_event.data["capability_id"] == "knowledge.retrieve"
    assert failed_event.data["actionable_recovery"] == "Request explicit skill permission"


# Exit Criterion 7: Degraded low-risk/free warning behavior
def test_exit_criterion_7_degraded_low_risk_free_warning_behavior():
    evaluator = CapabilityPolicyEvaluator()
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="mcp__product_intelligence__research_product",
        provider="product_intelligence",
        source="hermes_mcp",
        input_schema_version="1.0",
        output_schema_version="1.0",
        implementation_version="1.0",
        schema_digest="sha256:fe0a6c197bed9e00f97a967ff37f32cdbf017f8b90ad97485e9e97babde8df9f",
        health="degraded",
    )
    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    decision = evaluator.evaluate(spec, binding, context=context)
    assert decision.allowed is True
    assert len(decision.warnings) == 1
    assert decision.warnings[0].code == "degraded_capability_warning"


# Exit Criterion 8: Hermetic vertical slice turn context -> catalog -> fake execution
@pytest.mark.asyncio
async def test_exit_criterion_8_hermetic_vertical_slice():
    connection = _create_database()

    # Seed required foreign key records for turn_execution
    now_iso = "2026-08-24T00:00:00Z"
    connection.execute(
        "INSERT INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('usr_01', 'User', ?)",
        (now_iso,),
    )
    connection.execute(
        """
        INSERT INTO conversation_session (
            session_id, owner_user_id, channel, external_conversation_id, active_workflow_id, created_at, updated_at
        ) VALUES ('ses_01', 'usr_01', 'cli', 'conv_01', 'product_research', ?, ?)
        """,
        (now_iso, now_iso),
    )
    connection.commit()

    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    catalog_service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)
    catalog_service.reload()

    class FakeAgent:
        def run(self, req, hist):
            return iter(
                [
                    AgentOutput(
                        "tool_activity",
                        {
                            "tool_name": "mcp__product_intelligence__research_product",
                            "status": "executed",
                        },
                        workflow_id=req.workflow_id,
                        tool_call_id="tc_01",
                    ),
                    AgentOutput("completed", {}, workflow_id=req.workflow_id),
                ]
            )

    event_repo = EventRepository(connection)

    identity_repo = MagicMock()
    user_identity = GlobalUserIdentity(owner_user_id="usr_01", display_name="User", created_at=now_iso)
    identity_repo.resolve.return_value = user_identity

    session_repo = MagicMock()
    session = ConversationSession(
        session_id="ses_01",
        owner_user_id="usr_01",
        channel="cli",
        external_conversation_id="conv_01",
        active_workflow_id="product_research",
        created_at=now_iso,
        updated_at=now_iso,
    )
    session_repo.get.return_value = session

    transcript_factory = MagicMock()

    turn_service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=FakeAgent(),
        catalog_service=catalog_service,
    )

    principal = PrincipalContext(actor_id="usr_01", session_id="ses_01", owner_user_id="usr_01", channel="cli")
    request = AgentTurnRequest(
        principal=principal,
        message="Research phone specs",
        workflow_id="product_research",
    )

    policy_context = turn_service.build_policy_context(request, skill_id="hermes-personal-product-research")
    search_res = turn_service.catalog_service.search(query=request.message, context=policy_context)
    assert len(search_res.matches) > 0

    events: list[AgentEvent] = []
    async for ev in turn_service.handle(request):
        events.append(ev)

    assert len(events) == 2
    assert events[0].event_type == "tool_activity"
    assert events[0].data["tool_name"] == "mcp__product_intelligence__research_product"
    assert events[1].event_type == "completed"
