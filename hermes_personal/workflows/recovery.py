from __future__ import annotations

import sqlite3
from typing import List, Tuple

from .repository import WorkflowRepository
from .models import IllegalTransition  # placeholder import if needed


class WorkflowRecoveryService:
    """Simple recovery service for persisted workflows.

    - ``recover_pending_workflows`` returns workflow IDs present in the
      ``workflow`` table. In a real system this would rebuild in‑memory state.
    - ``replay_outbox`` returns unacknowledged messages without deleting them.
    - ``ack_outbox`` deletes a message only after downstream delivery succeeds.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection
        self.conn.row_factory = sqlite3.Row

    def recover_pending_workflows(self) -> List[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT workflow_id FROM workflow")
        return [row["workflow_id"] for row in cur.fetchall()]

    def replay_outbox(self) -> List[Tuple[str, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT outbox_id, workflow_id, message FROM workflow_outbox ORDER BY outbox_id"
        )
        rows = cur.fetchall()
        messages: List[Tuple[str, str]] = [
            (row["workflow_id"], row["message"]) for row in rows
        ]
        return messages

    def ack_outbox(self, workflow_id: str, message: str) -> None:
        """Acknowledge one delivered outbox record using its stable payload."""
        with self.conn:
            row = self.conn.execute(
                """
                SELECT outbox_id FROM workflow_outbox
                WHERE workflow_id = ? AND message = ?
                ORDER BY outbox_id LIMIT 1
                """,
                (workflow_id, message),
            ).fetchone()
            if row is not None:
                self.conn.execute(
                    "DELETE FROM workflow_outbox WHERE outbox_id = ?",
                    (row["outbox_id"],),
                )
