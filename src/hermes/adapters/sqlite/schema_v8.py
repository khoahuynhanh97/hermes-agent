"""Durable execution metadata for the canonical job plane."""

import sqlite3


def apply_schema_v8(connection: sqlite3.Connection) -> None:
    columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
    if "worker_id" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN worker_id TEXT")
    if "lease_expires_at" not in columns:
        connection.execute("ALTER TABLE jobs ADD COLUMN lease_expires_at TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_lease ON jobs(state, lease_expires_at)"
    )
    connection.commit()
