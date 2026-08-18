"""Transactional job event/outbox storage."""

import sqlite3


def apply_schema_v9(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS job_events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            owner_user_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL DEFAULT '{}',
            delivery_state TEXT NOT NULL DEFAULT 'pending' CHECK(delivery_state IN ('pending', 'delivered', 'failed')),
            delivery_worker_id TEXT,
            delivery_lease_expires_at TEXT NOT NULL DEFAULT '2000-01-01T00:00:00Z',
            attempt_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_job ON job_events(job_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_delivery "
        "ON job_events(delivery_state, delivery_lease_expires_at)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_events_owner "
        "ON job_events(owner_user_id)"
    )
    connection.commit()
