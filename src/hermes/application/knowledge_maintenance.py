"""K4 Knowledge Maintenance service.

Implements:
- Source change detection via content hash
- Source version history
- needs_reanalysis marking (existing semantic extended)
- Conflict recording (open/resolved/dismissed)
- Revision proposal with lineage
- Supersession preserving old lesson
- History retrieval

Non-destructive: never deletes old lessons/sources/evidence.
HITL required for any state-changing operation on approved knowledge.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from hermes.utils.json_helpers import dump_json, load_json


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SourceVersion:
    version_id: str
    source_id: str
    content_hash: str
    version_number: int
    registered_at: str
    reference_uri: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Conflict:
    conflict_id: str
    lesson_id: str
    conflicting_lesson_id: str | None = None
    conflicting_source_id: str | None = None
    reason: str = ""
    status: str = "open"  # open | resolved | dismissed
    created_at: str = ""
    resolved_at: str | None = None
    resolution_note: str = ""


@dataclass(frozen=True)
class RevisionProposal:
    """A proposed revision to an existing lesson."""
    revision_id: str
    original_lesson_id: str
    proposed_title: str
    proposed_content: str
    proposed_key_lessons: tuple[str, ...] = ()
    proposed_category: str = ""
    reason: str = ""
    source_evidence: tuple[str, ...] = ()  # new source IDs
    status: str = "pending"  # pending | approved | rejected | superseded
    created_at: str = ""


class KnowledgeMaintenanceService:
    """K4 maintenance operations on existing knowledge state."""

    def __init__(self, db_connection_factory):
        self._db = db_connection_factory

    # ---- Source change detection ----

    def register_source_version(
        self,
        owner: str,
        source_id: str,
        content_text: str,
        reference_uri: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> SourceVersion:
        """Register a new source version; returns the version info.

        Idempotent: same content hash + same version_number returns existing.
        """
        new_hash = content_hash(content_text)
        with self._db() as conn:
            # Find current latest version_number for this source
            row = conn.execute(
                """
                SELECT MAX(version_number) AS max_v
                FROM source_versions
                WHERE owner_user_id = ? AND source_id = ?
                """,
                (owner, source_id),
            ).fetchone()
            max_v = row["max_v"] if row and row["max_v"] else 0
            next_v = max_v + 1
            
            # Check if same hash already exists
            existing = conn.execute(
                """
                SELECT version_id, version_number, registered_at, reference_uri, metadata_json
                FROM source_versions
                WHERE owner_user_id = ? AND source_id = ? AND content_hash = ?
                """,
                (owner, source_id, new_hash),
            ).fetchone()
            
            if existing:
                # Idempotent: return existing version
                return SourceVersion(
                    version_id=existing["version_id"],
                    source_id=source_id,
                    content_hash=new_hash,
                    version_number=existing["version_number"],
                    registered_at=existing["registered_at"],
                    reference_uri=existing["reference_uri"] or "",
                    metadata=_load_json(existing["metadata_json"], {}),
                )
            
            version_id = new_id("ver")
            now = utc_now()
            conn.execute(
                """
                INSERT INTO source_versions(
                    version_id, source_id, owner_user_id,
                    content_hash, version_number, registered_at,
                    reference_uri, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    version_id, source_id, owner,
                    new_hash, next_v, now,
                    reference_uri,
                    _dump_json(metadata or {}),
                ),
            )
            return SourceVersion(
                version_id=version_id,
                source_id=source_id,
                content_hash=new_hash,
                version_number=next_v,
                registered_at=now,
                reference_uri=reference_uri,
                metadata=metadata or {},
            )

    def detect_source_change(
        self,
        owner: str,
        source_id: str,
        new_content_text: str,
    ) -> dict[str, Any]:
        """Detect if a source content has changed; return change info."""
        new_hash = content_hash(new_content_text)
        with self._db() as conn:
            latest = conn.execute(
                """
                SELECT content_hash, version_number, registered_at
                FROM source_versions
                WHERE owner_user_id = ? AND source_id = ?
                ORDER BY version_number DESC LIMIT 1
                """,
                (owner, source_id),
            ).fetchone()
            
            if latest is None:
                return {"changed": None, "is_new": True, "new_hash": new_hash}
            
            changed = latest["content_hash"] != new_hash
            return {
                "changed": changed,
                "is_new": False,
                "previous_hash": latest["content_hash"],
                "previous_version": latest["version_number"],
                "previous_registered_at": latest["registered_at"],
                "new_hash": new_hash,
            }

    # ---- needs_reanalysis ----

    def mark_lesson_needs_reanalysis(
        self,
        owner: str,
        lesson_id: str,
        reason: str,
        actor: str,
        validation_error: str = "",
    ) -> bool:
        """Mark a lesson as needing reanalysis. Preserves approval status.

        Existing semantics: lesson remains approved but flagged.
        """
        with self._db() as conn:
            row = conn.execute(
                "SELECT id, status, needs_reanalysis FROM lessons WHERE id = ? AND owner_user_id = ?",
                (lesson_id, owner),
            ).fetchone()
            if not row:
                return False
            
            detail = _load_json(
                conn.execute(
                    "SELECT detail_json FROM lessons WHERE id = ?", (lesson_id,)
                ).fetchone()["detail_json"],
                {},
            )
            detail["needs_reanalysis"] = True
            detail["reanalysis_reason"] = reason
            if validation_error:
                detail["validation_error"] = validation_error
            detail.setdefault("reanalysis_count", 0)
            detail["reanalysis_count"] += 1
            
            conn.execute(
                """
                UPDATE lessons
                SET needs_reanalysis = 1, detail_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_dump_json(detail), utc_now(), lesson_id),
            )
            conn.execute(
                """
                INSERT INTO lesson_events(lesson_id, action, actor_user_id, note, metadata_json, created_at)
                VALUES (?, 'reanalysis_requested', ?, ?, ?, ?)
                """,
                (lesson_id, actor or "", reason or "", _dump_json({"source": "k4_maintenance"}), utc_now()),
            )
            return True

    def list_needs_reanalysis(self, owner: str) -> list[dict[str, Any]]:
        """List lessons needing reanalysis for this owner."""
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT id, title, status, needs_reanalysis, updated_at, detail_json
                FROM lessons
                WHERE owner_user_id = ? AND needs_reanalysis = 1
                ORDER BY updated_at DESC
                """,
                (owner,),
            ).fetchall()
            return [
                {
                    "lesson_id": row["id"],
                    "title": row["title"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                    "detail": _load_json(row["detail_json"], {}),
                }
                for row in rows
            ]

    def clear_needs_reanalysis(
        self,
        owner: str,
        lesson_id: str,
        actor: str,
        reason: str,
    ) -> bool:
        """Clear needs_reanalysis flag. Requires explicit authorization (actor + reason)."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT id, status FROM lessons WHERE id = ? AND owner_user_id = ?",
                (lesson_id, owner),
            ).fetchone()
            if not row:
                return False
            
            detail = _load_json(
                conn.execute(
                    "SELECT detail_json FROM lessons WHERE id = ?", (lesson_id,)
                ).fetchone()["detail_json"],
                {},
            )
            detail["needs_reanalysis"] = False
            detail.pop("reanalysis_reason", None)
            detail.pop("validation_error", None)
            
            conn.execute(
                """
                UPDATE lessons
                SET needs_reanalysis = 0, detail_json = ?, updated_at = ?
                WHERE id = ?
                """,
                (_dump_json(detail), utc_now(), lesson_id),
            )
            conn.execute(
                """
                INSERT INTO lesson_events(lesson_id, action, actor_user_id, note, metadata_json, created_at)
                VALUES (?, 'reanalysis_cleared', ?, ?, ?, ?)
                """,
                (lesson_id, actor or "", reason or "", _dump_json({"source": "k4_maintenance"}), utc_now()),
            )
            return True

    # ---- Conflict model ----

    def record_conflict(
        self,
        owner: str,
        lesson_id: str,
        reason: str,
        conflicting_lesson_id: str | None = None,
        conflicting_source_id: str | None = None,
    ) -> Conflict | None:
        """Record a knowledge conflict. Idempotent on (lesson_id, conflicting_*).

        Returns Conflict with conflict_id, or None if lesson not owned by caller.
        """
        with self._db() as conn:
            # Verify owner has access to the lesson
            owner_row = conn.execute(
                "SELECT owner_user_id FROM lessons WHERE id = ?",
                (lesson_id,),
            ).fetchone()
            if not owner_row or owner_row["owner_user_id"] != owner:
                return None
            existing = conn.execute(
                """
                SELECT conflict_id, status, created_at FROM knowledge_conflicts
                WHERE owner_user_id = ? AND lesson_id = ?
                  AND (conflicting_lesson_id = ? OR (conflicting_lesson_id IS NULL AND ? IS NULL))
                  AND (conflicting_source_id = ? OR (conflicting_source_id IS NULL AND ? IS NULL))
                  AND status = 'open'
                LIMIT 1
                """,
                (owner, lesson_id, conflicting_lesson_id, conflicting_lesson_id,
                 conflicting_source_id, conflicting_source_id),
            ).fetchone()
            
            if existing:
                return Conflict(
                    conflict_id=existing["conflict_id"],
                    lesson_id=lesson_id,
                    conflicting_lesson_id=conflicting_lesson_id,
                    conflicting_source_id=conflicting_source_id,
                    reason=reason,
                    status=existing["status"],
                    created_at=existing["created_at"],
                )
            
            conflict_id = new_id("conf")
            now = utc_now()
            conn.execute(
                """
                INSERT INTO knowledge_conflicts(
                    conflict_id, owner_user_id, lesson_id,
                    conflicting_lesson_id, conflicting_source_id,
                    reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?)
                """,
                (conflict_id, owner, lesson_id, conflicting_lesson_id, conflicting_source_id, reason, now),
            )
            return Conflict(
                conflict_id=conflict_id,
                lesson_id=lesson_id,
                conflicting_lesson_id=conflicting_lesson_id,
                conflicting_source_id=conflicting_source_id,
                reason=reason,
                status="open",
                created_at=now,
            )

    def list_open_conflicts(self, owner: str) -> list[dict[str, Any]]:
        """List open conflicts for owner."""
        with self._db() as conn:
            rows = conn.execute(
                """
                SELECT conflict_id, lesson_id, conflicting_lesson_id,
                       conflicting_source_id, reason, status, created_at
                FROM knowledge_conflicts
                WHERE owner_user_id = ? AND status = 'open'
                ORDER BY created_at DESC
                """,
                (owner,),
            ).fetchall()
            return [dict(row) for row in rows]

    def resolve_conflict(
        self,
        owner: str,
        conflict_id: str,
        actor: str,
        resolution_note: str = "",
    ) -> bool:
        """Resolve a conflict (mark resolved). Requires explicit actor."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT status FROM knowledge_conflicts WHERE conflict_id = ? AND owner_user_id = ?",
                (conflict_id, owner),
            ).fetchone()
            if not row:
                return False
            
            conn.execute(
                """
                UPDATE knowledge_conflicts
                SET status = 'resolved', resolved_at = ?, resolution_note = ?
                WHERE conflict_id = ?
                """,
                (utc_now(), resolution_note, conflict_id),
            )
            return True

    def dismiss_conflict(
        self,
        owner: str,
        conflict_id: str,
        actor: str,
        resolution_note: str = "",
    ) -> bool:
        """Dismiss a conflict (mark as not-real). Requires explicit actor."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT status FROM knowledge_conflicts WHERE conflict_id = ? AND owner_user_id = ?",
                (conflict_id, owner),
            ).fetchone()
            if not row:
                return False
            
            conn.execute(
                """
                UPDATE knowledge_conflicts
                SET status = 'dismissed', resolved_at = ?, resolution_note = ?
                WHERE conflict_id = ?
                """,
                (utc_now(), resolution_note, conflict_id),
            )
            return True

    # ---- Revision / supersession ----

    def create_revision_proposal(
        self,
        owner: str,
        original_lesson_id: str,
        proposed_title: str,
        proposed_content: str,
        reason: str,
        actor: str,
        proposed_key_lessons: tuple[str, ...] = (),
        proposed_category: str = "",
        source_evidence: tuple[str, ...] = (),
    ) -> RevisionProposal | None:
        """Create a revision proposal for an existing lesson.

        Returns None if original lesson not found.
        Proposal is stored in detail_json of the original lesson and pending.
        """
        revision_id = new_id("rev")
        now = utc_now()
        with self._db() as conn:
            row = conn.execute(
                "SELECT id, title, category, key_lessons_json, summary, content, detail_json FROM lessons WHERE id = ? AND owner_user_id = ?",
                (original_lesson_id, owner),
            ).fetchone()
            if not row:
                return None
            
            proposal = RevisionProposal(
                revision_id=revision_id,
                original_lesson_id=original_lesson_id,
                proposed_title=proposed_title,
                proposed_content=proposed_content,
                proposed_key_lessons=proposed_key_lessons,
                proposed_category=proposed_category or row["category"],
                reason=reason,
                source_evidence=source_evidence,
                status="pending",
                created_at=now,
            )
            
            # Store in detail_json under revision_proposals
            detail = _load_json(row["detail_json"], {})
            detail.setdefault("revision_proposals", [])
            detail["revision_proposals"].append({
                "revision_id": revision_id,
                "proposed_title": proposed_title,
                "proposed_content": proposed_content,
                "proposed_key_lessons": list(proposed_key_lessons),
                "proposed_category": proposed_category,
                "reason": reason,
                "source_evidence": list(source_evidence),
                "status": "pending",
                "created_at": now,
                "actor": actor,
            })
            
            conn.execute(
                "UPDATE lessons SET detail_json = ?, updated_at = ? WHERE id = ?",
                (_dump_json(detail), now, original_lesson_id),
            )
            conn.execute(
                """
                INSERT INTO lesson_events(lesson_id, action, actor_user_id, note, metadata_json, created_at)
                VALUES (?, 'revision_proposed', ?, ?, ?, ?)
                """,
                (
                    original_lesson_id, actor or "", reason or "",
                    _dump_json({"revision_id": revision_id}),
                    now,
                ),
            )
            return proposal

    def list_revision_proposals(
        self,
        owner: str,
        lesson_id: str | None = None,
        status: str = "pending",
    ) -> list[dict[str, Any]]:
        """List revision proposals."""
        with self._db() as conn:
            if lesson_id:
                rows = conn.execute(
                    """
                    SELECT id, detail_json FROM lessons
                    WHERE id = ? AND owner_user_id = ?
                    """,
                    (lesson_id, owner),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, detail_json FROM lessons WHERE owner_user_id = ?",
                    (owner,),
                ).fetchall()
            
            proposals = []
            for row in rows:
                detail = _load_json(row["detail_json"], {})
                for p in detail.get("revision_proposals", []):
                    if status is None or p.get("status") == status:
                        p["lesson_id"] = row["id"]
                        proposals.append(p)
            return proposals

    def supersede_lesson(
        self,
        owner: str,
        old_lesson_id: str,
        new_lesson_id: str,
        reason: str,
        actor: str,
    ) -> bool:
        """Mark old lesson as superseded by new lesson. Non-destructive.

        Old lesson remains in DB but flagged superseded_by and is_current=0.
        """
        with self._db() as conn:
            old_row = conn.execute(
                "SELECT id FROM lessons WHERE id = ? AND owner_user_id = ?",
                (old_lesson_id, owner),
            ).fetchone()
            new_row = conn.execute(
                "SELECT id FROM lessons WHERE id = ? AND owner_user_id = ?",
                (new_lesson_id, owner),
            ).fetchone()
            if not old_row or not new_row:
                return False
            
            now = utc_now()
            # Mark old as superseded
            conn.execute(
                """
                UPDATE lessons
                SET superseded_by = ?, superseded_at = ?, is_current = 0, updated_at = ?
                WHERE id = ?
                """,
                (new_lesson_id, now, now, old_lesson_id),
            )
            
            # Record lineage
            lineage_id = new_id("lin")
            conn.execute(
                """
                INSERT INTO lesson_supersession(
                    lineage_id, owner_user_id, old_lesson_id, new_lesson_id, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (lineage_id, owner, old_lesson_id, new_lesson_id, reason, now),
            )
            
            conn.execute(
                """
                INSERT INTO lesson_events(lesson_id, action, actor_user_id, note, metadata_json, created_at)
                VALUES (?, 'superseded', ?, ?, ?, ?)
                """,
                (old_lesson_id, actor or "", reason or "",
                 _dump_json({"superseded_by": new_lesson_id}), now),
            )
            
            # Remove old from FTS, add new
            conn.execute("DELETE FROM lesson_fts WHERE lesson_id = ?", (old_lesson_id,))
            new_lesson_row = conn.execute(
                "SELECT * FROM lessons WHERE id = ?", (new_lesson_id,)
            ).fetchone()
            if new_lesson_row and new_lesson_row["status"] == "approved":
                from hermes.knowledge import build_lesson_fts_values
                conn.execute(
                    """
                    INSERT INTO lesson_fts(lesson_id, owner_user_id, title, summary, content, tags)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    build_lesson_fts_values(new_lesson_row),
                )
            
            return True

    def get_lesson_history(self, owner: str, lesson_id: str) -> dict[str, Any]:
        """Get full history of a lesson including supersession."""
        with self._db() as conn:
            row = conn.execute(
                "SELECT * FROM lessons WHERE id = ? AND owner_user_id = ?",
                (lesson_id, owner),
            ).fetchone()
            if not row:
                return {"found": False}
            
            events = conn.execute(
                """
                SELECT action, actor_user_id, note, metadata_json, created_at
                FROM lesson_events WHERE lesson_id = ?
                ORDER BY id
                """,
                (lesson_id,),
            ).fetchall()
            
            supersession_in = conn.execute(
                """
                SELECT old_lesson_id, new_lesson_id, reason, created_at
                FROM lesson_supersession
                WHERE new_lesson_id = ? AND owner_user_id = ?
                """,
                (lesson_id, owner),
            ).fetchall()
            
            supersession_out = conn.execute(
                """
                SELECT old_lesson_id, new_lesson_id, reason, created_at
                FROM lesson_supersession
                WHERE old_lesson_id = ? AND owner_user_id = ?
                """,
                (lesson_id, owner),
            ).fetchall()
            
            conflicts = conn.execute(
                """
                SELECT conflict_id, conflicting_lesson_id, conflicting_source_id,
                       reason, status, created_at, resolved_at, resolution_note
                FROM knowledge_conflicts
                WHERE lesson_id = ? AND owner_user_id = ?
                """,
                (lesson_id, owner),
            ).fetchall()
            
            return {
                "found": True,
                "lesson_id": lesson_id,
                "title": row["title"],
                "status": row["status"],
                "is_current": bool(row["is_current"]),
                "superseded_by": row["superseded_by"],
                "superseded_at": row["superseded_at"],
                "revision_of": row["revision_of"],
                "needs_reanalysis": bool(row["needs_reanalysis"]),
                "events": [dict(e) for e in events],
                "supersession_in": [dict(s) for s in supersession_in],
                "supersession_out": [dict(s) for s in supersession_out],
                "conflicts": [dict(c) for c in conflicts],
            }


# ---- JSON helpers ----

def _dump_json(value: Any) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str | None, fallback: Any) -> Any:
    import json
    try:
        parsed = json.loads(value or "")
    except (TypeError, json.JSONDecodeError):
        return fallback
    return parsed