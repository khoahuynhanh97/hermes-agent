from __future__ import annotations

import pytest

from hermes_personal.learning.models import (
    EvidenceRef,
    LearningCandidate,
)
from hermes_personal.learning.repository import LearningRepository
from hermes_personal.learning.retrieval import ApprovedLearningRetriever
from hermes_personal.storage.sqlite import connect as sqlite_connect


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite_connect(tmp_path / "retrieval_test.db")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user1', 'User One', '2026-08-24T00:00:00Z')")
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user2', 'User Two', '2026-08-24T00:00:00Z')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_conn):
    return LearningRepository(db_conn)


@pytest.fixture
def retriever(repository):
    return ApprovedLearningRetriever(repository)


def sample_evidence():
    return EvidenceRef(
        evidence_id="ev_ret1",
        source_type="turn",
        source_id="turn_1",
        digest="sha256:123",
        excerpt="evidence text",
    )


def test_retrieval_strict_owner_isolation(repository, retriever):
    # Setup knowledge for user1
    c1 = LearningCandidate(
        candidate_id="c_u1",
        owner_user_id="user1",
        kind="knowledge",
        title="TikTok Hook Formula",
        content="Begin with high contrast motion",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(c1)
    repository.create_version("c_u1", "Begin with high contrast motion")

    # User1 retrieves
    u1_results = retriever.retrieve(owner_user_id="user1", query="TikTok motion")
    assert len(u1_results) == 1
    assert u1_results[0].title == "TikTok Hook Formula"

    # User2 retrieves with same query -> empty!
    u2_results = retriever.retrieve(owner_user_id="user2", query="TikTok motion")
    assert len(u2_results) == 0


def test_revoked_and_superseded_versions_excluded(repository, retriever):
    cand = LearningCandidate(
        candidate_id="c_ver",
        owner_user_id="user1",
        kind="knowledge",
        title="Video Scaling Pattern",
        content="Scale via fast cuts",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(cand)
    v1 = repository.create_version("c_ver", "Scale via fast cuts v1")
    repository.update_version_status(v1.version_id, "superseded")

    v2 = repository.create_version("c_ver", "Scale via fast cuts v2")
    repository.update_version_status(v2.version_id, "revoked")

    # Both v1 (superseded) and v2 (revoked) must not appear in active retrieval
    results = retriever.retrieve(owner_user_id="user1", query="Scale cuts")
    assert len(results) == 0


def test_rejected_candidate_excluded(repository, retriever):
    cand = LearningCandidate(
        candidate_id="c_rej",
        owner_user_id="user1",
        kind="knowledge",
        title="Unverified Strategy",
        content="Random speculation",
        evidence=(sample_evidence(),),
        status="rejected",
    )
    repository.create_candidate(cand)
    repository.create_version("c_rej", "Random speculation")

    results = retriever.retrieve(owner_user_id="user1", query="Unverified Strategy")
    assert len(results) == 0


def test_unrelated_query_returns_empty_for_knowledge(repository, retriever):
    cand = LearningCandidate(
        candidate_id="c_spec",
        owner_user_id="user1",
        kind="knowledge",
        title="E-commerce Pricing",
        content="Price below 29 dollars for impulse purchase",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(cand)
    repository.create_version("c_spec", "Price below 29 dollars for impulse purchase")

    results = retriever.retrieve(owner_user_id="user1", query="Quantum physics simulation")
    assert len(results) == 0
