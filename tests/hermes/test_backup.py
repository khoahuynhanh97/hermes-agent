from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stdout
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

    def test_backup_is_consistent_and_never_prunes_automatically(self) -> None:
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
        self.assertTrue(all(path.exists() for path in paths))
        self.assertEqual(len(list((self.root / "backups").glob("*.db"))), 3)
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

    def test_backup_refuses_missing_source_without_creating_database(self) -> None:
        from hermes.backup import BackupOperationError, SQLiteBackupManager

        source = self.root / "missing" / "hermes.db"
        manager = SQLiteBackupManager(
            Database(source),
            self.root / "missing-source-backups",
        )

        with self.assertRaises(BackupOperationError) as raised:
            manager.create_backup(label="missing")

        self.assertFalse(source.exists())
        self.assertEqual(
            raised.exception.to_payload(),
            {
                "ok": False,
                "operation": "backup",
                "code": "invalid_source",
                "path": str(source.resolve()),
                "detail": "backup source is invalid",
            },
        )
        self.assertEqual(
            list((self.root / "missing-source-backups").glob("*.db*")),
            [],
        )

    def test_backup_refuses_corrupt_source_without_mutating_it(self) -> None:
        from hermes.backup import BackupOperationError, SQLiteBackupManager

        source = self.root / "corrupt-source.db"
        source.write_bytes(b"not a sqlite database")
        digest_before = self._sha256(source)
        mtime_before = source.stat().st_mtime_ns
        manager = SQLiteBackupManager(
            Database(source),
            self.root / "corrupt-source-backups",
        )

        with self.assertRaises(BackupOperationError):
            manager.create_backup(label="corrupt")

        self.assertEqual(self._sha256(source), digest_before)
        self.assertEqual(source.stat().st_mtime_ns, mtime_before)
        self.assertEqual(
            list((self.root / "corrupt-source-backups").glob("*.db*")),
            [],
        )

    def test_backup_paths_with_reserved_uri_characters_are_supported(self) -> None:
        special_root = self.root / "space % # dữ liệu"
        database = Database(special_root / "Hermes data.db")
        database.initialize()
        store = SQLiteKnowledgeStore(database)
        entry = store.add_entry(title="Unicode path", owner_user_id="42")
        manager = self._backup_manager()
        manager = type(manager)(
            database,
            special_root / "backup % # dữ liệu",
        )

        backup = manager.create_backup(label="uri")
        verification = manager.verify(backup)

        self.assertTrue(verification["ok"])
        with closing(sqlite3.connect(backup)) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT title FROM lessons WHERE id = ?",
                    (entry["id"],),
                ).fetchone(),
                ("Unicode path",),
            )

    def test_fixed_timestamp_collision_never_overwrites_existing_backup(self) -> None:
        manager = self._backup_manager()
        self.store.add_entry(title="First snapshot", owner_user_id="42")

        with mock.patch(
            "hermes.backup._timestamp",
            return_value="20260729T000000000000Z",
        ):
            first = manager.create_backup(label="collision")
            first_digest = self._sha256(first)
            self.store.add_entry(title="Second snapshot", owner_user_id="42")
            second = manager.create_backup(label="collision")

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists())
        self.assertTrue(second.exists())
        self.assertEqual(self._sha256(first), first_digest)
        with closing(sqlite3.connect(first)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
                1,
            )
        with closing(sqlite3.connect(second)) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
                2,
            )

    def test_exact_name_collision_preserves_old_backup_and_new_candidate(
        self,
    ) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        self.store.add_entry(title="First snapshot", owner_user_id="42")

        with mock.patch(
            "hermes.backup._timestamp",
            return_value="20260729T000000000000Z",
        ), mock.patch(
            "hermes.backup.secrets.token_hex",
            return_value="fixed-token",
        ):
            first = manager.create_backup(label="collision")
            first_digest = self._sha256(first)
            self.store.add_entry(title="Second snapshot", owner_user_id="42")
            with self.assertRaises(BackupOperationError) as raised:
                manager.create_backup(label="collision")

        self.assertEqual(raised.exception.code, "promotion_failed")
        self.assertEqual(self._sha256(first), first_digest)
        candidates = list((self.root / "backups").glob("*.db.tmp"))
        self.assertEqual(len(candidates), 1)
        with closing(sqlite3.connect(candidates[0])) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM lessons").fetchone()[0],
                2,
            )

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
        backup_digest = self._sha256(backup)
        backup_mtime = backup.stat().st_mtime_ns
        self.store.delete_entry(first["id"])
        self.assertIsNone(self.store.get_entry(first["id"]))

        result = manager.restore(backup)

        restored_store = SQLiteKnowledgeStore(Database(self.database.path))
        self.assertIsNotNone(restored_store.get_entry(first["id"]))
        self.assertTrue(Path(result["pre_restore_backup"]).exists())
        self.assertEqual(self._sha256(backup), backup_digest)
        self.assertEqual(backup.stat().st_mtime_ns, backup_mtime)

    def test_restore_rejects_invalid_source_before_pre_restore_snapshot(self) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        invalid = self.root / "invalid-restore.db"
        invalid.write_bytes(b"corrupt")
        digest_before = self._sha256(invalid)

        with mock.patch.object(
            manager,
            "create_backup",
            wraps=manager.create_backup,
        ) as create_backup:
            with self.assertRaises(BackupOperationError):
                manager.restore(invalid)

        create_backup.assert_not_called()
        self.assertEqual(self._sha256(invalid), digest_before)
        self.assertEqual(list((self.root / "backups").glob("*.db*")), [])

    def test_restore_refuses_source_that_is_the_live_destination(self) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        self.store.add_entry(title="Live source", owner_user_id="42")
        digest_before = self._sha256(self.database.path)

        with mock.patch.object(
            manager,
            "create_backup",
            wraps=manager.create_backup,
        ) as create_backup:
            with self.assertRaises(BackupOperationError) as raised:
                manager.restore(self.database.path)

        create_backup.assert_not_called()
        self.assertEqual(raised.exception.code, "source_is_destination")
        self.assertEqual(self._sha256(self.database.path), digest_before)

    def test_cli_returns_allowlisted_json_for_expected_failure(self) -> None:
        from hermes.backup import BackupOperationError
        from scripts import hermes_backup as backup_cli

        intended_path = self.root / "missing.db"
        manager = mock.Mock()
        manager.create_backup.side_effect = BackupOperationError(
            operation="backup",
            code="invalid_source",
            path=intended_path,
            detail="backup source is invalid",
        )
        output = io.StringIO()

        with mock.patch.object(
            backup_cli,
            "SQLiteBackupManager",
            return_value=manager,
        ), redirect_stdout(output):
            exit_code = backup_cli.main(["backup"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "ok": False,
                "operation": "backup",
                "code": "invalid_source",
                "path": str(intended_path.resolve()),
                "detail": "backup source is invalid",
            },
        )

    def test_cli_does_not_trust_expected_error_detail(self) -> None:
        from hermes.backup import BackupOperationError
        from scripts import hermes_backup as backup_cli

        intended_path = self.root / "missing.db"
        manager = mock.Mock()
        manager.create_backup.side_effect = BackupOperationError(
            operation="backup",
            code="invalid_source",
            path=intended_path,
            detail="API_KEY=super-secret",
        )
        output = io.StringIO()

        with mock.patch.object(
            backup_cli,
            "SQLiteBackupManager",
            return_value=manager,
        ), redirect_stdout(output):
            exit_code = backup_cli.main(["backup"])

        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue())["detail"],
            "backup source is invalid",
        )
        self.assertNotIn("super-secret", output.getvalue())

    def test_cli_redacts_unexpected_failure_and_exits_nonzero(self) -> None:
        from scripts import hermes_backup as backup_cli

        intended_path = self.root / "candidate.db"
        manager = mock.Mock()
        manager.verify.side_effect = RuntimeError(
            "API_KEY=super-secret; database bytes follow"
        )
        output = io.StringIO()

        with mock.patch.object(
            backup_cli,
            "SQLiteBackupManager",
            return_value=manager,
        ), redirect_stdout(output):
            exit_code = backup_cli.main(["verify", str(intended_path)])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 3)
        self.assertEqual(
            payload,
            {
                "ok": False,
                "operation": "verify",
                "code": "unexpected_error",
                "path": str(intended_path.resolve()),
                "detail": "verify failed",
            },
        )
        self.assertNotIn("super-secret", output.getvalue())

    def test_cli_redacts_manager_construction_failure(self) -> None:
        from scripts import hermes_backup as backup_cli

        intended_path = self.root / "candidate.db"
        output = io.StringIO()

        with mock.patch.object(
            backup_cli,
            "SQLiteBackupManager",
            side_effect=RuntimeError("TOKEN=constructor-secret"),
        ), redirect_stdout(output):
            exit_code = backup_cli.main(["verify", str(intended_path)])

        self.assertEqual(exit_code, 3)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "ok": False,
                "operation": "verify",
                "code": "unexpected_error",
                "path": str(intended_path.resolve()),
                "detail": "verify failed",
            },
        )
        self.assertNotIn("constructor-secret", output.getvalue())

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
