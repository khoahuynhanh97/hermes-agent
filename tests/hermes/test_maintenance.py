from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from hermes.data_health import (
    ActionOutcome,
    AuditReport,
    Finding,
    RepairAction,
    RepairPlan,
    RepairReport,
)
from hermes.db import SCHEMA_VERSION
from hermes.maintenance import (
    ArtifactCollisionError,
    DatabaseRunLock,
    MaintenanceBusyError,
    MaintenanceRunner,
    RuntimeState,
    StateValidationError,
)


FORBIDDEN_KEYS = (
    "content",
    "excerpt",
    "url",
    "token",
    "cookie",
    "credential",
    "telegram",
    "environment",
    "path",
)
PRIVATE_VALUES = (
    "private lesson body",
    "https://private.example/lesson",
    "secret-token-value",
    "raw-lesson-id",
    "raw-action-id",
)


def healthy_audit(
    *,
    findings: tuple[Finding, ...] = (),
    actions: tuple[RepairAction, ...] = (),
    integrity: str = "ok",
    foreign_key_violations: int = 0,
    schema_version: int = SCHEMA_VERSION,
    counts: dict[str, int] | None = None,
) -> AuditReport:
    return AuditReport(
        integrity=integrity,
        foreign_key_violations=foreign_key_violations,
        schema_version=schema_version,
        counts=counts
        or {
            "lessons": 12,
            "pending": 2,
            "approved": 8,
            "rejected": 2,
            "sources": 10,
            "evidence": 7,
            "lesson_events": 19,
            "fts_rows": 8,
        },
        findings=findings,
        repair_plan=RepairPlan(actions),
    )


def repaired_audit(**overrides: int) -> AuditReport:
    counts = {
        "lessons": 12,
        "pending": 2,
        "approved": 7,
        "rejected": 3,
        "sources": 10,
        "evidence": 7,
        "lesson_events": 20,
        "fts_rows": 7,
    }
    counts.update(overrides)
    return healthy_audit(counts=counts)


SAFE_FINDING = Finding(
    code="defect_needs_reanalysis",
    severity="error",
    subject_type="lesson",
    subject_id_hash="raw-lesson-id",
    repair_class="safe",
    metadata={
        "content": "private lesson body",
        "url": "https://private.example/lesson",
        "token": "secret-token-value",
    },
)
SAFE_ACTION = RepairAction(
    action_id="raw-action-id",
    kind="reject_lesson",
    subject_id="raw-lesson-id",
    expected={"status": "approved", "needs_reanalysis": True},
)
APPLIED_REPAIR = RepairReport(
    planned_count=1,
    applied_count=1,
    skipped_count=0,
    applied_action_ids=("raw-action-id",),
    skipped_action_ids=(),
    outcomes=(
        ActionOutcome(
            action_id="raw-action-id",
            kind="reject_lesson",
            status="applied",
            reason="applied",
            before={
                "content": "private lesson body",
                "status": "approved",
            },
            after={"status": "rejected"},
        ),
    ),
)


class FakeOfflineLease:
    def __init__(
        self,
        events: list[str],
        validations: list[bool] | None = None,
    ):
        self.events = events
        self.validations = list(validations or [True])
        self.released = False

    def validate(self) -> bool:
        self.events.append("validate_offline")
        if len(self.validations) > 1:
            return self.validations.pop(0)
        return self.validations[0]


class FakeProcessController:
    def __init__(
        self,
        events: list[str],
        *,
        discovered: RuntimeState | None = None,
        started: RuntimeState | None = None,
        health: dict[str, bool] | None = None,
        stop_error: Exception | None = None,
        start_error: BaseException | None = None,
        lease: FakeOfflineLease | None = None,
        lease_error: Exception | None = None,
        release_results: list[bool] | None = None,
        discoveries: list[RuntimeState] | None = None,
    ):
        self.events = events
        self.discovered = discovered or RuntimeState(
            bot_count=1,
            worker_count=1,
            unambiguous=True,
        )
        self.started = started or self.discovered
        self.health = health or {"bot": True, "worker": True}
        self.stop_error = stop_error
        self.start_error = start_error
        self.lease = lease or FakeOfflineLease(events)
        self.lease_error = lease_error
        self.release_results = list(release_results or [True])
        self.discoveries = list(discoveries or [])
        self.stop_states: list[RuntimeState] = []

    def discover(self) -> RuntimeState:
        self.events.append("discover")
        if self.discoveries:
            if len(self.discoveries) > 1:
                return self.discoveries.pop(0)
            return self.discoveries[0]
        return self.discovered

    def stop(self, state: RuntimeState, timeout_seconds: int) -> None:
        self.events.append("stop")
        self.stop_states.append(state)
        if self.stop_error is not None:
            raise self.stop_error

    def start(self, state: RuntimeState) -> RuntimeState:
        self.events.append("start")
        if self.start_error is not None:
            raise self.start_error
        return self.started

    def acquire_offline_lease(self, state: RuntimeState) -> FakeOfflineLease:
        self.events.append("acquire_offline")
        if self.lease_error is not None:
            raise self.lease_error
        return self.lease

    def release_offline_lease(self, lease: FakeOfflineLease) -> None:
        self.events.append("release_offline")
        result = self.release_results[0]
        if len(self.release_results) > 1:
            result = self.release_results.pop(0)
        if not result:
            raise RuntimeError("private release failure")
        lease.released = True

    def verify(self, state: RuntimeState) -> dict[str, bool]:
        self.events.append("verify_processes")
        return dict(self.health)


class FakeBackupManager:
    def __init__(
        self,
        events: list[str],
        backup_path: Path,
        *,
        create_error: Exception | None = None,
        verification: dict[str, object] | None = None,
        verifications: list[dict[str, object]] | None = None,
        database_path: Path | None = None,
    ):
        self.events = events
        self.backup_path = backup_path
        self.backup_dir = backup_path.parent
        self.explicit_database_path = database_path is not None
        self.database = SimpleNamespace(
            path=database_path or backup_path.parent.parent / "live" / "hermes.db"
        )
        self.create_error = create_error
        self.verification = verification or {
            "ok": True,
            "path": str(backup_path),
            "integrity": "ok",
            "foreign_key_violations": 0,
            "schema_version": SCHEMA_VERSION,
            "required_tables_missing": [],
            "counts": {
                "lessons": 12,
                "sources": 10,
                "evidence": 7,
                "lesson_events": 19,
                "lesson_fts": 8,
            },
            "sha256": "",
            "detail": "ok",
        }
        self.verifications = list(verifications or [])
        self.restore_calls = 0

    def create_backup(self, label: str = "scheduled") -> Path:
        self.events.append("create_backup")
        if self.create_error is not None:
            raise self.create_error
        self.backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.backup_path.exists():
            self.backup_path.write_bytes(b"verified-backup-v1")
        return self.backup_path

    def verify(self, path: str | Path) -> dict[str, object]:
        self.events.append("verify_backup")
        if self.verifications:
            if len(self.verifications) > 1:
                result = dict(self.verifications.pop(0))
            else:
                result = dict(self.verifications[0])
        else:
            result = dict(self.verification)
        candidate = Path(path)
        if candidate.is_file():
            result["sha256"] = hashlib.sha256(
                candidate.read_bytes()
            ).hexdigest()
        return result

    def restore(self, path: str | Path) -> None:
        self.restore_calls += 1
        raise AssertionError("maintenance must never restore automatically")


class FakeDataHealth:
    def __init__(
        self,
        events: list[str],
        audits: list[AuditReport],
        *,
        repair_report: RepairReport = APPLIED_REPAIR,
        repair_error: Exception | None = None,
        database_path: Path | None = None,
    ):
        self.events = events
        self.audits = list(audits)
        self.repair_report = repair_report
        self.repair_error = repair_error
        self.explicit_database_path = database_path is not None
        self.database = SimpleNamespace(
            path=database_path or Path("unused-live-hermes.db")
        )
        self.audit_calls = 0
        self.repair_calls = 0

    def audit(self) -> AuditReport:
        self.events.append("audit")
        self.audit_calls += 1
        if not self.audits:
            raise AssertionError("unexpected audit")
        if len(self.audits) > 1:
            return self.audits.pop(0)
        return self.audits[0]

    def repair(self, plan: RepairPlan) -> RepairReport:
        self.events.append("repair")
        self.repair_calls += 1
        if self.repair_error is not None:
            raise self.repair_error
        self.assert_safe_plan(plan)
        return self.repair_report

    @staticmethod
    def assert_safe_plan(plan: RepairPlan) -> None:
        allowed = {"rebuild_fts", "set_approved_at", "reject_lesson"}
        if any(action.kind not in allowed for action in plan.actions):
            raise AssertionError("unsafe repair action")


class CrashOnce:
    def __init__(self, boundary: str):
        self.boundary = boundary
        self.triggered = False

    def __call__(self, boundary: str) -> None:
        if boundary == self.boundary and not self.triggered:
            self.triggered = True
            raise KeyboardInterrupt(boundary)


class MaintenanceRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.report_dir = self.root / "reports"
        self.events: list[str] = []

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_runner(
        self,
        *,
        process: FakeProcessController | None = None,
        backup: FakeBackupManager | None = None,
        health: FakeDataHealth | None = None,
        run_id: str | None = None,
        report_dir: Path | None = None,
        crash_hook=None,
    ) -> tuple[
        MaintenanceRunner,
        FakeProcessController,
        FakeBackupManager,
        FakeDataHealth,
    ]:
        process = process or FakeProcessController(self.events)
        live_database = self.root / "live" / "hermes.db"
        live_database.parent.mkdir(parents=True, exist_ok=True)
        if not live_database.exists():
            live_database.write_bytes(b"live-database-identity")
        backup = backup or FakeBackupManager(
            self.events,
            self.root / "backups" / "verified.db",
            database_path=live_database,
        )
        if backup is not None and not backup.explicit_database_path:
            backup.database.path = live_database
        if health is not None and not health.explicit_database_path:
            health.database.path = live_database
        health = health or FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                repaired_audit(),
            ],
            database_path=live_database,
        )
        return (
            MaintenanceRunner(
                process_controller=process,
                backup_manager=backup,
                data_health=health,
                report_dir=report_dir or self.report_dir,
                run_id=run_id,
                stop_timeout_seconds=3,
                lock_root=self.root / "locks",
                crash_hook=crash_hook,
            ),
            process,
            backup,
            health,
        )

    def load_report(self, result) -> dict[str, object]:
        return json.loads(Path(result.report_json).read_text(encoding="utf-8"))

    def assert_recursively_redacted(self, value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).casefold()
                self.assertFalse(
                    any(word in normalized for word in FORBIDDEN_KEYS),
                    key,
                )
                self.assert_recursively_redacted(item)
            return
        if isinstance(value, list):
            for item in value:
                self.assert_recursively_redacted(item)
            return
        if isinstance(value, str):
            normalized = value.casefold()
            for private in PRIVATE_VALUES:
                self.assertNotIn(private.casefold(), normalized)
            self.assertNotIn("://", normalized)

    def test_success_runs_stages_in_order_and_writes_redacted_reports(self) -> None:
        runner, _, _, _ = self.make_runner(run_id="success-run")

        result = runner.run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(
            self.events,
            [
                "discover",
                "stop",
                "acquire_offline",
                "validate_offline",
                "create_backup",
                "validate_offline",
                "verify_backup",
                "validate_offline",
                "audit",
                "validate_offline",
                "repair",
                "validate_offline",
                "validate_offline",
                "audit",
                "validate_offline",
                "validate_offline",
                "release_offline",
                "start",
                "verify_processes",
            ],
        )
        report = self.load_report(result)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["repair"]["applied_count"], 1)
        self.assertNotEqual(
            report["repair"]["applied_action_id_hashes"],
            ["raw-action-id"],
        )
        self.assert_recursively_redacted(report)
        markdown = Path(result.report_markdown).read_text(encoding="utf-8")
        self.assert_recursively_redacted(markdown)
        state_path = next(self.report_dir.glob("*.state.json"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assert_recursively_redacted(state)
        self.assertNotIn(str(self.root), json.dumps(state))
        self.assertNotIn(str(self.root), json.dumps(report))

    def test_ambiguous_discovery_fails_without_stopping_runtime(self) -> None:
        process = FakeProcessController(
            self.events,
            discovered=RuntimeState(
                bot_count=2,
                worker_count=1,
                unambiguous=False,
            ),
        )
        runner, _, backup, health = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.events, ["discover"])
        self.assertEqual(backup.restore_calls, 0)
        self.assertEqual(health.repair_calls, 0)

    def test_missing_expected_process_fails_before_stop(self) -> None:
        process = FakeProcessController(
            self.events,
            discovered=RuntimeState(
                bot_count=1,
                worker_count=0,
                unambiguous=True,
            ),
        )
        runner, _, _, _ = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.events, ["discover"])

    def test_shutdown_timeout_requires_manual_intervention_and_stops(self) -> None:
        process = FakeProcessController(
            self.events,
            stop_error=TimeoutError("private shutdown detail"),
        )
        runner, _, backup, _ = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "manual_intervention_required")
        self.assertEqual(self.events, ["discover", "stop"])
        self.assertEqual(backup.restore_calls, 0)
        self.assertEqual(self.load_report(result)["error_code"], "stop_failed")

    def test_backup_creation_failure_does_not_audit_repair_or_restart(self) -> None:
        backup = FakeBackupManager(
            self.events,
            self.root / "backup.db",
            create_error=RuntimeError("secret-token-value"),
        )
        runner, _, _, health = self.make_runner(backup=backup)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            self.events,
            [
                "discover",
                "stop",
                "acquire_offline",
                "validate_offline",
                "create_backup",
                "release_offline",
            ],
        )
        self.assertEqual(health.repair_calls, 0)
        self.assertEqual(backup.restore_calls, 0)
        self.assert_recursively_redacted(self.load_report(result))

    def test_invalid_backup_never_reaches_audit_or_repair(self) -> None:
        backup = FakeBackupManager(
            self.events,
            self.root / "backup.db",
            verification={
                "ok": False,
                "path": "https://private.example/lesson",
                "integrity": "failed",
                "foreign_key_violations": 1,
                "schema_version": 0,
                "required_tables_missing": ["lessons"],
                "counts": {},
                "detail": "secret-token-value",
            },
        )
        runner, _, _, health = self.make_runner(backup=backup)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            self.events,
            [
                "discover",
                "stop",
                "acquire_offline",
                "validate_offline",
                "create_backup",
                "validate_offline",
                "verify_backup",
                "release_offline",
            ],
        )
        self.assertEqual(health.audit_calls, 0)
        self.assertEqual(backup.restore_calls, 0)
        self.assert_recursively_redacted(self.load_report(result))

    def test_repair_failure_leaves_runtime_stopped_without_restore(self) -> None:
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                )
            ],
            repair_error=RuntimeError("private lesson body"),
        )
        runner, process, backup, _ = self.make_runner(health=health)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertNotIn("start", self.events)
        self.assertEqual(len(process.stop_states), 1)
        self.assertEqual(backup.restore_calls, 0)
        self.assert_recursively_redacted(self.load_report(result))

    def test_post_check_failure_requires_manual_intervention(self) -> None:
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
            ],
        )
        runner, _, backup, _ = self.make_runner(health=health)

        result = runner.run()

        self.assertEqual(result.status, "manual_intervention_required")
        self.assertNotIn("start", self.events)
        self.assertEqual(backup.restore_calls, 0)

    def test_schema_or_foreign_key_post_check_failure_blocks_restart(self) -> None:
        for audit in (
            healthy_audit(schema_version=SCHEMA_VERSION + 1),
            healthy_audit(foreign_key_violations=1),
            healthy_audit(integrity="failed:1"),
        ):
            with self.subTest(audit=audit):
                self.events.clear()
                health = FakeDataHealth(
                    self.events,
                    [
                        healthy_audit(
                            findings=(SAFE_FINDING,),
                            actions=(SAFE_ACTION,),
                        ),
                        audit,
                    ],
                )
                runner, _, _, _ = self.make_runner(health=health)
                result = runner.run()
                self.assertEqual(
                    result.status,
                    "manual_intervention_required",
                )
                self.assertNotIn("start", self.events)

    def test_partial_restart_is_stopped_and_reported_failed(self) -> None:
        partial = RuntimeState(
            bot_count=1,
            worker_count=0,
            unambiguous=True,
        )
        process = FakeProcessController(
            self.events,
            started=partial,
            health={"bot": True, "worker": False},
        )
        runner, _, backup, _ = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.events[-3:], ["release_offline", "start", "stop"])
        self.assertEqual(process.stop_states[-1], partial)
        self.assertEqual(backup.restore_calls, 0)
        report = self.load_report(result)
        self.assertTrue(report["process"]["partial_restart_stopped"])

    def test_restart_exception_discovers_and_stops_started_process(self) -> None:
        partial = RuntimeState(
            bot_count=1,
            worker_count=0,
            unambiguous=True,
        )
        process = FakeProcessController(
            self.events,
            start_error=RuntimeError("secret-token-value"),
        )
        process.discovered = RuntimeState(
            bot_count=1,
            worker_count=1,
            unambiguous=True,
        )
        discoveries = iter((process.discovered, partial))

        def discover_next() -> RuntimeState:
            process.events.append("discover")
            return next(discoveries)

        process.discover = discover_next  # type: ignore[method-assign]
        runner, _, backup, _ = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(
            self.events[-3:],
            ["start", "discover", "stop"],
        )
        self.assertEqual(process.stop_states[-1], partial)
        self.assertEqual(backup.restore_calls, 0)
        self.assert_recursively_redacted(self.load_report(result))

    def test_resume_after_post_check_failure_does_not_repeat_prior_stages(self) -> None:
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                repaired_audit(),
            ],
        )
        runner, process, backup, _ = self.make_runner(
            health=health,
            run_id="resumable-run",
        )
        first = runner.run()
        first_event_count = len(self.events)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="resumable-run",
        )
        second = resumed.run()

        self.assertEqual(first.status, "manual_intervention_required")
        self.assertEqual(second.status, "completed")
        self.assertEqual(health.repair_calls, 1)
        self.assertEqual(self.events[:first_event_count].count("stop"), 1)
        self.assertEqual(self.events[first_event_count:], [
            "acquire_offline",
            "validate_offline",
            "verify_backup",
            "validate_offline",
            "audit",
            "validate_offline",
            "validate_offline",
            "release_offline",
            "start",
            "verify_processes",
        ])

    def test_completed_run_is_terminal_and_has_no_repeated_side_effects(self) -> None:
        runner, process, backup, health = self.make_runner(
            run_id="terminal-run",
        )
        first = runner.run()
        event_count = len(self.events)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="terminal-run",
        )
        second = resumed.run()

        self.assertEqual(first.status, "completed")
        self.assertEqual(second.status, "completed")
        self.assertEqual(len(self.events), event_count)
        self.assertEqual(second.backup_path, first.backup_path)

    def test_generated_run_ids_are_collision_safe(self) -> None:
        first, _, _, _ = self.make_runner()
        second, _, _, _ = self.make_runner()

        fixed = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)
        with (
            mock.patch("hermes.maintenance.datetime") as clock,
            mock.patch(
                "hermes.maintenance.secrets.token_hex",
                return_value="a" * 16,
            ),
        ):
            clock.now.return_value = fixed
            first_result = first.run()
            second_result = second.run()

        self.assertNotEqual(first_result.run_id, second_result.run_id)
        self.assertTrue(first_result.run_id.startswith("run-"))
        self.assertTrue(second_result.run_id.startswith("run-"))
        self.assertNotEqual(first_result.report_json, second_result.report_json)

    def test_offline_lease_is_revalidated_before_backup_and_repair(self) -> None:
        lease = FakeOfflineLease(self.events, [True, False])
        process = FakeProcessController(self.events, lease=lease)
        runner, _, _, health = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "manual_intervention_required")
        self.assertEqual(health.repair_calls, 0)
        self.assertTrue(lease.released)
        self.assertEqual(self.events.count("validate_offline"), 2)
        self.assertNotIn("start", self.events)

    def test_concurrent_runner_fails_before_process_or_database_side_effects(
        self,
    ) -> None:
        runner, _, backup, health = self.make_runner(run_id="busy-run")
        lock = DatabaseRunLock(
            database_path=backup.database.path,
            lock_root=self.root / "locks",
        )
        lock.acquire()
        try:
            with self.assertRaises(MaintenanceBusyError):
                runner.run()
            self.assertEqual(self.events, [])
            self.assertEqual(health.audit_calls, 0)
            self.assertEqual(health.repair_calls, 0)
        finally:
            lock.close()

    def test_resume_reverifies_stored_backup_before_audit_or_restart(self) -> None:
        backup = FakeBackupManager(
            self.events,
            self.root / "backups" / "verified.db",
        )
        invalid = {
            **backup.verification,
            "ok": False,
            "integrity": "failed",
        }
        backup.verifications = [dict(backup.verification), invalid]
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                repaired_audit(),
            ],
        )
        runner, process, backup, health = self.make_runner(
            backup=backup,
            health=health,
            run_id="backup-resume-run",
        )
        first = runner.run()
        first_event_count = len(self.events)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="backup-resume-run",
        )
        second = resumed.run()

        self.assertEqual(first.status, "manual_intervention_required")
        self.assertEqual(second.status, "manual_intervention_required")
        self.assertEqual(
            self.events[first_event_count:],
            [
                "acquire_offline",
                "validate_offline",
                "verify_backup",
                "release_offline",
            ],
        )
        self.assertEqual(health.repair_calls, 1)

    def test_restart_intent_prevents_double_start_after_crash(self) -> None:
        process = FakeProcessController(
            self.events,
            start_error=KeyboardInterrupt(),
        )
        runner, process, backup, health = self.make_runner(
            process=process,
            run_id="restart-crash-run",
        )

        with self.assertRaises(KeyboardInterrupt):
            runner.run()
        first_event_count = len(self.events)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="restart-crash-run",
        )
        result = resumed.run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(self.events.count("start"), 1)
        self.assertEqual(
            self.events[first_event_count:],
            ["verify_backup", "discover", "verify_processes"],
        )

    def test_tampered_state_fails_closed_before_side_effects(self) -> None:
        runner, process, backup, health = self.make_runner(
            run_id="tamper-run",
        )
        runner.run()
        state_path = next(self.report_dir.glob("*.state.json"))
        original = json.loads(state_path.read_text(encoding="utf-8"))

        tampered_states = (
            {**original, "environment": {"secret": "secret-token-value"}},
            {
                **original,
                "completed_stages": ["discovered", "backup_created"],
            },
            {
                **original,
                "post_audit": {
                    **original["post_audit"],
                    "counts": {
                        **original["post_audit"]["counts"],
                        "lessons": 11,
                    },
                },
            },
        )
        for index, tampered in enumerate(tampered_states):
            with self.subTest(index=index):
                state_path.write_text(
                    json.dumps(tampered),
                    encoding="utf-8",
                )
                self.events.clear()
                resumed, _, _, _ = self.make_runner(
                    process=process,
                    backup=backup,
                    health=health,
                    run_id="tamper-run",
                )
                with self.assertRaises(StateValidationError):
                    resumed.run()
                self.assertEqual(self.events, [])
                state_path.write_text(
                    json.dumps(original),
                    encoding="utf-8",
                )

    def test_miswired_backup_and_health_adapters_fail_before_discovery(self) -> None:
        backup = FakeBackupManager(
            self.events,
            self.root / "backups" / "verified.db",
            database_path=self.root / "live-a" / "hermes.db",
        )
        health = FakeDataHealth(
            self.events,
            [healthy_audit()],
            database_path=self.root / "live-b" / "hermes.db",
        )
        runner, _, _, _ = self.make_runner(
            backup=backup,
            health=health,
        )

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.events, [])
        self.assertEqual(
            self.load_report(result)["error_code"],
            "database_configuration_mismatch",
        )

    def test_backup_counts_must_match_pre_repair_live_audit(self) -> None:
        backup = FakeBackupManager(
            self.events,
            self.root / "backups" / "verified.db",
        )
        backup.verification["counts"] = {
            "lessons": 11,
            "sources": 10,
            "evidence": 7,
            "lesson_events": 19,
            "lesson_fts": 8,
        }
        runner, _, _, health = self.make_runner(backup=backup)

        result = runner.run()

        self.assertEqual(result.status, "manual_intervention_required")
        self.assertEqual(health.repair_calls, 0)
        self.assertNotIn("start", self.events)
        self.assertEqual(
            self.load_report(result)["error_code"],
            "backup_source_mismatch",
        )

    def test_post_check_enforces_explicit_count_invariants(self) -> None:
        invalid_posts = (
            repaired_audit(lessons=11),
            repaired_audit(sources=9),
            repaired_audit(evidence=6),
            repaired_audit(lesson_events=19),
            repaired_audit(approved=8),
            repaired_audit(rejected=2),
            repaired_audit(fts_rows=8),
        )
        for post_audit in invalid_posts:
            with self.subTest(counts=post_audit.counts):
                self.events.clear()
                health = FakeDataHealth(
                    self.events,
                    [
                        healthy_audit(
                            findings=(SAFE_FINDING,),
                            actions=(SAFE_ACTION,),
                        ),
                        post_audit,
                    ],
                )
                runner, _, _, _ = self.make_runner(health=health)
                result = runner.run()
                self.assertEqual(
                    result.status,
                    "manual_intervention_required",
                )
                self.assertNotIn("start", self.events)

    def test_report_artifact_collision_fails_before_discovery(self) -> None:
        self.report_dir.mkdir(parents=True)
        runner, _, _, _ = self.make_runner(run_id="artifact-run")
        collision = (
            self.report_dir
            / f"maintenance-{runner.run_id}-attempt-1.json"
        )
        collision.write_text("historical", encoding="utf-8")

        with self.assertRaises(ArtifactCollisionError):
            runner.run()

        self.assertEqual(self.events, [])
        self.assertEqual(collision.read_text(encoding="utf-8"), "historical")

    def test_restart_requires_unambiguous_exact_process_counts(self) -> None:
        duplicate = RuntimeState(
            bot_count=2,
            worker_count=1,
            unambiguous=True,
        )
        process = FakeProcessController(
            self.events,
            started=duplicate,
            health={"bot": True, "worker": True},
        )
        runner, process, _, _ = self.make_runner(process=process)

        result = runner.run()

        self.assertEqual(result.status, "failed")
        self.assertEqual(process.stop_states[-1], duplicate)
        self.assertTrue(
            self.load_report(result)["process"]["partial_restart_stopped"]
        )

    def test_lease_revocation_at_every_safety_boundary_blocks_restart(
        self,
    ) -> None:
        for boundary_index in range(8):
            with self.subTest(boundary_index=boundary_index):
                self.events.clear()
                lease = FakeOfflineLease(
                    self.events,
                    [True] * boundary_index + [False],
                )
                process = FakeProcessController(self.events, lease=lease)
                runner, _, _, _ = self.make_runner(
                    process=process,
                    run_id=f"lease-boundary-{boundary_index}",
                    report_dir=self.root / f"lease-report-{boundary_index}",
                )

                result = runner.run()

                self.assertEqual(
                    result.status,
                    "manual_intervention_required",
                )
                self.assertNotIn("start", self.events)
                self.assertTrue(lease.released)

    def test_database_lock_contends_across_report_dirs_and_close_releases(
        self,
    ) -> None:
        runner, _, backup, _ = self.make_runner(
            run_id="lock-run",
            report_dir=self.root / "reports-a",
        )
        lock = DatabaseRunLock(
            database_path=backup.database.path,
            lock_root=self.root / "locks",
        )
        lock.acquire()
        try:
            with self.assertRaises(MaintenanceBusyError):
                runner.run()
            self.assertEqual(self.events, [])
        finally:
            lock.close()

        result = runner.run()

        self.assertEqual(result.status, "completed")

    def test_report_artifacts_reconcile_crashes_without_repeating_start(
        self,
    ) -> None:
        boundaries = (
            "after_report_reservation",
            "after_restart_persist",
            "after_json_write",
            "after_markdown_write",
            "before_terminal_persist",
            "after_terminal_persist",
        )
        for boundary in boundaries:
            with self.subTest(boundary=boundary):
                self.events.clear()
                crash = CrashOnce(boundary)
                report_dir = self.root / f"crash-{boundary}"
                runner, process, backup, health = self.make_runner(
                    run_id=f"crash-{boundary}",
                    report_dir=report_dir,
                    crash_hook=crash,
                )
                with self.assertRaises(KeyboardInterrupt):
                    runner.run()
                starts_before_resume = self.events.count("start")

                resumed, _, _, _ = self.make_runner(
                    process=process,
                    backup=backup,
                    health=health,
                    run_id=f"crash-{boundary}",
                    report_dir=report_dir,
                    crash_hook=crash,
                )
                result = resumed.run()

                self.assertEqual(result.status, "completed")
                self.assertEqual(
                    self.events.count("start"),
                    max(1, starts_before_resume),
                )
                self.assertGreater(
                    Path(result.report_json).stat().st_size,
                    0,
                )
                self.assertGreater(
                    Path(result.report_markdown).stat().st_size,
                    0,
                )

    def test_repair_intent_reconciles_committed_crash_without_duplicate_event(
        self,
    ) -> None:
        crash = CrashOnce("after_repair_commit")
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                repaired_audit(),
                repaired_audit(),
            ],
        )
        runner, process, backup, health = self.make_runner(
            health=health,
            run_id="repair-crash-run",
            crash_hook=crash,
        )
        with self.assertRaises(KeyboardInterrupt):
            runner.run()
        self.assertEqual(health.repair_calls, 1)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="repair-crash-run",
            crash_hook=crash,
        )
        result = resumed.run()

        self.assertEqual(result.status, "completed")
        self.assertEqual(health.repair_calls, 1)
        self.assertEqual(self.events.count("start"), 1)

    def test_resume_rejects_same_name_backup_with_changed_digest(self) -> None:
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                ),
                repaired_audit(),
            ],
        )
        runner, process, backup, health = self.make_runner(
            health=health,
            run_id="digest-replacement-run",
        )
        first = runner.run()
        self.assertEqual(first.status, "manual_intervention_required")
        backup.backup_path.write_bytes(b"replacement-same-counts")
        event_count = len(self.events)

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="digest-replacement-run",
        )
        second = resumed.run()

        self.assertEqual(second.status, "manual_intervention_required")
        self.assertEqual(
            self.events[event_count:],
            [
                "acquire_offline",
                "validate_offline",
                "verify_backup",
                "release_offline",
            ],
        )
        self.assertNotIn("start", self.events[event_count:])

    def test_lease_release_failure_is_persisted_and_retryable(self) -> None:
        running = RuntimeState(1, 1, True)
        stopped = RuntimeState(0, 0, True)
        process = FakeProcessController(
            self.events,
            discoveries=[running, stopped],
            release_results=[False, True],
        )
        runner, _, _, _ = self.make_runner(
            process=process,
            run_id="release-retry-run",
        )

        first = runner.run()
        self.assertEqual(first.status, "manual_intervention_required")
        self.assertEqual(
            self.load_report(first)["error_code"],
            "offline_lease_release_failed",
        )
        self.assertTrue(
            self.load_report(first)["process"]["lease_release_pending"]
        )

        second = runner.run()

        self.assertEqual(second.status, "completed")
        self.assertEqual(self.events.count("start"), 1)

    def test_external_run_alias_is_hashed_and_sensitive_aliases_rejected(
        self,
    ) -> None:
        runner, _, _, _ = self.make_runner(run_id="operator-run")
        result = runner.run()

        self.assertNotEqual(result.run_id, "operator-run")
        self.assertNotIn(
            "operator-run",
            Path(result.report_json).read_text(encoding="utf-8"),
        )
        state = next(self.report_dir.glob("*.state.json"))
        self.assertNotIn(
            "operator-run",
            state.read_text(encoding="utf-8"),
        )
        with self.assertRaises(ValueError):
            self.make_runner(run_id="customer-secret-token")

    def test_boolean_counts_are_rejected_everywhere(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeState(bot_count=True, worker_count=1, unambiguous=True)

        backup = FakeBackupManager(
            self.events,
            self.root / "bool-backup" / "verified.db",
        )
        backup.verification["counts"]["lessons"] = True
        runner, _, _, _ = self.make_runner(
            backup=backup,
            run_id="bool-backup-run",
            report_dir=self.root / "bool-backup-report",
        )
        result = runner.run()
        self.assertEqual(result.status, "failed")
        self.assertNotIn("audit", self.events)

        self.events.clear()
        bad_counts = healthy_audit().counts
        bad_counts["lessons"] = True
        health = FakeDataHealth(
            self.events,
            [healthy_audit(counts=bad_counts)],
        )
        runner, _, _, _ = self.make_runner(
            health=health,
            run_id="bool-audit-run",
            report_dir=self.root / "bool-audit-report",
        )
        result = runner.run()
        self.assertEqual(result.status, "manual_intervention_required")
        self.assertEqual(health.repair_calls, 0)

        self.events.clear()
        invalid_repair = RepairReport(
            planned_count=True,
            applied_count=1,
            skipped_count=0,
            applied_action_ids=("raw-action-id",),
            skipped_action_ids=(),
            outcomes=APPLIED_REPAIR.outcomes,
        )
        health = FakeDataHealth(
            self.events,
            [
                healthy_audit(
                    findings=(SAFE_FINDING,),
                    actions=(SAFE_ACTION,),
                )
            ],
            repair_report=invalid_repair,
        )
        runner, _, _, _ = self.make_runner(
            health=health,
            run_id="bool-repair-run",
            report_dir=self.root / "bool-repair-report",
        )
        result = runner.run()
        self.assertEqual(result.status, "manual_intervention_required")
        self.assertNotIn("start", self.events)

    def test_terminal_state_reconstructs_missing_owned_reports_only(self) -> None:
        runner, process, backup, health = self.make_runner(
            run_id="terminal-rebuild-run",
        )
        first = runner.run()
        event_count = len(self.events)
        Path(first.report_json).unlink()
        Path(first.report_markdown).unlink()

        resumed, _, _, _ = self.make_runner(
            process=process,
            backup=backup,
            health=health,
            run_id="terminal-rebuild-run",
        )
        rebuilt = resumed.run()

        self.assertEqual(rebuilt.status, "completed")
        self.assertEqual(len(self.events), event_count)
        self.assertGreater(Path(rebuilt.report_json).stat().st_size, 0)
        self.assertGreater(Path(rebuilt.report_markdown).stat().st_size, 0)

        Path(rebuilt.report_json).write_text(
            "foreign historical artifact",
            encoding="utf-8",
        )
        with self.assertRaises(ArtifactCollisionError):
            resumed.run()
        self.assertEqual(
            Path(rebuilt.report_json).read_text(encoding="utf-8"),
            "foreign historical artifact",
        )


if __name__ == "__main__":
    unittest.main()
