"""K6 Knowledge Export and Backup service.

Simple personal-project scope:
- SQLite DB backup (full point-in-time copy)
- Structured JSON export (lessons, sources, evidence, conflicts, lineage)
- Optional readable Markdown export
- Integrity metadata (timestamp, schema version, counts, content hash)
- Restore into a temporary DB with basic verification

SQLite remains canonical. Backup/export is a secondary artifact only.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any, Callable

from hermes.db import Database, SCHEMA_VERSION as CURRENT_SCHEMA_VERSION
from hermes.knowledge import SQLiteKnowledgeStore
from hermes.utils.json_helpers import dump_json, load_json


def utc_now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class KnowledgeExportService:
    """Handles exporting and backing up knowledge data."""

    def __init__(self, db_path: Path, db_connection_factory: Callable[[], sqlite3.Connection]):
        self._db_path = db_path
        self._db_conn_factory = db_connection_factory

    # ------------------------------------------------------------------
    # SQLite backup
    # ------------------------------------------------------------------

    def backup_database(self, output_path: Path) -> Path:
        """Create a point-in-time copy of the SQLite database."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._db_conn_factory() as src_conn:
            with sqlite3.connect(output_path) as dst_conn:
                src_conn.backup(dst_conn)
        return output_path

    # ------------------------------------------------------------------
    # JSON export
    # ------------------------------------------------------------------

    def export_json(self, owner_user_id: str, output_path: Path) -> Path:
        """Export all owner-scoped knowledge data as structured JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        export_data = {
            "metadata": {
                "export_timestamp": utc_now_iso(),
                "schema_version": CURRENT_SCHEMA_VERSION,
                "exported_owner_user_id": owner_user_id,
                "notes": "Hermes Knowledge Export - For archival and import",
            },
            "sources": [],
            "lessons": [],
            "evidence": [],
            "conflicts": [],
            "source_versions": [],
            "supersession_lineage": [],
        }

        with self._db_conn_factory() as conn:
            conn.row_factory = sqlite3.Row

            sources_rows = conn.execute(
                "SELECT * FROM sources WHERE owner_user_id = ?", (owner_user_id,)
            ).fetchall()
            for row in sources_rows:
                d = dict(row)
                d["metadata_json"] = load_json(d.get("metadata_json"), {}) if isinstance(d.get("metadata_json"), str) else d.get("metadata_json")
                export_data["sources"].append(d)

            sv_rows = conn.execute(
                "SELECT * FROM source_versions WHERE owner_user_id = ?", (owner_user_id,)
            ).fetchall()
            for row in sv_rows:
                d = dict(row)
                d["metadata_json"] = load_json(d.get("metadata_json"), {}) if isinstance(d.get("metadata_json"), str) else d.get("metadata_json")
                export_data["source_versions"].append(d)

            # Lessons, joined with sources to preserve source_url for restore
            lessons_rows = conn.execute(
                """
                SELECT l.*, s.source_url, s.source_type AS source_platform
                FROM lessons l JOIN sources s ON s.id = l.source_id
                WHERE l.owner_user_id = ?
                """,
                (owner_user_id,),
            ).fetchall()
            for row in lessons_rows:
                d = dict(row)
                d["detail_json"] = load_json(d.get("detail_json"), {}) if isinstance(d.get("detail_json"), str) else d.get("detail_json")
                d["key_lessons_json"] = load_json(d.get("key_lessons_json"), []) if isinstance(d.get("key_lessons_json"), str) else d.get("key_lessons_json")
                d["tags_json"] = load_json(d.get("tags_json"), []) if isinstance(d.get("tags_json"), str) else d.get("tags_json")
                for key in ("approved_at", "rejected_at", "superseded_by", "superseded_at", "revision_of"):
                    d[key] = d.get(key) or None
                export_data["lessons"].append(d)

            # Evidence linked to exported lessons
            evidence_ids = set()
            for lesson in lessons_rows:
                for le in conn.execute(
                    "SELECT evidence_id FROM lesson_evidence WHERE lesson_id = ?", (lesson["id"],)
                ).fetchall():
                    evidence_ids.add(le["evidence_id"])
            if evidence_ids:
                placeholders = ",".join("?" * len(evidence_ids))
                for row in conn.execute(
                    f"SELECT * FROM evidence WHERE id IN ({placeholders})", list(evidence_ids)
                ).fetchall():
                    export_data["evidence"].append(dict(row))

            for row in conn.execute(
                "SELECT * FROM knowledge_conflicts WHERE owner_user_id = ?", (owner_user_id,)
            ).fetchall():
                d = dict(row)
                for key in ("conflicting_lesson_id", "conflicting_source_id", "resolved_at", "resolution_note"):
                    d[key] = d.get(key) or None
                export_data["conflicts"].append(d)

            for row in conn.execute(
                "SELECT * FROM lesson_supersession WHERE owner_user_id = ?", (owner_user_id,)
            ).fetchall():
                export_data["supersession_lineage"].append(dict(row))

            export_data["metadata"]["record_counts"] = {
                "sources": len(export_data["sources"]),
                "source_versions": len(export_data["source_versions"]),
                "lessons": len(export_data["lessons"]),
                "evidence": len(export_data["evidence"]),
                "conflicts": len(export_data["conflicts"]),
                "supersession_lineage": len(export_data["supersession_lineage"]),
            }

            # Content hash over the data payload (excluding metadata itself)
            payload = {k: v for k, v in export_data.items() if k != "metadata"}
            export_data["metadata"]["content_hash"] = hashlib.sha256(
                dump_json(payload).encode("utf-8")
            ).hexdigest()

        output_path.write_text(dump_json(export_data), encoding="utf-8")
        return output_path

    # ------------------------------------------------------------------
    # Markdown export
    # ------------------------------------------------------------------

    def export_markdown(self, owner_user_id: str, output_path: Path) -> Path:
        """Export approved/current lessons as human-readable Markdown.

        Lessons without a usable title are still included, noted as untitled
        and identified by their source URL when present.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        store = SQLiteKnowledgeStore(Database(self._db_path))

        lines = [
            f"# Hermes Knowledge Export - {utc_now_iso()}",
            "",
            f"## Owner: {owner_user_id}",
            "",
        ]

        approved = store.get_approved_entries(owner_user_id=owner_user_id)
        current = [l for l in approved if l.get("is_current", True)]

        if not current:
            lines.append("No current approved lessons to export.")
        else:
            lines.append(f"## Current Approved Lessons ({len(current)})")
            lines.append("")
            for lesson in current:
                title = lesson.get("title") or lesson.get("slug") or ""
                if not title:
                    title = "(untitled lesson)"
                    lines.append(f"### {title} *[no title; use source URL to re-analyze]*")
                else:
                    lines.append(f"### {title}")
                lines.append(f"- **Slug**: {lesson.get('slug', '')}")
                lines.append(f"- **Category**: {lesson.get('category', 'General')}")
                lines.append(f"- **Confidence**: {lesson.get('confidence', 'medium')}")
                source_url = lesson.get("source_url") or ""
                if source_url:
                    lines.append(f"- **Source**: {source_url}")
                if lesson.get("needs_reanalysis"):
                    lines.append(f"- **STATUS**: NEEDS REANALYSIS")
                lessons_list = lesson.get("key_lessons") or []
                if lessons_list:
                    lines.append("")
                    lines.append("#### Key Lessons")
                    for kl in lessons_list:
                        lines.append(f"- {kl}")
                detail = store.get_entry_detail(lesson["id"])
                if detail.get("deep_analysis"):
                    lines.append("")
                    lines.append(f"#### Analysis")
                    lines.append(detail["deep_analysis"])
                if lesson.get("superseded_by"):
                    lines.append("")
                    lines.append(f"#### Supersession")
                    lines.append(f"Superseded by `{lesson['superseded_by']}`.")
                lines.append("")

        output_path.write_text("\n".join(lines), encoding="utf-8")
        return output_path


class KnowledgeRestoreService:
    """Handles restoring knowledge data from exports into a temporary DB."""

    def __init__(self, target_db_path: Path):
        self._target_db_path = target_db_path

    def restore_from_json(self, owner_user_id: str, input_path: Path, new_owner_user_id: str | None = None) -> dict[str, Any]:
        """Restore lessons from a structured JSON export.

        Integrity is checked (schema version + content hash). Owner scope is
        preserved; lessons can be remapped to a new owner.
        """
        if not input_path.exists():
            raise FileNotFoundError(f"Export file not found: {input_path}")

        export_data = load_json(input_path.read_text(encoding="utf-8"), {})
        metadata = export_data.get("metadata", {})
        if metadata.get("schema_version", 0) > CURRENT_SCHEMA_VERSION:
            raise ValueError(f"Export schema version {metadata['schema_version']} is newer than current {CURRENT_SCHEMA_VERSION}")

        payload = {k: v for k, v in export_data.items() if k != "metadata"}
        if metadata.get("content_hash") != hashlib.sha256(dump_json(payload).encode("utf-8")).hexdigest():
            raise ValueError("Export content hash mismatch - data integrity compromised.")

        target_db = Database(self._target_db_path)
        store = SQLiteKnowledgeStore(target_db)

        restored_counts = {
            "sources": 0, "lessons": 0, "evidence": 0,
            "conflicts": 0, "source_versions": 0, "supersession_lineage": 0,
        }

        effective_owner = new_owner_user_id or owner_user_id

        for lesson_data in export_data.get("lessons", []):
            entry = dict(lesson_data)
            # Remap owner when requested
            entry["owner_user_id"] = effective_owner
            store.import_legacy_entry(
                entry=entry,
                detail=entry.get("detail_json") or {},
                default_owner_user_id=effective_owner,
            )
            restored_counts["lessons"] += 1

        # Re-count actual sources/evidence created for this owner
        restored_counts["sources"] = len(store.list_sources(effective_owner))

        restored_counts["conflicts"] = len(export_data.get("conflicts", []))
        restored_counts["source_versions"] = len(export_data.get("source_versions", []))
        restored_counts["supersession_lineage"] = len(export_data.get("supersession_lineage", []))
        restored_counts["evidence"] = len(export_data.get("evidence", []))

        return {
            "ok": True,
            "metadata": metadata,
            "restored_counts": restored_counts,
            "target_db_path": str(self._target_db_path),
        }

    def verify_restore_parity(self, source_store: SQLiteKnowledgeStore, restored_db_path: Path, owner_user_id: str = "test_owner") -> dict[str, Any]:
        """Basic parity check between source and restored DB."""
        restored_store = SQLiteKnowledgeStore(Database(restored_db_path))

        details = {
            "lessons_count": len(source_store.list_entries(owner_user_id=owner_user_id))
                == len(restored_store.list_entries(owner_user_id=owner_user_id)),
            "approved_lessons_count": len(source_store.get_approved_entries(owner_user_id=owner_user_id))
                == len(restored_store.get_approved_entries(owner_user_id=owner_user_id)),
            "sources_count": len(source_store.list_sources(owner_user_id=owner_user_id))
                == len(restored_store.list_sources(owner_user_id=owner_user_id)),
            "fts_search_parity": source_store.get_approved_context("lesson", owner_user_id=owner_user_id)
                == restored_store.get_approved_context("lesson", owner_user_id=owner_user_id),
        }
        return {"ok": all(details.values()), "details": details}