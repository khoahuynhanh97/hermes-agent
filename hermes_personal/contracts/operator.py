from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

from .principal import PrincipalContext

OperatorCommandType = Literal[
    "approve", "reject", "retry", "cancel", "upload", "form_update"
]


@dataclass(frozen=True)
class OperatorCommand:
    principal: PrincipalContext
    command_type: OperatorCommandType
    target_id: str
    expected_version: int
    schema_version: int = 1
    payload: Mapping[str, Any] = field(default_factory=dict)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    command_id: str = field(default_factory=lambda: f"cmd_{uuid4().hex}")
    idempotency_key: str = ""

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported OperatorCommand schema: {self.schema_version}")
        if not self.target_id.strip():
            raise ValueError("target_id must not be blank")
        if self.expected_version < 0:
            raise ValueError("expected_version must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))
        if not self.idempotency_key.strip():
            object.__setattr__(self, "idempotency_key", self.command_id)

    @property
    def owner_user_id(self) -> str:
        return self.principal.owner_user_id
