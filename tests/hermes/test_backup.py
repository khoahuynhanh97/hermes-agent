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


class FakeOfflineAccessLease:
    def __init__(self, *states: bool):
        self._states = list(states or (True,))
        self.validation_count = 0

    def validate(self) -> bool:
        self.validation_count += 1
        if len(self._states) > 1:
            return self._states.pop(0)
        return self._states[0]

    def close(self) -> None:
        raise AssertionError("BackupManager must not close an external lease")


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

    @staticmethod
    def _logical_database_hash(path: Path) -> str:
        with closing(sqlite3.connect(path)) as connection:
            payload = {
                table: connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                ).fetchall()
                for table in ("sources", "lessons", "lesson_events")
            }
        return hashlib.sha256(
            json.dumps(
                payload,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

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
                    "evidence": 0,
                    "lesson_events": 2,
                    "lesson_fts": 1,
                },
                "sha256": self._sha256(paths[-1]),
                "file_identity": mock.ANY,
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

    def test_hard_link_cleanup_failure_keeps_only_diagnostic_candidate(
        self,
    ) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        self.store.add_entry(title="Candidate only", owner_user_id="42")
        real_unlink = Path.unlink

        def fail_temporary_unlink(
            path: Path,
            *args: object,
            **kwargs: object,
        ) -> None:
            if path.name.endswith(".db.tmp"):
                raise OSError("injected temporary unlink failure")
            real_unlink(path, *args, **kwargs)

        with mock.patch.object(
            Path,
            "unlink",
            autospec=True,
            side_effect=fail_temporary_unlink,
        ):
            with self.assertRaises(BackupOperationError) as raised:
                manager.create_backup(label="unlink-failure")

        self.assertEqual(raised.exception.code, "promotion_cleanup_failed")
        promoted = list((self.root / "backups").glob("*.db"))
        candidates = list((self.root / "backups").glob("*.db.tmp"))
        self.assertEqual(promoted, [])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].stat().st_nlink, 1)
        self.assertTrue(manager.verify(candidates[0])["ok"])

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

    def test_verify_rejects_replacement_between_digest_and_sqlite_open(
        self,
    ) -> None:
        manager = self._backup_manager()
        backup = manager.create_backup(label="snapshot-race")
        replacement = manager.create_backup(label="replacement")
        with closing(sqlite3.connect(replacement)) as connection:
            connection.execute("CREATE TABLE replacement_marker(value TEXT)")
            connection.commit()

        def replace_candidate(boundary: str, candidate: Path) -> None:
            if boundary != "after_digest_before_sqlite":
                return
            candidate.unlink()
            replacement.replace(candidate)

        from hermes.backup import SQLiteBackupManager

        racing_manager = SQLiteBackupManager(
            self.database,
            self.root / "backups",
            verification_hook=replace_candidate,
        )
        verification = racing_manager.verify(backup)

        self.assertFalse(verification["ok"])
        self.assertEqual(
            verification["detail"],
            "backup changed during verification",
        )

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
                    {
                        "lessons": 0,
                        "sources": 0,
                        "evidence": 0,
                        "lesson_events": 0,
                        "lesson_fts": 0,
                    },
                )
                self.assertIn("sha256", verification)
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

    def test_restore_without_offline_lease_refuses_before_mutation(self) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        self.store.add_entry(title="Current DB", owner_user_id="42")
        backup = manager.create_backup(label="restore-source")
        database_hash = self._logical_database_hash(self.database.path)
        backups_before = set((self.root / "backups").iterdir())

        with mock.patch.object(
            manager,
            "create_backup",
            wraps=manager.create_backup,
        ) as create_backup:
            with self.assertRaises(BackupOperationError) as raised:
                manager.restore(backup)

        self.assertEqual(raised.exception.code, "offline_lease_required")
        create_backup.assert_not_called()
        self.assertEqual(
            self._logical_database_hash(self.database.path),
            database_hash,
        )
        self.assertEqual(set((self.root / "backups").iterdir()), backups_before)
        self.assertEqual(
            list(self.database.path.parent.glob("*.restore-*")),
            [],
        )

    def test_restore_rejects_boolean_in_place_of_offline_lease(self) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        backup = manager.create_backup(label="restore-source")
        backups_before = set((self.root / "backups").iterdir())

        with self.assertRaises(BackupOperationError) as raised:
            manager.restore(backup, lease=True)  # type: ignore[arg-type]

        self.assertEqual(raised.exception.code, "offline_lease_required")
        self.assertEqual(set((self.root / "backups").iterdir()), backups_before)

    def test_restore_replaces_database_and_keeps_pre_restore_copy(self) -> None:
        manager = self._backup_manager()
        first = self.store.add_entry(title="Kept lesson", owner_user_id="42")
        backup = manager.create_backup(label="known-good")
        backup_digest = self._sha256(backup)
        backup_mtime = backup.stat().st_mtime_ns
        self.store.delete_entry(first["id"])
        self.assertIsNone(self.store.get_entry(first["id"]))

        lease = FakeOfflineAccessLease()
        result = manager.restore(backup, lease=lease)

        restored_store = SQLiteKnowledgeStore(Database(self.database.path))
        self.assertIsNotNone(restored_store.get_entry(first["id"]))
        self.assertTrue(Path(result["pre_restore_backup"]).exists())
        self.assertEqual(self._sha256(backup), backup_digest)
        self.assertEqual(backup.stat().st_mtime_ns, backup_mtime)
        self.assertGreaterEqual(lease.validation_count, 3)

    def test_restore_into_missing_destination_does_not_require_checkpoint(
        self,
    ) -> None:
        from hermes.backup import SQLiteBackupManager

        manager = self._backup_manager()
        entry = self.store.add_entry(title="Restored new DB", owner_user_id="42")
        backup = manager.create_backup(label="new-destination")
        backup_digest = self._sha256(backup)
        destination = self.root / "new-data" / "hermes.db"
        destination_manager = SQLiteBackupManager(
            Database(destination),
            self.root / "new-destination-backups",
        )

        result = destination_manager.restore(
            backup,
            lease=FakeOfflineAccessLease(),
        )

        restored = SQLiteKnowledgeStore(Database(destination))
        self.assertIsNotNone(restored.get_entry(entry["id"]))
        self.assertEqual(result["pre_restore_backup"], "")
        self.assertEqual(result["rollback_snapshot"], "")
        self.assertEqual(self._sha256(backup), backup_digest)

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
                manager.restore(
                    invalid,
                    lease=FakeOfflineAccessLease(),
                )

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
                manager.restore(
                    self.database.path,
                    lease=FakeOfflineAccessLease(),
                )

        create_backup.assert_not_called()
        self.assertEqual(raised.exception.code, "source_is_destination")
        self.assertEqual(self._sha256(self.database.path), digest_before)

    def _assert_restore_stage_failure_is_atomic(
        self,
        *,
        failing_source_suffix: str,
    ) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        replacement = self.store.add_entry(
            title="Replacement snapshot",
            owner_user_id="42",
        )
        replacement_backup = manager.create_backup(label="replacement")
        self.store.delete_entry(replacement["id"])
        self.store.add_entry(title="Original one", owner_user_id="42")
        self.store.add_entry(title="Original two", owner_user_id="42")
        old_hash = self._logical_database_hash(self.database.path)
        backups_before = set((self.root / "backups").glob("*.db"))
        real_replace = manager._replace_path
        real_create_backup = manager.create_backup
        failure_injected = False

        def create_pre_restore_with_sidecars(label: str = "scheduled") -> Path:
            path = real_create_backup(label)
            if label == "pre-restore":
                Path(f"{self.database.path}-wal").touch()
                Path(f"{self.database.path}-shm").touch()
            return path

        def fail_selected_stage(source: Path, target: Path) -> None:
            nonlocal failure_injected
            if (
                not failure_injected
                and str(source).endswith(failing_source_suffix)
            ):
                failure_injected = True
                raise OSError(f"injected {failing_source_suffix} stage failure")
            real_replace(source, target)

        with mock.patch.object(
            manager,
            "_checkpoint_live_database",
            return_value=None,
        ), mock.patch.object(
            manager,
            "create_backup",
            side_effect=create_pre_restore_with_sidecars,
        ), mock.patch.object(
                manager,
                "_replace_path",
                side_effect=fail_selected_stage,
        ):
            with self.assertRaises(BackupOperationError):
                manager.restore(
                    replacement_backup,
                    lease=FakeOfflineAccessLease(),
                )

        self.assertTrue(failure_injected)
        self.assertEqual(
            self._logical_database_hash(self.database.path),
            old_hash,
        )
        backups_after = set((self.root / "backups").glob("*.db"))
        self.assertTrue(backups_before < backups_after)
        self.assertTrue(replacement_backup.exists())

    def test_restore_wal_stage_failure_preserves_original_logical_database(
        self,
    ) -> None:
        self._assert_restore_stage_failure_is_atomic(
            failing_source_suffix="-wal",
        )

    def test_restore_shm_stage_failure_preserves_original_logical_database(
        self,
    ) -> None:
        self._assert_restore_stage_failure_is_atomic(
            failing_source_suffix="-shm",
        )

    def test_restore_main_replace_failure_rolls_back_original_database(
        self,
    ) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        replacement = self.store.add_entry(
            title="Replacement snapshot",
            owner_user_id="42",
        )
        replacement_backup = manager.create_backup(label="replacement")
        self.store.delete_entry(replacement["id"])
        idle_connection = self.database.connect()
        self.store.add_entry(title="Original one", owner_user_id="42")
        self.store.add_entry(title="Original two", owner_user_id="42")
        old_hash = self._logical_database_hash(self.database.path)
        wal_path = Path(f"{self.database.path}-wal")
        self.assertTrue(wal_path.exists())
        self.assertGreater(wal_path.stat().st_size, 0)
        backups_before = set((self.root / "backups").glob("*.db"))
        real_replace = manager._replace_path
        real_checkpoint = manager._checkpoint_live_database
        failure_injected = False

        def checkpoint_then_release_idle_connection() -> None:
            try:
                real_checkpoint()
            finally:
                idle_connection.close()

        def fail_main_promotion(source: Path, target: Path) -> None:
            nonlocal failure_injected
            if (
                not failure_injected
                and target == self.database.path
                and source.name.endswith(".tmp")
            ):
                failure_injected = True
                raise OSError("injected main replace failure")
            real_replace(source, target)

        try:
            with mock.patch.object(
                manager,
                "_checkpoint_live_database",
                side_effect=checkpoint_then_release_idle_connection,
            ), mock.patch.object(
                manager,
                "_replace_path",
                side_effect=fail_main_promotion,
            ):
                with self.assertRaises(BackupOperationError):
                    manager.restore(
                        replacement_backup,
                        lease=FakeOfflineAccessLease(),
                    )
        finally:
            idle_connection.close()

        self.assertTrue(failure_injected)
        self.assertEqual(
            self._logical_database_hash(self.database.path),
            old_hash,
        )
        backups_after = set((self.root / "backups").glob("*.db"))
        self.assertTrue(backups_before < backups_after)
        self.assertTrue(replacement_backup.exists())

    def test_revoked_lease_refuses_immediately_before_live_staging(self) -> None:
        from hermes.backup import BackupOperationError

        manager = self._backup_manager()
        replacement = self.store.add_entry(
            title="Replacement snapshot",
            owner_user_id="42",
        )
        replacement_backup = manager.create_backup(label="replacement")
        self.store.delete_entry(replacement["id"])
        self.store.add_entry(title="Original snapshot", owner_user_id="42")
        old_hash = self._logical_database_hash(self.database.path)
        backups_before = set((self.root / "backups").glob("*.db"))
        lease = FakeOfflineAccessLease(True, False)

        with mock.patch.object(
            manager,
            "_stage_live_database",
            wraps=manager._stage_live_database,
        ) as stage:
            with self.assertRaises(BackupOperationError) as raised:
                manager.restore(replacement_backup, lease=lease)

        self.assertEqual(raised.exception.code, "offline_lease_revoked")
        stage.assert_not_called()
        self.assertEqual(
            self._logical_database_hash(self.database.path),
            old_hash,
        )
        self.assertTrue(
            backups_before < set((self.root / "backups").glob("*.db"))
        )
        self.assertEqual(
            list(self.database.path.parent.glob("*.restore-rollback-*")),
            [],
        )

    def test_offline_lease_documents_concurrent_writer_contract(self) -> None:
        import inspect

        from hermes.backup import OfflineAccessLease

        contract = inspect.getdoc(OfflineAccessLease) or ""
        self.assertIn("concurrent writers", contract)
        self.assertIn("entire restore", contract)

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

    def test_cli_restore_refuses_boolean_confirmation_without_real_lease(
        self,
    ) -> None:
        from scripts import hermes_backup as backup_cli

        source = self.root / "restore-source.db"
        output = io.StringIO()

        with mock.patch.object(
            backup_cli,
            "SQLiteBackupManager",
        ) as manager_type, redirect_stdout(output):
            exit_code = backup_cli.main(
                ["restore", str(source), "--confirm"]
            )

        manager_type.assert_not_called()
        self.assertEqual(exit_code, 2)
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "ok": False,
                "operation": "restore",
                "code": "offline_lease_unavailable",
                "path": str(source.resolve()),
                "detail": (
                    "restore requires an offline access lease from "
                    "the process controller"
                ),
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
