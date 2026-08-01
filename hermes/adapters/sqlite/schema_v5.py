from __future__ import annotations

import sqlite3


_PROJECTION_ITEMS_SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliate_projection_items (
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    projection TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'delivered')),
    external_message_id TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT,
    PRIMARY KEY(run_id, projection, item_id),
    FOREIGN KEY(run_id, projection)
        REFERENCES affiliate_projection_outbox(run_id, projection)
        ON DELETE CASCADE
);
"""

_V5_BACKFILLS = """
UPDATE affiliate_run_products
SET
    eligibility_status = COALESCE(
        (SELECT eligibility_status FROM affiliate_products
         WHERE affiliate_products.id = affiliate_run_products.product_id),
        'candidate'
    ),
    score = (
        SELECT score FROM affiliate_products
        WHERE affiliate_products.id = affiliate_run_products.product_id
    ),
    score_json = COALESCE(
        (SELECT score_json FROM affiliate_products
         WHERE affiliate_products.id = affiliate_run_products.product_id),
        '{}'
    ),
    score_reason = COALESCE(
        (SELECT score_reason FROM affiliate_products
         WHERE affiliate_products.id = affiliate_run_products.product_id),
        ''
    ),
    score_confidence = COALESCE(
        (SELECT score_confidence FROM affiliate_products
         WHERE affiliate_products.id = affiliate_run_products.product_id),
        'low'
    ),
    shortlisted = CASE
        WHEN (SELECT eligibility_status FROM affiliate_products
              WHERE affiliate_products.id = affiliate_run_products.product_id)
             = 'shortlisted'
        THEN 1 ELSE 0
    END
WHERE score IS NULL AND eligibility_status = 'candidate';

INSERT OR IGNORE INTO affiliate_projection_items(
    run_id, projection, item_id, status, external_message_id, attempts,
    created_at, updated_at
)
SELECT
    outbox.run_id,
    'telegram',
    package.id,
    'pending',
    '',
    0,
    outbox.created_at,
    outbox.updated_at
FROM affiliate_projection_outbox AS outbox
JOIN affiliate_content_packages AS package
  ON package.run_id = outbox.run_id
WHERE outbox.projection = 'telegram'
  AND outbox.status = 'pending'
  AND package.status = 'pending_review';

CREATE INDEX IF NOT EXISTS idx_affiliate_projection_items_pending
    ON affiliate_projection_items(run_id, projection, status, updated_at);
"""


def apply_schema_v5(connection: sqlite3.Connection) -> None:
    """Apply Wave-2 persistence after the immutable V4 release."""
    connection.executescript(_PROJECTION_ITEMS_SCHEMA)
    for column, declaration in (
        ("eligibility_status", "TEXT NOT NULL DEFAULT 'candidate'"),
        ("score", "REAL"),
        ("score_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("score_reason", "TEXT NOT NULL DEFAULT ''"),
        ("score_confidence", "TEXT NOT NULL DEFAULT 'low'"),
        ("rank", "INTEGER"),
        (
            "shortlisted",
            "INTEGER NOT NULL DEFAULT 0 CHECK(shortlisted IN (0, 1))",
        ),
        ("evidence_ids_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("snapshot_timestamps_json", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        _ensure_column(
            connection,
            "affiliate_run_products",
            column,
            declaration,
        )
    _ensure_column(
        connection,
        "affiliate_research_briefs",
        "reference_pattern_provenance_json",
        "TEXT NOT NULL DEFAULT '[]'",
    )
    connection.executescript(_V5_BACKFILLS)


def _ensure_column(
    connection: sqlite3.Connection,
    table: str,
    column: str,
    declaration: str,
) -> None:
    columns = {
        str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")
    }
    if column not in columns:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} {declaration}"
        )
