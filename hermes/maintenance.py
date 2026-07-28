from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, Protocol

from .backup import BackupVerification, OfflineAccessLease, SQLiteBackupManager
from .data_health import AuditReport, DataHealth, RepairPlan, RepairReport
from .db import SCHEMA_VERSION


MaintenanceStatus = Literal[
    "completed",
    "failed",
    "manual_intervention_required",
]

_STATE_VERSION = 4
_RUN_ID_PATTERN = re.compile(r"^run-[0-9a-f]{32}$")
_RUN_ALIAS_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
_ARTIFACT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$")
_ERROR_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
_HEX_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_COUNT_KEYS = (
    "lessons",
    "pending",
    "approved",
    "rejected",
    "sources",
    "evidence",
    "lesson_events",
    "fts_rows",
)
_BACKUP_COUNT_KEYS = ("lessons", "sources", "lesson_events")
_FULL_BACKUP_COUNT_KEYS = (
    "lessons",
    "sources",
    "evidence",
    "lesson_events",
    "lesson_fts",
)
_SAFE_ACTION_KINDS = {"rebuild_fts", "set_approved_at", "reject_lesson"}
_STAGES = (
    "discovered",
    "stopped",
    "backup_created",
    "backup_verified",
    "pre_audited",
    "repair_intent",
    "repaired",
    "post_checked",
    "restart_intent",
    "restarted",
    "completed",
)
_STATE_KEYS = {
    "state_version",
    "run_id",
    "status",
    "started_at",
    "updated_at",
    "completed_stages",
    "database_identity_hash",
    "artifact_ref",
    "artifact_hash",
    "artifact_digest",
    "backup",
    "pre_audit",
    "repair_intent",
    "repair",
    "post_audit",
    "process",
    "error_code",
    "pending_status",
    "pending_error_code",
    "report_attempt",
    "active_report_attempt",
    "report_owner_hash",
    "report_phase",
    "report_snapshot_at",
    "report_json_digest",
    "report_markdown_digest",
}
_SENSITIVE_RUN_WORDS = (
    "content",
    "cookie",
    "credential",
    "environment",
    "excerpt",
    "secret",
    "telegram",
    "token",
    "url",
)


class MaintenanceBusyError(RuntimeError):
    pass


class ArtifactCollisionError(RuntimeError):
    pass


class StateValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeState:
    """Only process cardinality is persisted; restart config stays adapter-owned."""

    bot_count: int
    worker_count: int
    unambiguous: bool

    def __post_init__(self) -> None:
        if (
            type(self.bot_count) is not int
            or self.bot_count < 0
            or type(self.worker_count) is not int
            or self.worker_count < 0
            or type(self.unambiguous) is not bool
        ):
            raise ValueError("runtime counts and ambiguity flag are invalid")

    @property
    def bot_running(self) -> bool:
        return self.bot_count > 0

    @property
    def worker_running(self) -> bool:
        return self.worker_count > 0


class ProcessController(Protocol):
    def discover(self) -> RuntimeState: ...

    def stop(self, state: RuntimeState, timeout_seconds: int) -> None: ...

    def acquire_offline_lease(
        self,
        state: RuntimeState,
    ) -> OfflineAccessLease: ...

    def release_offline_lease(self, lease: OfflineAccessLease) -> None: ...

    def start(self, state: RuntimeState) -> RuntimeState: ...

    def verify(self, state: RuntimeState) -> dict[str, bool]: ...


@dataclass(frozen=True)
class MaintenanceResult:
    run_id: str
    status: MaintenanceStatus
    backup_path: str
    report_json: str
    report_markdown: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _identifier_hash(value: str) -> str:
    return hashlib.sha256(
        f"hermes-maintenance:{value}".encode("utf-8")
    ).hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class DatabaseRunLock:
    """OS-owned advisory lock; closing the handle releases ownership."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        lock_root: str | Path | None = None,
    ):
        resolved = Path(database_path).expanduser().resolve()
        try:
            file_stat = resolved.stat()
        except OSError:
            identity_source = f"path:{os.path.normcase(str(resolved))}"
        else:
            if file_stat.st_ino:
                identity_source = (
                    f"file:{int(file_stat.st_dev)}:{int(file_stat.st_ino)}"
                )
            else:
                identity_source = f"path:{os.path.normcase(str(resolved))}"
        identity = _identifier_hash(identity_source)
        if sys.platform == "win32":
            default_root = (
                Path(os.environ.get("LOCALAPPDATA", tempfile.gettempdir()))
                / "HermesAgent"
                / "maintenance-locks"
            )
        else:
            default_root = (
                Path(tempfile.gettempdir())
                / "hermes-agent-maintenance-locks"
            )
        root = Path(
            lock_root or default_root
        ).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / f"{identity}.lock"
        self.handle = None

    def acquire(self) -> None:
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as initializer:
                initializer.write(b"0")
                initializer.flush()
                os.fsync(initializer.fileno())
        try:
            self.handle = self.path.open("r+b")
        except (OSError, PermissionError):
            raise MaintenanceBusyError("maintenance is already running") from None
        self.handle.seek(0)
        try:
            if sys.platform == "win32":
                import msvcrt

                msvcrt.locking(
                    self.handle.fileno(),
                    msvcrt.LK_NBLCK,
                    1,
                )
            else:
                import fcntl

                fcntl.flock(
                    self.handle.fileno(),
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
        except (OSError, BlockingIOError):
            self.handle.close()
            self.handle = None
            raise MaintenanceBusyError("maintenance is already running") from None

    def close(self) -> None:
        if self.handle is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(
                    self.handle.fileno(),
                    msvcrt.LK_UNLCK,
                    1,
                )
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


class MaintenanceRunner:
    """Fail-closed orchestration for one serialized offline maintenance run."""

    def __init__(
        self,
        *,
        process_controller: ProcessController,
        backup_manager: SQLiteBackupManager,
        data_health: DataHealth,
        report_dir: str | Path,
        run_id: str | None = None,
        stop_timeout_seconds: int = 60,
        lock_root: str | Path | None = None,
        crash_hook: Callable[[str], None] | None = None,
    ):
        if run_id is not None:
            normalized = run_id.casefold()
            if (
                not _RUN_ALIAS_PATTERN.fullmatch(run_id)
                or any(word in normalized for word in _SENSITIVE_RUN_WORDS)
            ):
                raise ValueError("run_id alias is unsafe")
            effective_run_id = (
                f"run-{_identifier_hash(f'external:{run_id}')[:32]}"
            )
        else:
            effective_run_id = None
        if stop_timeout_seconds <= 0:
            raise ValueError("stop_timeout_seconds must be positive")
        self.process_controller = process_controller
        self.backup_manager = backup_manager
        self.data_health = data_health
        self.report_dir = Path(report_dir).expanduser().resolve()
        self.requested_run_id = effective_run_id
        self.run_id = effective_run_id
        self.stop_timeout_seconds = int(stop_timeout_seconds)
        self.lock_root = (
            Path(lock_root).expanduser().resolve()
            if lock_root is not None
            else None
        )
        self.crash_hook = crash_hook
        self._state: dict[str, object] | None = None
        self._state_path: Path | None = None
        self._offline_lease: OfflineAccessLease | None = None
        self._reserved_attempt = 0
        self._resumed = False

    def run(self, *, resume_id: str | None = None) -> MaintenanceResult:
        if resume_id is not None:
            if not _RUN_ID_PATTERN.fullmatch(resume_id):
                raise ValueError("resume_id is not a canonical run identifier")
            if (
                self.requested_run_id is not None
                and self.requested_run_id != resume_id
            ):
                raise ValueError("resume_id conflicts with the external alias")
            if self.run_id is not None and self.run_id != resume_id:
                raise ValueError("resume_id conflicts with runner state")
            self.requested_run_id = resume_id
            self.run_id = resume_id
        self.report_dir.mkdir(parents=True, exist_ok=True)
        backup_database_path = self._adapter_database_path(
            self.backup_manager
        )
        if backup_database_path is None:
            raise StateValidationError("backup database configuration is missing")
        run_lock = DatabaseRunLock(
            database_path=backup_database_path,
            lock_root=self.lock_root,
        )
        run_lock.acquire()
        try:
            state = self._load_or_create_state()
            if state["status"] == "completed":
                self._ensure_terminal_reports()
                return self._result_from_state()
            self._reserve_report_artifacts()
            if state["pending_status"]:
                return self._reconcile_pending_terminal()
            state["status"] = "running"
            state["error_code"] = ""
            self._persist_state()
            configuration_error = self._bind_database_identity()
            if configuration_error is not None:
                return configuration_error
            return self._run_locked()
        finally:
            process = (
                self._process_payload()
                if self._state is not None
                else {}
            )
            release_pending = bool(
                process.get("lease_release_pending", False)
            )
            if self._offline_lease is not None and not release_pending:
                if not self._release_offline_lease():
                    run_lock.close()
                    raise RuntimeError("offline lease release failed")
            run_lock.close()

    def _crash(self, boundary: str) -> None:
        if self.crash_hook is not None:
            self.crash_hook(boundary)

    def _run_locked(self) -> MaintenanceResult:
        state = self._require_state()
        completed = self._completed_stages()
        original_state = self._runtime_state_from_persisted()

        if "restarted" in completed and "completed" not in completed:
            return self._finish("completed", "")

        if "restart_intent" in completed and "restarted" not in completed:
            if not self._reverify_stored_backup():
                return self._finish(
                    "manual_intervention_required",
                    "resume_backup_invalid",
                )
            return self._recover_restart_intent(original_state)

        if "discovered" not in completed:
            try:
                original_state = self.process_controller.discover()
            except Exception:
                return self._finish("failed", "discovery_failed")
            self._set_discovery(original_state)
            if not self._is_exact_running_state(original_state):
                code = (
                    "discovery_ambiguous"
                    if not original_state.unambiguous
                    else "runtime_not_ready"
                )
                return self._finish("failed", code)
            self._complete_stage("discovered")

        if "stopped" not in completed:
            try:
                self.process_controller.stop(
                    original_state,
                    self.stop_timeout_seconds,
                )
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "stop_failed",
                )
            self._update_process(stop_succeeded=True)
            self._complete_stage("stopped")

        lease_error = self._acquire_offline_lease(original_state)
        if lease_error is not None:
            return lease_error

        if self._resumed and "backup_verified" in completed:
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            if not self._reverify_stored_backup():
                return self._finish(
                    "manual_intervention_required",
                    "resume_backup_invalid",
                )

        if "backup_created" not in completed:
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            try:
                backup_path = self.backup_manager.create_backup(
                    label=f"maintenance-{self._run_id()}"
                )
                self._store_backup_artifact(Path(backup_path))
            except Exception:
                return self._finish("failed", "backup_creation_failed")
            self._complete_stage("backup_created")

        if "backup_verified" not in completed:
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            verification = self._verify_artifact()
            if verification is None:
                return self._finish("failed", "backup_verification_failed")
            if not self._backup_is_valid(verification):
                return self._finish("failed", "backup_verification_failed")
            state["backup"] = self._backup_summary(verification)
            state["artifact_digest"] = verification["sha256"]
            self._complete_stage("backup_verified")

        current_audit: AuditReport | None = None
        if "pre_audited" not in completed:
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            try:
                current_audit = self.data_health.audit()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "pre_audit_failed",
                )
            if not self._audit_core_is_valid(current_audit):
                return self._finish(
                    "manual_intervention_required",
                    "pre_audit_invalid",
                )
            state["pre_audit"] = self._audit_summary(current_audit)
            if not self._plan_is_safe(current_audit.repair_plan):
                return self._finish(
                    "manual_intervention_required",
                    "unsafe_repair_plan",
                )
            if not self._backup_matches_audit(current_audit):
                return self._finish(
                    "manual_intervention_required",
                    "backup_source_mismatch",
                )
            self._complete_stage("pre_audited")

        if "repair_intent" not in completed:
            if current_audit is None:
                try:
                    current_audit = self.data_health.audit()
                except Exception:
                    return self._finish(
                        "manual_intervention_required",
                        "pre_audit_failed",
                    )
                summary = self._audit_summary(current_audit)
                if (
                    not self._audit_core_is_valid(current_audit)
                    or not self._plan_is_safe(current_audit.repair_plan)
                    or not self._backup_matches_audit(current_audit)
                    or summary != state["pre_audit"]
                ):
                    return self._finish(
                        "manual_intervention_required",
                        "pre_audit_changed",
                    )
            state["repair_intent"] = self._repair_intent_summary(
                current_audit.repair_plan
            )
            self._complete_stage("repair_intent")

        if "repaired" not in completed:
            if current_audit is None:
                try:
                    current_audit = self.data_health.audit()
                except Exception:
                    return self._finish(
                        "manual_intervention_required",
                        "repair_reconciliation_failed",
                    )
            current_intent = self._repair_intent_summary(
                current_audit.repair_plan
            )
            intended = state["repair_intent"]
            if current_intent["plan_fingerprint"] != intended[
                "plan_fingerprint"
            ]:
                if self._audit_matches_applied_intent(current_audit):
                    state["repair"] = self._reconciled_repair_summary()
                    self._complete_stage("repaired")
                    current_audit = None
                else:
                    return self._finish(
                        "manual_intervention_required",
                        "repair_reconciliation_failed",
                    )
            if "repaired" in self._completed_stages():
                pass
            elif not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            elif not self._reverify_stored_backup():
                return self._finish(
                    "manual_intervention_required",
                    "resume_backup_invalid",
                )
            else:
                try:
                    repair_report = self.data_health.repair(
                        current_audit.repair_plan
                    )
                except Exception:
                    return self._finish("failed", "repair_failed")
                if not self._validate_offline_lease():
                    return self._finish(
                        "manual_intervention_required",
                        "offline_lease_invalid",
                    )
                self._crash("after_repair_commit")
                if not self._repair_report_is_valid(repair_report):
                    return self._finish(
                        "manual_intervention_required",
                        "repair_report_invalid",
                    )
                state["repair"] = self._repair_summary(repair_report)
                self._complete_stage("repaired")

        if "post_checked" not in completed:
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            try:
                post_audit = self.data_health.audit()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "post_audit_failed",
                )
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            if not self._audit_core_is_valid(post_audit):
                return self._finish(
                    "manual_intervention_required",
                    "post_check_failed",
                )
            state["post_audit"] = self._audit_summary(post_audit)
            if not self._post_audit_is_valid():
                return self._finish(
                    "manual_intervention_required",
                    "post_check_failed",
                )
            self._complete_stage("post_checked")

        if "restart_intent" not in completed:
            self._update_process(restart_intent=True)
            self._complete_stage("restart_intent")

        if not self._validate_offline_lease():
            return self._finish(
                "manual_intervention_required",
                "offline_lease_invalid",
            )
        if not self._release_offline_lease():
            return self._finish(
                "manual_intervention_required",
                "offline_lease_release_failed",
            )

        restart_result = self._start_and_verify(original_state)
        if restart_result is not None:
            return restart_result
        self._complete_stage("restarted")
        self._crash("after_restart_persist")
        return self._finish("completed", "")

    def _recover_restart_intent(
        self,
        original_state: RuntimeState,
    ) -> MaintenanceResult:
        try:
            observed = self.process_controller.discover()
        except Exception:
            return self._finish(
                "manual_intervention_required",
                "restart_state_unknown",
            )

        if self._is_exact_running_state(observed):
            try:
                health = self.process_controller.verify(observed)
            except Exception:
                return self._cleanup_restart_state(
                    observed,
                    "restart_verification_failed",
                )
            if self._health_is_exact(health):
                self._record_restart(observed, health)
                self._complete_stage("restarted")
                self._crash("after_restart_persist")
                return self._finish("completed", "")
            return self._cleanup_restart_state(
                observed,
                "restart_verification_failed",
            )

        if self._is_exact_stopped_state(observed):
            lease_error = self._acquire_offline_lease(original_state)
            if lease_error is not None:
                return lease_error
            if (
                not self._validate_offline_lease()
                or not self._reverify_stored_backup()
            ):
                return self._finish(
                    "manual_intervention_required",
                    "resume_backup_invalid",
                )
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            if not self._release_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_release_failed",
                )
            restart_result = self._start_and_verify(original_state)
            if restart_result is not None:
                return restart_result
            self._complete_stage("restarted")
            self._crash("after_restart_persist")
            return self._finish("completed", "")

        return self._cleanup_restart_state(
            observed,
            (
                "restart_state_ambiguous"
                if not observed.unambiguous
                else "partial_restart_detected"
            ),
        )

    def _start_and_verify(
        self,
        original_state: RuntimeState,
    ) -> MaintenanceResult | None:
        try:
            started = self.process_controller.start(original_state)
        except Exception:
            try:
                observed = self.process_controller.discover()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "restart_state_unknown",
                )
            if self._is_exact_stopped_state(observed):
                return self._finish("failed", "restart_failed")
            return self._cleanup_restart_state(observed, "restart_failed")

        if not self._is_exact_running_state(started):
            return self._cleanup_restart_state(
                started,
                "restart_cardinality_invalid",
            )
        try:
            health = self.process_controller.verify(started)
        except Exception:
            return self._cleanup_restart_state(
                started,
                "restart_verification_failed",
            )
        if not self._health_is_exact(health):
            return self._cleanup_restart_state(
                started,
                "restart_verification_failed",
            )
        self._record_restart(started, health)
        return None

    def _cleanup_restart_state(
        self,
        state: RuntimeState,
        error_code: str,
    ) -> MaintenanceResult:
        if state.bot_count <= 0 and state.worker_count <= 0:
            return self._finish(
                "manual_intervention_required"
                if not state.unambiguous
                else "failed",
                error_code,
            )
        try:
            self.process_controller.stop(state, self.stop_timeout_seconds)
        except Exception:
            self._update_process(partial_restart_stopped=False)
            return self._finish(
                "manual_intervention_required",
                "partial_restart_stop_failed",
            )
        self._update_process(partial_restart_stopped=True)
        return self._finish("failed", error_code)

    def _record_restart(
        self,
        state: RuntimeState,
        health: dict[str, bool],
    ) -> None:
        self._update_process(
            start_counts={
                "bot": int(state.bot_count),
                "worker": int(state.worker_count),
            },
            health={
                "bot": health.get("bot") is True,
                "worker": health.get("worker") is True,
            },
        )

    def _acquire_offline_lease(
        self,
        original_state: RuntimeState,
    ) -> MaintenanceResult | None:
        if self._offline_lease is not None:
            return None
        try:
            lease = self.process_controller.acquire_offline_lease(
                original_state
            )
        except Exception:
            return self._finish(
                "manual_intervention_required",
                "offline_lease_acquisition_failed",
            )
        self._offline_lease = lease
        self._update_process(offline_lease_acquired=True)
        return None

    def _validate_offline_lease(self) -> bool:
        if self._offline_lease is None:
            return False
        try:
            return self._offline_lease.validate() is True
        except Exception:
            return False

    def _release_offline_lease(self) -> bool:
        lease = self._offline_lease
        if lease is None:
            return True
        try:
            self.process_controller.release_offline_lease(lease)
        except Exception:
            self._update_process(lease_release_pending=True)
            return False
        self._offline_lease = None
        self._update_process(lease_release_pending=False)
        return True

    def _bind_database_identity(self) -> MaintenanceResult | None:
        backup_path = self._adapter_database_path(self.backup_manager)
        health_path = self._adapter_database_path(self.data_health)
        if backup_path is None or health_path is None:
            return self._finish(
                "failed",
                "database_configuration_missing",
            )
        backup_resolved = backup_path.expanduser().resolve()
        health_resolved = health_path.expanduser().resolve()
        if backup_resolved != health_resolved:
            return self._finish(
                "failed",
                "database_configuration_mismatch",
            )
        try:
            stat = backup_resolved.stat()
        except OSError:
            return self._finish(
                "failed",
                "database_source_missing",
            )
        identity_hash = _identifier_hash(
            json.dumps(
                {
                    "location_hash": _identifier_hash(str(backup_resolved)),
                    "device": int(stat.st_dev),
                    "inode": int(stat.st_ino),
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        state = self._require_state()
        persisted = str(state["database_identity_hash"])
        if persisted and persisted != identity_hash:
            return self._finish(
                "manual_intervention_required",
                "database_configuration_changed",
            )
        state["database_identity_hash"] = identity_hash
        self._persist_state()
        return None

    @staticmethod
    def _adapter_database_path(adapter: object) -> Path | None:
        database = getattr(adapter, "database", None)
        path = getattr(database, "path", None)
        if path is None:
            return None
        return Path(path)

    def _store_backup_artifact(self, path: Path) -> None:
        backup_dir = Path(self.backup_manager.backup_dir).expanduser().resolve()
        resolved = path.expanduser().resolve()
        if resolved.parent != backup_dir:
            raise ValueError("backup artifact is outside configured storage")
        if not _ARTIFACT_PATTERN.fullmatch(resolved.name):
            raise ValueError("backup artifact reference is invalid")
        state = self._require_state()
        state["artifact_ref"] = resolved.name
        state["artifact_hash"] = _identifier_hash(str(resolved))

    def _artifact_path(self) -> Path:
        reference = str(self._require_state()["artifact_ref"])
        if not _ARTIFACT_PATTERN.fullmatch(reference):
            raise StateValidationError("backup artifact reference is invalid")
        backup_dir = Path(self.backup_manager.backup_dir).expanduser().resolve()
        candidate = (backup_dir / reference).resolve()
        if candidate.parent != backup_dir:
            raise StateValidationError("backup artifact escaped storage")
        if _identifier_hash(str(candidate)) != self._require_state()[
            "artifact_hash"
        ]:
            raise StateValidationError("backup artifact identity changed")
        return candidate

    def _verify_artifact(self) -> BackupVerification | None:
        try:
            return self.backup_manager.verify(self._artifact_path())
        except Exception:
            return None

    def _reverify_stored_backup(self) -> bool:
        verification = self._verify_artifact()
        if verification is None or not self._backup_is_valid(verification):
            return False
        state = self._require_state()
        return (
            verification["sha256"] == state["artifact_digest"]
            and self._backup_summary(verification) == state["backup"]
        )

    def _backup_matches_audit(self, audit: AuditReport) -> bool:
        backup = self._require_state()["backup"]
        if not isinstance(backup, dict):
            return False
        backup_counts = backup["counts"]
        return all(
            backup_counts[backup_key] == audit.counts.get(audit_key, -1)
            for audit_key, backup_key in (
                ("lessons", "lessons"),
                ("sources", "sources"),
                ("evidence", "evidence"),
                ("lesson_events", "lesson_events"),
                ("fts_rows", "lesson_fts"),
            )
        )

    @staticmethod
    def _backup_is_valid(verification: BackupVerification) -> bool:
        counts = verification.get("counts")
        return (
            verification.get("ok") is True
            and verification.get("integrity") == "ok"
            and type(verification.get("foreign_key_violations")) is int
            and verification.get("foreign_key_violations") == 0
            and type(verification.get("schema_version")) is int
            and verification.get("schema_version") == SCHEMA_VERSION
            and verification.get("required_tables_missing") == []
            and isinstance(counts, dict)
            and set(counts) == set(_FULL_BACKUP_COUNT_KEYS)
            and all(
                type(value) is int and value >= 0
                for value in counts.values()
            )
            and isinstance(verification.get("sha256"), str)
            and _HEX_PATTERN.fullmatch(verification["sha256"]) is not None
            and isinstance(verification.get("file_identity"), str)
            and _HEX_PATTERN.fullmatch(
                verification["file_identity"]
            ) is not None
        )

    @staticmethod
    def _audit_core_is_valid(audit: AuditReport) -> bool:
        return (
            audit.integrity == "ok"
            and type(audit.foreign_key_violations) is int
            and audit.foreign_key_violations == 0
            and type(audit.schema_version) is int
            and audit.schema_version == SCHEMA_VERSION
            and isinstance(audit.counts, dict)
            and set(audit.counts) == set(_COUNT_KEYS)
            and all(
                type(value) is int and value >= 0
                for value in audit.counts.values()
            )
        )

    def _post_audit_is_valid(self) -> bool:
        state = self._require_state()
        return self._post_summaries_are_valid(
            state["pre_audit"],
            state["post_audit"],
            state["repair"],
        )

    @staticmethod
    def _post_summaries_are_valid(
        pre: object,
        post: object,
        repair: object,
    ) -> bool:
        if not all(isinstance(value, dict) for value in (pre, post, repair)):
            return False
        if not (
            post["integrity_ok"]
            and post["foreign_keys_ok"]
            and post["schema_ok"]
            and post["repair_class_counts"]["safe"] == 0
            and post["planned_action_count"] == 0
        ):
            return False
        before = pre["counts"]
        after = post["counts"]
        transitions = repair["applied_transition_counts"]
        approved_rejections = transitions["approved_to_rejected"]
        pending_rejections = transitions["pending_to_rejected"]
        other_rejections = transitions["other_to_rejected"]
        rejection_count = (
            approved_rejections + pending_rejections + other_rejections
        )
        return (
            after["lessons"] == before["lessons"]
            and after["sources"] == before["sources"]
            and after["evidence"] == before["evidence"]
            and after["pending"] == before["pending"] - pending_rejections
            and after["approved"] == before["approved"] - approved_rejections
            and after["rejected"] == before["rejected"] + rejection_count
            and after["lesson_events"]
            == before["lesson_events"] + rejection_count
            and after["fts_rows"] == after["approved"]
        )

    @staticmethod
    def _plan_is_safe(plan: RepairPlan) -> bool:
        action_ids: set[str] = set()
        for action in plan.actions:
            if action.kind not in _SAFE_ACTION_KINDS:
                return False
            if not action.action_id or action.action_id in action_ids:
                return False
            action_ids.add(action.action_id)
        return True

    @staticmethod
    def _repair_intent_summary(plan: RepairPlan) -> dict[str, object]:
        action_records: list[dict[str, str]] = []
        action_hashes: list[str] = []
        kind_counts = {
            "rebuild_fts": 0,
            "set_approved_at": 0,
            "reject_lesson": 0,
        }
        transitions = {
            "approved_to_rejected": 0,
            "pending_to_rejected": 0,
            "other_to_rejected": 0,
        }
        for action in plan.actions:
            action_hash = _identifier_hash(action.action_id)
            action_hashes.append(action_hash)
            kind_counts[action.kind] += 1
            action_records.append(
                {"kind": action.kind, "action_hash": action_hash}
            )
            if action.kind == "reject_lesson":
                status = str(action.expected.get("status", "other"))
                transition = (
                    f"{status}_to_rejected"
                    if status in {"approved", "pending"}
                    else "other_to_rejected"
                )
                transitions[transition] += 1
        canonical = json.dumps(
            action_records,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return {
            "plan_fingerprint": _identifier_hash(canonical),
            "planned_count": len(plan.actions),
            "planned_action_id_hashes": sorted(action_hashes),
            "planned_kind_counts": kind_counts,
            "planned_transition_counts": transitions,
        }

    def _audit_matches_applied_intent(self, audit: AuditReport) -> bool:
        if (
            not self._audit_core_is_valid(audit)
            or audit.repair_plan.actions
        ):
            return False
        state = self._require_state()
        pre = state["pre_audit"]["counts"]
        after = audit.counts
        transitions = state["repair_intent"]["planned_transition_counts"]
        approved_rejections = transitions["approved_to_rejected"]
        pending_rejections = transitions["pending_to_rejected"]
        other_rejections = transitions["other_to_rejected"]
        rejection_count = (
            approved_rejections + pending_rejections + other_rejections
        )
        return (
            after["lessons"] == pre["lessons"]
            and after["sources"] == pre["sources"]
            and after["evidence"] == pre["evidence"]
            and after["pending"] == pre["pending"] - pending_rejections
            and after["approved"] == pre["approved"] - approved_rejections
            and after["rejected"] == pre["rejected"] + rejection_count
            and after["lesson_events"]
            == pre["lesson_events"] + rejection_count
            and after["fts_rows"] == after["approved"]
        )

    def _reconciled_repair_summary(self) -> dict[str, object]:
        intent = self._require_state()["repair_intent"]
        planned = int(intent["planned_count"])
        return {
            "planned_count": planned,
            "applied_count": planned,
            "skipped_count": 0,
            "applied_action_id_hashes": list(
                intent["planned_action_id_hashes"]
            ),
            "skipped_action_id_hashes": [],
            "outcome_reason_counts": {
                "applied": planned,
                "already_applied": 0,
                "precondition_failed": 0,
            },
            "applied_kind_counts": dict(intent["planned_kind_counts"]),
            "applied_transition_counts": dict(
                intent["planned_transition_counts"]
            ),
        }

    @staticmethod
    def _is_exact_running_state(state: RuntimeState) -> bool:
        return (
            state.unambiguous
            and state.bot_count == 1
            and state.worker_count == 1
        )

    @staticmethod
    def _is_exact_stopped_state(state: RuntimeState) -> bool:
        return (
            state.unambiguous
            and state.bot_count == 0
            and state.worker_count == 0
        )

    @staticmethod
    def _health_is_exact(health: dict[str, bool]) -> bool:
        return (
            set(health) == {"bot", "worker"}
            and health["bot"] is True
            and health["worker"] is True
        )

    @staticmethod
    def _backup_summary(
        verification: BackupVerification,
    ) -> dict[str, object]:
        counts = verification.get("counts")
        safe_counts = counts if isinstance(counts, dict) else {}
        return {
            "ok": bool(verification.get("ok")),
            "integrity_ok": verification.get("integrity") == "ok",
            "foreign_keys_ok": (
                verification.get("foreign_key_violations") == 0
            ),
            "schema_ok": verification.get("schema_version") == SCHEMA_VERSION,
            "required_tables_ok": (
                verification.get("required_tables_missing") == []
            ),
            "schema_version": int(verification.get("schema_version") or 0),
            "counts": {
                key: int(safe_counts.get(key, 0))
                for key in _FULL_BACKUP_COUNT_KEYS
            },
            "digest": str(verification.get("sha256") or ""),
            "file_identity": str(
                verification.get("file_identity") or ""
            ),
        }

    @staticmethod
    def _audit_summary(audit: AuditReport) -> dict[str, object]:
        severity_counts = {"info": 0, "warning": 0, "error": 0}
        repair_class_counts = {"safe": 0, "review": 0, "forbidden": 0}
        finding_hashes: list[str] = []
        for finding in audit.findings:
            severity_counts[finding.severity] += 1
            repair_class_counts[finding.repair_class] += 1
            canonical = json.dumps(
                {
                    "code": finding.code,
                    "severity": finding.severity,
                    "repair_class": finding.repair_class,
                    "subject_hash": finding.subject_id_hash,
                },
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            finding_hashes.append(_identifier_hash(canonical))
        return {
            "integrity_ok": audit.integrity == "ok",
            "foreign_keys_ok": audit.foreign_key_violations == 0,
            "schema_ok": audit.schema_version == SCHEMA_VERSION,
            "schema_version": int(audit.schema_version),
            "counts": {
                key: int(audit.counts.get(key, 0)) for key in _COUNT_KEYS
            },
            "finding_count": len(audit.findings),
            "finding_id_hashes": sorted(finding_hashes),
            "severity_counts": severity_counts,
            "repair_class_counts": repair_class_counts,
            "planned_action_count": len(audit.repair_plan.actions),
            "planned_action_id_hashes": sorted(
                _identifier_hash(action.action_id)
                for action in audit.repair_plan.actions
            ),
        }

    @staticmethod
    def _repair_summary(report: RepairReport) -> dict[str, object]:
        reason_counts = {
            "applied": 0,
            "already_applied": 0,
            "precondition_failed": 0,
        }
        kind_counts = {
            "rebuild_fts": 0,
            "set_approved_at": 0,
            "reject_lesson": 0,
        }
        transitions = {
            "approved_to_rejected": 0,
            "pending_to_rejected": 0,
            "other_to_rejected": 0,
        }
        for outcome in report.outcomes:
            reason_counts[outcome.reason] += 1
            if outcome.status != "applied":
                continue
            kind_counts[outcome.kind] += 1
            if outcome.kind == "reject_lesson":
                before_status = str(outcome.before.get("status", "other"))
                key = (
                    f"{before_status}_to_rejected"
                    if before_status in {"approved", "pending"}
                    else "other_to_rejected"
                )
                transitions[key] += 1
        return {
            "planned_count": int(report.planned_count),
            "applied_count": int(report.applied_count),
            "skipped_count": int(report.skipped_count),
            "applied_action_id_hashes": sorted(
                _identifier_hash(value)
                for value in report.applied_action_ids
            ),
            "skipped_action_id_hashes": sorted(
                _identifier_hash(value)
                for value in report.skipped_action_ids
            ),
            "outcome_reason_counts": reason_counts,
            "applied_kind_counts": kind_counts,
            "applied_transition_counts": transitions,
        }

    @staticmethod
    def _repair_report_is_valid(report: RepairReport) -> bool:
        counts = (
            report.planned_count,
            report.applied_count,
            report.skipped_count,
        )
        return (
            all(type(value) is int and value >= 0 for value in counts)
            and report.applied_count + report.skipped_count
            == report.planned_count
            and len(report.outcomes) == report.planned_count
            and len(report.applied_action_ids) == report.applied_count
            and len(report.skipped_action_ids) == report.skipped_count
        )

    def _load_or_create_state(self) -> dict[str, object]:
        if self.requested_run_id is not None:
            run_id = self.requested_run_id
            self.run_id = run_id
            state_path = self._state_file(run_id)
            if state_path.exists():
                self._resumed = True
                state = self._read_state(state_path, run_id)
            else:
                state = self._new_state(run_id)
                self._create_state_exclusive(state_path, state)
            self._state_path = state_path
            self._state = state
            return state

        for attempt in range(32):
            nonce = secrets.token_hex(16)
            run_id = (
                f"run-{nonce}"
                if attempt == 0
                else f"run-{_identifier_hash(f'{nonce}:{attempt}')[:32]}"
            )
            state_path = self._state_file(run_id)
            state = self._new_state(run_id)
            try:
                self._create_state_exclusive(state_path, state)
            except FileExistsError:
                continue
            self._state_path = state_path
            self._state = state
            self.run_id = run_id
            return state
        raise ArtifactCollisionError("could not allocate maintenance state")

    @staticmethod
    def _new_state(run_id: str) -> dict[str, object]:
        now = _utc_now()
        return {
            "state_version": _STATE_VERSION,
            "run_id": run_id,
            "status": "running",
            "started_at": now,
            "updated_at": now,
            "completed_stages": [],
            "database_identity_hash": "",
            "artifact_ref": "",
            "artifact_hash": "",
            "artifact_digest": "",
            "backup": {},
            "pre_audit": {},
            "repair_intent": {},
            "repair": {},
            "post_audit": {},
            "process": {
                "discovery_unambiguous": False,
                "expected_counts": {"bot": 0, "worker": 0},
                "stop_succeeded": False,
                "offline_lease_acquired": False,
                "lease_release_pending": False,
                "restart_intent": False,
                "start_counts": {"bot": 0, "worker": 0},
                "health": {"bot": False, "worker": False},
                "partial_restart_stopped": False,
            },
            "error_code": "",
            "pending_status": "",
            "pending_error_code": "",
            "report_attempt": 0,
            "active_report_attempt": 0,
            "report_owner_hash": "",
            "report_phase": "idle",
            "report_snapshot_at": "",
            "report_json_digest": "",
            "report_markdown_digest": "",
        }

    @staticmethod
    def _create_state_exclusive(
        path: Path,
        state: dict[str, object],
    ) -> None:
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
                newline="\n",
            ) as handle:
                json.dump(
                    state,
                    handle,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            try:
                path.unlink()
            except OSError:
                pass
            raise

    def _reserve_report_artifacts(self) -> None:
        state = self._require_state()
        finished = int(state["report_attempt"])
        active = int(state["active_report_attempt"])
        if active:
            if active != finished + 1:
                raise ArtifactCollisionError("active report attempt is invalid")
            self._reserved_attempt = active
            self._ensure_owned_report_artifacts()
            return

        attempt = finished + 1
        state["active_report_attempt"] = attempt
        state["report_owner_hash"] = _identifier_hash(
            secrets.token_hex(32)
        )
        state["report_phase"] = "reserved"
        state["report_snapshot_at"] = ""
        state["report_json_digest"] = ""
        state["report_markdown_digest"] = ""
        self._reserved_attempt = attempt
        self._persist_state()
        self._crash("after_report_reservation")
        self._ensure_owned_report_artifacts()

    def _ensure_owned_report_artifacts(self) -> None:
        state = self._require_state()
        owner_hash = str(state["report_owner_hash"])
        self._validate_hash(owner_hash)
        json_path, markdown_path = self._report_paths(
            int(state["active_report_attempt"])
        )
        expected_json = None
        expected_markdown = None
        if state["report_snapshot_at"]:
            expected_json, expected_markdown = self._canonical_report_texts()
        self._ensure_owned_artifact(
            json_path,
            "json",
            owner_hash,
            expected_json,
        )
        self._ensure_owned_artifact(
            markdown_path,
            "markdown",
            owner_hash,
            expected_markdown,
        )

    @staticmethod
    def _reservation_marker(kind: str, owner_hash: str) -> str:
        if kind == "json":
            return json.dumps(
                {
                    "maintenance_reservation": owner_hash,
                    "report_kind": "json",
                },
                ensure_ascii=True,
                sort_keys=True,
            ) + "\n"
        return f"<!-- hermes-maintenance-owner:{owner_hash} -->\n"

    def _ensure_owned_artifact(
        self,
        path: Path,
        kind: str,
        owner_hash: str,
        expected_text: str | None = None,
    ) -> None:
        marker = self._reservation_marker(kind, owner_hash)
        if not path.exists():
            try:
                descriptor = os.open(
                    path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                    handle.write(marker)
                    handle.flush()
                    os.fsync(handle.fileno())
        if not self._artifact_is_owned(
            path,
            kind,
            owner_hash,
            expected_text,
        ):
            raise ArtifactCollisionError("report artifact is foreign")

    @staticmethod
    def _artifact_is_owned(
        path: Path,
        kind: str,
        owner_hash: str,
        expected_text: str | None = None,
    ) -> bool:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return False
        if text == MaintenanceRunner._reservation_marker(kind, owner_hash):
            return True
        return expected_text is not None and text == expected_text

    @classmethod
    def _read_state(
        cls,
        path: Path,
        run_id: str,
    ) -> dict[str, object]:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise StateValidationError("maintenance state is unreadable") from None
        cls._validate_state(state, expected_run_id=run_id)
        return state

    @classmethod
    def _validate_state(
        cls,
        state: object,
        *,
        expected_run_id: str | None = None,
    ) -> None:
        if not isinstance(state, dict) or set(state) != _STATE_KEYS:
            raise StateValidationError("maintenance state keys are invalid")
        if state["state_version"] != _STATE_VERSION:
            raise StateValidationError("maintenance state version is invalid")
        run_id = state["run_id"]
        if (
            not isinstance(run_id, str)
            or not _RUN_ID_PATTERN.fullmatch(run_id)
            or (expected_run_id is not None and run_id != expected_run_id)
        ):
            raise StateValidationError("maintenance run identifier is invalid")
        if state["status"] not in {
            "running",
            "completed",
            "failed",
            "manual_intervention_required",
        }:
            raise StateValidationError("maintenance status is invalid")
        cls._validate_timestamp(state["started_at"])
        cls._validate_timestamp(state["updated_at"])
        stages = state["completed_stages"]
        if (
            not isinstance(stages, list)
            or stages != list(_STAGES[: len(stages)])
        ):
            raise StateValidationError("maintenance stages are not a prefix")
        cls._validate_hash(state["database_identity_hash"], allow_empty=True)
        cls._validate_hash(state["artifact_hash"], allow_empty=True)
        cls._validate_hash(state["artifact_digest"], allow_empty=True)
        artifact_ref = state["artifact_ref"]
        if not isinstance(artifact_ref, str) or (
            artifact_ref and not _ARTIFACT_PATTERN.fullmatch(artifact_ref)
        ):
            raise StateValidationError("artifact reference is invalid")
        error_code = state["error_code"]
        if not isinstance(error_code, str) or (
            error_code and not _ERROR_PATTERN.fullmatch(error_code)
        ):
            raise StateValidationError("maintenance error code is invalid")
        pending_status = state["pending_status"]
        pending_error = state["pending_error_code"]
        if pending_status not in {
            "",
            "completed",
            "failed",
            "manual_intervention_required",
        }:
            raise StateValidationError("pending status is invalid")
        if not isinstance(pending_error, str) or (
            pending_error and not _ERROR_PATTERN.fullmatch(pending_error)
        ):
            raise StateValidationError("pending error code is invalid")
        if bool(pending_status) != bool(
            pending_error or pending_status == "completed"
        ):
            raise StateValidationError("pending terminal intent is invalid")
        report_attempt = state["report_attempt"]
        active_attempt = state["active_report_attempt"]
        if (
            type(report_attempt) is not int
            or report_attempt < 0
            or type(active_attempt) is not int
            or active_attempt < 0
            or active_attempt not in {0, report_attempt + 1}
        ):
            raise StateValidationError("report attempt state is invalid")
        owner_hash = state["report_owner_hash"]
        cls._validate_hash(owner_hash, allow_empty=True)
        snapshot_at = state["report_snapshot_at"]
        if snapshot_at:
            cls._validate_timestamp(snapshot_at)
        elif not isinstance(snapshot_at, str):
            raise StateValidationError("report snapshot timestamp is invalid")
        cls._validate_hash(state["report_json_digest"], allow_empty=True)
        cls._validate_hash(state["report_markdown_digest"], allow_empty=True)
        phase = state["report_phase"]
        if phase not in {
            "idle",
            "reserved",
            "json_written",
            "markdown_written",
        }:
            raise StateValidationError("report phase is invalid")
        if active_attempt == 0 and phase != "idle":
            raise StateValidationError("inactive report phase is invalid")
        if active_attempt > 0 and (
            not owner_hash or phase == "idle"
        ):
            raise StateValidationError("active report ownership is invalid")
        if pending_status and active_attempt == 0:
            raise StateValidationError("terminal intent lacks report ownership")
        report_hashes_present = bool(
            state["report_json_digest"]
            and state["report_markdown_digest"]
        )
        if bool(state["report_json_digest"]) != bool(
            state["report_markdown_digest"]
        ):
            raise StateValidationError("report digests are incomplete")
        if snapshot_at and not report_hashes_present:
            raise StateValidationError("report snapshot lacks digests")
        if phase in {"json_written", "markdown_written"} and not snapshot_at:
            raise StateValidationError("written report lacks snapshot")
        if report_attempt > 0 and active_attempt == 0 and (
            not snapshot_at or not report_hashes_present
        ):
            raise StateValidationError("terminal report binding is missing")
        cls._validate_process(state["process"])
        cls._validate_optional_backup(state["backup"])
        cls._validate_optional_audit(state["pre_audit"])
        cls._validate_optional_repair_intent(state["repair_intent"])
        cls._validate_optional_repair(state["repair"])
        cls._validate_optional_audit(state["post_audit"])
        cls._validate_stage_payloads(state)

    @staticmethod
    def _validate_timestamp(value: object) -> None:
        if not isinstance(value, str):
            raise StateValidationError("timestamp is invalid")
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise StateValidationError("timestamp is invalid") from None
        if parsed.tzinfo is None:
            raise StateValidationError("timestamp timezone is missing")

    @staticmethod
    def _validate_hash(value: object, *, allow_empty: bool = False) -> None:
        if not isinstance(value, str) or (
            not (allow_empty and value == "")
            and not _HEX_PATTERN.fullmatch(value)
        ):
            raise StateValidationError("hashed identifier is invalid")

    @classmethod
    def _validate_process(cls, value: object) -> None:
        expected_keys = {
            "discovery_unambiguous",
            "expected_counts",
            "stop_succeeded",
            "offline_lease_acquired",
            "lease_release_pending",
            "restart_intent",
            "start_counts",
            "health",
            "partial_restart_stopped",
        }
        if not isinstance(value, dict) or set(value) != expected_keys:
            raise StateValidationError("process state is invalid")
        for key in (
            "discovery_unambiguous",
            "stop_succeeded",
            "offline_lease_acquired",
            "lease_release_pending",
            "restart_intent",
            "partial_restart_stopped",
        ):
            if not isinstance(value[key], bool):
                raise StateValidationError("process boolean is invalid")
        cls._validate_role_counts(value["expected_counts"])
        cls._validate_role_counts(value["start_counts"])
        health = value["health"]
        if (
            not isinstance(health, dict)
            or set(health) != {"bot", "worker"}
            or not all(isinstance(item, bool) for item in health.values())
        ):
            raise StateValidationError("process health is invalid")

    @staticmethod
    def _validate_role_counts(value: object) -> None:
        if (
            not isinstance(value, dict)
            or set(value) != {"bot", "worker"}
            or not all(
                type(item) is int and item >= 0 for item in value.values()
            )
        ):
            raise StateValidationError("process counts are invalid")

    @classmethod
    def _validate_optional_backup(cls, value: object) -> None:
        if value == {}:
            return
        keys = {
            "ok",
            "integrity_ok",
            "foreign_keys_ok",
            "schema_ok",
            "required_tables_ok",
            "schema_version",
            "counts",
            "digest",
            "file_identity",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise StateValidationError("backup summary is invalid")
        for key in (
            "ok",
            "integrity_ok",
            "foreign_keys_ok",
            "schema_ok",
            "required_tables_ok",
        ):
            if not isinstance(value[key], bool):
                raise StateValidationError("backup verification is invalid")
        if type(value["schema_version"]) is not int:
            raise StateValidationError("backup schema version is invalid")
        cls._validate_counts(value["counts"], _FULL_BACKUP_COUNT_KEYS)
        cls._validate_hash(value["digest"])
        cls._validate_hash(value["file_identity"])

    @classmethod
    def _validate_optional_audit(cls, value: object) -> None:
        if value == {}:
            return
        keys = {
            "integrity_ok",
            "foreign_keys_ok",
            "schema_ok",
            "schema_version",
            "counts",
            "finding_count",
            "finding_id_hashes",
            "severity_counts",
            "repair_class_counts",
            "planned_action_count",
            "planned_action_id_hashes",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise StateValidationError("audit summary is invalid")
        for key in ("integrity_ok", "foreign_keys_ok", "schema_ok"):
            if not isinstance(value[key], bool):
                raise StateValidationError("audit verification is invalid")
        for key in ("schema_version", "finding_count", "planned_action_count"):
            if type(value[key]) is not int or value[key] < 0:
                raise StateValidationError("audit count is invalid")
        cls._validate_counts(value["counts"], _COUNT_KEYS)
        cls._validate_hash_list(value["finding_id_hashes"])
        cls._validate_hash_list(value["planned_action_id_hashes"])
        cls._validate_counts(
            value["severity_counts"],
            ("info", "warning", "error"),
        )
        cls._validate_counts(
            value["repair_class_counts"],
            ("safe", "review", "forbidden"),
        )

    @classmethod
    def _validate_optional_repair(cls, value: object) -> None:
        if value == {}:
            return
        keys = {
            "planned_count",
            "applied_count",
            "skipped_count",
            "applied_action_id_hashes",
            "skipped_action_id_hashes",
            "outcome_reason_counts",
            "applied_kind_counts",
            "applied_transition_counts",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise StateValidationError("repair summary is invalid")
        for key in ("planned_count", "applied_count", "skipped_count"):
            if type(value[key]) is not int or value[key] < 0:
                raise StateValidationError("repair count is invalid")
        cls._validate_hash_list(value["applied_action_id_hashes"])
        cls._validate_hash_list(value["skipped_action_id_hashes"])
        cls._validate_counts(
            value["outcome_reason_counts"],
            ("applied", "already_applied", "precondition_failed"),
        )
        cls._validate_counts(
            value["applied_kind_counts"],
            ("rebuild_fts", "set_approved_at", "reject_lesson"),
        )
        cls._validate_counts(
            value["applied_transition_counts"],
            (
                "approved_to_rejected",
                "pending_to_rejected",
                "other_to_rejected",
            ),
        )

    @classmethod
    def _validate_optional_repair_intent(cls, value: object) -> None:
        if value == {}:
            return
        keys = {
            "plan_fingerprint",
            "planned_count",
            "planned_action_id_hashes",
            "planned_kind_counts",
            "planned_transition_counts",
        }
        if not isinstance(value, dict) or set(value) != keys:
            raise StateValidationError("repair intent is invalid")
        cls._validate_hash(value["plan_fingerprint"])
        if type(value["planned_count"]) is not int or value["planned_count"] < 0:
            raise StateValidationError("repair intent count is invalid")
        cls._validate_hash_list(value["planned_action_id_hashes"])
        cls._validate_counts(
            value["planned_kind_counts"],
            ("rebuild_fts", "set_approved_at", "reject_lesson"),
        )
        cls._validate_counts(
            value["planned_transition_counts"],
            (
                "approved_to_rejected",
                "pending_to_rejected",
                "other_to_rejected",
            ),
        )

    @staticmethod
    def _validate_counts(value: object, keys: tuple[str, ...]) -> None:
        if (
            not isinstance(value, dict)
            or set(value) != set(keys)
            or not all(
                type(item) is int and item >= 0 for item in value.values()
            )
        ):
            raise StateValidationError("aggregate counts are invalid")

    @classmethod
    def _validate_hash_list(cls, value: object) -> None:
        if not isinstance(value, list):
            raise StateValidationError("hashed identifier list is invalid")
        for item in value:
            cls._validate_hash(item)
        if value != sorted(set(value)):
            raise StateValidationError("hashed identifiers are not canonical")

    @classmethod
    def _validate_stage_payloads(cls, state: dict[str, object]) -> None:
        stages = state["completed_stages"]
        process = state["process"]
        if "discovered" in stages and not (
            process["discovery_unambiguous"]
            and process["expected_counts"] == {"bot": 1, "worker": 1}
        ):
            raise StateValidationError("discovery stage payload is invalid")
        if "stopped" in stages and not process["stop_succeeded"]:
            raise StateValidationError("stop stage payload is invalid")
        if "backup_created" in stages and not (
            state["artifact_ref"]
            and state["artifact_hash"]
        ):
            raise StateValidationError("backup stage payload is invalid")
        if "backup_verified" in stages and not state["backup"]:
            raise StateValidationError("verification stage payload is invalid")
        if "backup_verified" in stages:
            backup = state["backup"]
            if not all(
                backup[key]
                for key in (
                    "ok",
                    "integrity_ok",
                    "foreign_keys_ok",
                    "schema_ok",
                    "required_tables_ok",
                )
            ):
                raise StateValidationError(
                    "verified backup payload is invalid"
                )
            if state["artifact_digest"] != backup["digest"]:
                raise StateValidationError("backup digest payload is invalid")
        if "pre_audited" in stages:
            pre = state["pre_audit"]
            backup = state["backup"]
            if not pre or not (
                pre["integrity_ok"]
                and pre["foreign_keys_ok"]
                and pre["schema_ok"]
                and all(
                    pre["counts"][audit_key] == backup["counts"][backup_key]
                    for audit_key, backup_key in (
                        ("lessons", "lessons"),
                        ("sources", "sources"),
                        ("evidence", "evidence"),
                        ("lesson_events", "lesson_events"),
                        ("fts_rows", "lesson_fts"),
                    )
                )
            ):
                raise StateValidationError("audit stage payload is invalid")
        if "repair_intent" in stages:
            intent = state["repair_intent"]
            pre = state["pre_audit"]
            if not intent or not (
                intent["planned_count"] == pre["planned_action_count"]
                and intent["planned_action_id_hashes"]
                == pre["planned_action_id_hashes"]
            ):
                raise StateValidationError("repair intent payload is invalid")
        if "repaired" in stages:
            repair = state["repair"]
            intent = state["repair_intent"]
            if not repair or not (
                repair["planned_count"] == intent["planned_count"]
                and repair["applied_count"] + repair["skipped_count"]
                == repair["planned_count"]
            ):
                raise StateValidationError("repair stage payload is invalid")
        if "post_checked" in stages and not cls._post_summaries_are_valid(
            state["pre_audit"],
            state["post_audit"],
            state["repair"],
        ):
            raise StateValidationError("post-check payload is invalid")
        if "restart_intent" in stages and not process["restart_intent"]:
            raise StateValidationError("restart intent payload is invalid")
        if "restarted" in stages and not (
            process["start_counts"] == {"bot": 1, "worker": 1}
            and process["health"] == {"bot": True, "worker": True}
        ):
            raise StateValidationError("restart stage payload is invalid")
        if ("completed" in stages) != (state["status"] == "completed"):
            raise StateValidationError("completion state is invalid")

    def _persist_state(self) -> None:
        state = self._require_state()
        state["updated_at"] = _utc_now()
        self._validate_state(state)
        _atomic_write(
            self._require_state_path(),
            json.dumps(
                state,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

    def _complete_stage(self, stage: str) -> None:
        completed = self._completed_stages()
        expected = _STAGES[len(completed)]
        if stage != expected:
            raise StateValidationError("stage completion order is invalid")
        completed.append(stage)
        self._persist_state()

    def _completed_stages(self) -> list[str]:
        completed = self._require_state()["completed_stages"]
        if not isinstance(completed, list):
            raise StateValidationError("maintenance stages are invalid")
        return completed

    def _runtime_state_from_persisted(self) -> RuntimeState:
        expected = self._process_payload()["expected_counts"]
        return RuntimeState(
            bot_count=int(expected["bot"]),
            worker_count=int(expected["worker"]),
            unambiguous=bool(
                self._process_payload()["discovery_unambiguous"]
            ),
        )

    def _set_discovery(self, state: RuntimeState) -> None:
        self._update_process(
            discovery_unambiguous=bool(state.unambiguous),
            expected_counts={
                "bot": int(state.bot_count),
                "worker": int(state.worker_count),
            },
        )

    def _process_payload(self) -> dict[str, object]:
        process = self._require_state()["process"]
        if not isinstance(process, dict):
            raise StateValidationError("process state is invalid")
        return process

    def _update_process(self, **changes: object) -> None:
        process = self._process_payload()
        process.update(changes)
        self._persist_state()

    def _finish(
        self,
        status: MaintenanceStatus,
        error_code: str,
    ) -> MaintenanceResult:
        state = self._require_state()
        if (
            self._offline_lease is not None
            and not self._process_payload()["lease_release_pending"]
        ):
            if not self._release_offline_lease():
                status = "manual_intervention_required"
                error_code = "offline_lease_release_failed"
        elif self._offline_lease is not None:
            status = "manual_intervention_required"
            error_code = "offline_lease_release_failed"
        state["pending_status"] = status
        state["pending_error_code"] = error_code
        self._persist_state()
        self._write_pending_reports()
        self._crash("before_terminal_persist")
        return self._persist_terminal_result()

    def _write_pending_reports(self) -> None:
        state = self._require_state()
        if not state["pending_status"]:
            raise StateValidationError("terminal report intent is missing")
        json_text, markdown_text = self._prepare_report_snapshot()
        json_path, markdown_path = self._report_paths(self._reserved_attempt)
        owner_hash = str(state["report_owner_hash"])
        self._ensure_owned_artifact(
            json_path,
            "json",
            owner_hash,
            json_text,
        )
        self._ensure_owned_artifact(
            markdown_path,
            "markdown",
            owner_hash,
            markdown_text,
        )
        if json_path.read_text(encoding="utf-8") != json_text:
            _atomic_write(json_path, json_text)
        state["report_phase"] = "json_written"
        self._persist_state()
        self._crash("after_json_write")
        if markdown_path.read_text(encoding="utf-8") != markdown_text:
            _atomic_write(markdown_path, markdown_text)
        state["report_phase"] = "markdown_written"
        self._persist_state()
        self._crash("after_markdown_write")

    def _persist_terminal_result(self) -> MaintenanceResult:
        state = self._require_state()
        status = str(state["pending_status"])
        error_code = str(state["pending_error_code"])
        if status not in {
            "completed",
            "failed",
            "manual_intervention_required",
        }:
            raise StateValidationError("terminal status intent is invalid")
        state["status"] = status
        state["error_code"] = error_code
        if status == "completed" and "completed" not in self._completed_stages():
            self._completed_stages().append("completed")
        state["report_attempt"] = int(state["active_report_attempt"])
        state["active_report_attempt"] = 0
        state["report_phase"] = "idle"
        state["pending_status"] = ""
        state["pending_error_code"] = ""
        self._persist_state()
        self._crash("after_terminal_persist")
        return self._result_from_state()

    def _reconcile_pending_terminal(self) -> MaintenanceResult:
        self._write_pending_reports()
        return self._persist_terminal_result()

    def _ensure_terminal_reports(self) -> None:
        state = self._require_state()
        attempt = int(state["report_attempt"])
        if attempt <= 0:
            raise StateValidationError("terminal report attempt is invalid")
        self._reserved_attempt = attempt
        json_path, markdown_path = self._report_paths(attempt)
        owner_hash = str(state["report_owner_hash"])
        json_text, markdown_text = self._canonical_report_texts()
        self._verify_report_digests(json_text, markdown_text)
        self._ensure_owned_artifact(
            json_path,
            "json",
            owner_hash,
            json_text,
        )
        self._ensure_owned_artifact(
            markdown_path,
            "markdown",
            owner_hash,
            markdown_text,
        )
        if json_path.read_text(encoding="utf-8") == self._reservation_marker(
            "json",
            owner_hash,
        ):
            _atomic_write(json_path, json_text)
        if markdown_path.read_text(
            encoding="utf-8"
        ) == self._reservation_marker("markdown", owner_hash):
            _atomic_write(markdown_path, markdown_text)

    def _prepare_report_snapshot(self) -> tuple[str, str]:
        state = self._require_state()
        if not state["report_snapshot_at"]:
            state["report_snapshot_at"] = _utc_now()
        json_text, markdown_text = self._canonical_report_texts()
        json_digest = hashlib.sha256(json_text.encode("utf-8")).hexdigest()
        markdown_digest = hashlib.sha256(
            markdown_text.encode("utf-8")
        ).hexdigest()
        if state["report_json_digest"] and (
            state["report_json_digest"] != json_digest
            or state["report_markdown_digest"] != markdown_digest
        ):
            raise StateValidationError("report snapshot binding changed")
        state["report_json_digest"] = json_digest
        state["report_markdown_digest"] = markdown_digest
        self._persist_state()
        return json_text, markdown_text

    def _canonical_report_texts(self) -> tuple[str, str]:
        state = self._require_state()
        if not state["report_snapshot_at"]:
            raise StateValidationError("report snapshot is missing")
        payload = self._report_payload()
        json_text = (
            json.dumps(
                payload,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
        markdown_text = (
            f"<!-- hermes-maintenance-owner:{state['report_owner_hash']} -->\n"
            + self._markdown(payload)
        )
        return json_text, markdown_text

    def _verify_report_digests(
        self,
        json_text: str,
        markdown_text: str,
    ) -> None:
        state = self._require_state()
        if (
            hashlib.sha256(json_text.encode("utf-8")).hexdigest()
            != state["report_json_digest"]
            or hashlib.sha256(markdown_text.encode("utf-8")).hexdigest()
            != state["report_markdown_digest"]
        ):
            raise StateValidationError("report snapshot digest is invalid")

    def _report_payload(self) -> dict[str, object]:
        state = self._require_state()
        reported_status = state["pending_status"] or state["status"]
        reported_error = (
            state["pending_error_code"]
            if state["pending_status"]
            else state["error_code"]
        )
        process = self._process_payload()
        reported_stages = list(self._completed_stages())
        if reported_status == "completed" and "completed" not in reported_stages:
            reported_stages.append("completed")
        return {
            "report_version": 4,
            "run_id": self._run_id(),
            "status": reported_status,
            "started_at": state["started_at"],
            "updated_at": (
                state["report_snapshot_at"] or state["updated_at"]
            ),
            "completed_stages": reported_stages,
            "error_code": reported_error,
            "report_owner_hash": state["report_owner_hash"],
            "database_identity_hash": state["database_identity_hash"],
            "artifact_hash": state["artifact_hash"],
            "artifact_digest": state["artifact_digest"],
            "backup": self._copy_backup(state["backup"]),
            "pre_audit": self._copy_audit(state["pre_audit"]),
            "repair_intent": self._copy_repair_intent(
                state["repair_intent"]
            ),
            "repair": self._copy_repair(state["repair"]),
            "post_audit": self._copy_audit(state["post_audit"]),
            "process": {
                "discovery_unambiguous": process["discovery_unambiguous"],
                "expected_counts": dict(process["expected_counts"]),
                "stop_succeeded": process["stop_succeeded"],
                "offline_lease_acquired": process[
                    "offline_lease_acquired"
                ],
                "lease_release_pending": process[
                    "lease_release_pending"
                ],
                "restart_intent": process["restart_intent"],
                "start_counts": dict(process["start_counts"]),
                "health": dict(process["health"]),
                "partial_restart_stopped": process[
                    "partial_restart_stopped"
                ],
            },
        }

    @staticmethod
    def _copy_backup(value: object) -> dict[str, object]:
        if not value:
            return {}
        summary = value
        return {
            "ok": summary["ok"],
            "integrity_ok": summary["integrity_ok"],
            "foreign_keys_ok": summary["foreign_keys_ok"],
            "schema_ok": summary["schema_ok"],
            "required_tables_ok": summary["required_tables_ok"],
            "schema_version": summary["schema_version"],
            "counts": {
                key: summary["counts"][key]
                for key in _FULL_BACKUP_COUNT_KEYS
            },
            "digest": summary["digest"],
            "file_identity": summary["file_identity"],
        }

    @staticmethod
    def _copy_audit(value: object) -> dict[str, object]:
        if not value:
            return {}
        summary = value
        return {
            "integrity_ok": summary["integrity_ok"],
            "foreign_keys_ok": summary["foreign_keys_ok"],
            "schema_ok": summary["schema_ok"],
            "schema_version": summary["schema_version"],
            "counts": {key: summary["counts"][key] for key in _COUNT_KEYS},
            "finding_count": summary["finding_count"],
            "finding_id_hashes": list(summary["finding_id_hashes"]),
            "severity_counts": {
                key: summary["severity_counts"][key]
                for key in ("info", "warning", "error")
            },
            "repair_class_counts": {
                key: summary["repair_class_counts"][key]
                for key in ("safe", "review", "forbidden")
            },
            "planned_action_count": summary["planned_action_count"],
            "planned_action_id_hashes": list(
                summary["planned_action_id_hashes"]
            ),
        }

    @staticmethod
    def _copy_repair(value: object) -> dict[str, object]:
        if not value:
            return {}
        summary = value
        return {
            "planned_count": summary["planned_count"],
            "applied_count": summary["applied_count"],
            "skipped_count": summary["skipped_count"],
            "applied_action_id_hashes": list(
                summary["applied_action_id_hashes"]
            ),
            "skipped_action_id_hashes": list(
                summary["skipped_action_id_hashes"]
            ),
            "outcome_reason_counts": {
                key: summary["outcome_reason_counts"][key]
                for key in (
                    "applied",
                    "already_applied",
                    "precondition_failed",
                )
            },
            "applied_kind_counts": {
                key: summary["applied_kind_counts"][key]
                for key in (
                    "rebuild_fts",
                    "set_approved_at",
                    "reject_lesson",
                )
            },
            "applied_transition_counts": {
                key: summary["applied_transition_counts"][key]
                for key in (
                    "approved_to_rejected",
                    "pending_to_rejected",
                    "other_to_rejected",
                )
            },
        }

    @staticmethod
    def _copy_repair_intent(value: object) -> dict[str, object]:
        if not value:
            return {}
        summary = value
        return {
            "plan_fingerprint": summary["plan_fingerprint"],
            "planned_count": summary["planned_count"],
            "planned_action_id_hashes": list(
                summary["planned_action_id_hashes"]
            ),
            "planned_kind_counts": {
                key: summary["planned_kind_counts"][key]
                for key in (
                    "rebuild_fts",
                    "set_approved_at",
                    "reject_lesson",
                )
            },
            "planned_transition_counts": {
                key: summary["planned_transition_counts"][key]
                for key in (
                    "approved_to_rejected",
                    "pending_to_rejected",
                    "other_to_rejected",
                )
            },
        }

    @staticmethod
    def _markdown(payload: dict[str, object]) -> str:
        return (
            f"# Hermes Maintenance {payload['run_id']}\n\n"
            f"- Status: `{payload['status']}`\n"
            f"- Started: `{payload['started_at']}`\n"
            f"- Updated: `{payload['updated_at']}`\n"
            f"- Error code: `{payload['error_code'] or 'none'}`\n\n"
            "## Redacted Run Summary\n\n"
            "```json\n"
            + json.dumps(
                payload,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n```\n"
        )

    def _result_from_state(self) -> MaintenanceResult:
        state = self._require_state()
        status = str(state["status"])
        if status not in {
            "completed",
            "failed",
            "manual_intervention_required",
        }:
            raise StateValidationError("maintenance result is not final")
        attempt = int(state["report_attempt"])
        if attempt <= 0:
            raise StateValidationError("maintenance report is missing")
        json_path, markdown_path = self._report_paths(attempt)
        if not json_path.is_file() or not markdown_path.is_file():
            raise StateValidationError("maintenance report artifact is missing")
        backup_path = ""
        if state["artifact_ref"]:
            backup_path = str(self._artifact_path())
        return MaintenanceResult(
            run_id=self._run_id(),
            status=status,
            backup_path=backup_path,
            report_json=str(json_path),
            report_markdown=str(markdown_path),
        )

    def _state_file(self, run_id: str) -> Path:
        return self.report_dir / f"maintenance-{run_id}.state.json"

    def _report_paths(self, attempt: int) -> tuple[Path, Path]:
        prefix = f"maintenance-{self._run_id()}-attempt-{attempt}"
        return (
            self.report_dir / f"{prefix}.json",
            self.report_dir / f"{prefix}.md",
        )

    def _run_id(self) -> str:
        return str(self._require_state()["run_id"])

    def _require_state(self) -> dict[str, object]:
        if self._state is None:
            raise StateValidationError("maintenance state is not initialized")
        return self._state

    def _require_state_path(self) -> Path:
        if self._state_path is None:
            raise StateValidationError("maintenance state path is missing")
        return self._state_path
