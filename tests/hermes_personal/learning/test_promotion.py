from __future__ import annotations

import pytest

from hermes_personal.learning.models import (
    CandidateEvaluation,
    EvidenceRef,
    InvalidCandidate,
    InvalidVersion,
    LearningCandidate,
)
from hermes_personal.learning.promotion import PromotionService
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.storage.sqlite import connect as sqlite_connect
from hermes_personal.workflows.approvals import ApprovalService


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "promotion_test.db")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user1', 'User One', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user2', 'User Two', '2026-08-24T00:00:00Z')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_conn):
    return LearningRepository(db_conn)


@pytest.fixture
def approval_service(db_conn):
    return ApprovalService(db_conn)


@pytest.fixture
def promotion_service(repository, approval_service):
    return PromotionService(repository, approval_service)


def sample_evidence():
    return EvidenceRef(
        evidence_id="ev_p1",
        source_type="turn",
        source_id="turn_1",
        digest="sha256:abc",
        excerpt="sample excerpt",
    )


def test_preference_auto_promotes(promotion_service, repository):
    candidate = LearningCandidate(
        candidate_id="cand_pref",
        owner_user_id="user1",
        kind="preference",
        title="Brevity preference",
        content="Prefer concise responses",
        evidence=(sample_evidence(),),
    )
    evaluation = CandidateEvaluation(
        evaluation_id="eval_p1",
        candidate_id="cand_pref",
        evaluator_name="test_eval",
        decision="eligible_auto",
        score=0.95,
        reason="Explicit preference meets auto criteria",
    )
    result = promotion_service.request_promotion(candidate, evaluation)
    assert result.status == "promoted_auto"
    assert result.version is not None
    assert result.version.version == 1
    assert result.version.status == "active"

    active = promotion_service.active_versions("user1", kind="preference")
    assert len(active) == 1
    assert active[0].version_id == result.version.version_id


def test_knowledge_requires_owner_approval(promotion_service, repository):
    candidate = LearningCandidate(
        candidate_id="cand_know",
        owner_user_id="user1",
        kind="knowledge",
        title="Hook Strategy",
        content="Use 3-second visual punch",
        evidence=(sample_evidence(),),
    )
    evaluation = CandidateEvaluation(
        evaluation_id="eval_k1",
        candidate_id="cand_know",
        evaluator_name="test_eval",
        decision="needs_approval",
        score=0.85,
        reason="Valid knowledge requires owner approval",
    )
    result = promotion_service.request_promotion(candidate, evaluation)
    assert result.status == "pending_approval"
    assert result.approval_id is not None
    assert promotion_service.active_versions("user1", kind="knowledge") == ()

    # Now approve it
    promoted_v = promotion_service.approve_promotion(
        approval_id=result.approval_id,
        owner_user_id="user1",
        candidate_id="cand_know",
        expected_version=1,
    )
    assert promoted_v.version == 1
    assert promoted_v.status == "active"

    active = promotion_service.active_versions("user1", kind="knowledge")
    assert len(active) == 1
    assert active[0].version_id == promoted_v.version_id


def test_rollback_reactivates_prior_version_and_revokes_new(promotion_service, repository):
    # Setup v1
    candidate = LearningCandidate(
        candidate_id="cand_rb",
        owner_user_id="user1",
        kind="knowledge",
        title="Market Insight",
        content="Insight v1 content",
        evidence=(sample_evidence(),),
    )
    repository.create_candidate(candidate)
    v1 = repository.create_version("cand_rb", "Insight v1 content")
    assert v1.version == 1

    # Update candidate content and promote v2
    repository.update_version_status(v1.version_id, "superseded")
    v2 = repository.create_version("cand_rb", "Insight v2 updated content")
    assert v2.version == 2

    # Verify v2 is currently active
    active = promotion_service.active_versions("user1", kind="knowledge")
    assert len(active) == 1
    assert active[0].version_id == v2.version_id

    # Rollback v2
    rb_result = promotion_service.rollback(v2.version_id, owner_user_id="user1", expected_version=2)
    assert rb_result.revoked_version_id == v2.version_id
    assert rb_result.active_version_id == v1.version_id

    # Verify v1 is now active and v2 is revoked
    active_after = promotion_service.active_versions("user1", kind="knowledge")
    assert len(active_after) == 1
    assert active_after[0].version_id == v1.version_id

    v2_record = repository.get_version(v2.version_id)
    assert v2_record.status == "revoked"


def test_rollback_cross_owner_isolation(promotion_service, repository):
    candidate = LearningCandidate(
        candidate_id="cand_user1",
        owner_user_id="user1",
        kind="knowledge",
        title="Owner 1 Knowledge",
        content="Secret formula",
        evidence=(sample_evidence(),),
    )
    repository.create_candidate(candidate)
    v1 = repository.create_version("cand_user1", "Secret formula")

    with pytest.raises(InvalidVersion, match="does not match"):
        promotion_service.rollback(v1.version_id, owner_user_id="user2")
