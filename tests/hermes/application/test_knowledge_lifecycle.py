from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from hermes.application.knowledge_lifecycle import (
    KnowledgeLifecycle,
    LifecycleActor,
    LifecycleCommand,
)
from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore


class KnowledgeLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.store = SQLiteKnowledgeStore(self.database)
        self.lifecycle = KnowledgeLifecycle(self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def add_entry(self, title: str, owner: str = "42") -> dict:
        return self.store.add_entry(
            title=title,
            source_url=f"https://example.com/{title.lower().replace(' ', '-')}",
            key_lessons=[f"{title} searchable detail"],
            owner_user_id=owner,
        )

    def event_actions(self, lesson_id: str) -> list[str]:
        return [event["action"] for event in self.store.list_events(lesson_id)]

    def fts_lesson_ids(self) -> list[str]:
        with self.database.connect() as connection:
            rows = connection.execute(
                "SELECT lesson_id FROM lesson_fts ORDER BY lesson_id"
            ).fetchall()
        return [str(row["lesson_id"]) for row in rows]

    def test_owner_cannot_change_another_owners_lesson(self) -> None:
        actor = LifecycleActor.owner("99")

        for action in ("approve", "reject", "request_reanalysis"):
            with self.subTest(action=action):
                entry = self.add_entry(f"Private {action}")
                result = self.lifecycle.apply(
                    [LifecycleCommand(action, entry["id"], actor)]
                )[0]

                self.assertFalse(result.ok)
                self.assertEqual(result.code, "forbidden")
                self.assertFalse(result.changed)
                self.assertEqual(self.store.get_entry(entry["id"])["status"], "pending")
                self.assertFalse(
                    self.store.get_entry(entry["id"])["needs_reanalysis"]
                )
                self.assertEqual(self.event_actions(entry["id"]), ["created"])

    def test_system_actor_can_change_an_owned_lesson(self) -> None:
        entry = self.add_entry("System repair")

        result = self.lifecycle.approve(
            entry["id"], LifecycleActor.system("maintenance"), mode="repair"
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(result.lesson["status"], "approved")
        self.assertEqual(self.event_actions(entry["id"]), ["created", "approved"])

    def test_approval_is_forbidden_when_reanalysis_is_required(self) -> None:
        entry = self.add_entry("Malformed analysis")
        self.store.mark_needs_reanalysis(entry["id"], "invalid JSON")

        result = self.lifecycle.approve(
            entry["id"], LifecycleActor.owner("42"), mode="test"
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.code, "needs_reanalysis")
        self.assertFalse(result.changed)
        self.assertEqual(result.lesson["status"], "pending")
        self.assertEqual(
            self.event_actions(entry["id"]), ["created", "reanalysis_requested"]
        )

    def test_approve_is_idempotent_and_adds_one_effective_event(self) -> None:
        entry = self.add_entry("Idempotent approval")
        actor = LifecycleActor.owner("42")

        result = self.lifecycle.approve(entry["id"], actor, mode="test")
        again = self.lifecycle.approve(entry["id"], actor, mode="test")

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertEqual(result.lesson["status"], "approved")
        self.assertTrue(again.ok)
        self.assertFalse(again.changed)
        self.assertEqual(again.lesson["status"], "approved")
        self.assertEqual(self.event_actions(entry["id"]), ["created", "approved"])

    def test_reject_is_idempotent_and_removes_lesson_from_fts(self) -> None:
        entry = self.add_entry("Search lifecycle")
        actor = LifecycleActor.owner("42")
        self.lifecycle.approve(entry["id"], actor, mode="test")
        self.assertIn(entry["id"], self.fts_lesson_ids())

        result = self.lifecycle.reject(entry["id"], actor, reason="outdated")
        again = self.lifecycle.reject(entry["id"], actor, reason="outdated")

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertTrue(again.ok)
        self.assertFalse(again.changed)
        self.assertNotIn(entry["id"], self.fts_lesson_ids())
        self.assertEqual(
            self.event_actions(entry["id"]), ["created", "approved", "rejected"]
        )

    def test_request_reanalysis_is_idempotent(self) -> None:
        entry = self.add_entry("Reanalysis request")
        actor = LifecycleActor.owner("42")

        result = self.lifecycle.request_reanalysis(entry["id"], actor)
        again = self.lifecycle.request_reanalysis(entry["id"], actor)

        self.assertTrue(result.ok)
        self.assertTrue(result.changed)
        self.assertTrue(result.lesson["needs_reanalysis"])
        self.assertTrue(again.ok)
        self.assertFalse(again.changed)
        self.assertEqual(
            self.event_actions(entry["id"]), ["created", "reanalysis_requested"]
        )

    def test_batch_rolls_back_when_second_command_fails_after_valid_first(self) -> None:
        first = self.add_entry("First atomic lesson")
        second = self.add_entry("Second atomic lesson")
        actor = LifecycleActor.owner("42")
        with self.database.connect() as connection:
            connection.execute(
                f"""
                CREATE TRIGGER fail_second_lifecycle_event
                BEFORE INSERT ON lesson_events
                WHEN NEW.lesson_id = '{second["id"]}' AND NEW.action = 'approved'
                BEGIN
                    SELECT RAISE(ABORT, 'forced lifecycle failure');
                END
                """
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "forced lifecycle failure"):
            self.lifecycle.apply(
                [
                    LifecycleCommand("approve", first["id"], actor, mode="batch"),
                    LifecycleCommand("approve", second["id"], actor, mode="batch"),
                ]
            )

        self.assertEqual(self.store.get_entry(first["id"])["status"], "pending")
        self.assertEqual(self.store.get_entry(second["id"])["status"], "pending")
        self.assertEqual(self.event_actions(first["id"]), ["created"])
        self.assertEqual(self.event_actions(second["id"]), ["created"])
        self.assertEqual(self.fts_lesson_ids(), [])

    def test_batch_rolls_back_when_second_command_is_forbidden(self) -> None:
        first = self.add_entry("First authorized lesson")
        second = self.add_entry("Second private lesson", owner="99")

        results = self.lifecycle.apply(
            [
                LifecycleCommand(
                    "approve", first["id"], LifecycleActor.owner("42"), mode="batch"
                ),
                LifecycleCommand(
                    "approve", second["id"], LifecycleActor.owner("42"), mode="batch"
                ),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertFalse(any(result.changed for result in results))
        self.assertEqual(results[1].code, "forbidden")
        self.assertEqual(self.store.get_entry(first["id"])["status"], "pending")
        self.assertEqual(self.store.get_entry(second["id"])["status"], "pending")
        self.assertEqual(self.event_actions(first["id"]), ["created"])
        self.assertEqual(self.event_actions(second["id"]), ["created"])
        self.assertEqual(self.fts_lesson_ids(), [])


if __name__ == "__main__":
    unittest.main()
