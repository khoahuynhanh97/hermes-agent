from __future__ import annotations

import sqlite3


SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS affiliate_run_products (
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    observation_status TEXT NOT NULL DEFAULT 'imported',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    observed_at TEXT NOT NULL,
    PRIMARY KEY(run_id, product_id)
);

CREATE TABLE IF NOT EXISTS affiliate_projection_outbox (
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    projection TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK(status IN ('pending', 'delivered', 'permanent_failure')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts >= 0),
    detail TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    delivered_at TEXT,
    PRIMARY KEY(run_id, projection)
);

CREATE TABLE IF NOT EXISTS affiliate_research_briefs (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK(revision > 0),
    verified_specs_json TEXT NOT NULL DEFAULT '[]',
    strengths_json TEXT NOT NULL DEFAULT '[]',
    limitations_json TEXT NOT NULL DEFAULT '[]',
    unverified_claims_json TEXT NOT NULL DEFAULT '[]',
    reference_patterns_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(owner_user_id, product_id, run_id, revision)
);

INSERT OR IGNORE INTO affiliate_run_products(
    run_id, product_id, observation_status, warnings_json, observed_at
)
SELECT run_id, product_id, 'imported', '[]', created_at
FROM affiliate_content_ideas;

INSERT OR IGNORE INTO affiliate_run_products(
    run_id, product_id, observation_status, warnings_json, observed_at
)
SELECT run_id, product_id, 'imported', '[]', created_at
FROM affiliate_content_packages;

INSERT OR IGNORE INTO affiliate_projection_outbox(
    run_id, projection, owner_user_id, status, attempts, detail, created_at, updated_at
)
SELECT
    id,
    'sheets',
    owner_user_id,
    CASE
        WHEN json_extract(counters_json, '$.projection_failures.sheets.retryable') = 0
            THEN 'permanent_failure'
        ELSE 'pending'
    END,
    0,
    COALESCE(json_extract(counters_json, '$.projection_failures.sheets.detail'), ''),
    updated_at,
    updated_at
FROM affiliate_research_runs
WHERE json_type(counters_json, '$.projection_failures.sheets') = 'object';

INSERT OR IGNORE INTO affiliate_projection_outbox(
    run_id, projection, owner_user_id, status, attempts, detail, created_at, updated_at
)
SELECT
    id,
    'telegram',
    owner_user_id,
    CASE
        WHEN json_extract(counters_json, '$.projection_failures.telegram.retryable') = 0
            THEN 'permanent_failure'
        ELSE 'pending'
    END,
    0,
    COALESCE(json_extract(counters_json, '$.projection_failures.telegram.detail'), ''),
    updated_at,
    updated_at
FROM affiliate_research_runs
WHERE json_type(counters_json, '$.projection_failures.telegram') = 'object';

ALTER TABLE affiliate_references
    ADD COLUMN source_type TEXT NOT NULL DEFAULT 'tiktok_oembed';
ALTER TABLE affiliate_references
    ADD COLUMN content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE affiliate_content_ideas
    ADD COLUMN score REAL NOT NULL DEFAULT 0;
ALTER TABLE affiliate_content_ideas
    ADD COLUMN rank INTEGER NOT NULL DEFAULT 0;
ALTER TABLE affiliate_content_ideas
    ADD COLUMN selected INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1));

CREATE INDEX IF NOT EXISTS idx_affiliate_run_products_run
    ON affiliate_run_products(run_id, product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_projection_pending
    ON affiliate_projection_outbox(status, updated_at);
CREATE INDEX IF NOT EXISTS idx_affiliate_briefs_run
    ON affiliate_research_briefs(run_id, product_id, revision DESC);
"""


def apply_schema_v4(connection: sqlite3.Connection) -> None:
    try:
        connection.executescript(SCHEMA_V4)
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
        _ensure_column(
            connection,
            "affiliate_references",
            "source_type",
            "TEXT NOT NULL DEFAULT 'tiktok_oembed'",
        )
        _ensure_column(
            connection,
            "affiliate_references",
            "content_hash",
            "TEXT NOT NULL DEFAULT ''",
        )
        _ensure_column(
            connection,
            "affiliate_content_ideas",
            "score",
            "REAL NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "affiliate_content_ideas",
            "rank",
            "INTEGER NOT NULL DEFAULT 0",
        )
        _ensure_column(
            connection,
            "affiliate_content_ideas",
            "selected",
            "INTEGER NOT NULL DEFAULT 0 CHECK(selected IN (0, 1))",
        )
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_affiliate_run_products_run
                ON affiliate_run_products(run_id, product_id);
            CREATE INDEX IF NOT EXISTS idx_affiliate_projection_pending
                ON affiliate_projection_outbox(status, updated_at);
            CREATE INDEX IF NOT EXISTS idx_affiliate_briefs_run
                ON affiliate_research_briefs(run_id, product_id, revision DESC);
            """
        )


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
