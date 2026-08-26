from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock
import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.discovery import DEFAULT_WIRE_BINDING_RULES
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES, CapabilitySpec
from hermes_personal.capabilities.policy import CapabilityPolicyEvaluator, PolicyRequestContext
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.contracts import AgentTurnRequest, PrincipalContext
from hermes_personal.orchestration.event_repository import EventRepository
from hermes_personal.orchestration.turn_service import HermesTurnService
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.budgets import BudgetPolicy, BudgetRepository


def _create_database() -> sqlite3.Connection:
    connection = connect(":memory:")
    # Initialize capability tables
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS capability_snapshot (
            snapshot_id TEXT PRIMARY KEY,
            digest TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS capability_snapshot_binding (
            snapshot_id TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            binding_json TEXT NOT NULL,
            PRIMARY KEY (snapshot_id, capability_id),
            FOREIGN KEY (snapshot_id) REFERENCES capability_snapshot(snapshot_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS capability_catalog_state (
            state_id INTEGER PRIMARY KEY CHECK (state_id = 1),
            active_snapshot_id TEXT NOT NULL,
            activated_at TEXT NOT NULL,
            FOREIGN KEY (active_snapshot_id) REFERENCES capability_snapshot(snapshot_id)
        );
        """
    )
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
                "parameters": {"type": "object", "properties": {}},
                "returns": {"type": "object"},
            },
        }
    return registry


def test_service_get_active_snapshot_without_active_raises_binding_unavailable():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    service = CapabilityCatalogService(snapshot_repository=repo)

    with pytest.raises(CapabilityError) as exc_info:
        service.get_active_snapshot()

    assert exc_info.value.code == "binding_unavailable"
    assert exc_info.value.retryable is True


def test_service_controlled_reload_saves_and_activates_snapshot():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)

    snapshot = service.reload()
    assert snapshot is not None
    assert len(snapshot.bindings) == len(INITIAL_CAPABILITIES)

    active = service.get_active_snapshot()
    assert active.snapshot_id == snapshot.snapshot_id


def test_service_reload_with_missing_wire_tools_raises_capability_error():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    incomplete_registry = {
        "mcp__product_intelligence__research_product": {
            "type": "function",
            "function": {
                "name": "mcp__product_intelligence__research_product",
                "description": "Research product",
                "parameters": {"type": "object"},
            },
        }
    }
    service = CapabilityCatalogService(snapshot_repository=repo, registry=incomplete_registry)

    with pytest.raises(CapabilityError) as exc_info:
        service.reload()

    assert exc_info.value.code == "binding_unavailable"


def test_service_governed_search_and_describe():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)
    service.reload()

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    search_res = service.search(query="product research", context=context)
    assert search_res.total_available > 0
    assert len(search_res.matches) > 0

    desc = service.describe("product.research", context=context)
    assert desc.capability_id == "product.research"
    assert desc.wire_name == "mcp__product_intelligence__research_product"


def test_hermetic_vertical_slice_turn_context_to_capability_service():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)
    service.reload()

    principal = PrincipalContext(actor_id="usr_01", session_id="ses_01", owner_user_id="usr_01", channel="cli")
    request = AgentTurnRequest(
        principal=principal,
        message="Find product specs",
        workflow_id="product_research",
    )

    policy_context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id=request.workflow_id,
        channel_id=request.channel,
        session_id=request.session_id,
    )

    search_res = service.search(query=request.message, context=policy_context)
    assert len(search_res.matches) > 0
    top_cap = search_res.matches[0].capability_id

    desc = service.describe(top_cap, context=policy_context)
    assert desc.capability_id == top_cap
    assert desc.input_schema is not None


class _MockUpstreamAgent:
    def run(self, request, history):
        return iter([])


def test_turn_service_integration_with_catalog_service():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    fake_registry = _make_full_fake_registry()
    catalog_service = CapabilityCatalogService(snapshot_repository=repo, registry=fake_registry)
    catalog_service.reload()

    event_repo = EventRepository(connection)
    identity_repo = MagicMock()
    session_repo = MagicMock()
    transcript_factory = MagicMock()

    turn_service = HermesTurnService(
        identity_repository=identity_repo,
        session_repository=session_repo,
        event_repository=event_repo,
        transcript_factory=transcript_factory,
        agent=_MockUpstreamAgent(),
        catalog_service=catalog_service,
    )

    assert turn_service.catalog_service is catalog_service

    principal = PrincipalContext(actor_id="usr_01", session_id="ses_01", owner_user_id="usr_01", channel="cli")
    request = AgentTurnRequest(
        principal=principal,
        message="Find product specs",
        workflow_id="product_research",
    )

    policy_context = turn_service.build_policy_context(
        request, skill_id="hermes-personal-product-research"
    )
    search_res = turn_service.catalog_service.search(query=request.message, context=policy_context)
    assert len(search_res.matches) > 0


def test_turn_service_propagates_capability_error_in_failed_event_data():
    principal = PrincipalContext(actor_id="usr_01", session_id="ses_01", owner_user_id="usr_01", channel="cli")
    request = AgentTurnRequest(
        principal=principal,
        message="Find product specs",
        workflow_id="product_research",
    )

    cap_error = CapabilityError(
        code="binding_unavailable",
        message="No active catalog snapshot",
        retryable=True,
        capability_id="product.research",
        actionable_recovery="Reload catalog snapshot",
    )

    event = HermesTurnService._failed_event(request, sequence=0, error=cap_error)
    assert event.event_type == "failed"
    assert event.data["code"] == "binding_unavailable"
    assert event.data["message"] == "No active catalog snapshot"
    assert event.data["retryable"] is True
    assert event.data["capability_id"] == "product.research"
    assert event.data["actionable_recovery"] == "Reload catalog snapshot"


def test_execute_capability_policy_denied_does_not_call_provider():
    connection = _create_database()
    repo = CapabilitySnapshotRepository(connection)
    service = CapabilityCatalogService(snapshot_repository=repo)

    spec = CapabilitySpec(
        capability_id="test.cap",
        owner="test_owner",
        input_schema_version="1.0",
        output_schema_version="1.0",
        allowed_skills=("skill_a",),
        allowed_workflows=("wf_a",),
        approval_policy="none",
        risk="low",
        cost_class="free",
    )
    binding = ImplementationBinding(
        capability_id="test.cap",
        wire_name="mcp__test__cap",
        source="builtin",
        provider="test_provider",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:000",
        health="healthy",
    )
    context = PolicyRequestContext(
        authenticated=False,  # Policy evaluation will fail
        skill_id="skill_a",
        workflow_id="wf_a",
    )

    provider_called = False

    def provider_fn():
        nonlocal provider_called
        provider_called = True
        return "success"

    with pytest.raises(CapabilityError) as exc_info:
        service.execute_capability(spec, binding, context, provider_fn)

    assert exc_info.value.code == "unauthenticated"
    assert provider_called is False


def test_execute_capability_success_commits_budget():
    connection = _create_database()

    # Create budget table
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS budget_reservation (
            reservation_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            idempotency_key TEXT,
            request_digest TEXT NOT NULL,
            state TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            operation_input_digest TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            policy_snapshot_json TEXT NOT NULL,
            external_reference TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    budget_repo = BudgetRepository(connection)
    policy = BudgetPolicy(max_total=1000, per_channel={"metered": 500})
    evaluator = CapabilityPolicyEvaluator(budget_repository=budget_repo, budget_policy=policy)
    snapshot_repo = CapabilitySnapshotRepository(connection)
    service = CapabilityCatalogService(snapshot_repository=snapshot_repo, policy_evaluator=evaluator)

    spec = CapabilitySpec(
        capability_id="test.metered",
        owner="test_owner",
        input_schema_version="1.0",
        output_schema_version="1.0",
        cost_class="metered",
        allowed_skills=("skill_a",),
        allowed_workflows=("wf_a",),
        approval_policy="none",
        risk="low",
    )
    binding = ImplementationBinding(
        capability_id="test.metered",
        wire_name="mcp__test__metered",
        source="builtin",
        provider="test_provider",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:000",
        health="healthy",
    )
    context = PolicyRequestContext(
        authenticated=True,
        skill_id="skill_a",
        workflow_id="wf_a",
        amount=100,
        owner_user_id="user_1",
    )

    result = service.execute_capability(spec, binding, context, lambda: "executed")
    assert result == "executed"

    # Verify committed budget
    assert budget_repo.get_allocated(owner_user_id="user_1", scope_id="wf_a", channel="metered") == 100


def test_execute_capability_failure_releases_budget():
    connection = _create_database()

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS budget_reservation (
            reservation_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            scope_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            amount INTEGER NOT NULL,
            currency TEXT NOT NULL,
            idempotency_key TEXT,
            request_digest TEXT NOT NULL,
            state TEXT NOT NULL,
            capability_id TEXT NOT NULL,
            operation_input_digest TEXT NOT NULL,
            policy_id TEXT NOT NULL,
            policy_version INTEGER NOT NULL,
            policy_snapshot_json TEXT NOT NULL,
            external_reference TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )

    budget_repo = BudgetRepository(connection)
    policy = BudgetPolicy(max_total=1000, per_channel={"metered": 500})
    evaluator = CapabilityPolicyEvaluator(budget_repository=budget_repo, budget_policy=policy)
    snapshot_repo = CapabilitySnapshotRepository(connection)
    service = CapabilityCatalogService(snapshot_repository=snapshot_repo, policy_evaluator=evaluator)

    spec = CapabilitySpec(
        capability_id="test.metered",
        owner="test_owner",
        input_schema_version="1.0",
        output_schema_version="1.0",
        cost_class="metered",
        allowed_skills=("skill_a",),
        allowed_workflows=("wf_a",),
        approval_policy="none",
        risk="low",
    )
    binding = ImplementationBinding(
        capability_id="test.metered",
        wire_name="mcp__test__metered",
        source="builtin",
        provider="test_provider",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:000",
        health="healthy",
    )
    context = PolicyRequestContext(
        authenticated=True,
        skill_id="skill_a",
        workflow_id="wf_a",
        amount=100,
        owner_user_id="user_1",
    )

    def failing_provider():
        raise RuntimeError("Provider failed")

    with pytest.raises(RuntimeError, match="Provider failed"):
        service.execute_capability(spec, binding, context, failing_provider)

    # Verify committed budget is 0 because reservation was released
    assert budget_repo.get_allocated(owner_user_id="user_1", scope_id="wf_a", channel="metered") == 0


def test_canonical_capability_execution_with_durable_budget_and_provider_gating(tmp_path):
    db_path = tmp_path / "exec_budget.sqlite"
    conn = connect(db_path)
    repo = BudgetRepository(conn)
    policy = BudgetPolicy(max_total=500, per_channel={"paid": 300})
    evaluator = CapabilityPolicyEvaluator(budget_repository=repo, budget_policy=policy)
    snapshots = CapabilitySnapshotRepository(conn)
    catalog_service = CapabilityCatalogService(snapshot_repository=snapshots, policy_evaluator=evaluator)

    spec = INITIAL_CAPABILITIES["video.render"]
    binding = ImplementationBinding(
        capability_id="video.render",
        wire_name="mcp__video_factory__render",
        source="hermes_mcp",
        provider="video_factory",
        implementation_version="1.0",
        input_schema_version=spec.input_schema_version,
        output_schema_version=spec.output_schema_version,
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="healthy",
    )

    fake_provider_calls = 0

    def fake_provider_fn():
        nonlocal fake_provider_calls
        fake_provider_calls += 1
        return {"status": "rendered"}

    # Test 1: Paid call succeeds & reserves budget
    context1 = PolicyRequestContext(
        authenticated=True,
        user_confirmed_approval=True,
        granted_policies=frozenset(["storyboard_approved"]),
        skill_id="hermes-personal-product-video-production",
        workflow_id="product_to_video",
        owner_user_id="alice",
        scope_id="wf_1",
        idempotency_key="tx_1",
        amount=200,
    )

    result = catalog_service.execute_capability(spec, binding, context1, fake_provider_fn)
    assert result == {"status": "rendered"}
    assert fake_provider_calls == 1
    assert repo.get_allocated("alice", "wf_1", "paid") == 200

    # Test 2: Budget exceeded => provider call count does NOT increase
    context2 = PolicyRequestContext(
        authenticated=True,
        user_confirmed_approval=True,
        granted_policies=frozenset(["storyboard_approved"]),
        skill_id="hermes-personal-product-video-production",
        workflow_id="product_to_video",
        owner_user_id="alice",
        scope_id="wf_1",
        idempotency_key="tx_2",
        amount=200,
    )

    with pytest.raises(CapabilityError) as exc_info:
        catalog_service.execute_capability(spec, binding, context2, fake_provider_fn)

    assert exc_info.value.code == "budget_exceeded"
    assert fake_provider_calls == 1

    # Test 3: Restart/reopen database retains reservation & limits
    conn.close()

    conn2 = connect(db_path)
    repo2 = BudgetRepository(conn2)
    evaluator2 = CapabilityPolicyEvaluator(budget_repository=repo2, budget_policy=policy)
    snapshots2 = CapabilitySnapshotRepository(conn2)
    catalog_service2 = CapabilityCatalogService(snapshot_repository=snapshots2, policy_evaluator=evaluator2)

    assert repo2.get_allocated("alice", "wf_1", "paid") == 200

    context3 = PolicyRequestContext(
        authenticated=True,
        user_confirmed_approval=True,
        granted_policies=frozenset(["storyboard_approved"]),
        skill_id="hermes-personal-product-video-production",
        workflow_id="product_to_video",
        owner_user_id="alice",
        scope_id="wf_1",
        idempotency_key="tx_3",
        amount=200,
    )

    with pytest.raises(CapabilityError) as exc_info2:
        catalog_service2.execute_capability(spec, binding, context3, fake_provider_fn)

    assert exc_info2.value.code == "budget_exceeded"
    assert fake_provider_calls == 1

    conn2.close()


def test_approval_failure_prevents_budget_reservation_and_provider_call(tmp_path):
    db_path = tmp_path / "approval_fail.sqlite"
    conn = connect(db_path)
    repo = BudgetRepository(conn)
    policy = BudgetPolicy(max_total=500, per_channel={"paid": 300})
    evaluator = CapabilityPolicyEvaluator(budget_repository=repo, budget_policy=policy)
    snapshots = CapabilitySnapshotRepository(conn)
    catalog_service = CapabilityCatalogService(snapshot_repository=snapshots, policy_evaluator=evaluator)

    spec = INITIAL_CAPABILITIES["video.render"]
    binding = ImplementationBinding(
        capability_id="video.render",
        wire_name="mcp__video_factory__render",
        source="hermes_mcp",
        provider="video_factory",
        implementation_version="1.0",
        input_schema_version=spec.input_schema_version,
        output_schema_version=spec.output_schema_version,
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="healthy",
    )

    fake_provider_calls = 0

    def fake_provider_fn():
        nonlocal fake_provider_calls
        fake_provider_calls += 1
        return {"status": "rendered"}

    context = PolicyRequestContext(
        authenticated=True,
        user_confirmed_approval=False,
        granted_policies=frozenset(),
        skill_id="hermes-personal-product-video-production",
        workflow_id="product_to_video",
        owner_user_id="alice",
        scope_id="wf_1",
        idempotency_key="tx_fail",
        amount=200,
    )

    with pytest.raises(CapabilityError) as exc_info:
        catalog_service.execute_capability(spec, binding, context, fake_provider_fn)

    assert exc_info.value.code == "unmet_precondition"
    assert fake_provider_calls == 0
    assert repo.get_allocated("alice", "wf_1", "paid") == 0
    conn.close()


def test_free_capability_execution_does_not_reserve_budget(tmp_path):
    db_path = tmp_path / "free_cap.sqlite"
    conn = connect(db_path)
    repo = BudgetRepository(conn)
    policy = BudgetPolicy(max_total=500, per_channel={"paid": 300})
    evaluator = CapabilityPolicyEvaluator(budget_repository=repo, budget_policy=policy)
    snapshots = CapabilitySnapshotRepository(conn)
    catalog_service = CapabilityCatalogService(snapshot_repository=snapshots, policy_evaluator=evaluator)

    spec = INITIAL_CAPABILITIES["product.research"]
    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="mcp__product_intelligence__research_product",
        source="hermes_mcp",
        provider="product_intelligence",
        implementation_version="1.0",
        input_schema_version=spec.input_schema_version,
        output_schema_version=spec.output_schema_version,
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="healthy",
    )

    fake_provider_calls = 0

    def fake_provider_fn():
        nonlocal fake_provider_calls
        fake_provider_calls += 1
        return {"status": "researched"}

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
        owner_user_id="alice",
        scope_id="wf_free",
        idempotency_key="tx_free",
        amount=100,
    )

    result = catalog_service.execute_capability(spec, binding, context, fake_provider_fn)

    assert result == {"status": "researched"}
    assert fake_provider_calls == 1
    assert repo.get_allocated("alice", "wf_free", "paid") == 0
    conn.close()
