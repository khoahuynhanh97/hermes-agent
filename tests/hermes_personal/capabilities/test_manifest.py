from __future__ import annotations

import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.manifest import (
    INITIAL_CAPABILITIES,
    CapabilitySpec,
    _build_initial_capabilities,
)


EXPECTED_MANIFEST_MATRIX: dict[str, dict[str, object]] = {
    "product.research": {
        "owner": "product_intelligence",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": (
            "hermes-personal-product-research",
            "hermes-personal-product-video-production",
        ),
        "allowed_workflows": ("product_research", "product_to_video"),
        "approval_policy": "none",
        "risk": "low",
        "cost_class": "free",
    },
    "product.resource_pack.build": {
        "owner": "product_intelligence",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": (
            "hermes-personal-product-research",
            "hermes-personal-product-video-production",
        ),
        "allowed_workflows": ("product_research", "product_to_video"),
        "approval_policy": "none",
        "risk": "medium",
        "cost_class": "metered",
    },
    "product.resource_pack.lock": {
        "owner": "product_intelligence",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": (
            "hermes-personal-product-research",
            "hermes-personal-product-video-production",
        ),
        "allowed_workflows": ("product_research", "product_to_video"),
        "approval_policy": "hitl:product_lock",
        "risk": "high",
        "cost_class": "free",
    },
    "video.brief.create": {
        "owner": "video_factory",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-product-video-production",),
        "allowed_workflows": ("product_to_video",),
        "approval_policy": "precondition:product_locked",
        "risk": "medium",
        "cost_class": "metered",
    },
    "video.scene_plan.create": {
        "owner": "video_factory",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-product-video-production",),
        "allowed_workflows": ("product_to_video",),
        "approval_policy": "precondition:brief_approved",
        "risk": "medium",
        "cost_class": "metered",
    },
    "video.storyboard.create": {
        "owner": "video_factory",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-product-video-production",),
        "allowed_workflows": ("product_to_video",),
        "approval_policy": "precondition:scene_approved",
        "risk": "medium",
        "cost_class": "paid",
    },
    "video.render": {
        "owner": "video_factory",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-product-video-production",),
        "allowed_workflows": ("product_to_video",),
        "approval_policy": "hitl:storyboard_and_budget",
        "risk": "high",
        "cost_class": "paid",
    },
    "video.export": {
        "owner": "video_factory",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-product-video-production",),
        "allowed_workflows": ("product_to_video",),
        "approval_policy": "hitl:final",
        "risk": "high",
        "cost_class": "paid",
    },
    "knowledge.candidate.create": {
        "owner": "learning",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": ("hermes-personal-knowledge-learning",),
        "allowed_workflows": ("knowledge_learning",),
        "approval_policy": "review_required",
        "risk": "medium",
        "cost_class": "free",
    },
    "knowledge.retrieve": {
        "owner": "learning",
        "input_schema_version": "1.0",
        "output_schema_version": "1.0",
        "allowed_skills": (
            "hermes-personal-product-research",
            "hermes-personal-product-video-production",
            "hermes-personal-knowledge-learning",
        ),
        "allowed_workflows": (
            "product_research",
            "product_to_video",
            "knowledge_learning",
        ),
        "approval_policy": "approved_only",
        "risk": "low",
        "cost_class": "free",
    },
}


def test_initial_manifest_has_exact_cutover_capabilities():
    assert set(INITIAL_CAPABILITIES.keys()) == set(EXPECTED_MANIFEST_MATRIX.keys())
    assert "note.create" not in INITIAL_CAPABILITIES


@pytest.mark.parametrize(
    "capability_id,expected", list(EXPECTED_MANIFEST_MATRIX.items())
)
def test_capability_spec_metadata_matrix(
    capability_id: str, expected: dict[str, object]
):
    spec = INITIAL_CAPABILITIES[capability_id]
    assert isinstance(spec, CapabilitySpec)
    assert spec.owner == expected["owner"]
    assert spec.input_schema_version == expected["input_schema_version"]
    assert spec.output_schema_version == expected["output_schema_version"]
    assert spec.allowed_skills == expected["allowed_skills"]
    assert spec.allowed_workflows == expected["allowed_workflows"]
    assert spec.approval_policy == expected["approval_policy"]
    assert spec.risk == expected["risk"]
    assert spec.cost_class == expected["cost_class"]


def test_manifest_entries_duplicate_id_raises_value_error():
    duplicate_entries = [
        INITIAL_CAPABILITIES["product.research"],
        INITIAL_CAPABILITIES["product.research"],
    ]
    with pytest.raises(
        ValueError,
        match="duplicate capability_id in manifest entries: product.research",
    ):
        _build_initial_capabilities(duplicate_entries)


def test_capability_spec_validation_and_immutability():
    spec = INITIAL_CAPABILITIES["product.research"]
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
