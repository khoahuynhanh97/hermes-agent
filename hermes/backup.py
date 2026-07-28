from __future__ import annotations

import json
import os
import re
import secrets
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import urlencode

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

_SAFE_OPERATION_DETAILS = {
    ("backup", "invalid_source"): "backup source is invalid",
    ("backup", "backup_failed"): "backup creation failed",
    ("backup", "candidate_verification_failed"): (
        "backup candidate verification failed"
    ),
    ("backup", "promotion_failed"): "backup candidate promotion failed",
    ("backup", "candidate_allocation_failed"): (
        "backup candidate allocation failed"
    ),
    ("restore", "invalid_backup"): "restore source is invalid",
    ("restore", "source_is_destination"): (
        "restore source cannot be the live database"
    ),
    ("restore", "restored_candidate_invalid"): (
        "restored database verification failed"
    ),
    ("restore", "restore_failed"): "restore failed",
}


class BackupVerification(TypedDict):
    ok: bool
    path: str
    integrity: str
    foreign_key_violations: int
    schema_version: int
    required_tables_missing: list[str]
    counts: dict[str, int]
    detail: str


class BackupOperationError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        code: str,
        path: str | Path,
        detail: str,
    ):
        self.operation = operation
        self.code = code
        self.path = Path(path).expanduser().resolve()
        self.detail = _SAFE_OPERATION_DETAILS.get(
            (operation, code),
            f"{operation} failed",
        )
        super().__init__(self.detail)

    def to_payload(self) -> dict[str, object]:
        return {
            "ok": False,
            "operation": self.operation,
            "code": self.code,
            "path": str(self.path),
            "detail": self.detail,
        }


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def _label(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "backup").strip("-")
    return cleaned[:48] or "backup"


def _sqlite_uri(path: Path, **query: str) -> str:
    return f"{path.expanduser().resolve().as_uri()}?{urlencode(query)}"


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
        source_path = self.database.path.expanduser().resolve()
        source_verification = self._verify_path(source_path, immutable=False)
        if not source_verification["ok"]:
            raise BackupOperationError(
                operation="backup",
                code="invalid_source",
                path=source_path,
                detail="backup source is invalid",
            )

        target, temporary = self._allocate_backup_paths(label)
        try:
            with closing(
                sqlite3.connect(
                    _sqlite_uri(source_path, mode="ro"),
                    uri=True,
                )
            ) as source, closing(sqlite3.connect(temporary)) as destination:
                source.execute("PRAGMA query_only = ON")
                source.backup(destination)
        except (OSError, sqlite3.Error):
            self._remove_sidecars(temporary)
            raise BackupOperationError(
                operation="backup",
                code="backup_failed",
                path=temporary,
                detail="backup creation failed",
            ) from None

        verification = self.verify(temporary)
        if not verification["ok"]:
            self._remove_sidecars(temporary)
            raise BackupOperationError(
                operation="backup",
                code="candidate_verification_failed",
                path=temporary,
                detail="backup candidate verification failed",
            )

        try:
            os.link(temporary, target)
        except (FileExistsError, OSError):
            raise BackupOperationError(
                operation="backup",
                code="promotion_failed",
                path=temporary,
                detail="backup candidate promotion failed",
            ) from None
        temporary.unlink()
        self._remove_sidecars(temporary)
        return target

    def _allocate_backup_paths(self, label: str) -> tuple[Path, Path]:
        prefix = f"hermes-{_timestamp()}-{_label(label)}"
        for _ in range(16):
            token = secrets.token_hex(8)
            target = self.backup_dir / f"{prefix}-{token}.db"
            temporary = target.with_suffix(".db.tmp")
            try:
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                continue
            except OSError:
                raise BackupOperationError(
                    operation="backup",
                    code="candidate_allocation_failed",
                    path=self.backup_dir,
                    detail="backup candidate allocation failed",
                ) from None
            os.close(descriptor)
            return target, temporary
        raise BackupOperationError(
            operation="backup",
            code="candidate_allocation_failed",
            path=self.backup_dir,
            detail="backup candidate allocation failed",
        )

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
        return self._verify_path(
            Path(path).expanduser().resolve(),
            immutable=True,
        )

    def _verify_path(
        self,
        candidate: Path,
        *,
        immutable: bool,
    ) -> BackupVerification:
        candidate = candidate.expanduser().resolve()
        if not candidate.is_file():
            return self._verification_failure(
                candidate,
                "backup file does not exist",
            )
        try:
            with closing(
                sqlite3.connect(
                    _sqlite_uri(
                        candidate,
                        mode="ro",
                        **({"immutable": "1"} if immutable else {}),
                    ),
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
            raise BackupOperationError(
                operation="restore",
                code="invalid_backup",
                path=source_path,
                detail="restore source is invalid",
            )
        if (
            self.database.path.exists()
            and source_path.samefile(self.database.path)
        ):
            raise BackupOperationError(
                operation="restore",
                code="source_is_destination",
                path=source_path,
                detail="restore source cannot be the live database",
            )

        pre_restore = (
            self.create_backup(label="pre-restore")
            if self.database.path.exists()
            else None
        )
        self.database.path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.database.path.name}.restore-",
            suffix=".tmp",
            dir=self.database.path.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            source_uri = _sqlite_uri(
                source_path,
                mode="ro",
                immutable="1",
            )
            with closing(
                sqlite3.connect(source_uri, uri=True)
            ) as source, closing(sqlite3.connect(temporary)) as destination:
                source.execute("PRAGMA query_only = ON")
                source.backup(destination)
            restored_check = self.verify(temporary)
            if not restored_check["ok"]:
                raise BackupOperationError(
                    operation="restore",
                    code="restored_candidate_invalid",
                    path=source_path,
                    detail="restored database verification failed",
                )
            for suffix in ("-wal", "-shm"):
                Path(str(self.database.path) + suffix).unlink(missing_ok=True)
            temporary.replace(self.database.path)
        except BackupOperationError:
            raise
        except (OSError, sqlite3.Error):
            raise BackupOperationError(
                operation="restore",
                code="restore_failed",
                path=source_path,
                detail="restore failed",
            ) from None
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

    @staticmethod
    def _remove_sidecars(database_path: Path) -> None:
        for suffix in ("-wal", "-shm"):
            Path(str(database_path) + suffix).unlink(missing_ok=True)
