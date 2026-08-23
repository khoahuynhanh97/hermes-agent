from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping, cast

from hermes_personal.contracts import (
    AgentEvent,
    AgentEventType,
    AgentTurnRequest,
    to_primitive,
)

TerminalStatus = Literal["completed", "failed"]


class IdempotencyConflict(ValueError):
    """An idempotency key was reused for different request semantics."""

    def __init__(self, idempotency_key: str) -> None:
        super().__init__("idempotency key was reused for a different request")
        self.idempotency_key = idempotency_key


class TurnInProgress(RuntimeError):
    """The canonical execution for an idempotency key is still running."""

    def __init__(self, turn_id: str) -> None:
        super().__init__("canonical turn execution is still in progress")
        self.turn_id = turn_id


def _request_digest(request: AgentTurnRequest) -> str:
    payload = to_primitive(request)
    for retry_specific_field in ("turn_id", "occurred_at", "idempotency_key"):
        payload.pop(retry_specific_field)
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _freeze_json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_json_value(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json_value(item) for item in value)
    return value


def _deserialize_event(row: sqlite3.Row) -> AgentEvent:
    payload = json.loads(row["payload_json"])
    event = AgentEvent(
        event_type=cast(AgentEventType, payload["event_type"]),
        principal_id=payload["principal_id"],
        session_id=payload["session_id"],
        turn_id=payload["turn_id"],
        sequence=payload["sequence"],
        schema_version=payload["schema_version"],
        data=_freeze_json_value(payload["data"]),
        workflow_id=payload["workflow_id"],
        job_id=payload["job_id"],
        approval_id=payload["approval_id"],
        tool_call_id=payload["tool_call_id"],
        occurred_at=datetime.fromisoformat(payload["occurred_at"]),
        event_id=payload["event_id"],
    )
    if event.sequence != row["sequence"] or event.event_id != row["event_id"]:
        raise RuntimeError("stored event envelope does not match its replay key")
    return event


class EventRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def claim(self, request: AgentTurnRequest) -> tuple[AgentEvent, ...] | None:
        digest = _request_digest(request)
        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            row = self._connection.execute(
                """
                SELECT request_digest, turn_id, status
                FROM turn_execution
                WHERE owner_user_id = ? AND idempotency_key = ?
                """,
                (request.principal.owner_user_id, request.idempotency_key),
            ).fetchone()
            if row is None:
                now_iso = datetime.now(timezone.utc).isoformat()
                self._connection.execute(
                    """
                    INSERT INTO turn_execution (
                      owner_user_id, idempotency_key, request_digest, turn_id,
                      session_id, user_message, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 'in_progress', ?, ?)
                    """,
                    (
                        request.principal.owner_user_id,
                        request.idempotency_key,
                        digest,
                        request.turn_id,
                        request.session_id,
                        request.message,
                        now_iso,
                        now_iso,
                    ),
                )
                return None

            if row["request_digest"] != digest:
                raise IdempotencyConflict(request.idempotency_key)
            if row["status"] == "in_progress":
                raise TurnInProgress(row["turn_id"])
            return self._load_events(row["turn_id"])

    def append_event(self, event: AgentEvent) -> None:
        with self._connection:
            execution = self._connection.execute(
                """
                SELECT owner_user_id, session_id, status
                FROM turn_execution
                WHERE turn_id = ?
                """,
                (event.turn_id,),
            ).fetchone()
            if execution is not None:
                if execution["status"] != "in_progress":
                    raise RuntimeError("cannot append event to terminal turn")
                if (
                    execution["owner_user_id"] != event.principal_id
                    or execution["session_id"] != event.session_id
                ):
                    raise ValueError("event identity does not match the claimed turn")
            payload_json = json.dumps(
                to_primitive(event),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            self._connection.execute(
                """
                INSERT INTO turn_event (turn_id, sequence, event_id, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (event.turn_id, event.sequence, event.event_id, payload_json),
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            if event.event_type in {"completed", "failed"}:
                self._connection.execute(
                    """
                    UPDATE turn_execution
                    SET status = ?, updated_at = ?
                    WHERE turn_id = ? AND status = 'in_progress'
                    """,
                    (event.event_type, now_iso, event.turn_id),
                )
            else:
                self._connection.execute(
                    """
                    UPDATE turn_execution
                    SET updated_at = ?
                    WHERE turn_id = ? AND status = 'in_progress'
                    """,
                    (now_iso, event.turn_id),
                )

    def mark_terminal(self, turn_id: str, status: TerminalStatus) -> None:
        if status not in {"completed", "failed"}:
            raise ValueError("terminal status must be completed or failed")
        with self._connection:
            latest_row = self._connection.execute(
                """
                SELECT payload_json
                FROM turn_event
                WHERE turn_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (turn_id,),
            ).fetchone()
            if latest_row is None:
                raise RuntimeError("cannot mark terminal without a stored terminal event")
            latest_payload = json.loads(latest_row["payload_json"])
            if latest_payload.get("event_type") != status:
                raise RuntimeError("latest stored event does not match terminal status")

            execution = self._connection.execute(
                """
                SELECT status FROM turn_execution WHERE turn_id = ?
                """,
                (turn_id,),
            ).fetchone()
            if execution is None:
                raise RuntimeError("claimed turn is missing or already terminal")
            if execution["status"] == status:
                return
            cursor = self._connection.execute(
                """
                UPDATE turn_execution
                SET status = ?, updated_at = ?
                WHERE turn_id = ? AND status = 'in_progress'
                """,
                (status, datetime.now(timezone.utc).isoformat(), turn_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("claimed turn is missing or already terminal")

    def load_session_history(self, session_id: str) -> tuple[Mapping[str, Any], ...]:
        rows = self._connection.execute(
            """
            SELECT turn_id, user_message, status
            FROM turn_execution
            WHERE session_id = ? AND status = 'completed'
            ORDER BY created_at, rowid
            """,
            (session_id,),
        ).fetchall()

        history: list[Mapping[str, Any]] = []
        for row in rows:
            turn_id = row["turn_id"]
            user_msg = row["user_message"]
            history.append(MappingProxyType({"role": "user", "content": user_msg}))

            event_rows = self._connection.execute(
                """
                SELECT sequence, event_id, payload_json
                FROM turn_event
                WHERE turn_id = ?
                ORDER BY sequence
                """,
                (turn_id,),
            ).fetchall()

            events = [_deserialize_event(er) for er in event_rows]
            assistant_text = ""
            for event in events:
                if event.event_type == "completed":
                    assistant_text = (
                        event.data.get("text")
                        or event.data.get("final_response")
                        or assistant_text
                    )
                elif event.event_type == "text_delta":
                    delta = event.data.get("text")
                    if isinstance(delta, str):
                        assistant_text += delta

            if assistant_text:
                history.append(
                    MappingProxyType({"role": "assistant", "content": assistant_text})
                )

        return tuple(history)

    def load_session_events(self, session_id: str) -> tuple[AgentEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT e.sequence, e.event_id, e.payload_json
            FROM turn_event e
            JOIN turn_execution x ON e.turn_id = x.turn_id
            WHERE x.session_id = ? AND x.status IN ('completed', 'failed')
            ORDER BY x.created_at, e.sequence
            """,
            (session_id,),
        ).fetchall()
        return tuple(_deserialize_event(row) for row in rows)

    def _load_events(self, turn_id: str) -> tuple[AgentEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT sequence, event_id, payload_json
            FROM turn_event
            WHERE turn_id = ?
            ORDER BY sequence
            """,
            (turn_id,),
        ).fetchall()
        events = tuple(_deserialize_event(row) for row in rows)
        if not events:
            raise RuntimeError("terminal turn has no replayable events")
        if [event.sequence for event in events] != list(range(len(events))):
            raise RuntimeError("stored turn event sequence is not contiguous")
        return events
