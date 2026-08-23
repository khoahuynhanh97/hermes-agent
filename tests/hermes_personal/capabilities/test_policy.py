from __future__ import annotations

import json
import pytest

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.capabilities.policy import (
    CapabilityPolicyEvaluator,
    PolicyRequestContext,
)


def _make_healthy_binding(cap_id: str) -> ImplementationBinding:
    spec = INITIAL_CAPABILITIES[cap_id]
    return ImplementationBinding(
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


@pytest.mark.parametrize("cap_id", sorted(INITIAL_CAPABILITIES.keys()))
def test_matrix_all_manifest_capabilities_happy_path(cap_id: str):
    spec = INITIAL_CAPABILITIES[cap_id]
    binding = _make_healthy_binding(cap_id)
    evaluator = CapabilityPolicyEvaluator()

    allowed_skill = next(iter(spec.allowed_skills))
    allowed_wf = next(iter(spec.allowed_workflows))

    context = PolicyRequestContext(
        skill_id=allowed_skill,
        workflow_id=allowed_wf,
        user_confirmed_approval=True,
        budget_available=10.0,
    )

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is True
    assert decision.capability_id == cap_id
    assert decision.error is None


def test_unavailable_binding_denied():
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="product_research_wire",
        source="hermes_mcp",
        provider="product_intelligence",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="unavailable",
    )
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext()

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "binding_unavailable"
    assert decision.error.retryable is True


def test_schema_version_mismatch_denied():
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="product_research_wire",
        source="hermes_mcp",
        provider="product_intelligence",
        implementation_version="1.0.0",
        input_schema_version="2.0",  # Mismatched input version
        output_schema_version="1.0",
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="healthy",
    )
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext()

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "schema_version_mismatch"
    assert decision.error.retryable is False


def test_unauthorized_skill_denied():
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = _make_healthy_binding("product.research")
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext(skill_id="unauthorized-skill-name")

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "unauthorized_skill"


def test_unauthorized_workflow_denied():
    spec = INITIAL_CAPABILITIES["product.research"]
    binding = _make_healthy_binding("product.research")
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext(workflow_id="unauthorized_workflow_name")

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "unauthorized_workflow"


def test_unmet_precondition_denied():
    spec = INITIAL_CAPABILITIES["video.render"]
    assert spec.approval_policy != "none"

    binding = _make_healthy_binding("video.render")
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext(user_confirmed_approval=False)

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "unmet_precondition"
    assert decision.error.retryable is True


def test_budget_exceeded_denied():
    spec = INITIAL_CAPABILITIES["video.render"]
    assert spec.cost_class == "paid"

    binding = _make_healthy_binding("video.render")
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext(
        user_confirmed_approval=True,
        budget_available=0.0,  # Exceeded / zero budget
    )

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "budget_exceeded"


def test_degraded_low_risk_free_allowed_with_warning():
    spec = INITIAL_CAPABILITIES["product.research"]
    assert spec.risk == "low"
    assert spec.cost_class == "free"
    assert spec.approval_policy == "none"

    binding = ImplementationBinding(
        capability_id="product.research",
        wire_name="product_research_wire",
        source="hermes_mcp",
        provider="product_intelligence",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="degraded",
    )
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext()

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is True
    assert len(decision.warnings) == 1
    assert decision.warnings[0].code == "degraded_capability_warning"


def test_degraded_medium_high_risk_or_metered_denied():
    spec = INITIAL_CAPABILITIES["video.render"]

    binding = ImplementationBinding(
        capability_id="video.render",
        wire_name="video_render_wire",
        source="hermes_mcp",
        provider="video_factory",
        implementation_version="1.0.0",
        input_schema_version="1.0",
        output_schema_version="1.0",
        schema_digest="sha256:0000000000000000000000000000000000000000000000000000000000000000",
        health="degraded",
    )
    evaluator = CapabilityPolicyEvaluator()
    context = PolicyRequestContext(user_confirmed_approval=True, budget_available=10.0)

    decision = evaluator.evaluate(spec, binding, context)
    assert decision.allowed is False
    assert decision.error is not None
    assert decision.error.code == "degraded_policy_denied"


def test_capability_error_serialization_and_redaction():
    err = CapabilityError(
        code="test_code",
        message="test message",
        retryable=True,
        capability_id="product.research",
        actionable_recovery="do something",
        details={
            "normal_prop": "normal_val",
            "api_key": "secret_12345",
            "auth_token": "token_abcde",
            "nested": {"user_secret": "my_secret"},
        },
    )

    as_dict = err.to_dict()
    assert as_dict["code"] == "test_code"
    assert as_dict["message"] == "test message"
    assert as_dict["retryable"] is True
    assert as_dict["capability_id"] == "product.research"
    assert as_dict["actionable_recovery"] == "do something"

    # Verify redaction
    assert as_dict["details"]["normal_prop"] == "normal_val"
    assert as_dict["details"]["api_key"] == "[REDACTED]"
    assert as_dict["details"]["auth_token"] == "[REDACTED]"
    assert as_dict["details"]["nested"]["user_secret"] == "[REDACTED]"

    # Verify JSON serializability
    json_str = json.dumps(as_dict)
    assert "test_code" in json_str
