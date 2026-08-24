from __future__ import annotations

import re
import uuid
from typing import Sequence

from hermes_personal.learning.models import (
    CandidateEvaluation,
    EvaluationDecision,
    LearningCandidate,
    TaskOutcome,
)

# Common patterns for sensitive data detection
SENSITIVE_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z\s]+PRIVATE KEY-----", re.IGNORECASE),
    re.compile(r"(?:api[_-]?key|access[_-]?token|auth[_-]?token|secret[_-]?key)\s*(?::=|=|:)\s*['\"]?[A-Za-z0-9_\-\.]{8,}['\"]?", re.IGNORECASE),
    re.compile(r"(?:password|passwd|pwd|secret)\s*(?::=|=|:)\s*['\"][^'\"]+['\"]", re.IGNORECASE),
    re.compile(r"\bsk-[a-zA-Z0-9]{20,}\b"),
    re.compile(r"\bghp_[a-zA-Z0-9]{20,}\b"),
    re.compile(r"\bbearer\s+[a-zA-Z0-9_\-\.]{25,}\b", re.IGNORECASE),
]



class CandidateEvaluator:
    """Evaluates learning candidates against deterministic governance and safety policies."""

    def __init__(
        self,
        evaluator_name: str = "default_policy_evaluator",
        min_auto_score: float = 0.8,
        min_approval_score: float = 0.7,
    ) -> None:
        self.evaluator_name = evaluator_name
        self.min_auto_score = min_auto_score
        self.min_approval_score = min_approval_score

    def _contains_sensitive_data(self, text: str) -> bool:
        return any(pattern.search(text) for pattern in SENSITIVE_PATTERNS)

    def evaluate(
        self,
        candidate: LearningCandidate,
        source_outcome: TaskOutcome | None = None,
        corrections: Sequence[str] | None = None,
        latency_ms: float | None = None,
        cost_minor_units: int | None = None,
    ) -> CandidateEvaluation:
        eval_id = f"eval_{uuid.uuid4().hex[:12]}"

        # 1. Check for sensitive information
        combined_text = f"{candidate.title}\n{candidate.content}"
        if self._contains_sensitive_data(combined_text):
            return CandidateEvaluation(
                evaluation_id=eval_id,
                candidate_id=candidate.candidate_id,
                evaluator_name=self.evaluator_name,
                decision="reject",
                score=0.0,
                reason="Sensitive data or credentials detected in candidate",
                evidence_summary="Rejected due to sensitive data pattern match",
            )

        # 2. Check evidence existence and validity
        if not candidate.evidence:
            return CandidateEvaluation(
                evaluation_id=eval_id,
                candidate_id=candidate.candidate_id,
                evaluator_name=self.evaluator_name,
                decision="reject",
                score=0.0,
                reason="Candidate missing required evidence",
                evidence_summary="No evidence references provided",
            )

        # Check evidence digests and polarity
        for ev in candidate.evidence:
            if not ev.digest or not ev.excerpt:
                return CandidateEvaluation(
                    evaluation_id=eval_id,
                    candidate_id=candidate.candidate_id,
                    evaluator_name=self.evaluator_name,
                    decision="reject",
                    score=0.0,
                    reason="Candidate contains invalid evidence reference (empty digest or excerpt)",
                    evidence_summary="Invalid evidence reference format",
                )
            if ev.polarity != "positive":
                return CandidateEvaluation(
                    evaluation_id=eval_id,
                    candidate_id=candidate.candidate_id,
                    evaluator_name=self.evaluator_name,
                    decision="reject",
                    score=0.0,
                    reason="Negative evidence cannot support positive learning candidate",
                    evidence_summary=f"Evidence {ev.evidence_id} has negative polarity",
                )

        # 3. Check source task outcome
        if source_outcome is not None:
            if source_outcome.status != "success":
                return CandidateEvaluation(
                    evaluation_id=eval_id,
                    candidate_id=candidate.candidate_id,
                    evaluator_name=self.evaluator_name,
                    decision="reject",
                    score=0.0,
                    reason=f"Source outcome status is {source_outcome.status}; positive learning requires successful outcome",
                    evidence_summary=f"Failed source outcome {source_outcome.outcome_id}",
                )

        # 4. Base score computation
        score = 1.0
        if corrections:
            # Deduct for corrections
            score -= 0.1 * min(len(corrections), 4)

        evidence_count = len(candidate.evidence)
        evidence_summary = f"Validated {evidence_count} evidence item(s) from {[e.source_type for e in candidate.evidence]}"

        # 5. Evaluate based on candidate kind
        if candidate.kind == "preference":
            has_explicit_feedback = any(
                e.source_type in ("feedback", "turn") for e in candidate.evidence
            )
            if has_explicit_feedback and score >= self.min_auto_score:
                decision: EvaluationDecision = "eligible_auto"
                reason = "Explicit owner preference with verified evidence meets auto-promotion criteria"
            elif score >= self.min_approval_score:
                decision = "needs_approval"
                reason = "Preference requires owner confirmation"
            else:
                decision = "reject"
                reason = "Preference confidence below acceptable threshold"

        elif candidate.kind in ("knowledge", "procedure"):
            # Knowledge and procedures NEVER auto-promote; they always require approval
            if score >= self.min_approval_score:
                decision = "needs_approval"
                reason = f"{candidate.kind.capitalize()} candidate validated with evidence; requires owner approval"
            else:
                decision = "reject"
                reason = f"{candidate.kind.capitalize()} score ({score:.2f}) below required threshold"
        else:
            decision = "reject"
            reason = f"Unknown candidate kind '{candidate.kind}'"

        return CandidateEvaluation(
            evaluation_id=eval_id,
            candidate_id=candidate.candidate_id,
            evaluator_name=self.evaluator_name,
            decision=decision,
            score=max(0.0, min(1.0, score)),
            reason=reason,
            evidence_summary=evidence_summary,
        )
