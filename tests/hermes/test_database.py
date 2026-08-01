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

        self.assertEqual(version, 5)
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

    def test_v2_database_migrates_to_v5_without_losing_existing_data(self) -> None:
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
        self.assertEqual(version, 5)
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

    def test_pre_wave2_v4_upgrades_to_v5_and_backfills_telegram_packages(
        self,
    ) -> None:
        from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
        from hermes.adapters.sqlite.schema_v4 import apply_schema_v4
        from hermes.adapters.sqlite.schema_v5 import apply_schema_v5
        from hermes.db import Database, SCHEMA_V1, SCHEMA_V3

        connection = sqlite3.connect(self.db_path)
        try:
            connection.executescript(SCHEMA_V1)
            apply_schema_v2(connection)
            connection.executescript(SCHEMA_V3)
            apply_schema_v4(connection)
            run_columns = {
                row[1]
                for row in connection.execute(
                    "PRAGMA table_info(affiliate_run_products)"
                )
            }
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            self.assertNotIn("score", run_columns)
            self.assertNotIn("affiliate_projection_items", tables)
            connection.execute(
                """
                INSERT INTO affiliate_products(
                    id, owner_user_id, platform, external_product_id, name,
                    category, price_vnd, sold_count, rating, review_count,
                    commission_rate, shop_name, product_url, image_urls_json,
                    visual_signals_json, source_type, source_url,
                    authorization_scope, rights_status, content_hash,
                    eligibility_status, score, score_json, score_reason,
                    score_confidence, created_at, updated_at
                ) VALUES (
                    'product-1', '42', 'shopee', '101', 'Mouse', 'mouse',
                    300000, 100, 4.8, 20, 0.1, 'Shop',
                    'https://example.test/101', '[]', '[]', 'affiliate_csv',
                    'https://example.test/feed.csv', 'user_export',
                    'affiliate_reference', 'source-hash', 'shortlisted', 82.5,
                    '{"components":{"sales":40}}', 'legacy score', 'high',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO affiliate_research_runs(
                    id, owner_user_id, idempotency_key, status, counters_json,
                    created_at, updated_at, finished_at
                ) VALUES (
                    'run-1', '42', 'key-1', 'completed', '{"packaged":1}',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO affiliate_run_products(
                    run_id, product_id, observation_status, warnings_json,
                    observed_at
                ) VALUES (
                    'run-1', 'product-1', 'imported', '[]',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO affiliate_content_packages(
                    id, owner_user_id, product_id, run_id, revision, status,
                    audience, angle, angle_reason, hook, script,
                    duration_seconds, storyboard_json, ai_prompts_json,
                    voiceover_plan, text_overlays_json, claims_json,
                    warnings_json, asset_rights_json, created_at, updated_at
                ) VALUES (
                    'pkg_legacy', '42', 'product-1', 'run-1', 1,
                    'pending_review', 'office_worker', 'Angle', 'Reason',
                    'Hook', 'Script', 45, '[]', '[]', 'Voice', '[]', '[]',
                    '[]', '{}', '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute(
                """
                INSERT INTO affiliate_projection_outbox(
                    run_id, projection, owner_user_id, status, attempts,
                    detail, created_at, updated_at
                ) VALUES (
                    'run-1', 'telegram', '42', 'pending', 1, 'offline',
                    '2026-08-01T00:00:00+00:00',
                    '2026-08-01T00:00:00+00:00'
                )
                """
            )
            connection.execute("PRAGMA user_version = 4")
            connection.commit()
        finally:
            connection.close()

        database = Database(self.db_path)
        database.initialize()
        with database.connect() as connection:
            apply_schema_v5(connection)
            apply_schema_v5(connection)

        with database.connect() as migrated:
            version = migrated.execute("PRAGMA user_version").fetchone()[0]
            observation = migrated.execute(
                """
                SELECT eligibility_status, score, score_reason,
                       score_confidence, shortlisted
                FROM affiliate_run_products
                WHERE run_id = 'run-1' AND product_id = 'product-1'
                """
            ).fetchone()
            checkpoints = migrated.execute(
                """
                SELECT item_id, status FROM affiliate_projection_items
                WHERE run_id = 'run-1' AND projection = 'telegram'
                """
            ).fetchall()

        self.assertEqual(version, 5)
        self.assertEqual(
            tuple(observation),
            ("shortlisted", 82.5, "legacy score", "high", 1),
        )
        self.assertEqual(
            [tuple(row) for row in checkpoints],
            [("pkg_legacy", "pending")],
        )

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
