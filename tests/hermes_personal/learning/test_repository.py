from __future__ import annotations

import sqlite3
import pytest

from hermes_personal.learning.models import (
    CandidateStatus,
    EvidenceRef,
    InvalidCandidate,
    InvalidVersion,
    LearningCandidate,
    LearningKind,
    LearningVersion,
    TaskOutcome,
    VersionStatus,
)
from hermes_personal.learning.repository import LearningRepository


@pytest.fixture
def db_conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "learning.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS global_user_identity (
            owner_user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_outcome (
            outcome_id TEXT PRIMARY KEY,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            status TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS learning_candidate (
            candidate_id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            digest TEXT NOT NULL,
            source_outcome_id TEXT,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(owner_user_id, kind, digest)
        );
        CREATE TABLE IF NOT EXISTS evidence_ref (
            evidence_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            digest TEXT NOT NULL,
            excerpt TEXT NOT NULL,
            polarity TEXT NOT NULL DEFAULT 'positive',
            created_at TEXT NOT NULL,
            FOREIGN KEY (candidate_id) REFERENCES learning_candidate(candidate_id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS learning_version (
            version_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            digest TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(candidate_id, version)
        );
        CREATE TABLE IF NOT EXISTS learning_event (
            event_id TEXT PRIMARY KEY,
            candidate_id TEXT NOT NULL,
            version_id TEXT,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        """
    )
    conn.execute("INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES ('user1', 'User One', '2026-08-24T00:00:00Z')")
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture
def repository(db_conn):
    return LearningRepository(db_conn)


def sample_evidence(source_id: str = "wf_1", polarity: str = "positive") -> EvidenceRef:
    return EvidenceRef(
        evidence_id=f"ev_{source_id}",
        source_type="workflow",
        source_id=source_id,
        digest="sha256:abc1234",
        excerpt="Successful product video rendering with ANC earbuds brief",
        polarity=polarity,
    )


def test_candidate_requires_owner_source_and_evidence(repository):
    """Prove that creating a candidate requires valid owner and at least one evidence ref."""
    # Missing evidence
    cand_no_evidence = LearningCandidate(
        candidate_id="cand_1",
        owner_user_id="user1",
        kind="knowledge",
        title="ANC brief standard",
        content="Always include ANC key features in TikTok briefs",
        evidence=(),
    )
    with pytest.raises(InvalidCandidate, match="evidence"):
        repository.create_candidate(cand_no_evidence)

    # Missing owner
    cand_no_owner = LearningCandidate(
        candidate_id="cand_2",
        owner_user_id="",
        kind="knowledge",
        title="ANC brief standard",
        content="Always include ANC key features in TikTok briefs",
        evidence=(sample_evidence(),),
    )
    with pytest.raises(InvalidCandidate, match="owner"):
        repository.create_candidate(cand_no_owner)


def test_failed_workflow_cannot_be_positive_evidence(repository):
    """Prove that positive evidence citing a failed task outcome is rejected."""
    outcome = TaskOutcome(
        outcome_id="out_failed_1",
        source_type="workflow",
        source_id="wf_failed",
        status="failure",
        details="Render timed out",
    )
    repository.record_task_outcome(outcome)

    cand = LearningCandidate(
        candidate_id="cand_failed_test",
        owner_user_id="user1",
        kind="knowledge",
        title="Failed knowledge",
        content="Some content",
        source_outcome_id="out_failed_1",
        evidence=(sample_evidence(source_id="wf_failed", polarity="positive"),),
    )
    with pytest.raises(InvalidCandidate, match="successful outcome"):
        repository.create_candidate(cand)


def test_versions_are_append_only(repository):
    """Prove that versions are append-only (1, 2, ...) and previous versions remain immutable."""
    cand = LearningCandidate(
        candidate_id="cand_vers",
        owner_user_id="user1",
        kind="knowledge",
        title="Scene planning patterns",
        content="Version 1 content",
        evidence=(sample_evidence(),),
        status="approved",
    )
    repository.create_candidate(cand)

    v1 = repository.create_version("cand_vers", content="Version 1 content")
    assert v1.version == 1
    assert v1.content == "Version 1 content"

    v2 = repository.create_version("cand_vers", content="Version 2 content updated")
    assert v2.version == 2
    assert v2.content == "Version 2 content updated"

    # Fetching v1 still yields original content
    fetched_v1 = repository.get_version(v1.version_id)
    assert fetched_v1 is not None
    assert fetched_v1.version == 1
    assert fetched_v1.content == "Version 1 content"


def test_digest_idempotency_for_candidate_creation(repository):
    """Prove that creating candidate with same (owner_user_id, kind, digest) returns existing record."""
    cand1 = LearningCandidate(
        candidate_id="cand_idemp_1",
        owner_user_id="user1",
        kind="knowledge",
        title="Tiktok hook structure",
        content="Hook in first 3 seconds",
        evidence=(sample_evidence(),),
    )
    created1 = repository.create_candidate(cand1)
    assert created1.candidate_id == "cand_idemp_1"

    # Second creation with same owner, kind, and content (same digest)
    cand2 = LearningCandidate(
        candidate_id="cand_idemp_2",
        owner_user_id="user1",
        kind="knowledge",
        title="Tiktok hook structure",
        content="Hook in first 3 seconds",
        evidence=(sample_evidence(),),
    )
    created2 = repository.create_candidate(cand2)
    # Returns existing candidate_id
    assert created2.candidate_id == "cand_idemp_1"


def test_knowledge_and_procedure_never_auto_approved(repository):
    """Prove that knowledge and procedure candidates are never created with auto-approved status."""
    cand_know = LearningCandidate(
        candidate_id="cand_k1",
        owner_user_id="user1",
        kind="knowledge",
        title="Video hook pattern",
        content="Use dynamic zooming in frame 1",
        evidence=(sample_evidence(),),
        status="approved",  # attempted auto-approval
    )
    created = repository.create_candidate(cand_know)
    # Repository forces draft/pending status for knowledge/procedure
    assert created.status != "approved"
    assert created.status == "draft"


def test_event_audit_logging(repository):
    """Prove that candidate creation, versioning, and status updates record immutable LearningEvents."""
    cand = LearningCandidate(
        candidate_id="cand_audit",
        owner_user_id="user1",
        kind="preference",
        title="Dark mode",
        content="Prefer dark mode previews",
        evidence=(sample_evidence(),),
    )
    repository.create_candidate(cand)
    events = repository.get_events("cand_audit")
    assert len(events) >= 1
    assert any(e.event_type == "candidate_created" for e in events)

    repository.update_candidate_status("cand_audit", "approved")
    events_after = repository.get_events("cand_audit")
    assert any(e.event_type == "status_updated" for e in events_after)
