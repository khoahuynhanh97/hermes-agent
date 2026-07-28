from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

from hermes.db import SCHEMA_VERSION, Database
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

    @staticmethod
    def _sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _backup_manager(self, *, keep: int = 14):
        from hermes.backup import SQLiteBackupManager

        return SQLiteBackupManager(
            self.database,
            self.root / "backups",
            keep=keep,
        )

    def test_backup_is_consistent_and_retention_is_bounded(self) -> None:
        entry = self.store.add_entry(title="Backup lesson", owner_user_id="42")
        self.store.mark_approved(entry["id"], approved_by="42")
        manager = self._backup_manager(keep=2)

        paths = [manager.create_backup(label=f"test-{index}") for index in range(3)]

        verification = manager.verify(paths[-1])
        self.assertEqual(
            verification,
            {
                "ok": True,
                "path": str(paths[-1]),
                "integrity": "ok",
                "foreign_key_violations": 0,
                "schema_version": SCHEMA_VERSION,
                "required_tables_missing": [],
                "counts": {
                    "lessons": 1,
                    "sources": 1,
                    "lesson_events": 2,
                },
                "detail": "ok",
            },
        )
        self.assertFalse(paths[0].exists())
        self.assertEqual(len(list((self.root / "backups").glob("*.db"))), 2)
        sidecars = [
            path.name
            for path in (self.root / "backups").iterdir()
            if path.name.endswith(("-wal", "-shm"))
        ]
        self.assertEqual(sidecars, [])

    def test_backup_includes_committed_wal_rows(self) -> None:
        manager = self._backup_manager()
        reader = self.database.connect()
        try:
            reader.execute("BEGIN")
            reader.execute("SELECT COUNT(*) FROM lessons").fetchone()
            entry = self.store.add_entry(
                title="Committed WAL lesson",
                owner_user_id="42",
            )
            self.assertTrue(Path(f"{self.database.path}-wal").exists())

            backup = manager.create_backup(label="wal")
        finally:
            reader.close()

        with closing(sqlite3.connect(backup)) as connection:
            row = connection.execute(
                "SELECT title FROM lessons WHERE id = ?",
                (entry["id"],),
            ).fetchone()
        self.assertEqual(row, ("Committed WAL lesson",))

    def test_verify_reopens_immutable_read_only_without_mutating_backup(self) -> None:
        manager = self._backup_manager()
        backup = manager.create_backup(label="read-only")
        digest_before = self._sha256(backup)
        mtime_before = backup.stat().st_mtime_ns

        with mock.patch(
            "hermes.backup.sqlite3.connect",
            wraps=sqlite3.connect,
        ) as connect:
            verification = manager.verify(backup)

        self.assertTrue(verification["ok"])
        uri = str(connect.call_args.args[0])
        self.assertIn("mode=ro", uri)
        self.assertIn("immutable=1", uri)
        self.assertEqual(self._sha256(backup), digest_before)
        self.assertEqual(backup.stat().st_mtime_ns, mtime_before)

    def test_verify_reports_missing_required_table_with_exact_type_check(self) -> None:
        manager = self._backup_manager()
        backup = manager.create_backup(label="missing-table")
        with closing(sqlite3.connect(backup)) as connection:
            connection.execute("DROP TABLE lesson_events")
            connection.execute("CREATE VIEW lesson_events AS SELECT 1 AS id")
            connection.commit()

        verification = manager.verify(backup)

        self.assertFalse(verification["ok"])
        self.assertIn("lesson_events", verification["required_tables_missing"])
        self.assertEqual(verification["schema_version"], SCHEMA_VERSION)
        self.assertEqual(verification["counts"]["lesson_events"], 0)

    def test_verify_reports_foreign_key_violations(self) -> None:
        manager = self._backup_manager()
        backup = manager.create_backup(label="fk-violation")
        with closing(sqlite3.connect(backup)) as connection:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                """
                INSERT INTO lesson_events(
                    lesson_id, action, actor_user_id, note,
                    metadata_json, created_at
                ) VALUES ('missing', 'approved', '', '', '{}',
                          '2026-07-29T00:00:00+00:00')
                """
            )
            connection.commit()

        verification = manager.verify(backup)

        self.assertFalse(verification["ok"])
        self.assertEqual(verification["integrity"], "ok")
        self.assertEqual(verification["foreign_key_violations"], 1)

    def test_verify_returns_structured_failure_for_missing_and_corrupt_files(self) -> None:
        manager = self._backup_manager()
        missing = self.root / "missing.db"
        corrupt = self.root / "corrupt.db"
        corrupt.write_bytes(b"not a sqlite database")

        for candidate in (missing, corrupt):
            with self.subTest(candidate=candidate.name):
                verification = manager.verify(candidate)
                self.assertFalse(verification["ok"])
                self.assertEqual(verification["path"], str(candidate.resolve()))
                self.assertIn("integrity", verification)
                self.assertIn("foreign_key_violations", verification)
                self.assertIn("schema_version", verification)
                self.assertIn("required_tables_missing", verification)
                self.assertEqual(
                    verification["counts"],
                    {"lessons": 0, "sources": 0, "lesson_events": 0},
                )
                self.assertTrue(verification["detail"])

    def test_verify_rejects_unsupported_schema_version(self) -> None:
        manager = self._backup_manager()
        backup = manager.create_backup(label="wrong-version")
        with closing(sqlite3.connect(backup)) as connection:
            connection.execute("PRAGMA user_version = 999")
            connection.commit()

        verification = manager.verify(backup)

        self.assertFalse(verification["ok"])
        self.assertEqual(verification["schema_version"], 999)
        self.assertEqual(verification["required_tables_missing"], [])

    def test_failed_candidate_is_kept_and_existing_backups_are_not_pruned(self) -> None:
        manager = self._backup_manager(keep=2)
        existing = [
            manager.create_backup(label=f"good-{index}")
            for index in range(2)
        ]
        failed = {
            "ok": False,
            "path": "",
            "integrity": "error",
            "foreign_key_violations": 0,
            "schema_version": 0,
            "required_tables_missing": [],
            "counts": {"lessons": 0, "sources": 0, "lesson_events": 0},
            "detail": "injected verification failure",
        }

        with mock.patch.object(manager, "verify", return_value=failed):
            with self.assertRaises(RuntimeError):
                manager.create_backup(label="failed")

        self.assertTrue(all(path.exists() for path in existing))
        self.assertEqual(
            sorted((self.root / "backups").glob("hermes-*.db")),
            sorted(existing),
        )
        failed_candidates = list(
            (self.root / "backups").glob("hermes-*.db.tmp")
        )
        self.assertEqual(len(failed_candidates), 1)
        self.assertGreater(failed_candidates[0].stat().st_size, 0)

    def test_restore_replaces_database_and_keeps_pre_restore_copy(self) -> None:
        manager = self._backup_manager()
        first = self.store.add_entry(title="Kept lesson", owner_user_id="42")
        backup = manager.create_backup(label="known-good")
        self.store.delete_entry(first["id"])
        self.assertIsNone(self.store.get_entry(first["id"]))

        result = manager.restore(backup)

        restored_store = SQLiteKnowledgeStore(Database(self.database.path))
        self.assertIsNotNone(restored_store.get_entry(first["id"]))
        self.assertTrue(Path(result["pre_restore_backup"]).exists())

    def test_export_contains_lifecycle_and_no_environment_secrets(self) -> None:
        entry = self.store.add_entry(title="Export lesson", owner_user_id="42")
        self.store.mark_rejected(entry["id"], rejected_by="42", rejection_reason="duplicate")

        export_path = self._backup_manager().export_json()
        payload = json.loads(export_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["lessons"][0]["status"], "rejected")
        self.assertTrue(payload["lesson_events"])
        self.assertNotIn("api_key", export_path.read_text(encoding="utf-8").lower())


if __name__ == "__main__":
    unittest.main()
