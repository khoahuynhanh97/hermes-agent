from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict

from .db import SCHEMA_VERSION, Database


EXPORT_TABLES = (
    "sources",
    "artifacts",
    "evidence",
    "lessons",
    "lesson_evidence",
    "lesson_events",
    "messages",
    "memories",
    "memory_events",
    "jobs",
)

REQUIRED_BACKUP_TABLES = (
    "artifacts",
    "assets",
    "evidence",
    "jobs",
    "lesson_evidence",
    "lesson_events",
    "lesson_fts",
    "lessons",
    "memories",
    "memory_events",
    "messages",
    "projects",
    "schema_migrations",
    "sources",
    "workflow_steps",
    "workflows",
)
VERIFICATION_COUNT_TABLES = ("lessons", "sources", "lesson_events")


class BackupVerification(TypedDict):
    ok: bool
    path: str
    integrity: str
    foreign_key_violations: int
    schema_version: int
    required_tables_missing: list[str]
    counts: dict[str, int]
    detail: str


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _label(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "backup").strip("-")
    return cleaned[:48] or "backup"


class SQLiteBackupManager:
    def __init__(
        self,
        database: Database | None = None,
        backup_dir: str | Path | None = None,
        keep: int = 14,
    ):
        self.database = database or Database()
        default_dir = self.database.path.parent / "backups"
        self.backup_dir = Path(
            backup_dir or os.environ.get("HERMES_BACKUP_DIR", "") or default_dir
        ).expanduser().resolve()
        self.keep = max(1, int(keep))
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def create_backup(self, label: str = "scheduled") -> Path:
        self.database.initialize()
        target = self.backup_dir / f"hermes-{_timestamp()}-{_label(label)}.db"
        temporary = target.with_suffix(".db.tmp")
        try:
            with self.database.connect() as source, closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
        except Exception:
            self._remove_sidecars(temporary)
            raise

        verification = self.verify(temporary)
        if not verification["ok"]:
            self._remove_sidecars(temporary)
            raise RuntimeError(
                "Backup verification failed: "
                f"{verification['detail']}. Candidate retained at {temporary}"
            )

        temporary.replace(target)
        self._remove_sidecars(temporary)
        self.prune()
        return target

    @staticmethod
    def _verification_failure(
        candidate: Path,
        detail: str,
        *,
        integrity: str = "error",
        foreign_key_violations: int = 0,
        schema_version: int = 0,
        required_tables_missing: list[str] | None = None,
        counts: dict[str, int] | None = None,
    ) -> BackupVerification:
        return {
            "ok": False,
            "path": str(candidate),
            "integrity": integrity,
            "foreign_key_violations": foreign_key_violations,
            "schema_version": schema_version,
            "required_tables_missing": (
                sorted(REQUIRED_BACKUP_TABLES)
                if required_tables_missing is None
                else required_tables_missing
            ),
            "counts": counts or {
                table: 0 for table in VERIFICATION_COUNT_TABLES
            },
            "detail": detail,
        }

    def verify(self, path: str | Path) -> BackupVerification:
        candidate = Path(path).expanduser().resolve()
        if not candidate.is_file():
            return self._verification_failure(
                candidate,
                "backup file does not exist",
            )
        try:
            with closing(
                sqlite3.connect(
                    f"file:{candidate.as_posix()}?mode=ro&immutable=1",
                    uri=True,
                )
            ) as connection:
                connection.execute("PRAGMA query_only = ON")
                integrity_rows = connection.execute(
                    "PRAGMA integrity_check"
                ).fetchall()
                integrity = (
                    "ok"
                    if integrity_rows == [("ok",)]
                    else "failed"
                )
                foreign_key_violations = len(
                    connection.execute("PRAGMA foreign_key_check").fetchall()
                )
                schema_version = int(
                    connection.execute("PRAGMA user_version").fetchone()[0]
                )
                placeholders = ",".join(
                    "?" for _ in REQUIRED_BACKUP_TABLES
                )
                object_types = {
                    str(name): str(object_type)
                    for name, object_type in connection.execute(
                        f"""
                        SELECT name, type
                        FROM sqlite_master
                        WHERE name IN ({placeholders})
                        """,
                        REQUIRED_BACKUP_TABLES,
                    ).fetchall()
                }
                required_tables_missing = sorted(
                    table
                    for table in REQUIRED_BACKUP_TABLES
                    if object_types.get(table) != "table"
                )
                counts = {
                    table: (
                        int(
                            connection.execute(
                                f"SELECT COUNT(*) FROM {table}"
                            ).fetchone()[0]
                        )
                        if object_types.get(table) == "table"
                        else 0
                    )
                    for table in VERIFICATION_COUNT_TABLES
                }
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return self._verification_failure(
                candidate,
                "backup is not a readable SQLite database",
            )

        failures: list[str] = []
        if integrity != "ok":
            failures.append("integrity check failed")
        if foreign_key_violations:
            failures.append("foreign key violations found")
        if schema_version != SCHEMA_VERSION:
            failures.append("unsupported schema version")
        if required_tables_missing:
            failures.append("required tables are missing or have invalid types")
        detail = "; ".join(failures) or "ok"
        return {
            "ok": not failures,
            "path": str(candidate),
            "integrity": integrity,
            "foreign_key_violations": foreign_key_violations,
            "schema_version": schema_version,
            "required_tables_missing": required_tables_missing,
            "counts": counts,
            "detail": detail,
        }

    def restore(self, backup_path: str | Path) -> dict[str, str]:
        source_path = Path(backup_path).expanduser().resolve()
        verification = self.verify(source_path)
        if not verification["ok"]:
            raise ValueError(f"Refusing invalid SQLite backup: {verification['detail']}")
        pre_restore = self.create_backup(label="pre-restore") if self.database.path.exists() else None
        temporary = self.database.path.with_suffix(".restore.tmp")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            source_uri = f"file:{source_path.as_posix()}?mode=ro&immutable=1"
            with closing(sqlite3.connect(source_uri, uri=True)) as source, closing(sqlite3.connect(temporary)) as destination:
                source.backup(destination)
            restored_check = self.verify(temporary)
            if not restored_check["ok"]:
                raise RuntimeError(f"Restored database failed integrity check: {restored_check['detail']}")
            for suffix in ("-wal", "-shm"):
                Path(str(self.database.path) + suffix).unlink(missing_ok=True)
            temporary.replace(self.database.path)
        finally:
            temporary.unlink(missing_ok=True)
            self._remove_sidecars(temporary)
        return {
            "restored_from": str(source_path),
            "database": str(self.database.path),
            "pre_restore_backup": str(pre_restore or ""),
        }

    def export_json(self, output_path: str | Path | None = None) -> Path:
        self.database.initialize()
        target = Path(output_path).expanduser().resolve() if output_path else (
            self.backup_dir / f"hermes-export-{_timestamp()}.json"
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "format": "hermes-personal-assistant-export-v1",
            "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        with self.database.connect() as connection:
            for table in EXPORT_TABLES:
                rows = connection.execute(f"SELECT * FROM {table}").fetchall()
                payload[table] = [dict(row) for row in rows]
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(target)
        return target

    def prune(self) -> list[Path]:
        backups = sorted(self.backup_dir.glob("hermes-*.db"), key=lambda path: path.stat().st_mtime)
        removed = backups[:-self.keep]
        for path in removed:
            path.unlink(missing_ok=True)
            self._remove_sidecars(path)
        return removed

    @staticmethod
    def _remove_sidecars(database_path: Path) -> None:
        for suffix in ("-wal", "-shm"):
            Path(str(database_path) + suffix).unlink(missing_ok=True)
