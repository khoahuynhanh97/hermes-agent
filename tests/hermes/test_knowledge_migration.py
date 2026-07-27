from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hermes.db import Database


class KnowledgeMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.legacy_root = self.root / "legacy"
        (self.legacy_root / "entries").mkdir(parents=True)
        self.database = Database(self.root / "hermes.db")
        self.database.initialize()

        entries = [
            {
                "id": "kb-approved",
                "slug": "approved-lesson",
                "source_url": "https://example.com/approved",
                "platform": "website",
                "category": "technology",
                "status": "approved",
                "learned_at": "2026-01-01T00:00:00",
                "approved_at": "2026-01-02T00:00:00",
                "approved_by": "42",
                "approval_mode": "telegram",
                "approval_history": [
                    {"status": "approved", "at": "2026-01-02T00:00:00", "actor": "42", "mode": "telegram"}
                ],
                "title": "Approved lesson",
                "key_lessons": ["Approved knowledge"],
                "detail_file": "entries/kb-approved.json",
            },
            {
                "id": "kb-pending",
                "slug": "pending-lesson",
                "source_url": "https://example.com/pending",
                "platform": "website",
                "category": "general",
                "status": "pending",
                "learned_at": "2026-01-03T00:00:00",
                "title": "Pending lesson",
                "key_lessons": ["Pending knowledge"],
                "needs_reanalysis": True,
                "detail_file": "entries/kb-pending.json",
            },
            {
                "id": "kb-rejected",
                "slug": "rejected-lesson",
                "source_url": "https://example.com/rejected",
                "platform": "website",
                "category": "general",
                "status": "rejected",
                "learned_at": "2026-01-04T00:00:00",
                "rejected_at": "2026-01-05T00:00:00",
                "rejected_by": "42",
                "rejection_reason": "not useful",
                "approval_history": [
                    {"status": "rejected", "at": "2026-01-05T00:00:00", "actor": "42", "reason": "not useful"}
                ],
                "title": "Rejected lesson",
                "key_lessons": ["Rejected knowledge"],
                "detail_file": "entries/kb-rejected.json",
            },
        ]
        (self.legacy_root / "unified_index.json").write_text(
            json.dumps({"version": 2, "entries": entries}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.legacy_root / "entries" / "kb-approved.json").write_text(
            json.dumps({**entries[0], "detail": {"summary": "Approved summary"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.legacy_root / "entries" / "kb-pending.json").write_text(
            json.dumps({**entries[1], "detail": {"raw_analysis": "Raw source analysis"}}, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.legacy_root / "entries" / "kb-rejected.json").write_text("{malformed", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dry_run_does_not_write_and_real_import_is_idempotent(self) -> None:
        from hermes.knowledge import SQLiteKnowledgeStore
        from hermes.migration import migrate_legacy_knowledge

        dry_run = migrate_legacy_knowledge(
            self.legacy_root,
            self.database,
            default_owner_user_id="42",
            dry_run=True,
        )
        self.assertEqual(dry_run.total, 3)
        self.assertEqual(dry_run.by_status, {"approved": 1, "pending": 1, "rejected": 1})
        self.assertEqual(len(SQLiteKnowledgeStore(self.database).list_entries()), 0)

        imported = migrate_legacy_knowledge(
            self.legacy_root,
            self.database,
            default_owner_user_id="42",
            dry_run=False,
        )
        repeated = migrate_legacy_knowledge(
            self.legacy_root,
            self.database,
            default_owner_user_id="42",
            dry_run=False,
        )

        store = SQLiteKnowledgeStore(self.database)
        self.assertEqual(imported.imported, 3)
        self.assertEqual(repeated.imported, 0)
        self.assertEqual(repeated.skipped, 3)
        self.assertEqual(len(store.list_entries()), 3)
        self.assertEqual(store.get_entry("kb-approved")["status"], "approved")
        self.assertEqual(store.get_entry_detail("kb-approved")["summary"], "Approved summary")
        self.assertTrue(store.get_entry("kb-pending")["needs_reanalysis"])
        self.assertIn("kb-rejected", imported.malformed_details)
        self.assertEqual(
            [event["action"] for event in store.list_events("kb-rejected")],
            ["rejected"],
        )


if __name__ == "__main__":
    unittest.main()
