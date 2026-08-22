from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

from .principal import ChannelName, PrincipalContext

AttachmentKind = Literal["image", "video", "audio", "document", "other"]


@dataclass(frozen=True)
class AttachmentRef:
    attachment_id: str
    kind: AttachmentKind
    media_type: str
    uri: str
    size_bytes: int | None = None
    digest_sha256: str | None = None

    def __post_init__(self) -> None:
        if not self.attachment_id.strip() or not self.uri.strip():
            raise ValueError("attachment_id and uri must not be blank")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be non-negative")
        if self.digest_sha256 is not None:
            digest = self.digest_sha256
            if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                raise ValueError("digest_sha256 must be lowercase SHA-256")


@dataclass(frozen=True)
class ChannelCapabilities:
    streaming: bool = False
    interactive_controls: bool = False
    attachments: bool = False


@dataclass(frozen=True)
class AgentTurnRequest:
    principal: PrincipalContext
    message: str
    schema_version: int = 1
    attachments: tuple[AttachmentRef, ...] = ()
    conversation_history: tuple[Mapping[str, Any], ...] = ()
    enabled_toolsets: tuple[str, ...] = ()
    workflow_id: str | None = None
    locale: str = "vi-VN"
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    turn_id: str = field(default_factory=lambda: f"turn_{uuid4().hex}")
    idempotency_key: str = ""
    channel_capabilities: ChannelCapabilities = field(default_factory=ChannelCapabilities)

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported AgentTurnRequest schema: {self.schema_version}")
        if not self.message.strip() and not self.attachments:
            raise ValueError("message or attachment is required")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(
            self,
            "conversation_history",
            tuple(MappingProxyType(dict(message)) for message in self.conversation_history),
        )
        if not self.idempotency_key.strip():
            object.__setattr__(self, "idempotency_key", self.turn_id)

    @property
    def channel(self) -> ChannelName:
        return self.principal.channel

    @property
    def session_id(self) -> str:
        return self.principal.session_id
