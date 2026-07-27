from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hermes.db import Database
from hermes.knowledge import SQLiteKnowledgeStore


class BackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.database = Database(self.root / "data" / "hermes.db")
        self.database.initialize()
        self.store = SQLiteKnowledgeStore(self.database)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_backup_is_consistent_and_retention_is_bounded(self) -> None:
        from hermes.backup import SQLiteBackupManager

        entry = self.store.add_entry(title="Backup lesson", owner_user_id="42")
        self.store.mark_approved(entry["id"], approved_by="42")
        manager = SQLiteBackupManager(self.database, self.root / "backups", keep=2)

        paths = [manager.create_backup(label=f"test-{index}") for index in range(3)]

        self.assertTrue(manager.verify(paths[-1])["ok"])
        self.assertFalse(paths[0].exists())
        self.assertEqual(len(list((self.root / "backups").glob("*.db"))), 2)
        sidecars = [
            path.name
            for path in (self.root / "backups").iterdir()
            if path.name.endswith(("-wal", "-shm"))
        ]
        self.assertEqual(sidecars, [])

    def test_restore_replaces_database_and_keeps_pre_restore_copy(self) -> None:
        from hermes.backup import SQLiteBackupManager

        manager = SQLiteBackupManager(self.database, self.root / "backups")
        first = self.store.add_entry(title="Kept lesson", owner_user_id="42")
        backup = manager.create_backup(label="known-good")
        self.store.delete_entry(first["id"])
        self.assertIsNone(self.store.get_entry(first["id"]))

        result = manager.restore(backup)

        restored_store = SQLiteKnowledgeStore(Database(self.database.path))
        self.assertIsNotNone(restored_store.get_entry(first["id"]))
        self.assertTrue(Path(result["pre_restore_backup"]).exists())

    def test_export_contains_lifecycle_and_no_environment_secrets(self) -> None:
        from hermes.backup import SQLiteBackupManager

        entry = self.store.add_entry(title="Export lesson", owner_user_id="42")
        self.store.mark_rejected(entry["id"], rejected_by="42", rejection_reason="duplicate")

        export_path = SQLiteBackupManager(self.database, self.root / "backups").export_json()
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["lessons"][0]["status"], "rejected")
        self.assertTrue(payload["lesson_events"])
        self.assertNotIn("api_key", export_path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
