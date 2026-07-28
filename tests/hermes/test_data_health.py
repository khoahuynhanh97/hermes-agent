from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor
from hermes.data_health import DataHealth, RepairAction, RepairPlan
from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore


class DataHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = Database(self.root / "hermes.db")
        self.store = SQLiteKnowledgeStore(self.database)
        self.lifecycle = KnowledgeLifecycle(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_lesson(
        self,
        title: str,
        *,
        category: str = "general",
        evidence: bool = True,
    ) -> dict:
        detail = {
            "summary": f"Summary for {title}",
            "content": f"Private body for {title}",
        }
        if evidence:
            detail["evidence"] = [
                {"kind": "transcript", "excerpt": f"Evidence for {title}"}
            ]
        return self.store.add_entry(
            title=title,
            category=category,
            source_url=f"https://private.example/{hashlib.sha256(title.encode()).hexdigest()}",
            key_lessons=[f"Rule for {title}"],
            detail_data=detail,
            owner_user_id="42",
        )

    def approve(self, lesson: dict) -> None:
        result = self.lifecycle.approve(
            lesson["id"],
            LifecycleActor.owner("42"),
            mode="test",
            force=True,
        )
        self.assertTrue(result.ok)

    def database_hash(self) -> str:
        connection = sqlite3.connect(self.database.path)
        try:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            connection.close()
        return hashlib.sha256(self.database.path.read_bytes()).hexdigest()

    def snapshot(self) -> dict[str, list[tuple]]:
        with self.database.connect() as connection:
            return {
                table: [
                    tuple(row)
                    for row in connection.execute(
                        f"SELECT * FROM {table} ORDER BY rowid"
                    ).fetchall()
                ]
                for table in ("lessons", "lesson_events", "lesson_fts")
            }

    @staticmethod
    def action_id(
        kind: str,
        subject_id: str,
        expected: dict[str, int | str | bool],
    ) -> str:
        canonical = json.dumps(
            {
                "kind": kind,
                "subject_id": subject_id,
                "expected": expected,
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def build_defective_fixture(self) -> tuple[dict, dict, dict, dict]:
        missing_timestamp = self.add_lesson("Missing approval timestamp")
        self.approve(missing_timestamp)
        needs_reanalysis = self.add_lesson("Malformed source")
        self.store.mark_needs_reanalysis(needs_reanalysis["id"], "invalid JSON")
        unknown_title = self.add_lesson(" Không xác định ")
        error_category = self.add_lesson("Provider failure", category=" ERROR ")
        self.approve(error_category)
        no_evidence = self.add_lesson("Review evidence gap", evidence=False)
        self.approve(no_evidence)

        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE lessons SET approved_at = NULL WHERE id = ?",
                (missing_timestamp["id"],),
            )
            connection.execute(
                "UPDATE lesson_fts SET title = 'drifted title' WHERE lesson_id = ?",
                (no_evidence["id"],),
            )
            connection.execute(
                """
                INSERT INTO lesson_fts(
                    lesson_id, owner_user_id, title, summary, content, tags
                ) VALUES ('orphan', '42', 'orphan', '', '', '')
                """
            )

        return missing_timestamp, needs_reanalysis, unknown_title, error_category

    def test_audit_is_read_only_and_classifies_all_required_findings(self) -> None:
        self.build_defective_fixture()
        legacy_index = self.root / "unified_index.json"
        legacy_index.write_text(
            json.dumps({"entries": [{"id": "legacy-only"}]}),
            encoding="utf-8",
        )
        health = DataHealth(self.database, legacy_index_path=legacy_index)
        before = self.database_hash()

        report = health.audit()

        after = self.database_hash()
        self.assertEqual(before, after)
        codes = {finding.code for finding in report.findings}
        self.assertIn("fts_orphan", codes)
        self.assertIn("fts_mismatch", codes)
        self.assertIn("approved_at_missing_unambiguous", codes)
        self.assertIn("defect_needs_reanalysis", codes)
        self.assertIn("defect_unknown_title", codes)
        self.assertIn("defect_error_category", codes)
        self.assertIn("approved_without_evidence", codes)
        self.assertIn("legacy_count_drift", codes)
        self.assertEqual(report.integrity, "ok")
        self.assertEqual(report.foreign_key_violations, 0)
        self.assertEqual(report.schema_version, 2)
        self.assertEqual(report.counts["lessons"], 5)
        self.assertGreaterEqual(len(report.repair_plan.actions), 5)

    def test_action_ids_and_preconditions_are_deterministic_and_redacted(self) -> None:
        lessons = self.build_defective_fixture()
        health = DataHealth(self.database)

        first = health.audit()
        second = health.audit()

        self.assertEqual(first.repair_plan.actions, second.repair_plan.actions)
        serialized = json.dumps(
            dataclasses.asdict(first),
            ensure_ascii=False,
            sort_keys=True,
        )
        self.assertNotIn("Private body", serialized)
        self.assertNotIn("private.example", serialized)
        for lesson in lessons:
            self.assertNotIn(lesson["id"], serialized)
        for action in first.repair_plan.actions:
            self.assertRegex(action.action_id, r"^[0-9a-f]{64}$")
            self.assertNotIn("title", action.expected)
            self.assertNotIn("url", action.expected)

    def test_repair_applies_safe_actions_and_second_application_is_idempotent(
        self,
    ) -> None:
        missing_timestamp, needs_reanalysis, unknown_title, error_category = (
            self.build_defective_fixture()
        )
        health = DataHealth(self.database)
        plan = health.audit().repair_plan

        first = health.repair(plan)
        after_first = self.snapshot()
        second = health.repair(plan)

        self.assertEqual(first.applied_count, len(plan.actions))
        self.assertEqual(first.skipped_count, 0)
        self.assertEqual(second.applied_count, 0)
        self.assertEqual(second.skipped_count, len(plan.actions))
        self.assertTrue(
            all(outcome.status == "applied" for outcome in first.outcomes)
        )
        self.assertTrue(
            all(
                outcome.status == "skipped"
                and outcome.reason == "already_applied"
                for outcome in second.outcomes
            )
        )
        self.assertEqual(after_first, self.snapshot())
        with self.database.connect() as connection:
            timestamp = connection.execute(
                "SELECT approved_at FROM lessons WHERE id = ?",
                (missing_timestamp["id"],),
            ).fetchone()[0]
            approved_event = connection.execute(
                """
                SELECT created_at FROM lesson_events
                WHERE lesson_id = ? AND action = 'approved'
                """,
                (missing_timestamp["id"],),
            ).fetchone()[0]
            self.assertEqual(timestamp, approved_event)
            for lesson in (needs_reanalysis, unknown_title, error_category):
                status = connection.execute(
                    "SELECT status FROM lessons WHERE id = ?",
                    (lesson["id"],),
                ).fetchone()[0]
                self.assertEqual(status, "rejected")
            expected_fts = {
                row[0]
                for row in connection.execute(
                    "SELECT id FROM lessons WHERE status = 'approved'"
                )
            }
            actual_fts = {
                row[0]
                for row in connection.execute("SELECT lesson_id FROM lesson_fts")
            }
            self.assertEqual(actual_fts, expected_fts)

    def test_repair_rolls_back_every_action_when_lifecycle_rejection_fails(
        self,
    ) -> None:
        self.build_defective_fixture()
        health = DataHealth(self.database)
        plan = health.audit().repair_plan
        before = self.snapshot()
        with self.database.connect() as connection:
            connection.execute(
                """
                CREATE TRIGGER inject_repair_failure
                BEFORE INSERT ON lesson_events
                WHEN NEW.action = 'rejected'
                BEGIN
                    SELECT RAISE(ABORT, 'injected repair failure');
                END
                """
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "injected repair failure"):
            health.repair(plan)

        self.assertEqual(before, self.snapshot())

    def test_changed_precondition_is_skipped_without_mutation(self) -> None:
        _, needs_reanalysis, _, _ = self.build_defective_fixture()
        health = DataHealth(self.database)
        plan = health.audit().repair_plan
        reject_action = next(
            action
            for action in plan.actions
            if action.kind == "reject_lesson"
            and action.expected.get("needs_reanalysis") is True
        )
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE lessons SET needs_reanalysis = 0 WHERE id = ?",
                (needs_reanalysis["id"],),
            )
        before = self.snapshot()

        report = health.repair(type(plan)((reject_action,)))

        self.assertEqual(report.applied_count, 0)
        self.assertEqual(report.skipped_count, 1)
        self.assertEqual(report.outcomes[0].reason, "precondition_failed")
        self.assertEqual(
            report.outcomes[0].before,
            report.outcomes[0].after,
        )
        self.assertEqual(before, self.snapshot())

    def test_ambiguous_approval_history_is_review_only(self) -> None:
        lesson = self.add_lesson("Ambiguous approval")
        self.approve(lesson)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE lessons SET approved_at = NULL WHERE id = ?",
                (lesson["id"],),
            )
            connection.execute(
                """
                INSERT INTO lesson_events(
                    lesson_id, action, actor_user_id, note, metadata_json, created_at
                ) VALUES (?, 'approved', '42', '', '{}', '2026-01-01T00:00:00+00:00')
                """,
                (lesson["id"],),
            )

        report = DataHealth(self.database).audit()

        finding = next(
            finding
            for finding in report.findings
            if finding.code == "approved_at_missing_ambiguous"
        )
        self.assertEqual(finding.repair_class, "review")
        self.assertFalse(
            any(
                action.kind == "set_approved_at"
                and action.subject_id
                == hashlib.sha256(lesson["id"].encode("utf-8")).hexdigest()
                for action in report.repair_plan.actions
            )
        )

    def test_integrity_and_foreign_key_checks_are_reported_without_repair(self) -> None:
        lesson = self.add_lesson("Foreign key audit")
        connection = sqlite3.connect(self.database.path)
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "INSERT INTO lesson_evidence(lesson_id, evidence_id) VALUES (?, ?)",
                (lesson["id"], "missing-evidence"),
            )
            connection.commit()
        finally:
            connection.close()

        report = DataHealth(self.database).audit()

        self.assertEqual(report.integrity, "ok")
        self.assertEqual(report.foreign_key_violations, 1)
        finding = next(
            finding
            for finding in report.findings
            if finding.code == "foreign_key_violation"
        )
        self.assertEqual(finding.repair_class, "forbidden")

    def test_repair_rejects_forged_action_ids_and_markerless_rejections(
        self,
    ) -> None:
        lesson = self.add_lesson("Forged repair target", category="error")
        self.approve(lesson)
        health = DataHealth(self.database)
        valid = next(
            action
            for action in health.audit().repair_plan.actions
            if action.kind == "reject_lesson"
        )
        before = self.snapshot()

        forged_id = dataclasses.replace(valid, action_id="0" * 64)
        with self.assertRaisesRegex(ValueError, "action ID"):
            health.repair(RepairPlan((forged_id,)))

        expected = {"status": "approved"}
        markerless = RepairAction(
            action_id=self.action_id(
                "reject_lesson",
                valid.subject_id,
                expected,
            ),
            kind="reject_lesson",
            subject_id=valid.subject_id,
            expected=expected,
        )
        with self.assertRaisesRegex(ValueError, "defect marker"):
            health.repair(RepairPlan((markerless,)))

        self.assertEqual(before, self.snapshot())

    def test_fts_rebuild_precondition_survives_rejection_in_same_plan(self) -> None:
        lesson = self.add_lesson("Rejected FTS drift", category="error")
        self.approve(lesson)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "UPDATE lesson_fts SET title = 'drifted' WHERE lesson_id = ?",
                (lesson["id"],),
            )
        health = DataHealth(self.database)
        plan = health.audit().repair_plan
        self.assertEqual(
            {action.kind for action in plan.actions},
            {"reject_lesson", "rebuild_fts"},
        )

        repaired = health.repair(plan)

        self.assertEqual(repaired.applied_count, 2)
        self.assertEqual(
            {outcome.kind for outcome in repaired.outcomes},
            {"reject_lesson", "rebuild_fts"},
        )
        self.assertFalse(
            any(
                finding.code.startswith("fts_")
                for finding in health.audit().findings
            )
        )
        self.assertEqual(self.store.get_entry(lesson["id"])["status"], "rejected")

    def test_missing_database_returns_forbidden_structured_audit_read_only(
        self,
    ) -> None:
        missing_path = self.root / "does-not-exist.db"

        health = DataHealth(Database(missing_path))
        report = health.audit()
        repair_report = health.repair(report.repair_plan)

        self.assertFalse(missing_path.exists())
        self.assertEqual(report.integrity, "unavailable")
        self.assertEqual(report.foreign_key_violations, 0)
        self.assertEqual(report.schema_version, 0)
        self.assertTrue(all(value == 0 for value in report.counts.values()))
        self.assertEqual(report.repair_plan.actions, ())
        self.assertEqual(repair_report.planned_count, 0)
        self.assertEqual(repair_report.outcomes, ())
        self.assertEqual(
            [finding.code for finding in report.findings],
            ["database_missing"],
        )
        self.assertEqual(report.findings[0].repair_class, "forbidden")

    def test_incompatible_schema_returns_forbidden_structured_audit_read_only(
        self,
    ) -> None:
        incompatible_path = self.root / "incompatible.db"
        connection = sqlite3.connect(incompatible_path)
        try:
            connection.execute("CREATE TABLE unrelated(id INTEGER PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()
        before = hashlib.sha256(incompatible_path.read_bytes()).hexdigest()

        report = DataHealth(Database(incompatible_path)).audit()

        after = hashlib.sha256(incompatible_path.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(report.integrity, "ok")
        self.assertEqual(report.schema_version, 0)
        self.assertTrue(all(value == 0 for value in report.counts.values()))
        self.assertEqual(report.repair_plan.actions, ())
        finding = next(
            finding
            for finding in report.findings
            if finding.code == "schema_incompatible"
        )
        self.assertEqual(finding.repair_class, "forbidden")
        self.assertGreater(finding.metadata["missing_table_count"], 0)

    def test_action_outcomes_are_redacted_and_include_before_after_metadata(
        self,
    ) -> None:
        lesson = self.add_lesson("Outcome metadata", category="error")
        self.approve(lesson)
        health = DataHealth(self.database)

        report = health.repair(health.audit().repair_plan)

        outcome = next(
            outcome
            for outcome in report.outcomes
            if outcome.kind == "reject_lesson"
        )
        self.assertEqual(outcome.status, "applied")
        self.assertEqual(outcome.reason, "applied")
        self.assertEqual(outcome.before["status"], "approved")
        self.assertEqual(outcome.after["status"], "rejected")
        serialized = json.dumps(dataclasses.asdict(report), ensure_ascii=False)
        self.assertNotIn(lesson["id"], serialized)
        self.assertNotIn("Outcome metadata", serialized)
        self.assertNotIn("private.example", serialized)

    def test_fts_findings_report_actual_row_counts(self) -> None:
        missing = self.add_lesson("Missing FTS row")
        duplicate = self.add_lesson("Duplicate FTS row")
        self.approve(missing)
        self.approve(duplicate)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM lesson_fts WHERE lesson_id = ?",
                (missing["id"],),
            )
            row = connection.execute(
                """
                SELECT lesson_id, owner_user_id, title, summary, content, tags
                FROM lesson_fts WHERE lesson_id = ?
                """,
                (duplicate["id"],),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO lesson_fts(
                    lesson_id, owner_user_id, title, summary, content, tags
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                tuple(row),
            )

        findings = DataHealth(self.database).audit().findings
        missing_finding = next(
            finding
            for finding in findings
            if finding.code == "fts_missing"
            and finding.subject_id_hash
            == hashlib.sha256(missing["id"].encode("utf-8")).hexdigest()
        )
        duplicate_finding = next(
            finding
            for finding in findings
            if finding.code == "fts_mismatch"
            and finding.subject_id_hash
            == hashlib.sha256(duplicate["id"].encode("utf-8")).hexdigest()
        )
        self.assertEqual(missing_finding.metadata["row_count"], 0)
        self.assertEqual(duplicate_finding.metadata["row_count"], 2)

    def test_unknown_title_rule_recognizes_vietnamese_and_known_mojibake(
        self,
    ) -> None:
        intended = "Không xác định"
        mojibake = intended.encode("utf-8").decode("cp1252")
        intended_lesson = self.add_lesson(f" {intended} ")
        mojibake_lesson = self.add_lesson(mojibake)

        report = DataHealth(self.database).audit()

        findings = [
            finding
            for finding in report.findings
            if finding.code == "defect_unknown_title"
        ]
        self.assertEqual(len(findings), 2)
        expected_subjects = {
            hashlib.sha256(lesson["id"].encode("utf-8")).hexdigest()
            for lesson in (intended_lesson, mojibake_lesson)
        }
        self.assertEqual(
            {finding.subject_id_hash for finding in findings},
            expected_subjects,
        )

    def test_timestamp_repair_only_sets_approved_at_and_reports_touched_field(
        self,
    ) -> None:
        lesson = self.add_lesson("Timestamp field isolation")
        self.approve(lesson)
        sentinel = "2035-01-02T03:04:05+00:00"
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE lessons
                SET approved_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (sentinel, lesson["id"]),
            )
        health = DataHealth(self.database)
        action = next(
            action
            for action in health.audit().repair_plan.actions
            if action.kind == "set_approved_at"
        )

        report = health.repair(RepairPlan((action,)))

        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT approved_at, updated_at FROM lessons WHERE id = ?",
                (lesson["id"],),
            ).fetchone()
        self.assertEqual(row["approved_at"], action.expected["event_created_at"])
        self.assertEqual(row["updated_at"], sentinel)
        outcome = report.outcomes[0]
        self.assertEqual(
            outcome.before,
            {"subject_present": True, "approved_at_missing": True},
        )
        self.assertEqual(
            outcome.after,
            {"subject_present": True, "approved_at_missing": False},
        )

    def test_stale_plan_does_not_recreate_deleted_or_modify_replaced_database(
        self,
    ) -> None:
        for replacement in ("deleted", "empty"):
            with self.subTest(replacement=replacement):
                path = self.root / f"stale-{replacement}.db"
                database = Database(path)
                store = SQLiteKnowledgeStore(database)
                lifecycle = KnowledgeLifecycle(store)
                lesson = store.add_entry(
                    title=f"Stale {replacement}",
                    category="error",
                    owner_user_id="42",
                )
                lifecycle.approve(
                    lesson["id"],
                    LifecycleActor.owner("42"),
                    mode="test",
                    force=True,
                )
                health = DataHealth(database, store=store)
                plan = health.audit().repair_plan
                self.assertTrue(plan.actions)
                path.unlink()
                for suffix in ("-wal", "-shm"):
                    Path(str(path) + suffix).unlink(missing_ok=True)
                if replacement == "empty":
                    path.write_bytes(b"")
                    before = hashlib.sha256(path.read_bytes()).hexdigest()

                report = health.repair(plan)

                self.assertEqual(report.applied_count, 0)
                self.assertEqual(report.skipped_count, len(plan.actions))
                self.assertTrue(
                    all(
                        outcome.reason == "precondition_failed"
                        for outcome in report.outcomes
                    )
                )
                if replacement == "deleted":
                    self.assertFalse(path.exists())
                else:
                    after = hashlib.sha256(path.read_bytes()).hexdigest()
                    self.assertEqual(before, after)

    def test_fts_rebuild_converges_for_valid_json_with_unexpected_types(
        self,
    ) -> None:
        lesson = self.add_lesson("Malformed valid JSON")
        self.approve(lesson)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                """
                UPDATE lessons
                SET tags_json = '{"topic":"agents"}',
                    key_lessons_json = '"One coherent lesson"'
                WHERE id = ?
                """,
                (lesson["id"],),
            )
        health = DataHealth(self.database)
        plan = health.audit().repair_plan
        action = next(
            action
            for action in plan.actions
            if action.kind == "rebuild_fts"
        )

        first = health.repair(RepairPlan((action,)))
        post_audit = health.audit()
        replay = health.repair(RepairPlan((action,)))

        self.assertEqual(first.applied_count, 1)
        self.assertFalse(
            any(
                finding.code.startswith("fts_")
                for finding in post_audit.findings
            )
        )
        self.assertEqual(replay.applied_count, 0)
        self.assertEqual(replay.outcomes[0].reason, "already_applied")

    def test_fts_rebuild_rechecks_finding_count_precondition(self) -> None:
        lesson = self.add_lesson("FTS finding count")
        self.approve(lesson)
        with self.database.transaction(immediate=True) as connection:
            connection.execute(
                "DELETE FROM lesson_fts WHERE lesson_id = ?",
                (lesson["id"],),
            )
        health = DataHealth(self.database)
        action = next(
            action
            for action in health.audit().repair_plan.actions
            if action.kind == "rebuild_fts"
        )
        forged_expected = dict(action.expected)
        forged_expected["finding_count"] = int(
            forged_expected["finding_count"]
        ) + 1
        stale_count = dataclasses.replace(
            action,
            action_id=self.action_id(
                action.kind,
                action.subject_id,
                forged_expected,
            ),
            expected=forged_expected,
        )
        before = self.snapshot()

        report = health.repair(RepairPlan((stale_count,)))

        self.assertEqual(report.applied_count, 0)
        self.assertEqual(report.outcomes[0].reason, "precondition_failed")
        self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main()
