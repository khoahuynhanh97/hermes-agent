"""Transactional job event/outbox storage."""

import sqlite3


def apply_schema_v9(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            aggregate_type TEXT NOT NULL,
            aggregate_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            occurred_at TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            delivery_state TEXT NOT NULL DEFAULT 'pending'
                CHECK(delivery_state IN ('pending', 'sending', 'delivered', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
            max_attempts INTEGER NOT NULL DEFAULT 3 CHECK(max_attempts > 0),
            last_error TEXT NOT NULL DEFAULT '',
            next_attempt_at TEXT NOT NULL,
            delivery_worker_id TEXT,
            delivery_lease_expires_at TEXT,
            delivered_at TEXT,
            UNIQUE(event_type, aggregate_type, aggregate_id)
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_delivery "
        "ON job_events(delivery_state, next_attempt_at, occurred_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_owner "
        "ON job_events(owner_user_id, occurred_at DESC)"
    )
    connection.commit()
