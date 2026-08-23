from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from hermes_personal.capabilities.bindings import ImplementationBinding
from hermes_personal.capabilities.errors import CapabilityError
from hermes_personal.capabilities.manifest import CapabilitySpec


@dataclass(frozen=True)
class PolicyRequestContext:
    skill_id: str | None = None
    workflow_id: str | None = None
    authenticated: bool = True
    user_confirmed_approval: bool = False
    budget_available: float | None = None
    channel_id: str | None = None
    session_id: str | None = None


@dataclass(frozen=True)
class PolicyWarning:
    code: str
    message: str


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    capability_id: str
    error: CapabilityError | None = None
    warnings: tuple[PolicyWarning, ...] = ()


class CapabilityPolicyEvaluator:
    def evaluate(
        self,
        spec: CapabilitySpec,
        binding: ImplementationBinding,
        context: PolicyRequestContext,
    ) -> PolicyDecision:
        cap_id = spec.capability_id

        # 1. Health check - unavailable
        if binding.health == "unavailable":
            err = CapabilityError(
                code="binding_unavailable",
                message=f"Capability {cap_id!r} binding is unavailable (wire={binding.wire_name!r})",
                retryable=True,
                capability_id=cap_id,
                actionable_recovery="Check underlying MCP server health or re-run discovery",
                details={"wire_name": binding.wire_name, "provider": binding.provider},
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 2. Schema version match check
        if (
            binding.input_schema_version != spec.input_schema_version
            or binding.output_schema_version != spec.output_schema_version
        ):
            err = CapabilityError(
                code="schema_version_mismatch",
                message=(
                    f"Capability {cap_id!r} schema version mismatch: "
                    f"binding=(in:{binding.input_schema_version}, out:{binding.output_schema_version}), "
                    f"spec=(in:{spec.input_schema_version}, out:{spec.output_schema_version})"
                ),
                retryable=False,
                capability_id=cap_id,
                actionable_recovery="Update implementation binding to match manifest schema version",
                details={
                    "binding_input": binding.input_schema_version,
                    "binding_output": binding.output_schema_version,
                    "spec_input": spec.input_schema_version,
                    "spec_output": spec.output_schema_version,
                },
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 3. Skill authorization check
        if context.skill_id is not None and context.skill_id not in spec.allowed_skills:
            err = CapabilityError(
                code="unauthorized_skill",
                message=f"Skill {context.skill_id!r} is not allowed to use capability {cap_id!r}",
                retryable=False,
                capability_id=cap_id,
                actionable_recovery="Add skill to spec.allowed_skills if access is intended",
                details={"skill_id": context.skill_id, "allowed_skills": list(spec.allowed_skills)},
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 4. Workflow authorization check
        if (
            context.workflow_id is not None
            and context.workflow_id not in spec.allowed_workflows
        ):
            err = CapabilityError(
                code="unauthorized_workflow",
                message=f"Workflow {context.workflow_id!r} is not allowed to use capability {cap_id!r}",
                retryable=False,
                capability_id=cap_id,
                actionable_recovery="Add workflow to spec.allowed_workflows if access is intended",
                details={
                    "workflow_id": context.workflow_id,
                    "allowed_workflows": list(spec.allowed_workflows),
                },
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 5. Approval / Precondition check
        requires_approval = spec.approval_policy != "none" and spec.approval_policy.startswith("hitl")
        if requires_approval and not context.user_confirmed_approval:
            err = CapabilityError(
                code="unmet_precondition",
                message=f"Capability {cap_id!r} requires explicit user approval before execution (policy={spec.approval_policy!r})",
                retryable=True,
                capability_id=cap_id,
                actionable_recovery="Solicit explicit user approval before executing capability",
                details={"approval_policy": spec.approval_policy},
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 6. Budget permission check
        if spec.cost_class in ("metered", "paid"):
            if context.budget_available is not None and context.budget_available <= 0:
                err = CapabilityError(
                    code="budget_exceeded",
                    message=f"Capability {cap_id!r} requires budget (cost_class={spec.cost_class!r}), but available budget is {context.budget_available}",
                    retryable=False,
                    capability_id=cap_id,
                    actionable_recovery="Allocate additional budget before calling capability",
                    details={"cost_class": spec.cost_class, "budget_available": context.budget_available},
                )
                return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 7. Degraded health check
        if binding.health == "degraded":
            if (
                spec.risk == "low"
                and spec.cost_class == "free"
                and not requires_approval
            ):
                warning = PolicyWarning(
                    code="degraded_capability_warning",
                    message=f"Capability {cap_id!r} is operating in degraded mode; results may be incomplete",
                )
                return PolicyDecision(
                    allowed=True,
                    capability_id=cap_id,
                    warnings=(warning,),
                )

            err = CapabilityError(
                code="degraded_policy_denied",
                message=f"Capability {cap_id!r} is degraded and cannot be executed due to risk/cost policy (risk={spec.risk!r}, cost_class={spec.cost_class!r})",
                retryable=True,
                capability_id=cap_id,
                actionable_recovery="Wait for MCP server recovery before executing degraded medium/high risk capability",
                details={"risk": spec.risk, "cost_class": spec.cost_class},
            )
            return PolicyDecision(allowed=False, capability_id=cap_id, error=err)

        # 8. Default Allow
        return PolicyDecision(allowed=True, capability_id=cap_id)
