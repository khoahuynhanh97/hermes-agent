from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, cast

from hermes_personal.contracts import (
    AgentTurnRequest,
    AttachmentRef,
    ChannelCapabilities,
    ChannelName,
    PrincipalContext,
)
from hermes_personal.identity import IdentityRepository
from hermes_personal.sessions import ConversationSession, SessionRepository


_CHANNEL_CAPABILITIES: dict[ChannelName, ChannelCapabilities] = {
    "telegram": ChannelCapabilities(
        streaming=True, interactive_controls=True, attachments=True
    ),
    "cli": ChannelCapabilities(
        streaming=True, interactive_controls=False, attachments=True
    ),
    "web": ChannelCapabilities(
        streaming=True, interactive_controls=True, attachments=True
    ),
    "omni": ChannelCapabilities(
        streaming=True, interactive_controls=True, attachments=True
    ),
}


class ChannelTurnNormalizer:
    """Construct canonical turns from authenticated channel envelopes only."""

    def __init__(
        self,
        channel: ChannelName,
        identity_repository: IdentityRepository,
        session_repository: SessionRepository,
    ) -> None:
        if channel not in _CHANNEL_CAPABILITIES:
            raise ValueError(f"unsupported channel: {channel}")
        self._channel = cast(ChannelName, channel)
        self._identity_repository = identity_repository
        self._session_repository = session_repository

    def normalize(
        self,
        *,
        external_subject: str,
        external_conversation_id: str,
        message: str,
        attachments: Iterable[AttachmentRef] = (),
        channel_capabilities: ChannelCapabilities | None = None,
        authenticated_idempotency_key: str | None = None,
        workflow_id: str | None = None,
        locale: str = "vi-VN",
        occurred_at: datetime | None = None,
    ) -> AgentTurnRequest:
        self._validate_text_inputs(
            external_subject, external_conversation_id, message, workflow_id
        )
        typed_attachments = self._typed_attachments(attachments)
        if not message.strip() and not typed_attachments:
            raise ValueError("message or attachment is required")
        if channel_capabilities is not None and not isinstance(
            channel_capabilities, ChannelCapabilities
        ):
            raise ValueError("channel_capabilities must be ChannelCapabilities")
        if authenticated_idempotency_key is not None and (
            not isinstance(authenticated_idempotency_key, str)
            or not authenticated_idempotency_key.strip()
        ):
            raise ValueError("authenticated_idempotency_key must not be blank")

        # Resolve the authenticated subject before any session can be materialized.
        owner = self._identity_repository.resolve(self._channel, external_subject)
        session = self._session_repository.get_or_create(
            owner.owner_user_id, self._channel, external_conversation_id
        )
        self._authorize_workflow(session, owner.owner_user_id, workflow_id)

        return AgentTurnRequest(
            principal=PrincipalContext(
                actor_id=external_subject,
                owner_user_id=owner.owner_user_id,
                channel=self._channel,
                session_id=session.session_id,
            ),
            message=message,
            attachments=typed_attachments,
            workflow_id=workflow_id,
            locale=locale,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            idempotency_key=authenticated_idempotency_key or "",
            channel_capabilities=channel_capabilities
            or _CHANNEL_CAPABILITIES[self._channel],
        )

    @staticmethod
    def _validate_text_inputs(
        external_subject: str,
        external_conversation_id: str,
        message: str,
        workflow_id: str | None,
    ) -> None:
        for field_name, value in (
            ("external_subject", external_subject),
            ("external_conversation_id", external_conversation_id),
            ("message", message),
        ):
            if not isinstance(value, str):
                raise ValueError(f"{field_name} must be text")
            if field_name != "message" and not value.strip():
                raise ValueError(f"{field_name} must not be blank")
        if workflow_id is not None and (
            not isinstance(workflow_id, str) or not workflow_id.strip()
        ):
            raise ValueError("workflow_id must not be blank")

    @staticmethod
    def _typed_attachments(
        attachments: Iterable[AttachmentRef],
    ) -> tuple[AttachmentRef, ...]:
        result = tuple(attachments)
        if any(not isinstance(attachment, AttachmentRef) for attachment in result):
            raise ValueError("attachments must contain AttachmentRef values")
        return result

    def _authorize_workflow(
        self,
        session: ConversationSession,
        owner_user_id: str,
        workflow_id: str | None,
    ) -> None:
        if workflow_id is None or workflow_id == session.active_workflow_id:
            return
        handoff = self._session_repository.resolve_handoff(session.session_id, workflow_id)
        if (
            handoff is None
            or handoff.owner_user_id != owner_user_id
            or handoff.target_session_id != session.session_id
        ):
            raise PermissionError("workflow is not authorized for this session")
