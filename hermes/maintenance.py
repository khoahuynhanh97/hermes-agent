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

from .backup import BackupVerification, SQLiteBackupManager
from .data_health import AuditReport, DataHealth, RepairPlan, RepairReport
from .db import SCHEMA_VERSION


MaintenanceStatus = Literal[
    "completed",
    "failed",
    "manual_intervention_required",
]

_STATE_VERSION = 1
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$")
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
_STAGES = (
    "discovered",
    "stopped",
    "backup_created",
    "backup_verified",
    "pre_audited",
    "repaired",
    "post_checked",
    "restarted",
    "completed",
)
_SAFE_ACTION_KINDS = {"rebuild_fts", "set_approved_at", "reject_lesson"}


@dataclass(frozen=True)
class RuntimeState:
    """Minimal runtime state; restart configuration remains adapter-owned."""

    bot_running: bool
    worker_running: bool
    unambiguous: bool


class ProcessController(Protocol):
    def discover(self) -> RuntimeState: ...

    def stop(self, state: RuntimeState, timeout_seconds: int) -> None: ...

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
    path.parent.mkdir(parents=True, exist_ok=True)
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


class MaintenanceRunner:
    """Resume-safe orchestration for offline Hermes data maintenance."""

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

    def run(self) -> MaintenanceResult:
        state = self._load_or_create_state()
        if state["status"] == "completed":
            return self._result_from_state()

        state["status"] = "running"
        state["error_code"] = ""
        self._persist_state()
        completed = self._completed_stages()
        original_state = self._runtime_state_from_persisted()

        if "discovered" not in completed:
            try:
                original_state = self.process_controller.discover()
            except Exception:
                return self._finish("failed", "discovery_failed")
            state["process"] = {
                **self._process_payload(),
                "discovery_unambiguous": bool(original_state.unambiguous),
                "expected": {
                    "bot": bool(original_state.bot_running),
                    "worker": bool(original_state.worker_running),
                },
            }
            if not original_state.unambiguous:
                return self._finish("failed", "discovery_ambiguous")
            if not original_state.bot_running or not original_state.worker_running:
                return self._finish("failed", "runtime_not_ready")
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

        if "backup_created" not in completed:
            try:
                backup_path = self.backup_manager.create_backup(
                    label=f"maintenance-{self._run_id()}"
                )
            except Exception:
                return self._finish("failed", "backup_creation_failed")
            state["backup_path"] = str(Path(backup_path).expanduser().resolve())
            self._complete_stage("backup_created")

        if "backup_verified" not in completed:
            try:
                verification = self.backup_manager.verify(
                    str(state["backup_path"])
                )
            except Exception:
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
                self._persist_state()
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
            if not self._post_audit_is_valid(post_audit):
                return self._finish(
                    "manual_intervention_required",
                    "post_check_failed",
                )
            self._complete_stage("post_checked")

        if "restarted" not in completed:
            restart_result = self._restart_runtime(original_state)
            if restart_result is not None:
                return restart_result
            self._complete_stage("restarted")

        self._complete_stage("completed")
        return self._finish("completed", "")

    def _restart_runtime(
        self,
        original_state: RuntimeState,
    ) -> MaintenanceResult | None:
        try:
            started_state = self.process_controller.start(original_state)
        except Exception:
            try:
                discovered = self.process_controller.discover()
            except Exception:
                return self._finish(
                    "manual_intervention_required",
                    "restart_state_unknown",
                )
            if not discovered.unambiguous:
                return self._finish(
                    "manual_intervention_required",
                    "restart_state_ambiguous",
                )
            observed = {
                "bot": bool(discovered.bot_running),
                "worker": bool(discovered.worker_running),
            }
            self._update_process(start=observed, health=observed)
            if observed["bot"] or observed["worker"]:
                stopped = self._stop_partial_restart(discovered)
                self._update_process(partial_restart_stopped=stopped)
                return self._finish(
                    "failed" if stopped else "manual_intervention_required",
                    (
                        "partial_restart_stopped"
                        if stopped
                        else "partial_restart_stop_failed"
                    ),
                )
            return self._finish("failed", "restart_failed")

        try:
            raw_health = self.process_controller.verify(started_state)
        except Exception:
            stopped = self._stop_partial_restart(started_state)
            return self._finish(
                "failed" if stopped else "manual_intervention_required",
                "restart_verification_failed",
            )

        health = {
            "bot": raw_health.get("bot") is True,
            "worker": raw_health.get("worker") is True,
        }
        self._update_process(
            start=health,
            health=health,
        )
        if health["bot"] and health["worker"]:
            return None

        if (
            health["bot"]
            or health["worker"]
            or started_state.bot_running
            or started_state.worker_running
        ):
            stopped = self._stop_partial_restart(started_state)
            self._update_process(partial_restart_stopped=stopped)
            return self._finish(
                "failed" if stopped else "manual_intervention_required",
                (
                    "partial_restart_stopped"
                    if stopped
                    else "partial_restart_stop_failed"
                ),
            )
        return self._finish("failed", "restart_failed")

    def _stop_partial_restart(self, state: RuntimeState) -> bool:
        try:
            self.process_controller.stop(state, self.stop_timeout_seconds)
        except Exception:
            return False
        return True

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

    @classmethod
    def _post_audit_is_valid(cls, audit: AuditReport) -> bool:
        return (
            cls._audit_core_is_valid(audit)
            and not any(
                finding.repair_class == "safe" for finding in audit.findings
            )
            and not audit.repair_plan.actions
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
                    "subject_id_hash": finding.subject_id_hash,
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
        for outcome in report.outcomes:
            reason_counts[outcome.reason] += 1
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
        }

    def _load_or_create_state(self) -> dict[str, object]:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        if self.requested_run_id is not None:
            run_id = self.requested_run_id
            path = self._state_file(run_id)
            if path.exists():
                self._state_path = path
                self._state = self._read_state(path, run_id)
                return self._state
            state = self._new_state(run_id)
            self._create_state_exclusive(path, state)
            self._state_path = path
            self._state = state
            return state

        for attempt in range(32):
            prefix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            token = secrets.token_hex(8)
            suffix = "" if attempt == 0 else f"-{attempt}"
            run_id = f"{prefix}-{token}{suffix}"
            path = self._state_file(run_id)
            state = self._new_state(run_id)
            try:
                self._create_state_exclusive(path, state)
            except FileExistsError:
                continue
            self._state_path = path
            self._state = state
            return state
        raise RuntimeError("could not allocate maintenance run")

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
            "backup_path": "",
            "backup": {},
            "pre_audit": {},
            "repair": {},
            "post_audit": {},
            "process": {
                "discovery_unambiguous": False,
                "expected": {"bot": False, "worker": False},
                "stop_succeeded": False,
                "start": {"bot": False, "worker": False},
                "health": {"bot": False, "worker": False},
                "partial_restart_stopped": False,
            },
            "error_code": "",
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

    @staticmethod
    def _read_state(path: Path, run_id: str) -> dict[str, object]:
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise RuntimeError("maintenance state is unreadable") from None
        if (
            not isinstance(state, dict)
            or state.get("state_version") != _STATE_VERSION
            or state.get("run_id") != run_id
            or not isinstance(state.get("completed_stages"), list)
            or any(
                stage not in _STAGES
                for stage in state.get("completed_stages", [])
            )
        ):
            raise RuntimeError("maintenance state is incompatible")
        return state

    def _persist_state(self) -> None:
        state = self._require_state()
        state["updated_at"] = _utc_now()
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
        if stage not in _STAGES:
            raise ValueError("unknown maintenance stage")
        completed = self._completed_stages()
        if stage not in completed:
            completed.append(stage)
        self._persist_state()

    def _completed_stages(self) -> list[str]:
        completed = self._require_state()["completed_stages"]
        if not isinstance(completed, list):
            raise RuntimeError("maintenance stages are invalid")
        return completed

    def _runtime_state_from_persisted(self) -> RuntimeState:
        process = self._process_payload()
        expected = process["expected"]
        return RuntimeState(
            bot_running=bool(expected["bot"]),
            worker_running=bool(expected["worker"]),
            unambiguous=bool(process["discovery_unambiguous"]),
        )

    def _process_payload(self) -> dict[str, object]:
        process = self._require_state().get("process")
        if not isinstance(process, dict):
            raise RuntimeError("maintenance process state is invalid")
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
        self._persist_state()
        self._write_reports()
        return self._result_from_state()

    def _write_reports(self) -> None:
        payload = self._report_payload()
        json_path = self._json_report_path()
        markdown_path = self._markdown_report_path()
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
        return {
            "report_version": 1,
            "run_id": self._run_id(),
            "status": state["status"],
            "started_at": state["started_at"],
            "updated_at": state["updated_at"],
            "completed_stages": list(self._completed_stages()),
            "error_code": state["error_code"],
            "backup": dict(state.get("backup") or {}),
            "pre_audit": dict(state.get("pre_audit") or {}),
            "repair": dict(state.get("repair") or {}),
            "post_audit": dict(state.get("post_audit") or {}),
            "process": dict(self._process_payload()),
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
            raise RuntimeError("maintenance result is not final")
        if not self._json_report_path().exists() or not (
            self._markdown_report_path().exists()
        ):
            self._write_reports()
        return MaintenanceResult(
            run_id=self._run_id(),
            status=status,
            backup_path=str(state.get("backup_path") or ""),
            report_json=str(self._json_report_path()),
            report_markdown=str(self._markdown_report_path()),
        )

    def _state_file(self, run_id: str) -> Path:
        return self.report_dir / f"maintenance-{run_id}.state.json"

    def _json_report_path(self) -> Path:
        return self.report_dir / f"maintenance-{self._run_id()}.json"

    def _markdown_report_path(self) -> Path:
        return self.report_dir / f"maintenance-{self._run_id()}.md"

    def _run_id(self) -> str:
        return str(self._require_state()["run_id"])

    def _require_state(self) -> dict[str, object]:
        if self._state is None:
            raise RuntimeError("maintenance state is not initialized")
        return self._state

    def _require_state_path(self) -> Path:
        if self._state_path is None:
            raise RuntimeError("maintenance state path is not initialized")
        return self._state_path
