from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from .backup import BackupVerification, OfflineAccessLease, SQLiteBackupManager
from .data_health import AuditReport, DataHealth, RepairPlan, RepairReport
from .db import SCHEMA_VERSION


MaintenanceStatus = Literal[
    "completed",
    "failed",
    "manual_intervention_required",
]

_STATE_VERSION = 2
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
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
_SAFE_ACTION_KINDS = {"rebuild_fts", "set_approved_at", "reject_lesson"}
_STAGES = (
    "discovered",
    "stopped",
    "backup_created",
    "backup_verified",
    "pre_audited",
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
    "backup",
    "pre_audit",
    "repair",
    "post_audit",
    "process",
    "error_code",
    "report_attempt",
    "active_report_attempt",
}


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


class _ExclusiveRunLock:
    def __init__(self, path: Path):
        self.path = path
        self.descriptor: int | None = None

    def acquire(self) -> None:
        try:
            self.descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError:
            raise MaintenanceBusyError("maintenance is already running") from None

    def release(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


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
    ):
        if run_id is not None and not _RUN_ID_PATTERN.fullmatch(run_id):
            raise ValueError("run_id contains unsupported characters")
        if stop_timeout_seconds <= 0:
            raise ValueError("stop_timeout_seconds must be positive")
        self.process_controller = process_controller
        self.backup_manager = backup_manager
        self.data_health = data_health
        self.report_dir = Path(report_dir).expanduser().resolve()
        self.requested_run_id = run_id
        self.stop_timeout_seconds = int(stop_timeout_seconds)
        self._state: dict[str, object] | None = None
        self._state_path: Path | None = None
        self._offline_lease: OfflineAccessLease | None = None
        self._reserved_attempt = 0
        self._resumed = False

    def run(self) -> MaintenanceResult:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run_lock = _ExclusiveRunLock(
            self.report_dir / ".maintenance-run.lock"
        )
        run_lock.acquire()
        try:
            state = self._load_or_create_state()
            if state["status"] == "completed":
                return self._result_from_state()
            self._reserve_report_artifacts()
            state["status"] = "running"
            state["error_code"] = ""
            self._persist_state()
            configuration_error = self._bind_database_identity()
            if configuration_error is not None:
                return configuration_error
            return self._run_locked()
        finally:
            self._release_offline_lease()
            run_lock.release()

    def _run_locked(self) -> MaintenanceResult:
        state = self._require_state()
        completed = self._completed_stages()
        original_state = self._runtime_state_from_persisted()

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
            verification = self._verify_artifact()
            if verification is None:
                return self._finish("failed", "backup_verification_failed")
            state["backup"] = self._backup_summary(verification)
            if not self._backup_is_valid(verification):
                return self._finish("failed", "backup_verification_failed")
            self._complete_stage("backup_verified")

        current_audit: AuditReport | None = None
        if "pre_audited" not in completed:
            try:
                current_audit = self.data_health.audit()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "pre_audit_failed",
                )
            state["pre_audit"] = self._audit_summary(current_audit)
            if not self._audit_core_is_valid(current_audit):
                return self._finish(
                    "manual_intervention_required",
                    "pre_audit_invalid",
                )
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

        if "repaired" not in completed:
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
            if not self._validate_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_invalid",
                )
            try:
                repair_report = self.data_health.repair(
                    current_audit.repair_plan
                )
            except Exception:
                return self._finish("failed", "repair_failed")
            state["repair"] = self._repair_summary(repair_report)
            self._complete_stage("repaired")

        if "post_checked" not in completed:
            try:
                post_audit = self.data_health.audit()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "post_audit_failed",
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

        if not self._release_offline_lease():
            return self._finish(
                "manual_intervention_required",
                "offline_lease_release_failed",
            )

        restart_result = self._start_and_verify(original_state)
        if restart_result is not None:
            return restart_result
        self._complete_stage("restarted")
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
            if not self._release_offline_lease():
                return self._finish(
                    "manual_intervention_required",
                    "offline_lease_release_failed",
                )
            restart_result = self._start_and_verify(original_state)
            if restart_result is not None:
                return restart_result
            self._complete_stage("restarted")
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
        self._offline_lease = None
        try:
            self.process_controller.release_offline_lease(lease)
        except Exception:
            return False
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
        identity_hash = _identifier_hash(str(backup_resolved))
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
        return self._backup_summary(verification) == self._require_state()[
            "backup"
        ]

    def _backup_matches_audit(self, audit: AuditReport) -> bool:
        backup = self._require_state()["backup"]
        if not isinstance(backup, dict):
            return False
        backup_counts = backup["counts"]
        return all(
            int(backup_counts[key]) == int(audit.counts.get(key, -1))
            for key in _BACKUP_COUNT_KEYS
        )

    @staticmethod
    def _backup_is_valid(verification: BackupVerification) -> bool:
        return (
            verification.get("ok") is True
            and verification.get("integrity") == "ok"
            and verification.get("foreign_key_violations") == 0
            and verification.get("schema_version") == SCHEMA_VERSION
            and verification.get("required_tables_missing") == []
        )

    @staticmethod
    def _audit_core_is_valid(audit: AuditReport) -> bool:
        return (
            audit.integrity == "ok"
            and audit.foreign_key_violations == 0
            and audit.schema_version == SCHEMA_VERSION
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
                for key in _BACKUP_COUNT_KEYS
            },
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

    def _load_or_create_state(self) -> dict[str, object]:
        if self.requested_run_id is not None:
            run_id = self.requested_run_id
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
            prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            suffix = "" if attempt == 0 else f"-{attempt}"
            run_id = f"{prefix}-{secrets.token_hex(8)}{suffix}"
            state_path = self._state_file(run_id)
            state = self._new_state(run_id)
            try:
                self._create_state_exclusive(state_path, state)
            except FileExistsError:
                continue
            self._state_path = state_path
            self._state = state
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
            "backup": {},
            "pre_audit": {},
            "repair": {},
            "post_audit": {},
            "process": {
                "discovery_unambiguous": False,
                "expected_counts": {"bot": 0, "worker": 0},
                "stop_succeeded": False,
                "offline_lease_acquired": False,
                "restart_intent": False,
                "start_counts": {"bot": 0, "worker": 0},
                "health": {"bot": False, "worker": False},
                "partial_restart_stopped": False,
            },
            "error_code": "",
            "report_attempt": 0,
            "active_report_attempt": 0,
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
            json_path, markdown_path = self._report_paths(active)
            if (
                active != finished + 1
                or not json_path.is_file()
                or not markdown_path.is_file()
                or json_path.stat().st_size != 0
                or markdown_path.stat().st_size != 0
            ):
                raise ArtifactCollisionError(
                    "active report reservation is invalid"
                )
            self._reserved_attempt = active
            return

        attempt = finished + 1
        json_path, markdown_path = self._report_paths(attempt)
        created: list[Path] = []
        try:
            for path in (json_path, markdown_path):
                descriptor = os.open(
                    path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                )
                os.close(descriptor)
                created.append(path)
        except FileExistsError:
            for path in created:
                path.unlink()
            raise ArtifactCollisionError(
                "maintenance report artifact already exists"
            ) from None
        state["active_report_attempt"] = attempt
        self._reserved_attempt = attempt
        self._persist_state()

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
        report_attempt = state["report_attempt"]
        active_attempt = state["active_report_attempt"]
        if (
            not isinstance(report_attempt, int)
            or report_attempt < 0
            or not isinstance(active_attempt, int)
            or active_attempt < 0
            or active_attempt not in {0, report_attempt + 1}
        ):
            raise StateValidationError("report attempt state is invalid")
        cls._validate_process(state["process"])
        cls._validate_optional_backup(state["backup"])
        cls._validate_optional_audit(state["pre_audit"])
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
                isinstance(item, int) and item >= 0 for item in value.values()
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
        if not isinstance(value["schema_version"], int):
            raise StateValidationError("backup schema version is invalid")
        cls._validate_counts(value["counts"], _BACKUP_COUNT_KEYS)

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
            if not isinstance(value[key], int) or value[key] < 0:
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
            if not isinstance(value[key], int) or value[key] < 0:
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

    @staticmethod
    def _validate_counts(value: object, keys: tuple[str, ...]) -> None:
        if (
            not isinstance(value, dict)
            or set(value) != set(keys)
            or not all(
                isinstance(item, int) and item >= 0 for item in value.values()
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
            state["artifact_ref"] and state["artifact_hash"]
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
        if "pre_audited" in stages:
            pre = state["pre_audit"]
            backup = state["backup"]
            if not pre or not (
                pre["integrity_ok"]
                and pre["foreign_keys_ok"]
                and pre["schema_ok"]
                and all(
                    pre["counts"][key] == backup["counts"][key]
                    for key in _BACKUP_COUNT_KEYS
                )
            ):
                raise StateValidationError("audit stage payload is invalid")
        if "repaired" in stages:
            repair = state["repair"]
            pre = state["pre_audit"]
            if not repair or not (
                repair["planned_count"] == pre["planned_action_count"]
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
        state["status"] = status
        state["error_code"] = error_code
        if status == "completed" and "completed" not in self._completed_stages():
            self._completed_stages().append("completed")
        self._persist_state()
        self._write_reports()
        state["report_attempt"] = self._reserved_attempt
        state["active_report_attempt"] = 0
        self._persist_state()
        return self._result_from_state()

    def _write_reports(self) -> None:
        payload = self._report_payload()
        json_path, markdown_path = self._report_paths(self._reserved_attempt)
        if not (
            json_path.is_file()
            and markdown_path.is_file()
            and json_path.stat().st_size == 0
            and markdown_path.stat().st_size == 0
        ):
            raise ArtifactCollisionError("report reservation was modified")
        _atomic_write(
            json_path,
            json.dumps(
                payload,
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        _atomic_write(markdown_path, self._markdown(payload))

    def _report_payload(self) -> dict[str, object]:
        state = self._require_state()
        process = self._process_payload()
        return {
            "report_version": 2,
            "run_id": self._run_id(),
            "status": state["status"],
            "started_at": state["started_at"],
            "updated_at": state["updated_at"],
            "completed_stages": list(self._completed_stages()),
            "error_code": state["error_code"],
            "database_identity_hash": state["database_identity_hash"],
            "artifact_hash": state["artifact_hash"],
            "backup": self._copy_backup(state["backup"]),
            "pre_audit": self._copy_audit(state["pre_audit"]),
            "repair": self._copy_repair(state["repair"]),
            "post_audit": self._copy_audit(state["post_audit"]),
            "process": {
                "discovery_unambiguous": process["discovery_unambiguous"],
                "expected_counts": dict(process["expected_counts"]),
                "stop_succeeded": process["stop_succeeded"],
                "offline_lease_acquired": process[
                    "offline_lease_acquired"
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
                key: summary["counts"][key] for key in _BACKUP_COUNT_KEYS
            },
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
