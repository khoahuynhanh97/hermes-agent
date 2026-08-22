from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS global_user_identity (
  owner_user_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_identity (
  channel TEXT NOT NULL,
  external_subject TEXT NOT NULL,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (channel, external_subject)
);
CREATE INDEX IF NOT EXISTS channel_identity_owner_idx
  ON channel_identity(owner_user_id, channel);
CREATE TABLE IF NOT EXISTS conversation_session (
  session_id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  channel TEXT NOT NULL,
  external_conversation_id TEXT NOT NULL,
  active_workflow_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(owner_user_id, channel, external_conversation_id)
);
CREATE TABLE IF NOT EXISTS workflow_handoff (
  handoff_id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  workflow_id TEXT NOT NULL,
  source_session_id TEXT NOT NULL REFERENCES conversation_session(session_id) ON DELETE RESTRICT,
  target_session_id TEXT NOT NULL REFERENCES conversation_session(session_id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  UNIQUE(workflow_id, target_session_id)
);
"""


def connect(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    return connection
