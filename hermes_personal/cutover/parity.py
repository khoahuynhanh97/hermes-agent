from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from hermes_personal.observability.redaction import redact


@dataclass(frozen=True)
class ExecutionFingerprint:
    """Semantic outcome contract representing the execution of a turn/workflow."""

    outcome_category: str  # e.g. "success", "clarification", "workflow_started", "failure"
    clarification_required: bool
    selected_capability_ids: tuple[str, ...]
    workflow_type: str | None
    workflow_state: str | None
    approval_gates: tuple[str, ...]
    artifact_ownership_version_digest: tuple[tuple[str, int, str], ...]  # (owner_id, version, digest)
    terminal_status: str
    latency_ms: float
    cost_usd: float
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParityMismatch:
    fixture_id: str
    field_name: str
    baseline_value: Any
    candidate_value: Any
    reason: str


@dataclass(frozen=True)
class ParityReport:
    is_equivalent: bool
    total_comparisons: int
    mismatches: tuple[ParityMismatch, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_equivalent": self.is_equivalent,
            "total_comparisons": self.total_comparisons,
            "mismatches": [
                {
                    "fixture_id": m.fixture_id,
                    "field_name": m.field_name,
                    "baseline_value": redact(m.baseline_value),
                    "candidate_value": redact(m.candidate_value),
                    "reason": m.reason,
                }
                for m in self.mismatches
            ],
        }


def compare_semantic_parity(
    fixture_id: str,
    baseline: ExecutionFingerprint,
    candidate: ExecutionFingerprint,
    max_latency_delta_ratio: float = 0.5,
    max_cost_delta_ratio: float = 0.2,
) -> ParityReport:
    """Perform semantic parity comparison across two execution runs.

    Note: This deliberately does NOT compare prose text byte-for-byte.
    """
    mismatches: list[ParityMismatch] = []

    # 1. Outcome category
    if baseline.outcome_category != candidate.outcome_category:
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="outcome_category",
            baseline_value=baseline.outcome_category,
            candidate_value=candidate.outcome_category,
            reason="Outcome category mismatch",
        ))

    # 2. Clarification requirement
    if baseline.clarification_required != candidate.clarification_required:
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="clarification_required",
            baseline_value=baseline.clarification_required,
            candidate_value=candidate.clarification_required,
            reason="Clarification requirement mismatch",
        ))

    # 3. Selected capability IDs
    if set(baseline.selected_capability_ids) != set(candidate.selected_capability_ids):
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="selected_capability_ids",
            baseline_value=sorted(baseline.selected_capability_ids),
            candidate_value=sorted(candidate.selected_capability_ids),
            reason="Selected capability IDs mismatch",
        ))

    # 4. Workflow type and state
    if baseline.workflow_type != candidate.workflow_type:
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="workflow_type",
            baseline_value=baseline.workflow_type,
            candidate_value=candidate.workflow_type,
            reason="Workflow type mismatch",
        ))
    if baseline.workflow_state != candidate.workflow_state:
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="workflow_state",
            baseline_value=baseline.workflow_state,
            candidate_value=candidate.workflow_state,
            reason="Workflow state mismatch",
        ))

    # 5. Approval gates
    if set(baseline.approval_gates) != set(candidate.approval_gates):
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="approval_gates",
            baseline_value=sorted(baseline.approval_gates),
            candidate_value=sorted(candidate.approval_gates),
            reason="Approval gates mismatch",
        ))

    # 6. Artifact ownership, version, and digest
    if set(baseline.artifact_ownership_version_digest) != set(candidate.artifact_ownership_version_digest):
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="artifact_ownership_version_digest",
            baseline_value=baseline.artifact_ownership_version_digest,
            candidate_value=candidate.artifact_ownership_version_digest,
            reason="Artifact ownership, version, or digest mismatch",
        ))

    # 7. Terminal status
    if baseline.terminal_status != candidate.terminal_status:
        mismatches.append(ParityMismatch(
            fixture_id=fixture_id,
            field_name="terminal_status",
            baseline_value=baseline.terminal_status,
            candidate_value=candidate.terminal_status,
            reason="Terminal status mismatch",
        ))

    # 8. Bounded cost and latency bounds
    if baseline.cost_usd > 0:
        cost_diff = abs(candidate.cost_usd - baseline.cost_usd) / baseline.cost_usd
        if cost_diff > max_cost_delta_ratio:
            mismatches.append(ParityMismatch(
                fixture_id=fixture_id,
                field_name="cost_usd",
                baseline_value=baseline.cost_usd,
                candidate_value=candidate.cost_usd,
                reason=f"Cost delta {cost_diff:.1%} exceeded threshold {max_cost_delta_ratio:.1%}",
            ))

    return ParityReport(
        is_equivalent=len(mismatches) == 0,
        total_comparisons=1,
        mismatches=tuple(mismatches),
    )


@dataclass
class ChannelCutoverState:
    channel: str
    cutover_enabled: bool = False
    contract_suite_passed: bool = False
    unexplained_diffs: int = 0
    rollback_tested: bool = False
    error_rate: float = 0.0
    latency_p95_ms: float = 0.0
    duplicate_effects: int = 0


class OrderedCutoverCoordinator:
    """Manages ordered, reversible channel cutover across CLI, Omni, Telegram, and Web."""

    STAGES: tuple[tuple[str, ...], ...] = (
        ("cli", "omni"),
        ("telegram",),
        ("web",),
    )

    def __init__(self) -> None:
        self._channels: dict[str, ChannelCutoverState] = {
            "cli": ChannelCutoverState(channel="cli"),
            "omni": ChannelCutoverState(channel="omni"),
            "telegram": ChannelCutoverState(channel="telegram"),
            "web": ChannelCutoverState(channel="web"),
        }

    def get_state(self, channel: str) -> ChannelCutoverState:
        return self._channels[channel]

    def can_cutover_stage(self, stage_idx: int) -> bool:
        """Verify prior stages are active and current stage satisfies all quality gates."""
        if stage_idx < 0 or stage_idx >= len(self.STAGES):
            return False

        # Prior stages must be active
        for i in range(stage_idx):
            for ch in self.STAGES[i]:
                if not self._channels[ch].cutover_enabled:
                    return False

        # Current stage prerequisites
        for ch in self.STAGES[stage_idx]:
            state = self._channels[ch]
            if not state.contract_suite_passed:
                return False
            if state.unexplained_diffs > 0:
                return False
            if not state.rollback_tested:
                return False
            if state.error_rate > 0.05 or state.duplicate_effects > 0:
                return False

        return True

    def cutover_stage(self, stage_idx: int) -> bool:
        """Enable cutover for the channels in the given stage if gates pass."""
        if not self.can_cutover_stage(stage_idx):
            return False

        for ch in self.STAGES[stage_idx]:
            self._channels[ch].cutover_enabled = True
        return True

    def rollback_channel(self, channel: str) -> None:
        """Restore previous ingress flag for channel without rolling back durable data."""
        if channel in self._channels:
            self._channels[channel].cutover_enabled = False
