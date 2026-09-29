from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Sequence

from hermes_personal.memos.models import PersonalMemo


def _normalize_tag(tag: str) -> str:
    cleaned = tag.strip().lower()
    if cleaned.startswith("#"):
        cleaned = cleaned[1:]
    return cleaned


def _row_to_memo(row: sqlite3.Row | tuple) -> PersonalMemo:
    tags_raw = row["tags_json"] if hasattr(row, "keys") else row[4]
    tags: list[str] = []
    if tags_raw:
        try:
            tags = json.loads(tags_raw)
        except (json.JSONDecodeError, TypeError):
            pass

    return PersonalMemo(
        memo_id=row["memo_id"] if hasattr(row, "keys") else row[0],
        owner_user_id=row["owner_user_id"] if hasattr(row, "keys") else row[1],
        title=row["title"] if hasattr(row, "keys") else row[2],
        content=row["content"] if hasattr(row, "keys") else row[3],
        group_name=row["group_name"] if hasattr(row, "keys") else row[4],
        tags=tuple(tags),
        pinned=bool(row["pinned"] if hasattr(row, "keys") else row[6]),
        archived=bool(row["archived"] if hasattr(row, "keys") else row[7]),
        created_at=row["created_at"] if hasattr(row, "keys") else row[8],
        updated_at=row["updated_at"] if hasattr(row, "keys") else row[9],
    )


class MemoRepository:
    """SQLite-backed repository for personal memos and quick notes.

    Provides fast indexing, categorization by group, tagging, and FTS5 search.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._conn = connection

    def create_memo(
        self,
        owner_user_id: str,
        title: str,
        content: str,
        group_name: str = "general",
        tags: Sequence[str] = (),
        pinned: bool = False,
    ) -> PersonalMemo:
        memo_id = f"memo_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        normalized_tags = tuple(sorted({_normalize_tag(t) for t in tags if _normalize_tag(t)}))
        tags_json = json.dumps(list(normalized_tags))
        group_clean = group_name.strip().lower() or "general"

        memo = PersonalMemo(
            memo_id=memo_id,
            owner_user_id=owner_user_id,
            title=title.strip(),
            content=content.strip(),
            group_name=group_clean,
            tags=normalized_tags,
            pinned=pinned,
            archived=False,
            created_at=now,
            updated_at=now,
        )

        with self._conn:
            self._conn.execute(
                """
                INSERT INTO personal_memo (
                    memo_id, owner_user_id, title, content, group_name,
                    tags_json, pinned, archived, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memo.memo_id,
                    memo.owner_user_id,
                    memo.title,
                    memo.content,
                    memo.group_name,
                    tags_json,
                    1 if memo.pinned else 0,
                    0,
                    memo.created_at,
                    memo.updated_at,
                ),
            )
            # Sync to FTS5
            tags_text = " ".join(normalized_tags)
            self._conn.execute(
                """
                INSERT INTO memo_fts (title, content, tags, memo_id, owner_user_id, group_name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (memo.title, memo.content, tags_text, memo.memo_id, memo.owner_user_id, memo.group_name),
            )

        return memo

    def get_memo(self, memo_id: str, owner_user_id: str | None = None) -> PersonalMemo | None:
        if owner_user_id:
            row = self._conn.execute(
                "SELECT * FROM personal_memo WHERE memo_id = ? AND owner_user_id = ?",
                (memo_id, owner_user_id),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM personal_memo WHERE memo_id = ?",
                (memo_id,),
            ).fetchone()
        if not row:
            return None
        return _row_to_memo(row)

    def update_memo(
        self,
        memo_id: str,
        owner_user_id: str,
        title: str | None = None,
        content: str | None = None,
        group_name: str | None = None,
        tags: Sequence[str] | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
    ) -> PersonalMemo:
        current = self.get_memo(memo_id, owner_user_id)
        if not current:
            raise KeyError(f"Memo '{memo_id}' not found for owner '{owner_user_id}'")

        new_title = title.strip() if title is not None else current.title
        new_content = content.strip() if content is not None else current.content
        new_group = group_name.strip().lower() if group_name is not None else current.group_name
        if tags is not None:
            new_tags = tuple(sorted({_normalize_tag(t) for t in tags if _normalize_tag(t)}))
        else:
            new_tags = current.tags
        new_pinned = pinned if pinned is not None else current.pinned
        new_archived = archived if archived is not None else current.archived
        now = datetime.now(timezone.utc).isoformat()

        updated_memo = PersonalMemo(
            memo_id=memo_id,
            owner_user_id=owner_user_id,
            title=new_title,
            content=new_content,
            group_name=new_group,
            tags=new_tags,
            pinned=new_pinned,
            archived=new_archived,
            created_at=current.created_at,
            updated_at=now,
        )

        with self._conn:
            self._conn.execute(
                """
                UPDATE personal_memo
                SET title = ?, content = ?, group_name = ?, tags_json = ?,
                    pinned = ?, archived = ?, updated_at = ?
                WHERE memo_id = ? AND owner_user_id = ?
                """,
                (
                    updated_memo.title,
                    updated_memo.content,
                    updated_memo.group_name,
                    json.dumps(list(updated_memo.tags)),
                    1 if updated_memo.pinned else 0,
                    1 if updated_memo.archived else 0,
                    updated_memo.updated_at,
                    memo_id,
                    owner_user_id,
                ),
            )
            # Sync FTS
            self._conn.execute("DELETE FROM memo_fts WHERE memo_id = ?", (memo_id,))
            if not updated_memo.archived:
                tags_text = " ".join(updated_memo.tags)
                self._conn.execute(
                    """
                    INSERT INTO memo_fts (title, content, tags, memo_id, owner_user_id, group_name)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (updated_memo.title, updated_memo.content, tags_text, memo_id, owner_user_id, updated_memo.group_name),
                )

        return updated_memo

    def delete_memo(self, memo_id: str, owner_user_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute(
                "DELETE FROM personal_memo WHERE memo_id = ? AND owner_user_id = ?",
                (memo_id, owner_user_id),
            )
            self._conn.execute("DELETE FROM memo_fts WHERE memo_id = ?", (memo_id,))
            return cur.rowcount > 0

    def list_memos(
        self,
        owner_user_id: str,
        group_name: str | None = None,
        tag: str | None = None,
        pinned_only: bool = False,
        include_archived: bool = False,
        limit: int = 50,
    ) -> tuple[PersonalMemo, ...]:
        query_parts = ["SELECT * FROM personal_memo WHERE owner_user_id = ?"]
        params: list[Any] = [owner_user_id]

        if not include_archived:
            query_parts.append("AND archived = 0")

        if pinned_only:
            query_parts.append("AND pinned = 1")

        if group_name:
            query_parts.append("AND group_name = ?")
            params.append(group_name.strip().lower())

        query_parts.append("ORDER BY pinned DESC, updated_at DESC LIMIT ?")
        params.append(limit)

        sql = " ".join(query_parts)
        rows = self._conn.execute(sql, params).fetchall()
        memos = [_row_to_memo(r) for r in rows]

        if tag:
            target_tag = _normalize_tag(tag)
            memos = [m for m in memos if target_tag in m.tags]

        return tuple(memos)

    def search_memos(
        self,
        owner_user_id: str,
        query: str,
        group_name: str | None = None,
        tag: str | None = None,
        limit: int = 20,
    ) -> tuple[PersonalMemo, ...]:
        if not query.strip():
            return self.list_memos(owner_user_id, group_name=group_name, tag=tag, limit=limit)

        safe_query = query.replace('"', '""')
        try:
            if group_name:
                cur = self._conn.execute(
                    """
                    SELECT memo_id FROM memo_fts
                    WHERE memo_fts MATCH ? AND owner_user_id = ? AND group_name = ?
                    ORDER BY rank LIMIT ?
                    """,
                    (f'"{safe_query}"', owner_user_id, group_name.strip().lower(), limit * 2),
                )
            else:
                cur = self._conn.execute(
                    """
                    SELECT memo_id FROM memo_fts
                    WHERE memo_fts MATCH ? AND owner_user_id = ?
                    ORDER BY rank LIMIT ?
                    """,
                    (f'"{safe_query}"', owner_user_id, limit * 2),
                )
            memo_ids = [r[0] for r in cur.fetchall()]
        except Exception:
            memo_ids = []

        if not memo_ids:
            # Fallback substring search
            pattern = f"%{query.strip()}%"
            cur = self._conn.execute(
                """
                SELECT * FROM personal_memo
                WHERE owner_user_id = ? AND archived = 0 AND (title LIKE ? OR content LIKE ?)
                ORDER BY pinned DESC, updated_at DESC LIMIT ?
                """,
                (owner_user_id, pattern, pattern, limit),
            )
            results = [_row_to_memo(r) for r in cur.fetchall()]
        else:
            placeholders = ",".join("?" for _ in memo_ids)
            cur = self._conn.execute(
                f"SELECT * FROM personal_memo WHERE memo_id IN ({placeholders}) AND archived = 0",
                memo_ids,
            )
            results_by_id = {r["memo_id"]: _row_to_memo(r) for r in cur.fetchall()}
            # Preserve FTS ranking order
            results = [results_by_id[mid] for mid in memo_ids if mid in results_by_id]

        if tag:
            target_tag = _normalize_tag(tag)
            results = [m for m in results if target_tag in m.tags]

        return tuple(results[:limit])

    def list_tags(self, owner_user_id: str) -> list[tuple[str, int]]:
        """Return all tags used by the owner with their memo counts."""
        rows = self._conn.execute(
            "SELECT tags_json FROM personal_memo WHERE owner_user_id = ? AND archived = 0",
            (owner_user_id,),
        ).fetchall()
        tag_counts: dict[str, int] = {}
        for r in rows:
            raw = r[0] if isinstance(r, tuple) else r["tags_json"]
            if raw:
                try:
                    for t in json.loads(raw):
                        tag_counts[t] = tag_counts.get(t, 0) + 1
                except Exception:
                    pass
        return sorted(tag_counts.items(), key=lambda item: (-item[1], item[0]))

    def list_groups(self, owner_user_id: str) -> list[tuple[str, int]]:
        """Return all groups used by the owner with their memo counts."""
        rows = self._conn.execute(
            """
            SELECT group_name, COUNT(*) as cnt
            FROM personal_memo
            WHERE owner_user_id = ? AND archived = 0
            GROUP BY group_name
            ORDER BY cnt DESC, group_name ASC
            """,
            (owner_user_id,),
        ).fetchall()
        return [(r[0] if isinstance(r, tuple) else r["group_name"], r[1] if isinstance(r, tuple) else r["cnt"]) for r in rows]
