from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from hermes_personal.contracts import ChannelName


@dataclass(frozen=True)
class GlobalUserIdentity:
    owner_user_id: str
    display_name: str
    created_at: datetime


@dataclass(frozen=True)
class ChannelIdentity:
    channel: ChannelName
    external_subject: str
    owner_user_id: str
    created_at: datetime


class UnknownIdentity(LookupError):
    """The authenticated channel subject has no owner mapping."""


class IdentityConflict(ValueError):
    """A channel subject is already linked to a different owner."""
