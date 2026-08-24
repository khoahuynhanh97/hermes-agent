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
CREATE UNIQUE INDEX IF NOT EXISTS conversation_session_identity_idx
  ON conversation_session(session_id, owner_user_id);
CREATE TABLE IF NOT EXISTS workflow_handoff (
  handoff_id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  workflow_id TEXT NOT NULL,
  source_session_id TEXT NOT NULL REFERENCES conversation_session(session_id) ON DELETE RESTRICT,
  target_session_id TEXT NOT NULL REFERENCES conversation_session(session_id) ON DELETE RESTRICT,
  created_at TEXT NOT NULL,
  UNIQUE(workflow_id, target_session_id)
);
CREATE TABLE IF NOT EXISTS turn_execution (
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  turn_id TEXT NOT NULL UNIQUE,
  session_id TEXT NOT NULL,
  user_message TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL CHECK(status IN ('in_progress', 'completed', 'failed')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (owner_user_id, idempotency_key),
  FOREIGN KEY (session_id, owner_user_id)
    REFERENCES conversation_session(session_id, owner_user_id) ON DELETE RESTRICT
);
CREATE TABLE IF NOT EXISTS turn_event (
  turn_id TEXT NOT NULL REFERENCES turn_execution(turn_id) ON DELETE RESTRICT,
  sequence INTEGER NOT NULL CHECK(sequence >= 0),
  event_id TEXT NOT NULL UNIQUE,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (turn_id, sequence)
);
CREATE TABLE IF NOT EXISTS legacy_session_cutover (
  session_id TEXT PRIMARY KEY REFERENCES conversation_session(session_id) ON DELETE CASCADE,
  cutover_turn_id TEXT NOT NULL,
  legacy_messages_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capability_snapshot (
  snapshot_id TEXT PRIMARY KEY,
  digest TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS capability_snapshot_binding (
  snapshot_id TEXT NOT NULL REFERENCES capability_snapshot(snapshot_id) ON DELETE CASCADE,
  capability_id TEXT NOT NULL,
  binding_json TEXT NOT NULL,
  PRIMARY KEY (snapshot_id, capability_id)
);
CREATE TABLE IF NOT EXISTS capability_catalog_state (
  state_id INTEGER PRIMARY KEY CHECK(state_id = 1),
  active_snapshot_id TEXT NOT NULL REFERENCES capability_snapshot(snapshot_id) ON DELETE RESTRICT,
  activated_at TEXT NOT NULL
);
-- New workflow persistence tables
CREATE TABLE IF NOT EXISTS workflow (
  workflow_id TEXT PRIMARY KEY,
  aggregate_json TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS workflow_event (
  event_id TEXT PRIMARY KEY,
  workflow_id TEXT NOT NULL REFERENCES workflow(workflow_id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS processed_command (
  workflow_id TEXT NOT NULL REFERENCES workflow(workflow_id) ON DELETE CASCADE,
  command_id TEXT NOT NULL,
  UNIQUE(workflow_id, command_id)
);
CREATE TABLE IF NOT EXISTS workflow_outbox (
  outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
  workflow_id TEXT NOT NULL REFERENCES workflow(workflow_id) ON DELETE CASCADE,
  message TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- Governed learning tables
CREATE TABLE IF NOT EXISTS task_outcome (
  outcome_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  status TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_candidate (
  candidate_id TEXT PRIMARY KEY,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  digest TEXT NOT NULL,
  source_outcome_id TEXT REFERENCES task_outcome(outcome_id) ON DELETE SET NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(owner_user_id, kind, digest)
);

CREATE TABLE IF NOT EXISTS evidence_ref (
  evidence_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES learning_candidate(candidate_id) ON DELETE CASCADE,
  source_type TEXT NOT NULL,
  source_id TEXT NOT NULL,
  digest TEXT NOT NULL,
  excerpt TEXT NOT NULL,
  polarity TEXT NOT NULL DEFAULT 'positive',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_version (
  version_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES learning_candidate(candidate_id) ON DELETE CASCADE,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id) ON DELETE RESTRICT,
  version INTEGER NOT NULL,
  content TEXT NOT NULL,
  digest TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(candidate_id, version)
);

CREATE TABLE IF NOT EXISTS candidate_evaluation (
  evaluation_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL REFERENCES learning_candidate(candidate_id) ON DELETE CASCADE,
  evaluator_name TEXT NOT NULL,
  decision TEXT NOT NULL,
  score REAL NOT NULL,
  reason TEXT NOT NULL,
  evidence_summary TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_event (
    event_id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL REFERENCES learning_candidate(candidate_id) ON DELETE CASCADE,
    version_id TEXT REFERENCES learning_version(version_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);


"""

def _migrate_schema(connection: sqlite3.Connection) -> None:
    with connection:
        columns = [
            row["name"]
            for row in connection.execute("PRAGMA table_info(turn_execution)").fetchall()
        ]
        if columns and "user_message" not in columns:
            connection.execute(
                "ALTER TABLE turn_execution ADD COLUMN user_message TEXT NOT NULL DEFAULT ''"
            )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS legacy_session_cutover (
              session_id TEXT PRIMARY KEY REFERENCES conversation_session(session_id) ON DELETE CASCADE,
              cutover_turn_id TEXT NOT NULL,
              legacy_messages_json TEXT NOT NULL,
              created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_snapshot (
              snapshot_id TEXT PRIMARY KEY,
              digest TEXT NOT NULL UNIQUE,
              created_at TEXT NOT NULL
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_snapshot_binding (
              snapshot_id TEXT NOT NULL REFERENCES capability_snapshot(snapshot_id) ON DELETE CASCADE,
              capability_id TEXT NOT NULL,
              binding_json TEXT NOT NULL,
              PRIMARY KEY (snapshot_id, capability_id)
            );
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS capability_catalog_state (
              state_id INTEGER PRIMARY KEY CHECK(state_id = 1),
              active_snapshot_id TEXT NOT NULL REFERENCES capability_snapshot(snapshot_id) ON DELETE RESTRICT,
              activated_at TEXT NOT NULL
            );
            """
        )


def connect(database_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA)
    _migrate_schema(connection)
    return connection
