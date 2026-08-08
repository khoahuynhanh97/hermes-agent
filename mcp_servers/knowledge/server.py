"""Thin Knowledge MCP facade over the governed SQLite knowledge lifecycle."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor
from hermes.application.knowledge_maintenance import KnowledgeMaintenanceService
from hermes.application.knowledge_export import KnowledgeExportService, KnowledgeRestoreService
from hermes.config import get_data_path
from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore


mcp = FastMCP("hermes-knowledge")


def knowledge_search(owner_user_id: str, query: str, limit: int = 10) -> dict[str, Any]:
    """Search approved owner-scoped knowledge through the existing FTS5 index."""
    owner_user_id = _required_owner(owner_user_id)
    if not isinstance(query, str) or not query.strip():
        raise ValueError("query is required")
    results = _store().search_approved(query, owner_user_id, limit)
    return {"ok": True, "owner_user_id": owner_user_id, "query": query, "results": results}


def knowledge_get(owner_user_id: str, lesson_id: str) -> dict[str, Any]:
    """Read one owner-scoped knowledge item and its evidence."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    store = _store()
    entry = store.get_owned_entry(lesson_id, owner_user_id)
    if entry is None:
        raise ValueError("lesson_id was not found for owner_user_id")
    entry["evidence"] = store.get_entry_evidence(lesson_id, owner_user_id)
    return {"ok": True, "entry": entry}


def knowledge_propose(
    owner_user_id: str,
    title: str,
    content: str,
    source_url: str = "",
    category: str = "General",
    key_lessons: list[str] | None = None,
    evidence: list[dict[str, Any]] | None = None,
    source: str = "hermes_research",
) -> dict[str, Any]:
    """Create a pending proposal using the existing duplicate/evidence rules."""
    owner_user_id = _required_owner(owner_user_id)
    title = _required_id(title, "title")
    content = _required_id(content, "content")
    store = _store()
    entry = store.add_entry(
        title=title,
        source_url=source_url,
        category=category or "General",
        key_lessons=key_lessons or [],
        detail_data={
            "summary": content,
            "deep_analysis": content,
            "evidence": evidence or [],
        },
        source=source or "hermes_research",
        owner_user_id=owner_user_id,
    )
    return {"ok": True, "entry": entry, "lifecycle": "pending"}


def knowledge_approve(
    owner_user_id: str,
    lesson_id: str,
    approval_mode: str = "hermes_business_review",
    force: bool = False,
) -> dict[str, Any]:
    """Run the existing owner-scoped approval transition."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    result = KnowledgeLifecycle(_store()).approve(
        lesson_id,
        LifecycleActor.owner(owner_user_id),
        mode=approval_mode,
        force=bool(force),
    )
    return _lifecycle_payload(result)


def knowledge_reject(
    owner_user_id: str,
    lesson_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Run the existing owner-scoped rejection transition."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    result = KnowledgeLifecycle(_store()).reject(
        lesson_id,
        LifecycleActor.owner(owner_user_id),
        reason=reason,
    )
    return _lifecycle_payload(result)


def knowledge_list_pending(owner_user_id: str) -> dict[str, Any]:
    """List pending proposals through the existing review queue query."""
    owner_user_id = _required_owner(owner_user_id)
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "entries": _store().get_pending_entries(owner_user_id),
    }


# K4: Maintenance tools

def knowledge_mark_reanalysis(
    owner_user_id: str,
    lesson_id: str,
    reason: str,
) -> dict[str, Any]:
    """Mark a lesson as needing reanalysis (preserves approval status)."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    reason = _required_id(reason, "reason")
    
    success = _maintenance().mark_lesson_needs_reanalysis(
        owner_user_id, lesson_id, reason=reason, actor=owner_user_id
    )
    return {
        "ok": success,
        "lesson_id": lesson_id,
        "marked": "needs_reanalysis" if success else None,
    }


def knowledge_list_reanalysis(owner_user_id: str) -> dict[str, Any]:
    """List lessons needing reanalysis."""
    owner_user_id = _required_owner(owner_user_id)
    items = _maintenance().list_needs_reanalysis(owner_user_id)
    return {"ok": True, "owner_user_id": owner_user_id, "items": items}


def knowledge_clear_reanalysis(
    owner_user_id: str,
    lesson_id: str,
    reason: str,
) -> dict[str, Any]:
    """Clear needs_reanalysis flag (requires explicit reason)."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    reason = _required_id(reason, "reason")
    
    success = _maintenance().clear_needs_reanalysis(
        owner_user_id, lesson_id, actor=owner_user_id, reason=reason
    )
    return {"ok": success, "lesson_id": lesson_id}


def knowledge_record_conflict(
    owner_user_id: str,
    lesson_id: str,
    reason: str,
    conflicting_source_id: str = "",
    conflicting_lesson_id: str = "",
) -> dict[str, Any]:
    """Record a knowledge conflict."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    reason = _required_id(reason, "reason")
    
    conflict = _maintenance().record_conflict(
        owner_user_id, lesson_id,
        reason=reason,
        conflicting_lesson_id=conflicting_lesson_id or None,
        conflicting_source_id=conflicting_source_id or None,
    )
    if conflict is None:
        return {"ok": False, "code": "lesson_not_found"}
    return {
        "ok": True,
        "conflict_id": conflict.conflict_id,
        "status": conflict.status,
    }


def knowledge_list_conflicts(owner_user_id: str, status: str = "open") -> dict[str, Any]:
    """List conflicts (open by default)."""
    owner_user_id = _required_owner(owner_user_id)
    if status == "open":
        conflicts = _maintenance().list_open_conflicts(owner_user_id)
    else:
        return {"ok": False, "code": "unsupported_status"}
    return {"ok": True, "owner_user_id": owner_user_id, "conflicts": conflicts}


def knowledge_resolve_conflict(
    owner_user_id: str,
    conflict_id: str,
    resolution_note: str = "",
) -> dict[str, Any]:
    """Resolve a conflict."""
    owner_user_id = _required_owner(owner_user_id)
    conflict_id = _required_id(conflict_id, "conflict_id")
    
    success = _maintenance().resolve_conflict(
        owner_user_id, conflict_id,
        actor=owner_user_id,
        resolution_note=resolution_note,
    )
    return {"ok": success, "conflict_id": conflict_id, "status": "resolved" if success else None}


def knowledge_propose_revision(
    owner_user_id: str,
    original_lesson_id: str,
    proposed_title: str,
    proposed_content: str,
    reason: str,
    proposed_key_lessons: list[str] | None = None,
) -> dict[str, Any]:
    """Create a revision proposal for an existing lesson."""
    owner_user_id = _required_owner(owner_user_id)
    original_lesson_id = _required_id(original_lesson_id, "original_lesson_id")
    proposed_title = _required_id(proposed_title, "proposed_title")
    proposed_content = _required_id(proposed_content, "proposed_content")
    reason = _required_id(reason, "reason")
    
    proposal = _maintenance().create_revision_proposal(
        owner_user_id, original_lesson_id,
        proposed_title=proposed_title,
        proposed_content=proposed_content,
        reason=reason,
        actor=owner_user_id,
        proposed_key_lessons=tuple(proposed_key_lessons or []),
    )
    if proposal is None:
        return {"ok": False, "code": "lesson_not_found"}
    return {
        "ok": True,
        "revision_id": proposal.revision_id,
        "status": proposal.status,
        "original_lesson_id": original_lesson_id,
    }


def knowledge_get_history(owner_user_id: str, lesson_id: str) -> dict[str, Any]:
    """Get complete history of a lesson including supersession and conflicts."""
    owner_user_id = _required_owner(owner_user_id)
    lesson_id = _required_id(lesson_id, "lesson_id")
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "history": _maintenance().get_lesson_history(owner_user_id, lesson_id),
    }


def knowledge_health(owner_user_id: str) -> dict[str, Any]:
    """Maintenance health metrics: reanalysis count, open conflicts, supersession count."""
    owner_user_id = _required_owner(owner_user_id)
    maintenance = _maintenance()
    reanalyzes = maintenance.list_needs_reanalysis(owner_user_id)
    conflicts = maintenance.list_open_conflicts(owner_user_id)
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "needs_reanalysis_count": len(reanalyzes),
        "open_conflicts_count": len(conflicts),
        "needs_reanalysis": reanalyzes,
        "open_conflicts": conflicts,
    }


# K6: Export and Backup Tools

def knowledge_backup_db(owner_user_id: str, output_dir: str) -> dict[str, Any]:
    """Create a point-in-time copy of the SQLite Knowledge database."""
    owner_user_id = _required_owner(owner_user_id)
    output_path = Path(output_dir) / f"{owner_user_id}_knowledge_backup_{_now_iso()}.sqlite"
    exported_path = _export_service().backup_database(output_path)
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "backup_path": str(exported_path),
        "exported_at": _now_iso(),
    }


def knowledge_export_json(owner_user_id: str, output_dir: str) -> dict[str, Any]:
    """Export all owner-scoped knowledge data as structured JSON."""
    owner_user_id = _required_owner(owner_user_id)
    output_path = Path(output_dir) / f"{owner_user_id}_knowledge_export_{_now_iso()}.json"
    exported_path = _export_service().export_json(owner_user_id, output_path)
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "export_path": str(exported_path),
        "exported_at": _now_iso(),
    }


def knowledge_export_markdown(owner_user_id: str, output_dir: str) -> dict[str, Any]:
    """Export current approved lessons as human-readable Markdown."""
    owner_user_id = _required_owner(owner_user_id)
    output_path = Path(output_dir) / f"{owner_user_id}_knowledge_export_{_now_iso()}.md"
    exported_path = _export_service().export_markdown(owner_user_id, output_path)
    return {
        "ok": True,
        "owner_user_id": owner_user_id,
        "export_path": str(exported_path),
        "exported_at": _now_iso(),
    }


def knowledge_restore_verify_json(owner_user_id: str, input_path: str, target_db_path: str, new_owner_user_id: str = "") -> dict[str, Any]:
    """Restore knowledge from JSON to a temporary DB and verify parity."""
    owner_user_id = _required_owner(owner_user_id)
    input_path_obj = Path(input_path)
    target_db_path_obj = Path(target_db_path)
    
    restore_service = KnowledgeRestoreService(target_db_path_obj)
    
    result = restore_service.restore_from_json(owner_user_id, input_path_obj, new_owner_user_id or None)
    
    if result["ok"]:
        source_store = _store() # Original store
        parity_check = restore_service.verify_restore_parity(source_store, target_db_path_obj)
        result["parity_check"] = parity_check
        result["ok"] = parity_check["ok"]
    
    return result


def _store() -> SQLiteKnowledgeStore:
    configured = os.environ.get("HERMES_KNOWLEDGE_DB_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else get_data_path("knowledge", "knowledge.sqlite")
    return SQLiteKnowledgeStore(Database(path))


def _maintenance() -> KnowledgeMaintenanceService:
    configured = os.environ.get("HERMES_KNOWLEDGE_DB_PATH", "").strip()
    path = Path(configured).expanduser().resolve() if configured else get_data_path("knowledge", "knowledge.sqlite")
    db = Database(path)
    
    @contextmanager
    def _conn():
        c = db.connect()
        try:
            yield c
        finally:
            c.close()
    
    return KnowledgeMaintenanceService(_conn)


def _export_service() -> KnowledgeExportService:
    configured = os.environ.get("HERMES_KNOWLEDGE_DB_PATH", "").strip()
    db_path = Path(configured).expanduser().resolve() if configured else get_data_path("knowledge", "knowledge.sqlite")
    db = Database(db_path)
    
    @contextmanager
    def _conn():
        c = db.connect()
        try:
            yield c
        finally:
            c.close()
    
    return KnowledgeExportService(db_path, _conn)

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _required_owner(value: str) -> str:
    return _required_id(value, "owner_user_id")


def _required_id(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _lifecycle_payload(result: Any) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "code": result.code,
        "changed": result.changed,
        "entry": result.lesson,
    }


for _tool in (
    knowledge_search,
    knowledge_get,
    knowledge_propose,
    knowledge_approve,
    knowledge_reject,
    knowledge_list_pending,
    knowledge_mark_reanalysis,
    knowledge_list_reanalysis,
    knowledge_clear_reanalysis,
    knowledge_record_conflict,
    knowledge_list_conflicts,
    knowledge_resolve_conflict,
    knowledge_propose_revision,
    knowledge_get_history,
    knowledge_health,
    knowledge_backup_db,
    knowledge_export_json,
    knowledge_export_markdown,
    knowledge_restore_verify_json,
):
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()
