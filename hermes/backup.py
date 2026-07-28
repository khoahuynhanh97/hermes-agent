from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, TypedDict
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
VERIFICATION_COUNT_TABLES = (
    "lessons",
    "sources",
    "evidence",
    "lesson_events",
    "lesson_fts",
)

_SAFE_OPERATION_DETAILS = {
    ("backup", "invalid_source"): "backup source is invalid",
    ("backup", "backup_failed"): "backup creation failed",
    ("backup", "candidate_verification_failed"): (
        "backup candidate verification failed"
    ),
    ("backup", "promotion_failed"): "backup candidate promotion failed",
    ("backup", "promotion_cleanup_failed"): (
        "backup candidate promotion cleanup failed"
    ),
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
    ("restore", "offline_lease_required"): (
        "restore requires an active offline access lease"
    ),
    ("restore", "offline_lease_revoked"): (
        "offline access lease is no longer active"
    ),
    ("restore", "exclusive_access_required"): (
        "restore requires exclusive database access"
    ),
    ("restore", "stage_failed"): "restore staging failed",
    ("restore", "rollback_failed"): "restore rollback failed",
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
    sha256: str
    file_identity: str
    detail: str


class OfflineAccessLease(Protocol):
    """Externally owned proof of exclusive offline access.

    The provider must prevent concurrent writers for the entire restore,
    including destructive staging, rollback, and cleanup. BackupManager only
    validates this lease; it never closes, releases, or deletes it.
    """

    def validate(self) -> bool:
        """Return whether exclusive offline access is still active."""
        ...


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_stat(path: Path) -> tuple[int, int, int, int, int]:
    value = path.stat()
    return (
        int(value.st_dev),
        int(value.st_ino),
        int(value.st_size),
        int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _snapshot_identity(value: tuple[int, int, int, int, int]) -> str:
    return hashlib.sha256(
        ":".join(str(item) for item in value).encode("ascii")
    ).hexdigest()


class SQLiteBackupManager:
    def __init__(
        self,
        database: Database | None = None,
        backup_dir: str | Path | None = None,
        keep: int = 14,
        verification_hook: Callable[[str, Path], None] | None = None,
    ):
        self.database = database or Database()
        default_dir = self.database.path.parent / "backups"
        self.backup_dir = Path(
            backup_dir or os.environ.get("HERMES_BACKUP_DIR", "") or default_dir
        ).expanduser().resolve()
        self.keep = max(1, int(keep))
        self._verification_hook = verification_hook
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
        try:
            temporary.unlink()
        except OSError:
            try:
                target.unlink()
            except OSError:
                for alias in (target, temporary):
                    try:
                        alias.chmod(0o444)
                    except OSError:
                        pass
            raise BackupOperationError(
                operation="backup",
                code="promotion_cleanup_failed",
                path=temporary,
                detail="backup candidate promotion cleanup failed",
            ) from None
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
        sha256: str = "",
        file_identity: str = "",
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
            "sha256": sha256,
            "file_identity": file_identity,
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
            initial_stat = _snapshot_stat(candidate)
            digest = _sha256_file(candidate)
            after_digest_stat = _snapshot_stat(candidate)
            if initial_stat != after_digest_stat:
                return self._verification_failure(
                    candidate,
                    "backup changed during verification",
                )
            if self._verification_hook is not None:
                self._verification_hook(
                    "after_digest_before_sqlite",
                    candidate,
                )
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
            final_digest = _sha256_file(candidate)
            final_stat = _snapshot_stat(candidate)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            return self._verification_failure(
                candidate,
                "backup is not a readable SQLite database",
            )
        if (
            initial_stat != final_stat
            or digest != final_digest
        ):
            return self._verification_failure(
                candidate,
                "backup changed during verification",
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
            "sha256": digest,
            "file_identity": _snapshot_identity(initial_stat),
            "detail": detail,
        }

    def restore(
        self,
        backup_path: str | Path,
        *,
        lease: OfflineAccessLease | None = None,
    ) -> dict[str, str]:
        self._require_active_lease(
            lease,
            code="offline_lease_required",
        )
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
        rollback_dir: Path | None = None
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

            staged: list[tuple[Path, Path]] = []
            self._require_active_lease(
                lease,
                code="offline_lease_revoked",
            )
            if self.database.path.exists():
                self._checkpoint_live_database()
                rollback_dir = self._allocate_restore_rollback()
                staged = self._stage_live_database(rollback_dir)
            try:
                self._require_active_lease(
                    lease,
                    code="offline_lease_revoked",
                )
            except BackupOperationError:
                self._rollback_staged(staged)
                raise
            try:
                self._replace_path(temporary, self.database.path)
            except OSError:
                self._rollback_staged(staged)
                raise BackupOperationError(
                    operation="restore",
                    code="restore_failed",
                    path=source_path,
                    detail="restore failed",
                ) from None
        except BackupOperationError:
            raise
        except (OSError, sqlite3.Error):
            raise BackupOperationError(
                operation="restore",
                code="restore_failed",
                path=source_path,
                detail="restore failed",
            ) from None
        self._require_active_lease(
            lease,
            code="offline_lease_revoked",
            path=rollback_dir or self.database.path,
        )
        return {
            "restored_from": str(source_path),
            "database": str(self.database.path),
            "pre_restore_backup": str(pre_restore or ""),
            "rollback_snapshot": str(rollback_dir or ""),
        }

    def _require_active_lease(
        self,
        lease: OfflineAccessLease | None,
        *,
        code: str,
        path: Path | None = None,
    ) -> None:
        validate = getattr(lease, "validate", None)
        try:
            active = bool(validate()) if callable(validate) else False
        except Exception:
            active = False
        if active:
            return
        raise BackupOperationError(
            operation="restore",
            code=code,
            path=path or self.database.path,
            detail=(
                "restore requires an active offline access lease"
                if code == "offline_lease_required"
                else "offline access lease is no longer active"
            ),
        )

    def _checkpoint_live_database(self) -> None:
        try:
            with closing(
                sqlite3.connect(
                    _sqlite_uri(self.database.path, mode="rw"),
                    uri=True,
                    timeout=self.database.busy_timeout_ms / 1000,
                    isolation_level=None,
                )
            ) as connection:
                connection.execute(
                    f"PRAGMA busy_timeout = {self.database.busy_timeout_ms}"
                )
                checkpoint = connection.execute(
                    "PRAGMA wal_checkpoint(TRUNCATE)"
                ).fetchone()
                if checkpoint and int(checkpoint[0]) != 0:
                    raise BackupOperationError(
                        operation="restore",
                        code="exclusive_access_required",
                        path=self.database.path,
                        detail="restore requires exclusive database access",
                    )
                connection.execute("BEGIN EXCLUSIVE")
                connection.rollback()
        except BackupOperationError:
            raise
        except (OSError, sqlite3.Error):
            raise BackupOperationError(
                operation="restore",
                code="exclusive_access_required",
                path=self.database.path,
                detail="restore requires exclusive database access",
            ) from None

    def _allocate_restore_rollback(self) -> Path:
        for _ in range(16):
            path = self.database.path.parent / (
                f".{self.database.path.name}.restore-rollback-"
                f"{_timestamp()}-{secrets.token_hex(8)}"
            )
            try:
                path.mkdir()
            except FileExistsError:
                continue
            except OSError:
                break
            return path
        raise BackupOperationError(
            operation="restore",
            code="stage_failed",
            path=self.database.path,
            detail="restore staging failed",
        )

    def _stage_live_database(
        self,
        rollback_dir: Path,
    ) -> list[tuple[Path, Path]]:
        originals = [
            Path(f"{self.database.path}-wal"),
            Path(f"{self.database.path}-shm"),
            self.database.path,
        ]
        staged: list[tuple[Path, Path]] = []
        try:
            for original in originals:
                if not original.exists():
                    continue
                rollback_path = rollback_dir / original.name
                self._replace_path(original, rollback_path)
                staged.append((original, rollback_path))
        except OSError:
            self._rollback_staged(staged)
            raise BackupOperationError(
                operation="restore",
                code="stage_failed",
                path=self.database.path,
                detail="restore staging failed",
            ) from None
        return staged

    def _rollback_staged(
        self,
        staged: list[tuple[Path, Path]],
    ) -> None:
        try:
            for original, rollback_path in reversed(staged):
                if rollback_path.exists():
                    self._replace_path(rollback_path, original)
        except OSError:
            raise BackupOperationError(
                operation="restore",
                code="rollback_failed",
                path=self.database.path,
                detail="restore rollback failed",
            ) from None

    @staticmethod
    def _replace_path(source: Path, target: Path) -> None:
        os.replace(source, target)

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
