from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Sequence

from hermes_personal.learning.models import (
    CandidateEvaluation,
    CandidateStatus,
    EvidenceRef,
    InvalidCandidate,
    InvalidVersion,
    LearningCandidate,
    LearningEvent,
    LearningRepositoryError,
    LearningVersion,
    TaskOutcome,
)


class LearningRepository:
    """Repository for governed learning candidates, versions, evidence, outcomes, evaluations, and audit events."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def record_task_outcome(self, outcome: TaskOutcome) -> None:
        existing = self.get_task_outcome(outcome.outcome_id)
        if existing:
            if (
                existing.source_type == outcome.source_type
                and existing.source_id == outcome.source_id
                and existing.status == outcome.status
                and existing.details == outcome.details
            ):
                return
            raise LearningRepositoryError(f"Task outcome '{outcome.outcome_id}' already recorded and is immutable")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO task_outcome (outcome_id, source_type, source_id, status, details_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    outcome.outcome_id,
                    outcome.source_type,
                    outcome.source_id,
                    outcome.status,
                    json.dumps({"details": outcome.details}),
                    outcome.created_at,
                ),
            )

    def get_task_outcome(self, outcome_id: str) -> TaskOutcome | None:
        cur = self._conn.execute(
            "SELECT outcome_id, source_type, source_id, status, details_json, created_at FROM task_outcome WHERE outcome_id = ?",
            (outcome_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        details = json.loads(row["details_json"]).get("details", "")
        return TaskOutcome(
            outcome_id=row["outcome_id"],
            source_type=row["source_type"],
            source_id=row["source_id"],
            status=row["status"],
            details=details,
            created_at=row["created_at"],
        )

    def create_candidate(self, candidate: LearningCandidate) -> LearningCandidate:
        if not candidate.owner_user_id:
            raise InvalidCandidate("Candidate must specify owner_user_id")
        if not candidate.evidence:
            raise InvalidCandidate("Candidate requires at least one evidence ref")

        for ev in candidate.evidence:
            if candidate.source_outcome_id:
                outcome = self.get_task_outcome(candidate.source_outcome_id)
                if outcome and outcome.status == "failure" and ev.polarity == "positive":
                    raise InvalidCandidate("Failed task outcome cannot be cited as positive evidence; requires successful outcome")

        status = candidate.status
        if candidate.kind in ("knowledge", "procedure") and status == "approved":
            status = "draft"

        digest = candidate.digest or candidate.compute_digest()

        cur = self._conn.execute(
            "SELECT candidate_id, owner_user_id, kind, title, content, digest, source_outcome_id, status, created_at FROM learning_candidate WHERE owner_user_id = ? AND kind = ? AND digest = ?",
            (candidate.owner_user_id, candidate.kind, digest),
        )
        existing = cur.fetchone()
        if existing:
            evidence_list = self.get_evidence_for_candidate(existing["candidate_id"])
            return LearningCandidate(
                candidate_id=existing["candidate_id"],
                owner_user_id=existing["owner_user_id"],
                kind=existing["kind"],
                title=existing["title"],
                content=existing["content"],
                digest=existing["digest"],
                source_outcome_id=existing["source_outcome_id"],
                status=existing["status"],
                created_at=existing["created_at"],
                evidence=tuple(evidence_list),
            )

        with self._conn:
            self._conn.execute(
                """
                INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at)
                VALUES (?, ?, ?)
                """,
                (candidate.owner_user_id, candidate.owner_user_id, datetime.now(timezone.utc).isoformat()),
            )
            self._conn.execute(
                """
                INSERT INTO learning_candidate (candidate_id, owner_user_id, kind, title, content, digest, source_outcome_id, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate.candidate_id,
                    candidate.owner_user_id,
                    candidate.kind,
                    candidate.title,
                    candidate.content,
                    digest,
                    candidate.source_outcome_id,
                    status,
                    candidate.created_at,
                ),
            )
            for ev in candidate.evidence:
                self._conn.execute(
                    """
                    INSERT INTO evidence_ref (evidence_id, candidate_id, source_type, source_id, digest, excerpt, polarity, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ev.evidence_id,
                        candidate.candidate_id,
                        ev.source_type,
                        ev.source_id,
                        ev.digest,
                        ev.excerpt,
                        ev.polarity,
                        ev.created_at,
                    ),
                )
            self._conn.execute(
                """
                INSERT INTO learning_event (event_id, candidate_id, version_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    candidate.candidate_id,
                    None,
                    "candidate_created",
                    json.dumps({"title": candidate.title, "kind": candidate.kind, "status": status}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        return LearningCandidate(
            candidate_id=candidate.candidate_id,
            owner_user_id=candidate.owner_user_id,
            kind=candidate.kind,
            title=candidate.title,
            content=candidate.content,
            digest=digest,
            source_outcome_id=candidate.source_outcome_id,
            status=status,
            created_at=candidate.created_at,
            evidence=candidate.evidence,
        )

    def get_candidate(self, candidate_id: str) -> LearningCandidate | None:
        cur = self._conn.execute(
            "SELECT candidate_id, owner_user_id, kind, title, content, digest, source_outcome_id, status, created_at FROM learning_candidate WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        evidence = self.get_evidence_for_candidate(candidate_id)
        return LearningCandidate(
            candidate_id=row["candidate_id"],
            owner_user_id=row["owner_user_id"],
            kind=row["kind"],
            title=row["title"],
            content=row["content"],
            digest=row["digest"],
            source_outcome_id=row["source_outcome_id"],
            status=row["status"],
            created_at=row["created_at"],
            evidence=tuple(evidence),
        )

    def update_candidate_status(self, candidate_id: str, new_status: CandidateStatus) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE learning_candidate SET status = ? WHERE candidate_id = ?",
                (new_status, candidate_id),
            )
            self._conn.execute(
                """
                INSERT INTO learning_event (event_id, candidate_id, version_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    candidate_id,
                    None,
                    "status_updated",
                    json.dumps({"status": new_status}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_evidence_for_candidate(self, candidate_id: str) -> list[EvidenceRef]:
        cur = self._conn.execute(
            "SELECT evidence_id, source_type, source_id, digest, excerpt, polarity, created_at FROM evidence_ref WHERE candidate_id = ?",
            (candidate_id,),
        )
        return [
            EvidenceRef(
                evidence_id=r["evidence_id"],
                source_type=r["source_type"],
                source_id=r["source_id"],
                digest=r["digest"],
                excerpt=r["excerpt"],
                polarity=r["polarity"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def record_evaluation(self, evaluation: CandidateEvaluation) -> CandidateEvaluation:
        cand = self.get_candidate(evaluation.candidate_id)
        if not cand:
            raise InvalidCandidate(f"Candidate '{evaluation.candidate_id}' not found for evaluation")
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO candidate_evaluation (evaluation_id, candidate_id, evaluator_name, decision, score, reason, evidence_summary, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evaluation.evaluation_id,
                    evaluation.candidate_id,
                    evaluation.evaluator_name,
                    evaluation.decision,
                    evaluation.score,
                    evaluation.reason,
                    evaluation.evidence_summary,
                    evaluation.created_at,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO learning_event (event_id, candidate_id, version_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    evaluation.candidate_id,
                    None,
                    "evaluation_recorded",
                    json.dumps({
                        "evaluator": evaluation.evaluator_name,
                        "decision": evaluation.decision,
                        "score": evaluation.score,
                        "reason": evaluation.reason,
                    }),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return evaluation

    def get_evaluations_for_candidate(self, candidate_id: str) -> list[CandidateEvaluation]:
        cur = self._conn.execute(
            "SELECT evaluation_id, candidate_id, evaluator_name, decision, score, reason, evidence_summary, created_at FROM candidate_evaluation WHERE candidate_id = ? ORDER BY created_at ASC",
            (candidate_id,),
        )
        return [
            CandidateEvaluation(
                evaluation_id=r["evaluation_id"],
                candidate_id=r["candidate_id"],
                evaluator_name=r["evaluator_name"],
                decision=r["decision"],
                score=r["score"],
                reason=r["reason"],
                evidence_summary=r["evidence_summary"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def get_evaluation(self, evaluation_id: str) -> CandidateEvaluation | None:
        cur = self._conn.execute(
            "SELECT evaluation_id, candidate_id, evaluator_name, decision, score, reason, evidence_summary, created_at FROM candidate_evaluation WHERE evaluation_id = ?",
            (evaluation_id,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return CandidateEvaluation(
            evaluation_id=r["evaluation_id"],
            candidate_id=r["candidate_id"],
            evaluator_name=r["evaluator_name"],
            decision=r["decision"],
            score=r["score"],
            reason=r["reason"],
            evidence_summary=r["evidence_summary"],
            created_at=r["created_at"],
        )

    def create_version(
        self, candidate_id: str, content: str, *, expected_version: int | None = None,
    ) -> LearningVersion:
        cand = self.get_candidate(candidate_id)
        if not cand:
            raise InvalidVersion(f"Candidate '{candidate_id}' not found")

        cur = self._conn.execute(
            "SELECT MAX(version) as max_v FROM learning_version WHERE candidate_id = ?",
            (candidate_id,),
        )
        row = cur.fetchone()
        next_v = (row["max_v"] or 0) + 1

        digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()
        version_id = f"v_{candidate_id}_{next_v}"
        created_at = datetime.now(timezone.utc).isoformat()

        with self._conn:
            if expected_version is not None:
                # Acquire the writer lock before checking the approved version.
                self._conn.execute(
                    "UPDATE learning_candidate SET status = status WHERE candidate_id = ?",
                    (candidate_id,),
                )
                current = self._conn.execute(
                    "SELECT COALESCE(MAX(version), 0) FROM learning_version WHERE candidate_id = ?",
                    (candidate_id,),
                ).fetchone()[0]
                if current + 1 != expected_version or next_v != expected_version:
                    raise InvalidVersion("Approval version is stale")
                self._conn.execute(
                    "UPDATE learning_version SET status = 'superseded' "
                    "WHERE candidate_id = ? AND status = 'active'", (candidate_id,),
                )
                self._conn.execute(
                    "UPDATE learning_candidate SET status = 'approved' WHERE candidate_id = ?",
                    (candidate_id,),
                )
            self._conn.execute(
                """
                INSERT INTO learning_version (version_id, candidate_id, owner_user_id, version, content, digest, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id,
                    candidate_id,
                    cand.owner_user_id,
                    next_v,
                    content,
                    digest,
                    "active",
                    created_at,
                ),
            )
            self._conn.execute(
                """
                INSERT INTO learning_event (event_id, candidate_id, version_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    candidate_id,
                    version_id,
                    "version_created",
                    json.dumps({"version": next_v, "digest": digest}),
                    created_at,
                ),
            )

        # Index into FTS if candidate is approved
        if cand.status == "approved" or (expected_version is not None):
            self.index_version_fts(candidate_id, version_id)

        return LearningVersion(
            version_id=version_id,
            candidate_id=candidate_id,
            owner_user_id=cand.owner_user_id,
            version=next_v,
            content=content,
            digest=digest,
            status="active",
            created_at=created_at,
        )

    def get_version(self, version_id: str) -> LearningVersion | None:
        cur = self._conn.execute(
            "SELECT version_id, candidate_id, owner_user_id, version, content, digest, status, created_at FROM learning_version WHERE version_id = ?",
            (version_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return LearningVersion(
            version_id=row["version_id"],
            candidate_id=row["candidate_id"],
            owner_user_id=row["owner_user_id"],
            version=row["version"],
            content=row["content"],
            digest=row["digest"],
            status=row["status"],
            created_at=row["created_at"],
        )

    def get_versions_for_candidate(self, candidate_id: str) -> list[LearningVersion]:
        cur = self._conn.execute(
            "SELECT version_id, candidate_id, owner_user_id, version, content, digest, status, created_at FROM learning_version WHERE candidate_id = ? ORDER BY version ASC",
            (candidate_id,),
        )
        return [
            LearningVersion(
                version_id=r["version_id"],
                candidate_id=r["candidate_id"],
                owner_user_id=r["owner_user_id"],
                version=r["version"],
                content=r["content"],
                digest=r["digest"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def update_version_status(self, version_id: str, new_status: VersionStatus) -> None:
        version = self.get_version(version_id)
        if not version:
            raise InvalidVersion(f"Version '{version_id}' not found")
        with self._conn:
            self._conn.execute(
                "UPDATE learning_version SET status = ? WHERE version_id = ?",
                (new_status, version_id),
            )
            self._conn.execute(
                """
                INSERT INTO learning_event (event_id, candidate_id, version_id, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    f"evt_{uuid.uuid4().hex[:12]}",
                    version.candidate_id,
                    version_id,
                    f"version_{new_status}",
                    json.dumps({"old_status": version.status, "new_status": new_status}),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_active_versions_for_owner(
        self, owner_user_id: str, kind: LearningKind | None = None
    ) -> list[LearningVersion]:
        if kind:
            cur = self._conn.execute(
                """
                SELECT v.version_id, v.candidate_id, v.owner_user_id, v.version, v.content, v.digest, v.status, v.created_at
                FROM learning_version v
                JOIN learning_candidate c ON v.candidate_id = c.candidate_id
                WHERE v.owner_user_id = ? AND v.status = 'active' AND c.kind = ?
                ORDER BY v.created_at DESC
                """,
                (owner_user_id, kind),
            )
        else:
            cur = self._conn.execute(
                """
                SELECT version_id, candidate_id, owner_user_id, version, content, digest, status, created_at
                FROM learning_version
                WHERE owner_user_id = ? AND status = 'active'
                ORDER BY created_at DESC
                """,
                (owner_user_id,),
            )
        return [
            LearningVersion(
                version_id=r["version_id"],
                candidate_id=r["candidate_id"],
                owner_user_id=r["owner_user_id"],
                version=r["version"],
                content=r["content"],
                digest=r["digest"],
                status=r["status"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def get_events(self, candidate_id: str) -> list[LearningEvent]:
        cur = self._conn.execute(
            "SELECT event_id, candidate_id, version_id, event_type, payload_json, created_at FROM learning_event WHERE candidate_id = ? ORDER BY created_at ASC",
            (candidate_id,),
        )
        return [
            LearningEvent(
                event_id=r["event_id"],
                candidate_id=r["candidate_id"],
                version_id=r["version_id"],
                event_type=r["event_type"],
                payload_json=r["payload_json"],
                created_at=r["created_at"],
            )
            for r in cur.fetchall()
        ]

    def index_version_fts(self, candidate_id: str, version_id: str) -> None:
        """Index an approved learning version into the FTS5 knowledge index."""
        cand = self.get_candidate(candidate_id)
        version = self.get_version(version_id)
        if not cand or not version:
            return
        # Remove any existing FTS entry for this version and insert new one
        try:
            with self._conn:
                self._conn.execute(
                    "DELETE FROM knowledge_fts WHERE version_id = ?", (version_id,)
                )
                self._conn.execute(
                    """
                    INSERT INTO knowledge_fts (title, content, candidate_id, version_id, owner_user_id, kind)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (cand.title, version.content, candidate_id, version_id, version.owner_user_id, cand.kind),
                )
        except Exception:
            pass

    def search_fts(
        self, query: str, owner_user_id: str, kind: str | None = None, limit: int = 10
    ) -> list[tuple[str, str, str, str, float]]:
        """Full-text search over the knowledge FTS5 index.

        Returns list of (candidate_id, version_id, title, snippet, rank) tuples
        filtered by owner and optionally by kind.
        """
        if not query.strip():
            return []
        # Escape FTS5 special characters for safety
        safe_query = query.replace('"', '""')
        try:
            if kind:
                cur = self._conn.execute(
                    """
                    SELECT candidate_id, version_id, title,
                           snippet(knowledge_fts, 1, '<b>', '</b>', '...', 64) as snippet,
                           rank
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ? AND owner_user_id = ? AND kind = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (f'"{safe_query}"', owner_user_id, kind, limit),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT candidate_id, version_id, title,
                           snippet(knowledge_fts, 1, '<b>', '</b>', '...', 64) as snippet,
                           rank
                    FROM knowledge_fts
                    WHERE knowledge_fts MATCH ? AND owner_user_id = ?
                    ORDER BY rank
                    LIMIT ?
                    """,
                    (f'"{safe_query}"', owner_user_id, limit),
                )
            return [
                (row[0], row[1], row[2], row[3], row[4])
                for row in cur.fetchall()
            ]
        except Exception:
            return []
