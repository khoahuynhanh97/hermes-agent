from __future__ import annotations

import json
from typing import Any

from .db import Database, utc_now


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load(value: str | None) -> dict:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class JobRepository:
    def __init__(self, database: Database | None = None):
        self.database = database or Database()
        self.database.initialize()

    def enqueue(
        self,
        job_id: str,
        owner_user_id: str | int,
        job_type: str,
        payload: dict,
        *,
        chat_id: str | int = "",
        max_attempts: int = 3,
        available_at: str | None = None,
    ) -> dict:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            existing = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if existing:
                return self._row(existing)
            connection.execute(
                """
                INSERT INTO jobs(
                    id, owner_user_id, chat_id, job_type, state, stage,
                    input_json, result_json, error, attempts, max_attempts,
                    cancel_requested, available_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', 'queued', ?, '{}', '', 0, ?, 0, ?, ?, ?)
                """,
                (
                    job_id,
                    str(owner_user_id),
                    str(chat_id),
                    job_type,
                    _dump(payload),
                    max(1, int(max_attempts)),
                    available_at or now,
                    now,
                    now,
                ),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def get(self, job_id: str) -> dict | None:
        with self.database.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row(row) if row else None

    def claim_next(self, job_type: str | None = None) -> dict | None:
        """Atomically claim the next available job, optionally for one job type."""
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                """
                SELECT * FROM jobs
                WHERE state = 'queued' AND cancel_requested = 0 AND available_at <= ?
                  AND (? IS NULL OR job_type = ?)
                ORDER BY available_at ASC, created_at ASC, id ASC
                LIMIT 1
                """,
                (now, job_type, job_type),
            ).fetchone()
            if not row:
                return None
            cursor = connection.execute(
                """
                UPDATE jobs
                SET state = 'running', stage = 'running', attempts = attempts + 1,
                    started_at = ?, updated_at = ?
                WHERE id = ? AND state = 'queued'
                """,
                (now, now, row["id"]),
            )
            if cursor.rowcount != 1:
                return None
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (row["id"],)).fetchone())

    def update_payload(self, job_id: str, payload: dict, stage: str | None = None) -> dict | None:
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            connection.execute(
                "UPDATE jobs SET input_json = ?, stage = ?, updated_at = ? WHERE id = ?",
                (_dump(payload), stage or row["stage"], utc_now(), job_id),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def complete(self, job_id: str, result: dict) -> dict | None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            connection.execute(
                """
                UPDATE jobs
                SET state = 'completed', stage = 'completed', result_json = ?,
                    error = '', cancel_requested = 0, completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (_dump(result), now, now, job_id),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def fail(self, job_id: str, error: str, *, retryable: bool = False) -> dict | None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row:
                return None
            requeue = bool(retryable and row["attempts"] < row["max_attempts"])
            state = "queued" if requeue else "failed"
            stage = "queued" if requeue else "failed"
            connection.execute(
                """
                UPDATE jobs
                SET state = ?, stage = ?, error = ?, available_at = ?,
                    completed_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (state, stage, str(error)[:4000], now, None if requeue else now, now, job_id),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def retry(self, job_id: str, owner_user_id: str | int) -> dict | None:
        owner = str(owner_user_id)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ? AND owner_user_id = ? AND state = 'failed'",
                (job_id, owner),
            ).fetchone()
            if not row:
                return None
            connection.execute(
                """
                UPDATE jobs
                SET state = 'queued', stage = 'queued', attempts = 0, error = '',
                    cancel_requested = 0, available_at = ?, completed_at = NULL, updated_at = ?
                WHERE id = ?
                """,
                (now, now, job_id),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def cancel(self, job_id: str, owner_user_id: str | int) -> dict | None:
        owner = str(owner_user_id)
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id = ? AND owner_user_id = ?", (job_id, owner)
            ).fetchone()
            if not row or row["state"] in {"completed", "failed", "cancelled"}:
                return None
            if row["state"] == "running":
                connection.execute(
                    "UPDATE jobs SET cancel_requested = 1, updated_at = ? WHERE id = ?",
                    (now, job_id),
                )
            else:
                connection.execute(
                    """
                    UPDATE jobs SET state = 'cancelled', stage = 'cancelled',
                        cancel_requested = 1, completed_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, job_id),
                )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def is_cancel_requested(self, job_id: str) -> bool:
        with self.database.connect() as connection:
            row = connection.execute("SELECT cancel_requested FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return bool(row and row["cancel_requested"])

    def acknowledge_cancel(self, job_id: str) -> dict | None:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or not row["cancel_requested"]:
                return None
            connection.execute(
                """
                UPDATE jobs SET state = 'cancelled', stage = 'cancelled',
                    completed_at = ?, updated_at = ? WHERE id = ?
                """,
                (now, now, job_id),
            )
            return self._row(connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())

    def recover_interrupted(self) -> list[str]:
        now = utc_now()
        with self.database.transaction(immediate=True) as connection:
            rows = connection.execute("SELECT id, cancel_requested FROM jobs WHERE state = 'running'").fetchall()
            recovered = []
            for row in rows:
                if row["cancel_requested"]:
                    connection.execute(
                        """
                        UPDATE jobs SET state = 'cancelled', stage = 'cancelled',
                            completed_at = ?, updated_at = ? WHERE id = ?
                        """,
                        (now, now, row["id"]),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE jobs SET state = 'queued', stage = 'queued',
                            available_at = ?, updated_at = ? WHERE id = ?
                        """,
                        (now, now, row["id"]),
                    )
                    recovered.append(str(row["id"]))
            return recovered

    def list_jobs(self, owner_user_id: str | int | None = None, limit: int = 30) -> list[dict]:
        values: list[Any] = []
        where = ""
        if owner_user_id is not None:
            where = "WHERE owner_user_id = ?"
            values.append(str(owner_user_id))
        values.append(max(1, min(int(limit), 500)))
        with self.database.connect() as connection:
            rows = connection.execute(
                f"SELECT * FROM jobs {where} ORDER BY created_at DESC, id DESC LIMIT ?", values
            ).fetchall()
        return [self._row(row) for row in rows]

    def prune_terminal(self, completed_before: str) -> int:
        """Delete only old terminal job rows; source and knowledge records are untouched."""
        with self.database.transaction(immediate=True) as connection:
            cursor = connection.execute(
                """
                DELETE FROM jobs
                WHERE state IN ('completed', 'failed', 'cancelled')
                  AND completed_at IS NOT NULL
                  AND completed_at < ?
                """,
                (completed_before,),
            )
            return int(cursor.rowcount)

    @staticmethod
    def _row(row) -> dict:
        value = dict(row)
        value["payload"] = _load(value.pop("input_json", "{}"))
        value["result"] = _load(value.pop("result_json", "{}"))
        value["cancel_requested"] = bool(value.get("cancel_requested"))
        return value
