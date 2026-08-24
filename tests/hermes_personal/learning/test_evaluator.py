from __future__ import annotations

import pytest

from hermes_personal.learning.evaluator import CandidateEvaluator
from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
    TaskOutcome,
)


@pytest.fixture
def evaluator():
    return CandidateEvaluator()


def sample_evidence(source_type="turn", polarity="positive", excerpt="Sample evidence excerpt"):
    return EvidenceRef(
        evidence_id="ev_1",
        source_type=source_type,
        source_id="turn_123",
        digest="sha256:abc123456",
        excerpt=excerpt,
        polarity=polarity,
    )


def test_knowledge_candidate_requires_approval_never_auto(evaluator):
    """Knowledge candidate with valid evidence must be evaluated as needs_approval, never eligible_auto."""
    candidate = LearningCandidate(
        candidate_id="cand_k1",
        owner_user_id="user1",
        kind="knowledge",
        title="TikTok Hook Optimization",
        content="Start with high energy visual within 2 seconds.",
        evidence=(sample_evidence(),),
    )
    evaluation = evaluator.evaluate(candidate)
    assert evaluation.decision == "needs_approval"
    assert evaluation.score >= 0.7
    assert "Knowledge candidate validated with evidence" in evaluation.reason


def test_procedure_candidate_requires_approval_never_auto(evaluator):
    """Procedure candidate with valid evidence and successful outcome requires approval."""
    outcome = TaskOutcome(
        outcome_id="out_1",
        source_type="workflow",
        source_id="wf_123",
        status="success",
    )
    candidate = LearningCandidate(
        candidate_id="cand_p1",
        owner_user_id="user1",
        kind="procedure",
        title="Video Generation Procedure",
        content="Step 1: Ingest product. Step 2: Render clips.",
        evidence=(sample_evidence(source_type="workflow"),),
        source_outcome_id="out_1",
    )
    evaluation = evaluator.evaluate(candidate, source_outcome=outcome)
    assert evaluation.decision == "needs_approval"
    assert evaluation.score >= 0.7


def test_preference_candidate_with_explicit_feedback_is_eligible_auto(evaluator):
    """Low-risk preference candidate with explicit feedback is eligible for auto-promotion."""
    candidate = LearningCandidate(
        candidate_id="cand_pref1",
        owner_user_id="user1",
        kind="preference",
        title="Preferred Tone",
        content="Always respond concisely in bullet points.",
        evidence=(sample_evidence(source_type="feedback"),),
    )
    evaluation = evaluator.evaluate(candidate)
    assert evaluation.decision == "eligible_auto"
    assert evaluation.score >= 0.8


def test_missing_evidence_is_rejected(evaluator):
    """Candidate with no evidence is rejected."""
    candidate = LearningCandidate(
        candidate_id="cand_no_ev",
        owner_user_id="user1",
        kind="knowledge",
        title="Unbacked claim",
        content="Some unbacked claim.",
        evidence=(),
    )
    evaluation = evaluator.evaluate(candidate)
    assert evaluation.decision == "reject"
    assert evaluation.score == 0.0
    assert "missing required evidence" in evaluation.reason


def test_invalid_evidence_digest_or_excerpt_is_rejected(evaluator):
    """Evidence with empty digest or empty excerpt is rejected."""
    invalid_ev = EvidenceRef(
        evidence_id="ev_inv",
        source_type="turn",
        source_id="t1",
        digest="",
        excerpt="text",
    )
    candidate = LearningCandidate(
        candidate_id="cand_inv_ev",
        owner_user_id="user1",
        kind="knowledge",
        title="Title",
        content="Content",
        evidence=(invalid_ev,),
    )
    evaluation = evaluator.evaluate(candidate)
    assert evaluation.decision == "reject"
    assert "invalid evidence reference" in evaluation.reason


def test_negative_evidence_polarity_is_rejected(evaluator):
    """Negative evidence cannot support positive learning candidate."""
    neg_ev = EvidenceRef(
        evidence_id="ev_neg",
        source_type="turn",
        source_id="t1",
        digest="sha256:123",
        excerpt="The action failed.",
        polarity="negative",
    )
    candidate = LearningCandidate(
        candidate_id="cand_neg",
        owner_user_id="user1",
        kind="knowledge",
        title="Title",
        content="Content",
        evidence=(neg_ev,),
    )
    evaluation = evaluator.evaluate(candidate)
    assert evaluation.decision == "reject"
    assert "Negative evidence" in evaluation.reason


def test_failed_source_outcome_is_rejected(evaluator):
    """Failed source task outcome causes rejection of positive learning."""
    failed_outcome = TaskOutcome(
        outcome_id="out_fail",
        source_type="workflow",
        source_id="wf_99",
        status="failure",
    )
    candidate = LearningCandidate(
        candidate_id="cand_failed_src",
        owner_user_id="user1",
        kind="procedure",
        title="Procedure from failed run",
        content="Do X then Y.",
        evidence=(sample_evidence(),),
        source_outcome_id="out_fail",
    )
    evaluation = evaluator.evaluate(candidate, source_outcome=failed_outcome)
    assert evaluation.decision == "reject"
    assert evaluation.score == 0.0
    assert "Source outcome status is failure" in evaluation.reason


def test_sensitive_data_detection(evaluator):
    """Candidates containing API keys, private keys, or passwords are automatically rejected."""
    sensitive_candidates = [
        LearningCandidate(
            candidate_id="cand_s1",
            owner_user_id="user1",
            kind="preference",
            title="API Key config",
            content="Use openai_api_key = 'sk-1234567890abcdef1234567890abcdef'",
            evidence=(sample_evidence(),),
        ),
        LearningCandidate(
            candidate_id="cand_s2",
            owner_user_id="user1",
            kind="knowledge",
            title="Private Key",
            content="-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----",
            evidence=(sample_evidence(),),
        ),
        LearningCandidate(
            candidate_id="cand_s3",
            owner_user_id="user1",
            kind="preference",
            title="Password record",
            content="My password := 'SuperSecretPassword123!'",
            evidence=(sample_evidence(),),
        ),
    ]

    for cand in sensitive_candidates:
        eval_result = evaluator.evaluate(cand)
        assert eval_result.decision == "reject"
        assert eval_result.score == 0.0
        assert "Sensitive data" in eval_result.reason
