from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hermes_personal.contracts import ChannelName


@dataclass(frozen=True)
class ConversationSession:
    session_id: str
    owner_user_id: str
    channel: ChannelName
    external_conversation_id: str
    active_workflow_id: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class WorkflowHandoff:
    handoff_id: str
    owner_user_id: str
    workflow_id: str
    source_session_id: str
    target_session_id: str
    created_at: datetime


class UnknownSession(LookupError):
    """The requested channel-local session does not exist."""


class OwnerMismatchError(ValueError):
    """A handoff may only connect sessions owned by the same user."""
