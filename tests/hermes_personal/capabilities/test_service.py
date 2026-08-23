from __future__ import annotations

import sqlite3
import pytest

from hermes_personal.capabilities.discovery import DEFAULT_WIRE_BINDING_RULES
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import PolicyRequestContext
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository
from hermes_personal.contracts import AgentTurnRequest, PrincipalContext


def _create_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
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
    # Incomplete registry with only 1 tool
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
