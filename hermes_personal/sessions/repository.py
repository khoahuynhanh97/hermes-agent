from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from hermes_personal.contracts import ChannelName

from .models import (
    ConversationSession,
    OwnerMismatchError,
    UnknownSession,
    WorkflowHandoff,
)


class SessionRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def get_or_create(
        self,
        owner_user_id: str,
        channel: ChannelName,
        external_conversation_id: str,
        workflow_id: str | None = None,
    ) -> ConversationSession:
        if not owner_user_id.strip() or not external_conversation_id.strip():
            raise ValueError("owner_user_id and external_conversation_id must not be blank")

        with self._connection:
            session = self._find_by_channel(owner_user_id, channel, external_conversation_id)
            if session is None:
                now = datetime.now(timezone.utc)
                session = ConversationSession(
                    session_id=f"session_{uuid4().hex}",
                    owner_user_id=owner_user_id,
                    channel=channel,
                    external_conversation_id=external_conversation_id,
                    active_workflow_id=workflow_id,
                    created_at=now,
                    updated_at=now,
                )
                self._connection.execute(
                    """
                    INSERT INTO conversation_session (
                      session_id, owner_user_id, channel, external_conversation_id,
                      active_workflow_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session.session_id,
                        session.owner_user_id,
                        session.channel,
                        session.external_conversation_id,
                        session.active_workflow_id,
                        session.created_at.isoformat(),
                        session.updated_at.isoformat(),
                    ),
                )
            elif workflow_id is not None and session.active_workflow_id != workflow_id:
                session = self._set_active_workflow(session.session_id, workflow_id)
        return session

    def link_workflow(self, session_id: str, workflow_id: str) -> ConversationSession:
        if not workflow_id.strip():
            raise ValueError("workflow_id must not be blank")
        with self._connection:
            return self._set_active_workflow(session_id, workflow_id)

    def create_handoff(
        self,
        owner_user_id: str,
        workflow_id: str,
        source_session_id: str,
        target_session_id: str,
    ) -> WorkflowHandoff:
        if not owner_user_id.strip() or not workflow_id.strip():
            raise ValueError("owner_user_id and workflow_id must not be blank")

        with self._connection:
            self._connection.execute("BEGIN IMMEDIATE")
            source = self._require_session(source_session_id)
            target = self._require_session(target_session_id)
            if source.owner_user_id != owner_user_id or target.owner_user_id != owner_user_id:
                raise OwnerMismatchError("workflow handoff sessions must share the owner")

            handoff = WorkflowHandoff(
                handoff_id=f"handoff_{uuid4().hex}",
                owner_user_id=owner_user_id,
                workflow_id=workflow_id,
                source_session_id=source_session_id,
                target_session_id=target_session_id,
                created_at=datetime.now(timezone.utc),
            )
            self._connection.execute(
                """
                INSERT INTO workflow_handoff (
                  handoff_id, owner_user_id, workflow_id, source_session_id,
                  target_session_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff.handoff_id,
                    handoff.owner_user_id,
                    handoff.workflow_id,
                    handoff.source_session_id,
                    handoff.target_session_id,
                    handoff.created_at.isoformat(),
                ),
            )
        return handoff

    def resolve_handoff(
        self, target_session_id: str, workflow_id: str
    ) -> WorkflowHandoff | None:
        row = self._connection.execute(
            """
            SELECT handoff_id, owner_user_id, workflow_id, source_session_id,
                   target_session_id, created_at
            FROM workflow_handoff
            WHERE target_session_id = ? AND workflow_id = ?
            """,
            (target_session_id, workflow_id),
        ).fetchone()
        return self._handoff_from_row(row) if row is not None else None

    def _find_by_channel(
        self,
        owner_user_id: str,
        channel: ChannelName,
        external_conversation_id: str,
    ) -> ConversationSession | None:
        row = self._connection.execute(
            """
            SELECT session_id, owner_user_id, channel, external_conversation_id,
                   active_workflow_id, created_at, updated_at
            FROM conversation_session
            WHERE owner_user_id = ? AND channel = ? AND external_conversation_id = ?
            """,
            (owner_user_id, channel, external_conversation_id),
        ).fetchone()
        return self._session_from_row(row) if row is not None else None

    def _require_session(self, session_id: str) -> ConversationSession:
        row = self._connection.execute(
            """
            SELECT session_id, owner_user_id, channel, external_conversation_id,
                   active_workflow_id, created_at, updated_at
            FROM conversation_session
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        if row is None:
            raise UnknownSession("channel-local session does not exist")
        return self._session_from_row(row)

    def _set_active_workflow(
        self, session_id: str, workflow_id: str
    ) -> ConversationSession:
        updated_at = datetime.now(timezone.utc)
        cursor = self._connection.execute(
            """
            UPDATE conversation_session
            SET active_workflow_id = ?, updated_at = ?
            WHERE session_id = ?
            """,
            (workflow_id, updated_at.isoformat(), session_id),
        )
        if cursor.rowcount != 1:
            raise UnknownSession("channel-local session does not exist")
        return self._require_session(session_id)

    @staticmethod
    def _session_from_row(row: sqlite3.Row) -> ConversationSession:
        return ConversationSession(
            session_id=row["session_id"],
            owner_user_id=row["owner_user_id"],
            channel=row["channel"],
            external_conversation_id=row["external_conversation_id"],
            active_workflow_id=row["active_workflow_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )

    @staticmethod
    def _handoff_from_row(row: sqlite3.Row) -> WorkflowHandoff:
        return WorkflowHandoff(
            handoff_id=row["handoff_id"],
            owner_user_id=row["owner_user_id"],
            workflow_id=row["workflow_id"],
            source_session_id=row["source_session_id"],
            target_session_id=row["target_session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
