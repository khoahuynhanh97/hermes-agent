from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
from hermes.adapters.sqlite.schema_v4 import apply_schema_v4
from hermes.adapters.sqlite.schema_v5 import apply_schema_v5
from .config import HermesPaths


SCHEMA_VERSION = 5

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    source_key TEXT NOT NULL,
    source_url TEXT,
    local_path TEXT,
    title TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence IN ('high', 'medium', 'low', 'needs_source')),
    acquisition_status TEXT NOT NULL DEFAULT 'ready',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_user_id, source_key)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    local_path TEXT NOT NULL,
    sha256 TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    size_bytes INTEGER NOT NULL DEFAULT 0 CHECK (size_bytes >= 0),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    artifact_id TEXT REFERENCES artifacts(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    locator TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL,
    slug TEXT NOT NULL DEFAULT '',
    lesson_type TEXT NOT NULL DEFAULT 'general',
    category TEXT NOT NULL DEFAULT 'general',
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    key_lessons_json TEXT NOT NULL DEFAULT '[]',
    detail_json TEXT NOT NULL DEFAULT '{}',
    confidence REAL NOT NULL DEFAULT 0.5 CHECK (confidence >= 0.0 AND confidence <= 1.0),
    confidence_label TEXT NOT NULL DEFAULT 'medium'
        CHECK (confidence_label IN ('high', 'medium', 'low', 'needs_source')),
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected')),
    needs_reanalysis INTEGER NOT NULL DEFAULT 0 CHECK (needs_reanalysis IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    rejected_at TEXT,
    UNIQUE(owner_user_id, id)
);

CREATE TABLE IF NOT EXISTS lesson_evidence (
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
    PRIMARY KEY (lesson_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS lesson_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id TEXT NOT NULL REFERENCES lessons(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor_user_id TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    memory_type TEXT NOT NULL
        CHECK (memory_type IN ('preference', 'fact', 'decision', 'task')),
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved', 'rejected', 'deactivated')),
    source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    approved_at TEXT,
    deactivated_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    action TEXT NOT NULL,
    actor_user_id TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    chat_id TEXT NOT NULL DEFAULT '',
    job_type TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued'
        CHECK (state IN ('queued', 'running', 'completed', 'failed', 'cancelled')),
    stage TEXT NOT NULL DEFAULT 'queued',
    input_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    error TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    cancel_requested INTEGER NOT NULL DEFAULT 0 CHECK (cancel_requested IN (0, 1)),
    available_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_sources_owner_type ON sources(owner_user_id, source_type);
CREATE INDEX IF NOT EXISTS idx_artifacts_source ON artifacts(source_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source ON evidence(source_id);
CREATE INDEX IF NOT EXISTS idx_lessons_owner_status ON lessons(owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_lessons_source_status ON lessons(source_id, status);
CREATE INDEX IF NOT EXISTS idx_lesson_events_lesson ON lesson_events(lesson_id, created_at);
CREATE INDEX IF NOT EXISTS idx_messages_owner_chat ON messages(owner_user_id, chat_id, id DESC);
CREATE INDEX IF NOT EXISTS idx_memories_owner_status ON memories(owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_state_available ON jobs(state, available_at, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_owner_created ON jobs(owner_user_id, created_at DESC);

CREATE VIRTUAL TABLE IF NOT EXISTS lesson_fts USING fts5(
    lesson_id UNINDEXED,
    owner_user_id UNINDEXED,
    title,
    summary,
    content,
    tags
);
"""

SCHEMA_V3 = """
CREATE TABLE IF NOT EXISTS affiliate_products (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_vnd INTEGER NOT NULL CHECK(price_vnd >= 0),
    sold_count INTEGER,
    rating REAL,
    review_count INTEGER,
    commission_rate REAL,
    shop_name TEXT NOT NULL DEFAULT '',
    product_url TEXT NOT NULL DEFAULT '',
    image_urls_json TEXT NOT NULL DEFAULT '[]',
    visual_signals_json TEXT NOT NULL DEFAULT '[]',
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    authorization_scope TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    eligibility_status TEXT NOT NULL DEFAULT 'candidate',
    score REAL,
    score_json TEXT NOT NULL DEFAULT '{}',
    score_reason TEXT NOT NULL DEFAULT '',
    score_confidence TEXT NOT NULL DEFAULT 'low',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_user_id, platform, external_product_id)
);

CREATE TABLE IF NOT EXISTS affiliate_research_runs (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK(status IN ('running', 'completed', 'failed')),
    counters_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    finished_at TEXT,
    UNIQUE(owner_user_id, idempotency_key)
);

CREATE TABLE IF NOT EXISTS affiliate_product_snapshots (
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    snapshot_date TEXT NOT NULL,
    price_vnd INTEGER NOT NULL CHECK(price_vnd >= 0),
    sold_count INTEGER,
    rating REAL,
    review_count INTEGER,
    commission_rate REAL,
    collected_at TEXT NOT NULL,
    PRIMARY KEY(product_id, snapshot_date),
    UNIQUE(product_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS affiliate_references (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    author_name TEXT NOT NULL DEFAULT '',
    author_url TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    caption TEXT NOT NULL DEFAULT '',
    embed_html TEXT NOT NULL DEFAULT '',
    authorization_scope TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    media_local_path TEXT NOT NULL DEFAULT '',
    collected_at TEXT NOT NULL,
    UNIQUE(owner_user_id, source_url)
);

CREATE TABLE IF NOT EXISTS affiliate_content_ideas (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    audience TEXT NOT NULL,
    angle TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(owner_user_id, id)
);

CREATE TABLE IF NOT EXISTS affiliate_content_packages (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    product_id TEXT NOT NULL REFERENCES affiliate_products(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES affiliate_research_runs(id) ON DELETE CASCADE,
    revision INTEGER NOT NULL CHECK(revision > 0),
    status TEXT NOT NULL CHECK(status IN ('pending_review', 'approved', 'revision_requested', 'rejected')),
    audience TEXT NOT NULL,
    angle TEXT NOT NULL,
    angle_reason TEXT NOT NULL,
    hook TEXT NOT NULL,
    script TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL CHECK(duration_seconds > 0),
    storyboard_json TEXT NOT NULL DEFAULT '[]',
    ai_prompts_json TEXT NOT NULL DEFAULT '[]',
    voiceover_plan TEXT NOT NULL DEFAULT '',
    text_overlays_json TEXT NOT NULL DEFAULT '[]',
    claims_json TEXT NOT NULL DEFAULT '[]',
    warnings_json TEXT NOT NULL DEFAULT '[]',
    asset_rights_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_user_id, id)
);

CREATE TABLE IF NOT EXISTS affiliate_approval_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_id TEXT NOT NULL REFERENCES affiliate_content_packages(id) ON DELETE CASCADE,
    owner_user_id TEXT NOT NULL,
    action TEXT NOT NULL CHECK(action IN ('approve', 'revise', 'reject')),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_affiliate_products_owner ON affiliate_products(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_products_score ON affiliate_products(owner_user_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_snapshots_product ON affiliate_product_snapshots(product_id, snapshot_date DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_references_product ON affiliate_references(product_id, collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_affiliate_ideas_run ON affiliate_content_ideas(run_id, product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_packages_owner_status ON affiliate_content_packages(owner_user_id, status);
CREATE INDEX IF NOT EXISTS idx_affiliate_packages_run ON affiliate_content_packages(run_id, product_id);
CREATE INDEX IF NOT EXISTS idx_affiliate_events_package ON affiliate_approval_events(package_id, created_at);
CREATE INDEX IF NOT EXISTS idx_affiliate_runs_owner_status ON affiliate_research_runs(owner_user_id, status);
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, path: str | Path | None = None, busy_timeout_ms: int = 5000):
        paths = HermesPaths.from_env()
        self.path = Path(path or paths.database).expanduser().resolve()
        self.busy_timeout_ms = max(100, int(busy_timeout_ms))

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self.busy_timeout_ms / 1000,
            isolation_level=None,
            factory=_ClosingConnection,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {self.busy_timeout_ms}")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            # Apply schema_v1 if database is new or at version 0
            cursor = connection.cursor()
            cursor.execute("PRAGMA user_version")
            current_version = cursor.fetchone()[0]

            if current_version < 1:
                connection.executescript(SCHEMA_V1)
                connection.execute("PRAGMA user_version = 1")
            
            if current_version < 2:
                apply_schema_v2(connection)
                connection.execute("PRAGMA user_version = 2")

            if current_version < 3:
                connection.executescript(SCHEMA_V3)
                connection.execute("PRAGMA user_version = 3")

            if current_version < 4:
                apply_schema_v4(connection)
                connection.execute("PRAGMA user_version = 4")

            if current_version < 5:
                apply_schema_v5(connection)
                connection.execute("PRAGMA user_version = 5")
            
        finally:
            connection.close()

    @contextmanager
    def transaction(self, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
