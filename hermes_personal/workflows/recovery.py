from __future__ import annotations

import sqlite3
from typing import List, Tuple

from .outbox_repository import OutboxRepository


class WorkflowRecoveryService:
    """Recovery service wrapping OutboxRepository while preserving backward compatibility.

    - ``recover_pending_workflows`` returns workflow IDs present in the
      ``workflow`` table.
    - ``replay_outbox`` returns unacknowledged messages without deleting them.
    - ``ack_outbox`` deletes a message after downstream delivery succeeds.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.conn = connection
        self.conn.row_factory = sqlite3.Row
        self.outbox_repository = OutboxRepository(connection)
        self.outbox_repo = self.outbox_repository

    def recover_pending_workflows(self) -> List[str]:
        cur = self.conn.cursor()
        cur.execute("SELECT workflow_id FROM workflow")
        return [row["workflow_id"] for row in cur.fetchall()]

    def replay_outbox(self) -> List[Tuple[str, str]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT workflow_id, message FROM workflow_outbox WHERE state != 'quarantined' ORDER BY outbox_id"
        )
        rows = cur.fetchall()
        return [(row["workflow_id"], row["message"]) for row in rows]

    def ack_outbox(self, workflow_id: str, message: str) -> None:
        """Acknowledge one delivered outbox record using its stable payload."""
        with self.conn:
            row = self.conn.execute(
                """
                SELECT outbox_id, lease_token, lease_owner FROM workflow_outbox
                WHERE workflow_id = ? AND message = ?
                ORDER BY outbox_id LIMIT 1
                """,
                (workflow_id, message),
            ).fetchone()
            if row is not None:
                if (
                    row["lease_token"] is not None
                    and row["lease_owner"] is not None
                ):
                    self.outbox_repository.ack(
                        outbox_id=row["outbox_id"],
                        lease_token=row["lease_token"],
                        worker_id=row["lease_owner"],
                    )
                else:
                    self.conn.execute(
                        "DELETE FROM workflow_outbox WHERE outbox_id = ?",
                        (row["outbox_id"],),
                    )
