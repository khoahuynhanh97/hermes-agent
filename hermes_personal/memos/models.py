from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PersonalMemo:
    """A lightweight personal memo / note entry.

    Memos are personal scratchpad items (thoughts, ideas, quick notes, meeting
    summaries, todo lists) that belong directly to the owner without requiring
    formal evidence or HITL approval gates.
    """

    memo_id: str
    owner_user_id: str
    title: str
    content: str
    group_name: str = "general"
    tags: tuple[str, ...] = ()
    pinned: bool = False
    archived: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not self.memo_id:
            raise ValueError("memo_id must not be empty")
        if not self.owner_user_id:
            raise ValueError("owner_user_id must not be empty")
        if not self.title.strip() and not self.content.strip():
            raise ValueError("Memo must have a non-empty title or content")

    @property
    def tags_csv(self) -> str:
        return ", ".join(self.tags)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memo_id": self.memo_id,
            "owner_user_id": self.owner_user_id,
            "title": self.title,
            "content": self.content,
            "group_name": self.group_name,
            "tags": list(self.tags),
            "pinned": self.pinned,
            "archived": self.archived,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
