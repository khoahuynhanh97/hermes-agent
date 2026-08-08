from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .db import Database
from .knowledge import SQLiteKnowledgeStore, VALID_STATUSES


@dataclass
class MigrationReport:
    total: int = 0
    imported: int = 0
    skipped: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    malformed_details: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "imported": self.imported,
            "skipped": self.skipped,
            "by_status": dict(self.by_status),
            "malformed_details": list(self.malformed_details),
            "errors": list(self.errors),
        }


def _read_detail(root: Path, entry: dict, report: MigrationReport) -> dict:
    relative = str(entry.get("detail_file") or "").strip()
    if not relative:
        return {}
    try:
        path = (root / relative).resolve()
        path.relative_to(root.resolve())
    except (OSError, ValueError):
        report.malformed_details.append(str(entry.get("id") or relative))
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        report.malformed_details.append(str(entry.get("id") or relative))
        return {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail if isinstance(detail, dict) else {}


def migrate_legacy_knowledge(
    source_root: str | Path,
    database: Database,
    *,
    default_owner_user_id: str,
    dry_run: bool = True,
) -> MigrationReport:
    root = Path(source_root).expanduser().resolve()
    index_path = root / "unified_index.json"
    report = MigrationReport()
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        report.errors.append(f"Could not read {index_path}: {exc}")
        return report

    entries = payload.get("entries", []) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        report.errors.append("Legacy knowledge index does not contain an entries list")
        return report

    store = SQLiteKnowledgeStore(database, default_owner_user_id=default_owner_user_id)
    report.total = len(entries)
    for entry in entries:
        if not isinstance(entry, dict):
            report.errors.append("Skipped a non-object legacy entry")
            report.skipped += 1
            continue
        status = str(entry.get("status") or "pending").lower()
        if status not in VALID_STATUSES:
            status = "pending"
        report.by_status[status] = report.by_status.get(status, 0) + 1
        detail = _read_detail(root, entry, report)
        if dry_run:
            continue
        entry_id = str(entry.get("id") or "")
        if entry_id and store.get_entry(entry_id):
            report.skipped += 1
            continue
        try:
            if store.import_legacy_entry(entry, detail, default_owner_user_id):
                report.imported += 1
            else:
                report.skipped += 1
        except Exception as exc:
            report.errors.append(f"{entry_id or '<unknown>'}: {exc}")
    return report

