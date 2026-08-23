from __future__ import annotations

import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import PolicyRequestContext
from hermes_personal.capabilities.search import GovernedCapabilitySearch
from hermes_personal.capabilities.snapshots import CatalogSnapshot


def _make_full_snapshot() -> CatalogSnapshot:
    bindings = [
        ImplementationBinding(
            capability_id=cap_id,
            wire_name=f"wire_{cap_id.replace('.', '_')}",
            source="hermes_mcp",
            provider="test_provider",
            implementation_version="1.0.0",
            input_schema_version=spec.input_schema_version,
            output_schema_version=spec.output_schema_version,
            schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
            health="healthy",
        )
        for cap_id, spec in INITIAL_CAPABILITIES.items()
    ]
    return CatalogSnapshot(
        snapshot_id="test_snapshot_01",
        digest="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        created_at="2026-08-23T00:00:00Z",
        bindings=tuple(bindings),
    )


def test_search_governed_capabilities_bm25_filtering():
    snapshot = _make_full_snapshot()
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot)

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    res = search_adapter.search(query="product research", context=context, limit=5)
    assert res.total_available > 0
    assert len(res.matches) > 0
    top_match = res.matches[0]
    assert top_match.capability_id == "product.research"
    assert top_match.wire_name == "wire_product_research"


def test_search_filters_unauthorized_policy_capabilities():
    snapshot = _make_full_snapshot()
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot)

    context = PolicyRequestContext(
        authenticated=False,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    res = search_adapter.search(query="product research", context=context, limit=5)
    assert res.total_available == 0
    assert len(res.matches) == 0


def test_describe_allowed_capability_lazy_schema():
    snapshot = _make_full_snapshot()
    fake_registry = {
        "wire_product_research": {
            "type": "function",
            "function": {
                "name": "wire_product_research",
                "description": "Research product details",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
                "returns": {"type": "object"},
            },
        }
    }
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot, registry=fake_registry)

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    desc = search_adapter.describe("product.research", context=context)
    assert desc.capability_id == "product.research"
    assert desc.wire_name == "wire_product_research"
    assert desc.input_schema["type"] == "object"
    assert "query" in desc.input_schema["properties"]


def test_describe_denied_capability_raises_capability_error():
    snapshot = _make_full_snapshot()
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot)

    context = PolicyRequestContext(
        authenticated=False,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    with pytest.raises(CapabilityError) as exc_info:
        search_adapter.describe("product.research", context=context)

    assert exc_info.value.code == "unauthenticated"


def test_describe_unknown_capability_raises_tool_not_found():
    snapshot = _make_full_snapshot()
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot)

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    with pytest.raises(CapabilityError) as exc_info:
        search_adapter.describe("non_existent_cap", context=context)

    assert exc_info.value.code == "tool_not_found"


def test_describe_missing_binding_raises_binding_unavailable():
    snapshot = CatalogSnapshot(
        snapshot_id="empty_snap",
        digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        created_at="2026-08-23T00:00:00Z",
        bindings=(),
    )
    search_adapter = GovernedCapabilitySearch(snapshot=snapshot)

    context = PolicyRequestContext(
        authenticated=True,
        skill_id="hermes-personal-product-research",
        workflow_id="product_research",
    )

    with pytest.raises(CapabilityError) as exc_info:
        search_adapter.describe("product.research", context=context)

    assert exc_info.value.code == "binding_unavailable"
