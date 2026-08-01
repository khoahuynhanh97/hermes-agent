from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path


class DatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "hermes.db"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_initialize_creates_core_schema_and_fts(self) -> None:
        from hermes.db import Database

        database = Database(self.db_path)
        database.initialize()

        with database.connect() as connection:
            objects = {
                row[0]: row[1]
                for row in connection.execute(
                    "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view')"
                )
            }
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]

        expected = {
            "schema_migrations",
            "sources",
            "artifacts",
            "evidence",
            "lessons",
            "lesson_events",
            "messages",
            "memories",
            "memory_events",
            "jobs",
            "lesson_fts",
        }
        self.assertTrue(expected.issubset(objects))
        self.assertEqual(journal_mode.lower(), "wal")
        self.assertEqual(foreign_keys, 1)

    def test_initialize_creates_affiliate_schema(self) -> None:
        from hermes.db import Database

        database = Database(self.db_path)
        database.initialize()

        with database.connect() as connection:
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            version = connection.execute("PRAGMA user_version").fetchone()[0]

        self.assertEqual(version, 4)
        self.assertTrue(
            {
                "affiliate_products",
                "affiliate_product_snapshots",
                "affiliate_references",
                "affiliate_content_ideas",
                "affiliate_content_packages",
                "affiliate_approval_events",
                "affiliate_research_runs",
            }.issubset(names)
        )

    def test_v2_database_migrates_to_v4_without_losing_existing_data(self) -> None:
        from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
        from hermes.db import Database, SCHEMA_V1

        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(SCHEMA_V1)
            apply_schema_v2(connection)
            connection.execute(
                """
                INSERT INTO sources(
                    id, owner_user_id, source_type, source_key, confidence,
                    acquisition_status, metadata_json, created_at, updated_at
                ) VALUES ('source-1', '42', 'text', 'source:one', 'high', 'ready', '{}',
                          '2026-08-01T00:00:00+00:00', '2026-08-01T00:00:00+00:00')
                """
            )
            connection.execute("PRAGMA user_version = 2")
            connection.commit()
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            connection.close()
        self.assertNotIn("affiliate_products", names)

        database = Database(self.db_path)
        database.initialize()

        with database.connect() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            source = connection.execute("SELECT id FROM sources").fetchone()[0]
        self.assertEqual(version, 4)
        self.assertEqual(source, "source-1")

    def test_v3_projection_failure_is_backfilled_into_v4_outbox(self) -> None:
        from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
        from hermes.db import Database, SCHEMA_V1, SCHEMA_V3

        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(SCHEMA_V1)
            apply_schema_v2(connection)
            connection.executescript(SCHEMA_V3)
            connection.execute(
                """
                INSERT INTO affiliate_research_runs(
                    id, owner_user_id, idempotency_key, status, counters_json,
                    created_at, updated_at, finished_at
                ) VALUES (
                    'run-1', '42', 'key-1', 'completed',
                    '{"projection_failures":{"sheets":{"detail":"offline","retryable":true}}}',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute("PRAGMA user_version = 3")
            connection.commit()
        finally:
            connection.close()

        database = Database(self.db_path)
        database.initialize()

        with database.connect() as migrated:
            outbox = migrated.execute(
                """
                SELECT projection, status, detail
                FROM affiliate_projection_outbox
                WHERE run_id = 'run-1'
                """
            ).fetchone()
        self.assertEqual(tuple(outbox), ("sheets", "pending", "offline"))

    def test_foreign_keys_reject_orphan_evidence(self) -> None:
        from hermes.db import Database

        database = Database(self.db_path)
        database.initialize()

        with self.assertRaises(sqlite3.IntegrityError):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO evidence(id, source_id, kind, created_at)
                    VALUES ('ev-1', 'missing-source', 'transcript', '2026-01-01T00:00:00Z')
                    """
                )

    def test_transaction_rolls_back_on_error(self) -> None:
        from hermes.db import Database

        database = Database(self.db_path)
        database.initialize()

        with self.assertRaises(RuntimeError):
            with database.transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO sources(
                        id, owner_user_id, source_type, source_key,
                        confidence, acquisition_status, metadata_json,
                        created_at, updated_at
                    ) VALUES ('source-1', '42', 'text', 'text:one',
                              'high', 'ready', '{}',
                              '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                    """
                )
                raise RuntimeError("force rollback")

        with database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        self.assertEqual(count, 0)

    def test_immediate_transaction_commits(self) -> None:
        from hermes.db import Database

        database = Database(self.db_path)
        database.initialize()

        with database.transaction(immediate=True) as connection:
            connection.execute(
                """
                INSERT INTO sources(
                    id, owner_user_id, source_type, source_key,
                    confidence, acquisition_status, metadata_json,
                    created_at, updated_at
                ) VALUES ('source-1', '42', 'text', 'text:one',
                          'high', 'ready', '{}',
                          '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')
                """
            )

        with database.connect() as connection:
            count = connection.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
