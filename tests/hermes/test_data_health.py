from __future__ import annotations

import dataclasses
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor
from hermes.data_health import DataHealth
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


if __name__ == "__main__":
    unittest.main()
