"""SQLite schema V7: additive persistence for ``AffiliateAnalysis``.

Mirrors the spec's Layer-3 output without disturbing any table
introduced by schema v1..v6. Idempotent; safe to re-apply on a
database already at user_version=6 or higher.
"""

import sqlite3

SCHEMA_V7 = """
CREATE TABLE IF NOT EXISTS affiliate_analyses (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    usp_list_json TEXT NOT NULL,
    pain_points_json TEXT NOT NULL,
    target_audience TEXT NOT NULL,
    hook TEXT NOT NULL,
    body TEXT NOT NULL,
    cta TEXT NOT NULL,
    image_prompt TEXT NOT NULL,
    video_prompt TEXT NOT NULL,
    fallback_used INTEGER NOT NULL DEFAULT 0 CHECK(fallback_used IN (0, 1)),
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_user_id, product_id, run_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_affiliate_analyses_owner_product
    ON affiliate_analyses(owner_user_id, product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_analyses_run
    ON affiliate_analyses(run_id);
"""


def apply_schema_v7(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_V7)
