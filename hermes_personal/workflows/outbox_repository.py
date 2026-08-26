from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4


@dataclass
class OutboxMessage:
    outbox_id: int
    workflow_id: str
    message: str
    state: str = "pending"
    lease_token: str | None = None
    lease_owner: str | None = None
    lease_expires_at: str | None = None
    attempt_count: int = 0
    max_attempts: int = 5
    next_attempt_at: str | None = None
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass
class OutboxClaim:
    outbox_id: int
    workflow_id: str
    message: str
    lease_token: str
    lease_owner: str
    lease_expires_at: str
    attempt_count: int = 0
    max_attempts: int = 5
    created_at: str = ""
    updated_at: str = ""


def _now_iso(now_iso: str | None = None) -> str:
    if now_iso is not None:
        return now_iso
    return datetime.now(timezone.utc).isoformat()


def _add_seconds(iso_str: str, seconds: float) -> str:
    dt = datetime.fromisoformat(iso_str)
    dt_new = dt + timedelta(seconds=seconds)
    return dt_new.isoformat()


class OutboxRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection
        self.connection.row_factory = sqlite3.Row

    def enqueue(
        self,
        workflow_id: str,
        message: str,
        max_attempts: int = 5,
        created_at: str | None = None,
    ) -> OutboxMessage:
        now = _now_iso(created_at)
        with self.connection:
            cur = self.connection.execute(
                """
                INSERT INTO workflow_outbox (
                    workflow_id, message, state, attempt_count, max_attempts, created_at, updated_at
                ) VALUES (?, ?, 'pending', 0, ?, ?, ?)
                """,
                (workflow_id, message, max_attempts, now, now),
            )
            outbox_id = cur.lastrowid
        return OutboxMessage(
            outbox_id=outbox_id,
            workflow_id=workflow_id,
            message=message,
            state="pending",
            attempt_count=0,
            max_attempts=max_attempts,
            created_at=now,
            updated_at=now,
        )

    def claim(
        self,
        worker_id: str,
        lease_duration_seconds: float = 30.0,
        batch_size: int = 10,
        now_iso: str | None = None,
    ) -> list[OutboxClaim]:
        now = _now_iso(now_iso)
        claims: list[OutboxClaim] = []
        with self.connection:
            try:
                self.connection.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                pass

            cur = self.connection.execute(
                """
                SELECT outbox_id, workflow_id, message, attempt_count, max_attempts, created_at, updated_at
                FROM workflow_outbox
                WHERE (state = 'pending' AND (next_attempt_at IS NULL OR next_attempt_at <= ?))
                   OR (state = 'leased' AND lease_expires_at <= ?)
                ORDER BY outbox_id ASC
                LIMIT ?
                """,
                (now, now, batch_size),
            )
            rows = cur.fetchall()

            for row in rows:
                token = f"claim_{uuid4().hex}"
                expires_at = _add_seconds(now, lease_duration_seconds)
                self.connection.execute(
                    """
                    UPDATE workflow_outbox
                    SET state = 'leased',
                        lease_token = ?,
                        lease_owner = ?,
                        lease_expires_at = ?,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (token, worker_id, expires_at, now, row["outbox_id"]),
                )
                claims.append(
                    OutboxClaim(
                        outbox_id=row["outbox_id"],
                        workflow_id=row["workflow_id"],
                        message=row["message"],
                        lease_token=token,
                        lease_owner=worker_id,
                        lease_expires_at=expires_at,
                        attempt_count=row["attempt_count"],
                        max_attempts=row["max_attempts"],
                        created_at=row["created_at"],
                        updated_at=now,
                    )
                )
        return claims

    def ack(
        self,
        outbox_id: int,
        lease_token: str,
        worker_id: str,
        now_iso: str | None = None,
    ) -> bool:
        now = _now_iso(now_iso)
        with self.connection:
            cur = self.connection.execute(
                """
                DELETE FROM workflow_outbox
                WHERE outbox_id = ?
                  AND lease_token = ?
                  AND lease_owner = ?
                  AND state = 'leased'
                  AND lease_expires_at > ?
                """,
                (outbox_id, lease_token, worker_id, now),
            )
            return cur.rowcount > 0

    def record_failure(
        self,
        outbox_id: int,
        lease_token: str,
        worker_id: str,
        error_message: str,
        backoff_base_seconds: float = 2.0,
        max_backoff_seconds: float = 300.0,
        now_iso: str | None = None,
    ) -> str:
        now = _now_iso(now_iso)
        with self.connection:
            cur = self.connection.execute(
                """
                SELECT attempt_count, max_attempts FROM workflow_outbox
                WHERE outbox_id = ? AND lease_token = ? AND lease_owner = ? AND state = 'leased'
                """,
                (outbox_id, lease_token, worker_id),
            )
            row = cur.fetchone()
            if row is None:
                return "stale_lease"

            attempt_count = row["attempt_count"] + 1
            max_attempts = row["max_attempts"]

            if attempt_count >= max_attempts:
                self.connection.execute(
                    """
                    UPDATE workflow_outbox
                    SET state = 'quarantined',
                        attempt_count = ?,
                        last_error = ?,
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (attempt_count, error_message, now, outbox_id),
                )
                return "quarantined"
            else:
                backoff = min(
                    max_backoff_seconds,
                    backoff_base_seconds ** attempt_count,
                )
                next_attempt_at = _add_seconds(now, backoff)
                self.connection.execute(
                    """
                    UPDATE workflow_outbox
                    SET state = 'pending',
                        attempt_count = ?,
                        next_attempt_at = ?,
                        last_error = ?,
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (attempt_count, next_attempt_at, error_message, now, outbox_id),
                )
                return "retry_scheduled"

    def reclaim_expired(self, now_iso: str | None = None) -> int:
        now = _now_iso(now_iso)
        with self.connection:
            cur = self.connection.execute(
                """
                UPDATE workflow_outbox
                SET state = 'pending',
                    lease_token = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE state = 'leased' AND lease_expires_at <= ?
                """,
                (now, now),
            )
            return cur.rowcount

    def requeue_quarantined(self, outbox_id: int, now_iso: str | None = None) -> bool:
        now = _now_iso(now_iso)
        with self.connection:
            cur = self.connection.execute(
                """
                UPDATE workflow_outbox
                SET state = 'pending',
                    attempt_count = 0,
                    next_attempt_at = NULL,
                    last_error = NULL,
                    lease_token = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE outbox_id = ? AND state = 'quarantined'
                """,
                (now, outbox_id),
            )
            return cur.rowcount > 0
