from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelTier(str, Enum):
    FAST = "fast"
    REASON = "reason"
    VISION = "vision"
    CODE = "code"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str

    @staticmethod
    def user(content: str) -> "Message":
        return Message(role=MessageRole.USER, content=content)

    @staticmethod
    def assistant(content: str) -> "Message":
        return Message(role=MessageRole.ASSISTANT, content=content)

    @staticmethod
    def system(content: str) -> "Message":
        return Message(role=MessageRole.SYSTEM, content=content)


@dataclass(frozen=True)
class ModelRequest:
    tier: str # Change type to str to allow direct string assignment
    messages: list[Message]
    correlation_id: str | None = None
    timeout_seconds: int = 60
    json_schema: dict[str, Any] | None = None

    def __post_init__(self):
        # Validate that the string value of tier is a valid ModelTier member
        if self.tier not in [t.value for t in ModelTier]:
            raise ValueError(f"Invalid model tier: {self.tier}. Must be one of {[t.value for t in ModelTier]}.")

        # Convert tier string to ModelTier enum internally for consistency if needed later
        # For now, keeping it as string for direct comparison
        # object.__setattr__(self, 'tier', ModelTier(self.tier)) # This would convert it, but might interfere with frozen=True and direct string assignment

    @staticmethod
    def fast(messages: list[Message], correlation_id: str | None = None, timeout_seconds: int = 60) -> "ModelRequest":
        return ModelRequest(ModelTier.FAST.value, messages, correlation_id, timeout_seconds)

    @staticmethod
    def reason(messages: list[Message], correlation_id: str | None = None, timeout_seconds: int = 120, json_schema: dict[str, Any] | None = None) -> "ModelRequest":
        return ModelRequest(ModelTier.REASON.value, messages, correlation_id, timeout_seconds, json_schema)

    @staticmethod
    def vision(messages: list[Message], correlation_id: str | None = None, timeout_seconds: int = 120) -> "ModelRequest":
        return ModelRequest(ModelTier.VISION.value, messages, correlation_id, timeout_seconds)

    @staticmethod
    def code(messages: list[Message], correlation_id: str | None = None, timeout_seconds: int = 120) -> "ModelRequest":
        return ModelRequest(ModelTier.CODE.value, messages, correlation_id, timeout_seconds)


@dataclass(frozen=True)
class ModelResponse:
    content: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0
