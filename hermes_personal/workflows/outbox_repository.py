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
                SELECT outbox_id, workflow_id, message, state, attempt_count, max_attempts, created_at, updated_at
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
                new_attempt_count = row["attempt_count"] + 1
                if new_attempt_count > row["max_attempts"]:
                    self.connection.execute(
                        """
                        UPDATE workflow_outbox
                        SET state = 'quarantined',
                            attempt_count = ?,
                            last_error = 'max_attempts_exceeded_on_claim',
                            lease_token = NULL,
                            lease_owner = NULL,
                            lease_expires_at = NULL,
                            updated_at = ?
                        WHERE outbox_id = ?
                        """,
                        (new_attempt_count, now, row["outbox_id"]),
                    )
                    continue

                token = f"claim_{uuid4().hex}"
                expires_at = _add_seconds(now, lease_duration_seconds)
                self.connection.execute(
                    """
                    UPDATE workflow_outbox
                    SET state = 'leased',
                        lease_token = ?,
                        lease_owner = ?,
                        lease_expires_at = ?,
                        attempt_count = ?,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (token, worker_id, expires_at, new_attempt_count, now, row["outbox_id"]),
                )
                claims.append(
                    OutboxClaim(
                        outbox_id=row["outbox_id"],
                        workflow_id=row["workflow_id"],
                        message=row["message"],
                        lease_token=token,
                        lease_owner=worker_id,
                        lease_expires_at=expires_at,
                        attempt_count=new_attempt_count,
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

            attempt_count = row["attempt_count"]
            max_attempts = row["max_attempts"]

            if attempt_count >= max_attempts:
                self.connection.execute(
                    """
                    UPDATE workflow_outbox
                    SET state = 'quarantined',
                        last_error = ?,
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (error_message, now, outbox_id),
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
                        next_attempt_at = ?,
                        last_error = ?,
                        lease_token = NULL,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = ?
                    WHERE outbox_id = ?
                    """,
                    (next_attempt_at, error_message, now, outbox_id),
                )
                return "retry_scheduled"

    def reclaim_expired(self, now_iso: str | None = None) -> int:
        now = _now_iso(now_iso)
        with self.connection:
            cur1 = self.connection.execute(
                """
                UPDATE workflow_outbox
                SET state = 'quarantined',
                    last_error = 'lease_expired_max_attempts_exceeded',
                    lease_token = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE state = 'leased' AND lease_expires_at <= ? AND attempt_count >= max_attempts
                """,
                (now, now),
            )
            cur2 = self.connection.execute(
                """
                UPDATE workflow_outbox
                SET state = 'pending',
                    lease_token = NULL,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = ?
                WHERE state = 'leased' AND lease_expires_at <= ? AND attempt_count < max_attempts
                """,
                (now, now),
            )
            return cur1.rowcount + cur2.rowcount

    def list_unacknowledged(self) -> list[OutboxMessage]:
        with self.connection:
            cur = self.connection.execute(
                """
                SELECT outbox_id, workflow_id, message, state, lease_token, lease_owner,
                       lease_expires_at, attempt_count, max_attempts, next_attempt_at,
                       last_error, created_at, updated_at
                FROM workflow_outbox
                WHERE state != 'quarantined'
                ORDER BY outbox_id ASC
                """
            )
            rows = cur.fetchall()
            return [
                OutboxMessage(
                    outbox_id=row["outbox_id"],
                    workflow_id=row["workflow_id"],
                    message=row["message"],
                    state=row["state"],
                    lease_token=row["lease_token"],
                    lease_owner=row["lease_owner"],
                    lease_expires_at=row["lease_expires_at"],
                    attempt_count=row["attempt_count"],
                    max_attempts=row["max_attempts"],
                    next_attempt_at=row["next_attempt_at"],
                    last_error=row["last_error"],
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
                for row in rows
            ]

    def ack_message(
        self,
        workflow_id: str,
        message: str,
        worker_id: str = "recovery_worker",
        now_iso: str | None = None,
    ) -> bool:
        now = _now_iso(now_iso)
        with self.connection:
            cur = self.connection.execute(
                """
                SELECT outbox_id, lease_token, lease_owner, lease_expires_at
                FROM workflow_outbox
                WHERE workflow_id = ? AND message = ? AND state != 'quarantined'
                ORDER BY outbox_id ASC
                LIMIT 1
                """,
                (workflow_id, message),
            )
            row = cur.fetchone()
            if row is None:
                return False

            if (
                row["lease_token"] is not None
                and row["lease_owner"] is not None
                and row["lease_expires_at"] is not None
                and row["lease_expires_at"] > now
            ):
                return self.ack(
                    outbox_id=row["outbox_id"],
                    lease_token=row["lease_token"],
                    worker_id=row["lease_owner"],
                    now_iso=now,
                )

        claims = self.claim(worker_id=worker_id, batch_size=1000, now_iso=now)
        for claim in claims:
            if claim.outbox_id == row["outbox_id"]:
                return self.ack(
                    outbox_id=claim.outbox_id,
                    lease_token=claim.lease_token,
                    worker_id=claim.lease_owner,
                    now_iso=now,
                )
        return False

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
