from __future__ import annotations

import tempfile
import unittest
from os import environ
from pathlib import Path
from unittest.mock import patch

from hermes.db import Database


class KnowledgeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database = Database(Path(self.temp_dir.name) / "hermes.db")
        self.database.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_only_approved_owner_knowledge_is_retrieved(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database)
        pending = store.add_entry(
            title="Pending OpenCode workflow",
            source_url="https://example.com/pending",
            key_lessons=["Pending content must not be retrieved"],
            owner_user_id=42,
        )
        approved = store.add_entry(
            title="OpenCode with 9Router",
            source_url="https://example.com/approved",
            key_lessons=["Route OpenCode through a local model gateway"],
            detail_data={
                "summary": "Connect OpenCode to 9Router on localhost.",
                "evidence": [{"kind": "transcript", "excerpt": "Use the local 9Router endpoint."}],
            },
            owner_user_id=42,
        )
        other_owner = store.add_entry(
            title="Private OpenCode note",
            source_url="https://example.com/private",
            key_lessons=["This belongs to another user"],
            owner_user_id=99,
        )
        store.mark_approved(approved["id"], approved_by="42", approval_mode="test")
        store.mark_approved(other_owner["id"], approved_by="99", approval_mode="test")

        context = store.get_approved_context("OpenCode 9Router", owner_user_id=42)

        self.assertIn("OpenCode with 9Router", context)
        self.assertIn("https://example.com/approved", context)
        self.assertNotIn(pending["title"], context)
        self.assertNotIn(other_owner["title"], context)

    def test_lifecycle_records_events_and_updates_fts(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database)
        entry = store.add_entry(
            title="Agent token optimization",
            source_url="https://example.com/token",
            key_lessons=["Use repository maps to reduce repeated context"],
            owner_user_id=42,
        )
        self.assertEqual(store.get_approved_context("token optimization", owner_user_id=42), "")

        approved = store.mark_approved(entry["id"], approved_by="42", approval_mode="telegram")
        self.assertEqual(approved["status"], "approved")
        self.assertIn("Agent token optimization", store.get_approved_context("token optimization", owner_user_id=42))

        rejected = store.mark_rejected(entry["id"], rejected_by="42", rejection_reason="outdated")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(store.get_approved_context("token optimization", owner_user_id=42), "")

        events = store.list_events(entry["id"])
        self.assertEqual([event["action"] for event in events], ["created", "approved", "rejected"])

    def test_source_deduplication_and_approve_all(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database)
        first = store.add_entry(
            title="First lesson",
            source_url="https://example.com/tutorial?utm_source=test",
            owner_user_id=42,
            allow_multiple_source_lessons=True,
        )
        second = store.add_entry(
            title="Second lesson",
            source_url="https://example.com/tutorial",
            owner_user_id=42,
            allow_multiple_source_lessons=True,
        )

        self.assertEqual(first["source_id"], second["source_id"])
        approved = store.approve_source(first["source_id"], approved_by="42")
        self.assertEqual(approved, 2)
        self.assertEqual(len(store.list_entries(status="approved", owner_user_id=42)), 2)

    def test_reanalysis_replaces_pending_lesson_in_place(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database)
        entry = store.add_entry(title="Needs review", owner_user_id=42)
        flagged = store.mark_needs_reanalysis(
            entry["id"],
            "invalid JSON",
            {"raw_analysis": "Source-bound raw analysis"},
        )
        self.assertTrue(flagged["needs_reanalysis"])

        replaced = store.replace_pending_lesson(
            entry["id"],
            {"title": "Recovered lesson", "key_lessons": ["Recovered from raw analysis"]},
            {"summary": "Recovered summary"},
        )
        self.assertEqual(replaced["id"], entry["id"])
        self.assertFalse(replaced["needs_reanalysis"])
        self.assertEqual(store.get_entry_detail(entry["id"])["summary"], "Recovered summary")

    def test_mark_needs_reanalysis_is_idempotent_and_preserves_detail_updates(
        self,
    ) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database)
        entry = store.add_entry(title="Recoverable malformed lesson", owner_user_id=42)

        first = store.mark_needs_reanalysis(
            entry["id"],
            "invalid JSON",
            {"raw_analysis": "source-bound analysis", "reanalysis_count": 1},
        )
        second = store.mark_needs_reanalysis(
            entry["id"],
            "different retry error",
            {"raw_analysis": "replacement should not apply", "reanalysis_count": 2},
        )

        detail = store.get_entry_detail(entry["id"])
        self.assertTrue(first["needs_reanalysis"])
        self.assertTrue(second["needs_reanalysis"])
        self.assertEqual(detail["validation_error"], "invalid JSON")
        self.assertEqual(detail["raw_analysis"], "source-bound analysis")
        self.assertEqual(detail["reanalysis_count"], 1)
        self.assertEqual(
            [event["action"] for event in store.list_events(entry["id"])],
            ["created", "reanalysis_requested"],
        )

    def test_legacy_factory_selects_sqlite_backend(self) -> None:
        import core.knowledge_store as legacy_module
        from hermes.knowledge import SQLiteKnowledgeStore

        with patch.dict(
            environ,
            {
                "HERMES_STORAGE_BACKEND": "sqlite",
                "HERMES_DB_PATH": str(self.database.path),
            },
        ):
            store = legacy_module.get_store()

        self.assertIsInstance(store, SQLiteKnowledgeStore)

    def test_needs_reanalysis_lesson_cannot_be_approved(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database, default_owner_user_id="42")
        first = store.add_entry(
            title="Malformed one",
            source_url="https://example.com/source",
            owner_user_id="42",
            allow_multiple_source_lessons=True,
        )
        second = store.add_entry(
            title="Valid sibling",
            source_url="https://example.com/source",
            owner_user_id="42",
            allow_multiple_source_lessons=True,
        )
        store.mark_needs_reanalysis(first["id"], "invalid JSON")

        self.assertIsNone(store.mark_approved(first["id"], approved_by="42"))
        self.assertEqual(store.approve_source(first["source_id"], approved_by="42"), 1)
        self.assertEqual(store.get_entry(first["id"])["status"], "pending")
        self.assertEqual(store.get_entry(second["id"])["status"], "approved")

    def test_sqlite_mark_approved_accepts_force_compatibility_argument(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database, default_owner_user_id="42")
        approved_entry = store.add_entry(
            title="Force-compatible approval",
            source_url="https://example.com/force-approved",
            owner_user_id="42",
        )
        duplicate_entry = store.add_entry(
            title="Force-compatible approval",
            source_url="https://example.com/force-pending",
            owner_user_id="42",
        )
        store.mark_approved(
            approved_entry["id"],
            approved_by="42",
            approval_mode="initial",
        )

        warning = store.mark_approved(
            duplicate_entry["id"],
            approved_by="42",
            approval_mode="telegram_command",
        )

        approved = store.mark_approved(
            duplicate_entry["id"],
            approved_by="42",
            approval_mode="force_approve",
            force=True,
        )

        self.assertEqual(warning["status"], "pending")
        self.assertTrue(warning["duplicate_warning"]["has_duplicates"])
        self.assertEqual(approved["status"], "approved")
        self.assertEqual(approved["approval_mode"], "force_approve")

    def test_legacy_transition_methods_preserve_system_caller_compatibility(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore

        store = SQLiteKnowledgeStore(self.database, default_owner_user_id="42")
        entry = store.add_entry(title="GUI-reviewed lesson", owner_user_id="42")

        approved = store.mark_approved(
            entry["id"],
            approved_by="gui_user",
            approval_mode="manual",
        )
        rejected = store.mark_rejected(
            entry["id"],
            rejected_by="gui_user",
            rejection_reason="manual review",
        )

        self.assertEqual(approved["status"], "approved")
        self.assertEqual(rejected["status"], "rejected")
        self.assertEqual(
            [event["action"] for event in store.list_events(entry["id"])],
            ["created", "approved", "rejected"],
        )


if __name__ == "__main__":
    unittest.main()
