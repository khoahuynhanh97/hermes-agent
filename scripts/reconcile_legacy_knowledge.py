"""Reconcile and import legacy Hermes knowledge & messages into hermes_personal.

Reads:
- sources & lessons from legacy database
- messages (Telegram conversations)
Writes:
- learning_candidate (approved)
- evidence_ref (linked source/excerpt)
- learning_version (active v1)
- knowledge_fts (full-text search index)
- personal_memo (for memo-like notes)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")


def reconcile_legacy_data(source_db_path: Path, target_db_path: Path) -> dict[str, int]:
    if not source_db_path.is_file():
        raise FileNotFoundError(f"Source database not found: {source_db_path}")

    from hermes_personal.storage.sqlite import connect as sqlite_connect

    src_conn = sqlite3.connect(source_db_path)
    src_conn.row_factory = sqlite3.Row

    tgt_conn = sqlite_connect(target_db_path)

    stats = {
        "sources_migrated": 0,
        "lessons_migrated": 0,
        "memos_migrated": 0,
        "fts_indexed": 0,
    }

    # 1. Map existing users / default owner
    default_owner = "5069349064"  # Telegram user ID from real messages
    now_iso = datetime.now(timezone.utc).isoformat()
    with tgt_conn:
        tgt_conn.execute(
            "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES (?, ?, ?)",
            (default_owner, "Telegram Owner", now_iso),
        )
        tgt_conn.execute(
            "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES (?, ?, ?)",
            ("default_user", "Default User", now_iso),
        )

    # 2. Migrate legacy lessons
    print("\n[1/3] Migrating legacy lessons...")
    lessons = src_conn.execute("SELECT * FROM lessons").fetchall()
    for lesson in lessons:
        lesson_id = str(lesson["id"])
        title = lesson["title"] or "Untitled Lesson"
        content = lesson["content"] or ""
        category = lesson["category"] or "general"
        status = lesson["status"] or "approved"
        created_at = lesson["created_at"] or now_iso
        source_id = lesson["source_id"]

        # Determine learning kind
        l_type = (lesson["lesson_type"] or "rule").lower() if "lesson_type" in lesson.keys() else "knowledge"
        if "procedure" in l_type or "workflow" in l_type or "playbook" in l_type:
            kind = "procedure"
        elif "preference" in l_type or "style" in l_type:
            kind = "preference"
        else:
            kind = "knowledge"

        owner_id = str(lesson["owner_user_id"] or default_owner)
        with tgt_conn:
            tgt_conn.execute(
                "INSERT OR IGNORE INTO global_user_identity (owner_user_id, display_name, created_at) VALUES (?, ?, ?)",
                (owner_id, f"User {owner_id}", now_iso),
            )

        candidate_id = f"cand_legacy_{lesson_id}"
        cand_digest = "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

        # Fetch source info if available
        src_url = ""
        if source_id:
            src_row = src_conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
            if src_row:
                src_url = src_row["source_url"] if "source_url" in src_row.keys() and src_row["source_url"] else (src_row["source_key"] if "source_key" in src_row.keys() else "")

        ev_id = f"ev_legacy_{lesson_id}"
        ev_digest = "sha256:" + hashlib.sha256((src_url or content[:100]).encode("utf-8")).hexdigest()

        with tgt_conn:
            # Check if candidate with same digest already exists
            existing = tgt_conn.execute(
                "SELECT candidate_id FROM learning_candidate WHERE owner_user_id = ? AND kind = ? AND digest = ?",
                (owner_id, kind, cand_digest),
            ).fetchone()
            if existing:
                continue

            tgt_conn.execute(
                """
                INSERT OR IGNORE INTO learning_candidate (
                    candidate_id, owner_user_id, kind, title, content, digest, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    owner_id,
                    kind,
                    title,
                    content,
                    cand_digest,
                    "approved" if status == "approved" else "draft",
                    created_at,
                ),
            )
            tgt_conn.execute(
                """
                INSERT OR IGNORE INTO evidence_ref (
                    evidence_id, candidate_id, source_type, source_id, digest, excerpt, polarity, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev_id,
                    candidate_id,
                    "url" if src_url.startswith("http") else "legacy_import",
                    src_url or f"legacy_source_{source_id}",
                    ev_digest,
                    content[:200],
                    "positive",
                    created_at,
                ),
            )

            # If approved, create active version 1
            if status == "approved":
                version_id = f"v_{candidate_id}_1"
                tgt_conn.execute(
                    """
                    INSERT OR IGNORE INTO learning_version (
                        version_id, candidate_id, owner_user_id, version, content, digest, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        version_id,
                        candidate_id,
                        owner_id,
                        1,
                        content,
                        cand_digest,
                        "active",
                        created_at,
                    ),
                )
                # Index in FTS5
                tgt_conn.execute(
                    "DELETE FROM knowledge_fts WHERE version_id = ?", (version_id,)
                )
                tgt_conn.execute(
                    """
                    INSERT INTO knowledge_fts (title, content, candidate_id, version_id, owner_user_id, kind)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (title, content, candidate_id, version_id, owner_id, kind),
                )
                stats["fts_indexed"] += 1

            stats["lessons_migrated"] += 1

    # 3. Check Telegram messages and migrate notes
    print("\n[2/3] Analyzing Telegram message history...")
    messages = src_conn.execute("SELECT * FROM messages WHERE role = 'user'").fetchall()
    for msg in messages:
        text = (msg["content"] or "").strip()
        msg_owner = str(msg["owner_user_id"] or default_owner)
        created = msg["created_at"] or now_iso

        # If user was saving a note/memo or learning prompt
        if text.startswith("Hãy học kiến thức này:") or text.startswith("Ghi nhớ:") or text.startswith("Note:"):
            note_content = text
            title = text.splitlines()[0][:50]
            memo_id = f"memo_legacy_{msg['id']}"

            tags = []
            if "token" in text.lower():
                tags.append("token")
            if "repo" in text.lower():
                tags.append("code")

            with tgt_conn:
                exists = tgt_conn.execute(
                    "SELECT 1 FROM personal_memo WHERE memo_id = ?", (memo_id,)
                ).fetchone()
                if not exists:
                    tgt_conn.execute(
                        """
                        INSERT INTO personal_memo (
                            memo_id, owner_user_id, title, content, group_name,
                            tags_json, pinned, archived, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            memo_id,
                            msg_owner,
                            title,
                            note_content,
                            "imported",
                            json.dumps(tags),
                            0,
                            0,
                            created,
                            created,
                        ),
                    )
                    tags_text = " ".join(tags)
                    tgt_conn.execute(
                        """
                        INSERT INTO memo_fts (title, content, tags, memo_id, owner_user_id, group_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (title, note_content, tags_text, memo_id, msg_owner, "imported"),
                    )
                    stats["memos_migrated"] += 1

    src_conn.close()
    tgt_conn.close()
    return stats


if __name__ == "__main__":
    src_db = Path(r"D:\work\hermes-agent-data\backups\hermes-before-qc-budget-reconcile-20260924.db")
    from hermes_constants import get_hermes_home
    tgt_db = Path(get_hermes_home()) / "hermes_personal.sqlite"
    tgt_db.parent.mkdir(parents=True, exist_ok=True)

    print(f"Source DB: {src_db}")
    print(f"Target DB: {tgt_db}")

    res = reconcile_legacy_data(src_db, tgt_db)
    print("\n=== Reconciliation Summary ===")
    for k, v in res.items():
        print(f"  {k}: {v}")
    print("\nDone! All legacy knowledge and messages are successfully reconciled.")
