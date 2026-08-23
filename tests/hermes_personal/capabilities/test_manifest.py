from __future__ import annotations

import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES, CapabilitySpec


EXPECTED_CAPABILITIES = {
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


def test_initial_manifest_has_exact_cutover_capabilities():
    assert set(INITIAL_CAPABILITIES.keys()) == EXPECTED_CAPABILITIES
    assert "note.create" not in INITIAL_CAPABILITIES
    assert all(
        spec.input_schema_version == "1.0" for spec in INITIAL_CAPABILITIES.values()
    )
    assert all(
        spec.output_schema_version == "1.0" for spec in INITIAL_CAPABILITIES.values()
    )


def test_manifest_entries_are_immutable_and_validated():
    spec = INITIAL_CAPABILITIES["product.research"]
    assert isinstance(spec, CapabilitySpec)
    assert spec.owner == "product_intelligence"
    assert spec.approval_policy == "none"
    assert spec.risk == "low"
    assert spec.cost_class == "free"

    with pytest.raises(AttributeError):
        spec.risk = "high"  # type: ignore[misc]

    with pytest.raises(ValueError, match="capability_id must not be blank"):
        CapabilitySpec(
            capability_id=" ",
            owner="owner",
            input_schema_version="1.0",
            output_schema_version="1.0",
            allowed_skills=(),
            allowed_workflows=(),
            approval_policy="none",
            risk="low",
            cost_class="free",
        )


def test_implementation_binding_immutability_and_validation():
    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="mcp__product_intelligence__research_product",
        source="hermes_mcp",
        provider="product_intelligence",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:1234",
        health="healthy",
    )
    assert binding.wire_name == "mcp__product_intelligence__research_product"

    with pytest.raises(ValueError, match="schema_digest must not be blank"):
        ImplementationBinding(
            capability_id="product.research",
            wire_name="mcp__product_intelligence__research_product",
            source="hermes_mcp",
            provider="product_intelligence",
            implementation_version="1.0.0",
            input_schema_version="1.0",
            output_schema_version="1.0",
            schema_digest="",
            health="healthy",
        )
