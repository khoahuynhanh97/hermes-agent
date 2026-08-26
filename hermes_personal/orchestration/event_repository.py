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


class MigrationError(RuntimeError):
    """Raised when database migration or legacy cutover reconstruction fails."""


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
            self._connection.execute(
                """
                INSERT INTO owner_event_cursor (owner_user_id, event_id, created_at)
                VALUES (?, ?, ?)
                """,
                (event.principal_id, event.event_id, now_iso),
            )
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

    def load_session_history(
        self,
        session_id: str,
        legacy_transcript_messages: list[Mapping[str, Any]] | None = None,
    ) -> tuple[Mapping[str, Any], ...]:
        rows = self._connection.execute(
            """
            SELECT turn_id, user_message, status
            FROM turn_execution
            WHERE session_id = ? AND status = 'completed'
            ORDER BY created_at, rowid
            """,
            (session_id,),
        ).fetchall()

        cutover_row = self._connection.execute(
            "SELECT cutover_turn_id, legacy_messages_json FROM legacy_session_cutover WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        cutover_messages: list[Mapping[str, Any]] = []
        if cutover_row:
            try:
                raw_legacy = json.loads(cutover_row["legacy_messages_json"])
                if not isinstance(raw_legacy, list):
                    raise MigrationError(f"corrupt legacy cutover JSON for session {session_id}")
                stored_cutover_turn_id = cutover_row["cutover_turn_id"]
                if rows and stored_cutover_turn_id != "legacy_cutover" and stored_cutover_turn_id != rows[0]["turn_id"]:
                    raise MigrationError(
                        f"mismatched cutover_turn_id for session {session_id}: stored '{stored_cutover_turn_id}' != first canonical turn '{rows[0]['turn_id']}'"
                    )
                cutover_messages = [
                    _freeze_json_value(m) for m in raw_legacy if isinstance(m, Mapping)
                ]
            except (json.JSONDecodeError, TypeError) as exc:
                raise MigrationError(f"corrupt legacy cutover JSON for session {session_id}") from exc

        if not rows and not cutover_messages and not legacy_transcript_messages:
            return ()

        if not cutover_row and legacy_transcript_messages:
            cutover_messages = self._migrate_legacy_cutover_and_backfill(
                session_id, rows, legacy_transcript_messages
            )
            rows = self._connection.execute(
                """
                SELECT turn_id, user_message, status
                FROM turn_execution
                WHERE session_id = ? AND status = 'completed'
                ORDER BY created_at, rowid
                """,
                (session_id,),
            ).fetchall()

        history: list[Mapping[str, Any]] = list(cutover_messages)

        for row in rows:
            turn_id = row["turn_id"]
            user_msg = row["user_message"]
            if user_msg:
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
            turn_messages = _reconstruct_turn_messages(events)
            history.extend(turn_messages)

        return tuple(history)

    def _migrate_legacy_cutover_and_backfill(
        self,
        session_id: str,
        rows: list[sqlite3.Row],
        legacy_transcript_messages: list[Mapping[str, Any]],
    ) -> list[Mapping[str, Any]]:
        for idx, item in enumerate(legacy_transcript_messages):
            if not isinstance(item, Mapping) or not item.get("role"):
                raise MigrationError(
                    f"invalid legacy transcript message at index {idx} for session {session_id}: missing mapping or role"
                )

        turn_id_to_user_msg: dict[str, str] = {}
        first_canonical_transcript_idx: int | None = None

        for i, msg in enumerate(legacy_transcript_messages):
            meta = msg.get("event_metadata")
            if isinstance(meta, Mapping):
                tid = meta.get("turn_id")
                if isinstance(tid, str) and tid and tid not in turn_id_to_user_msg:
                    user_idx = i - 1
                    while user_idx >= 0:
                        prev = legacy_transcript_messages[user_idx]
                        if isinstance(prev, Mapping) and prev.get("role") == "user":
                            content = prev.get("content")
                            if isinstance(content, str):
                                turn_id_to_user_msg[tid] = content
                                if (
                                    first_canonical_transcript_idx is None
                                    or user_idx < first_canonical_transcript_idx
                                ):
                                    first_canonical_transcript_idx = user_idx
                            break
                        user_idx -= 1

        user_msg_entries = [
            (i, msg.get("content"))
            for i, msg in enumerate(legacy_transcript_messages)
            if isinstance(msg, Mapping)
            and msg.get("role") == "user"
            and isinstance(msg.get("content"), str)
            and msg.get("content")
        ]

        num_canonical = len(rows)
        if first_canonical_transcript_idx is None and num_canonical > 0 and len(user_msg_entries) >= num_canonical:
            canonical_user_entries = user_msg_entries[-num_canonical:]
            first_canonical_transcript_idx = canonical_user_entries[0][0]
            for r, (_, content) in zip(rows, canonical_user_entries):
                if content:
                    turn_id_to_user_msg[r["turn_id"]] = content

        unresolved = [
            r["turn_id"]
            for r in rows
            if not r["user_message"] and r["turn_id"] not in turn_id_to_user_msg
        ]
        if unresolved:
            raise MigrationError(
                f"unresolved canonical turn IDs during legacy cutover migration for session {session_id}: {unresolved}"
            )

        pre_canonical: list[Mapping[str, Any]] = []
        if first_canonical_transcript_idx is not None:
            pre_canonical = [
                _freeze_json_value(dict(m))
                for m in legacy_transcript_messages[:first_canonical_transcript_idx]
                if isinstance(m, Mapping)
            ]
        elif legacy_transcript_messages and not rows:
            pre_canonical = [
                _freeze_json_value(dict(m))
                for m in legacy_transcript_messages
                if isinstance(m, Mapping)
            ]

        json_serializable_pre_canonical = [to_primitive(m) for m in pre_canonical]

        first_turn_id = rows[0]["turn_id"] if rows else "legacy_cutover"
        with self._connection:
            for r in rows:
                if not r["user_message"]:
                    tid = r["turn_id"]
                    user_msg = turn_id_to_user_msg.get(tid, "")
                    if user_msg:
                        self._connection.execute(
                            "UPDATE turn_execution SET user_message = ? WHERE turn_id = ?",
                            (user_msg, tid),
                        )

            self._connection.execute(
                """
                INSERT OR REPLACE INTO legacy_session_cutover
                (session_id, cutover_turn_id, legacy_messages_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    session_id,
                    first_turn_id,
                    json.dumps(json_serializable_pre_canonical, ensure_ascii=False),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

        return pre_canonical

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

    def get_event_records_for_owner(
        self,
        owner_id: str,
        after_cursor: int = 0,
        limit: int = 100,
    ) -> list[tuple[int, AgentEvent]]:
        """Return committed events using an owner-global durable cursor."""
        if not owner_id.strip():
            raise ValueError("owner_id must not be blank")
        if after_cursor < 0:
            raise ValueError("after_cursor must be non-negative")
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = self._connection.execute(
            """
            SELECT c.cursor, e.sequence, e.event_id, e.payload_json
            FROM owner_event_cursor c
            JOIN turn_event e ON e.event_id = c.event_id
            WHERE c.owner_user_id = ? AND c.cursor > ?
            ORDER BY c.cursor
            LIMIT ?
            """,
            (owner_id, after_cursor, limit),
        ).fetchall()
        return [(row["cursor"], _deserialize_event(row)) for row in rows]

    def get_events_for_owner(
        self,
        owner_id: str,
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[AgentEvent]:
        """Compatibility projection; ``after_seq`` is an owner cursor here."""
        return [
            event
            for _, event in self.get_event_records_for_owner(
                owner_id, after_cursor=after_seq, limit=limit
            )
        ]

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


def _reconstruct_turn_messages(events: list[AgentEvent]) -> list[Mapping[str, Any]]:
    for event in events:
        if event.event_type == "completed":
            raw_messages = event.data.get("messages")
            if isinstance(raw_messages, (list, tuple)) and raw_messages:
                reconstructed: list[Mapping[str, Any]] = []
                for msg in raw_messages:
                    if isinstance(msg, Mapping):
                        if msg.get("role") != "user":
                            reconstructed.append(_freeze_json_value(dict(msg)))
                if reconstructed:
                    return reconstructed

    messages: list[Mapping[str, Any]] = []
    pending_tool_calls: list[Mapping[str, Any]] = []
    assistant_text_parts: list[str] = []
    terminal_text: str | None = None

    def flush_pending_tool_calls() -> None:
        nonlocal pending_tool_calls, assistant_text_parts
        if pending_tool_calls:
            text = "".join(assistant_text_parts) if assistant_text_parts else None
            messages.append(
                MappingProxyType(
                    {
                        "role": "assistant",
                        "content": text,
                        "tool_calls": tuple(
                            MappingProxyType(dict(tc)) for tc in pending_tool_calls
                        ),
                    }
                )
            )
            pending_tool_calls = []
            assistant_text_parts = []

    def flush_assistant_text() -> None:
        nonlocal assistant_text_parts, terminal_text
        text = terminal_text or "".join(assistant_text_parts)
        if text:
            messages.append(
                MappingProxyType({"role": "assistant", "content": text})
            )
        assistant_text_parts = []
        terminal_text = None

    for event in events:
        if event.event_type == "tool_activity":
            kind = event.data.get("kind")
            if kind == "tool_call":
                tool_call = event.data.get("tool_call")
                if isinstance(tool_call, Mapping):
                    pending_tool_calls.append(dict(tool_call))
            elif kind == "tool_result":
                flush_pending_tool_calls()
                flush_assistant_text()
                tool_msg = event.data.get("message")
                if isinstance(tool_msg, Mapping):
                    messages.append(
                        MappingProxyType(
                            {
                                key: _freeze_json_value(val)
                                for key, val in tool_msg.items()
                            }
                        )
                    )
                else:
                    messages.append(
                        MappingProxyType(
                            {
                                "role": "tool",
                                "tool_call_id": event.tool_call_id or "",
                                "content": str(event.data.get("tool_result", "")),
                            }
                        )
                    )
        elif event.event_type == "text_delta":
            delta = event.data.get("text")
            if isinstance(delta, str):
                assistant_text_parts.append(delta)
        elif event.event_type == "completed":
            final_text = event.data.get("text") or event.data.get("final_response")
            if isinstance(final_text, str) and final_text:
                terminal_text = final_text

    flush_pending_tool_calls()
    flush_assistant_text()
    return messages
