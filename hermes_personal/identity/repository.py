from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from hermes_personal.contracts import ChannelName

from .models import ChannelIdentity, GlobalUserIdentity, IdentityConflict, UnknownIdentity


class IdentityRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create_owner(self, display_name: str) -> GlobalUserIdentity:
        owner = GlobalUserIdentity(
            owner_user_id=uuid4().hex,
            display_name=display_name,
            created_at=datetime.now(timezone.utc),
        )
        with self._connection:
            self._connection.execute(
                """
                INSERT INTO global_user_identity (owner_user_id, display_name, created_at)
                VALUES (?, ?, ?)
                """,
                (owner.owner_user_id, owner.display_name, owner.created_at.isoformat()),
            )
        return owner

    def link(
        self,
        owner_user_id: str,
        channel: ChannelName,
        external_subject: str,
    ) -> ChannelIdentity:
        if not external_subject.strip():
            raise ValueError("external_subject must not be blank")

        identity = ChannelIdentity(
            channel=channel,
            external_subject=external_subject,
            owner_user_id=owner_user_id,
            created_at=datetime.now(timezone.utc),
        )
        try:
            with self._connection:
                self._connection.execute(
                    """
                    INSERT INTO channel_identity (
                      channel, external_subject, owner_user_id, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        identity.channel,
                        identity.external_subject,
                        identity.owner_user_id,
                        identity.created_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed: channel_identity.channel, channel_identity.external_subject" in str(error):
                raise IdentityConflict(
                    "channel subject is already linked to an owner"
                ) from error
            raise
        return identity

    def resolve(
        self, channel: ChannelName, external_subject: str
    ) -> GlobalUserIdentity:
        row = self._connection.execute(
            """
            SELECT global_user_identity.owner_user_id,
                   global_user_identity.display_name,
                   global_user_identity.created_at
            FROM channel_identity
            JOIN global_user_identity
              ON global_user_identity.owner_user_id = channel_identity.owner_user_id
            WHERE channel_identity.channel = ?
              AND channel_identity.external_subject = ?
            """,
            (channel, external_subject),
        ).fetchone()
        if row is None:
            raise UnknownIdentity("authenticated channel subject has no owner mapping")
        return GlobalUserIdentity(
            owner_user_id=row["owner_user_id"],
            display_name=row["display_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
