"""Personal Memo MCP and Tool Integration.

Provides fast notes and memo capability with tags and groups, completely
decoupled from the governed knowledge base.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from hermes_constants import get_hermes_home
from hermes_personal.memos.models import PersonalMemo as PersonalMemo
from hermes_personal.memos.repository import MemoRepository
from hermes_personal.storage.sqlite import connect

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    try:
        from mcp.server import MCPServer as FastMCP
    except ImportError:
        FastMCP = None  # type: ignore[misc,assignment]

DEFAULT_OWNER_USER_ID = "default_user"


class MemoCapability:
    """Capability managing personal notes and scratchpad items."""

    def __init__(
        self,
        repository: MemoRepository,
        default_owner_user_id: str = DEFAULT_OWNER_USER_ID,
    ) -> None:
        self._repository = repository
        self._default_owner_user_id = default_owner_user_id

    def create_memo(
        self,
        title: str,
        content: str,
        group_name: str = "general",
        tags: Sequence[str] = (),
        pinned: bool = False,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        memo = self._repository.create_memo(
            owner_user_id=owner,
            title=title,
            content=content,
            group_name=group_name,
            tags=tags,
            pinned=pinned,
        )
        return {
            "status": "created",
            "memo": memo.to_dict(),
            "message": f"Memo '{memo.title}' saved in [{memo.group_name}] with tags: {memo.tags_csv or 'none'}",
        }

    def search_memos(
        self,
        query: str = "",
        group_name: str | None = None,
        tag: str | None = None,
        limit: int = 10,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        memos = self._repository.search_memos(
            owner_user_id=owner,
            query=query,
            group_name=group_name,
            tag=tag,
            limit=limit,
        )
        return {
            "count": len(memos),
            "memos": [m.to_dict() for m in memos],
        }

    def list_memos(
        self,
        group_name: str | None = None,
        tag: str | None = None,
        pinned_only: bool = False,
        include_archived: bool = False,
        limit: int = 20,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        memos = self._repository.list_memos(
            owner_user_id=owner,
            group_name=group_name,
            tag=tag,
            pinned_only=pinned_only,
            include_archived=include_archived,
            limit=limit,
        )
        return {
            "count": len(memos),
            "memos": [m.to_dict() for m in memos],
        }

    def update_memo(
        self,
        memo_id: str,
        title: str | None = None,
        content: str | None = None,
        group_name: str | None = None,
        tags: Sequence[str] | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        try:
            memo = self._repository.update_memo(
                memo_id=memo_id,
                owner_user_id=owner,
                title=title,
                content=content,
                group_name=group_name,
                tags=tags,
                pinned=pinned,
                archived=archived,
            )
            return {"status": "updated", "memo": memo.to_dict()}
        except KeyError as exc:
            return {"status": "error", "message": str(exc)}

    def delete_memo(
        self,
        memo_id: str,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        success = self._repository.delete_memo(memo_id=memo_id, owner_user_id=owner)
        if success:
            return {"status": "deleted", "memo_id": memo_id}
        return {"status": "not_found", "memo_id": memo_id}

    def list_tags(self, owner_user_id: str | None = None) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        tags = self._repository.list_tags(owner)
        return {"tags": [{"tag": t, "count": c} for t, c in tags]}

    def list_groups(self, owner_user_id: str | None = None) -> dict[str, Any]:
        owner = (owner_user_id or self._default_owner_user_id).strip()
        groups = self._repository.list_groups(owner)
        return {"groups": [{"group": g, "count": c} for g, c in groups]}


def create_memo_mcp(
    capability: MemoCapability | None = None,
) -> Any:
    """Create the Memo MCP server."""
    if FastMCP is None:
        raise RuntimeError("FastMCP is not installed; cannot create Memo MCP server")

    if capability is None:
        hermes_home = Path(get_hermes_home())
        db_path = hermes_home / "hermes_personal.sqlite"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = connect(db_path)
        repository = MemoRepository(connection)
        bound_owner = os.environ.get("HERMES_OWNER_ID", DEFAULT_OWNER_USER_ID)
        capability = MemoCapability(
            repository=repository,
            default_owner_user_id=bound_owner,
        )

    mcp = FastMCP("memos")

    @mcp.tool()
    def memo_create(
        title: str,
        content: str,
        group_name: str = "general",
        tags: list[str] = [],
        pinned: bool = False,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a new personal memo or note with tags and category/group."""
        return capability.create_memo(
            title=title,
            content=content,
            group_name=group_name,
            tags=tags,
            pinned=pinned,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def memo_search(
        query: str = "",
        group_name: str | None = None,
        tag: str | None = None,
        limit: int = 10,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Search personal memos by keyword (FTS), group, or tag."""
        return capability.search_memos(
            query=query,
            group_name=group_name,
            tag=tag,
            limit=limit,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def memo_list(
        group_name: str | None = None,
        tag: str | None = None,
        pinned_only: bool = False,
        limit: int = 20,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """List personal memos filtered by group, tag, or pinned status."""
        return capability.list_memos(
            group_name=group_name,
            tag=tag,
            pinned_only=pinned_only,
            limit=limit,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def memo_update(
        memo_id: str,
        title: str | None = None,
        content: str | None = None,
        group_name: str | None = None,
        tags: list[str] | None = None,
        pinned: bool | None = None,
        archived: bool | None = None,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing personal memo."""
        return capability.update_memo(
            memo_id=memo_id,
            title=title,
            content=content,
            group_name=group_name,
            tags=tags,
            pinned=pinned,
            archived=archived,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def memo_delete(
        memo_id: str,
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Delete a personal memo permanently."""
        return capability.delete_memo(
            memo_id=memo_id,
            owner_user_id=owner_user_id,
        )

    @mcp.tool()
    def memo_tags_list(
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """List all memo tags with their usage counts."""
        return capability.list_tags(owner_user_id=owner_user_id)

    @mcp.tool()
    def memo_groups_list(
        owner_user_id: str | None = None,
    ) -> dict[str, Any]:
        """List all memo groups/categories with their counts."""
        return capability.list_groups(owner_user_id=owner_user_id)

    return mcp


def main() -> None:
    """Run the Memos MCP server over stdio transport."""
    server = create_memo_mcp()
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
