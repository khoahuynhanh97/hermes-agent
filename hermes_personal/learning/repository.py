from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Sequence

from hermes_personal.learning.models import (
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
    """Repository for governed learning candidates, versions, evidence, outcomes, and audit events."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def record_task_outcome(self, outcome: TaskOutcome) -> None:
        with self._conn:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO task_outcome (outcome_id, source_type, source_id, status, details_json, created_at)
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
        # Validation rules:
        if not candidate.owner_user_id:
            raise InvalidCandidate("Candidate must specify owner_user_id")
        if not candidate.evidence:
            raise InvalidCandidate("Candidate requires at least one evidence ref")

        # Validate evidence against task outcome
        for ev in candidate.evidence:
            if candidate.source_outcome_id:
                outcome = self.get_task_outcome(candidate.source_outcome_id)
                if outcome and outcome.status == "failure" and ev.polarity == "positive":
                    raise InvalidCandidate("Failed task outcome cannot be cited as positive evidence; requires successful outcome")

        # Knowledge/procedure can never be created as auto-approved
        status = candidate.status
        if candidate.kind in ("knowledge", "procedure") and status == "approved":
            status = "draft"

        digest = candidate.digest or candidate.compute_digest()

        # Idempotent lookup by (owner_user_id, kind, digest)
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
            # Record audit event
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

    def create_version(self, candidate_id: str, content: str) -> LearningVersion:
        cand = self.get_candidate(candidate_id)
        if not cand:
            raise InvalidVersion(f"Candidate '{candidate_id}' not found")

        # Determine next append-only version number
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
