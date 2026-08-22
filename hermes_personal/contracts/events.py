from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import MappingProxyType
from typing import Any, Literal, Mapping
from uuid import uuid4

AgentEventType = Literal[
    "text_delta",
    "clarification_required",
    "tool_activity",
    "workflow_state",
    "approval_required",
    "cost_update",
    "artifact",
    "warning",
    "completed",
    "failed",
]


@dataclass(frozen=True)
class AgentEvent:
    event_type: AgentEventType
    principal_id: str
    session_id: str
    turn_id: str
    sequence: int
    schema_version: int = 1
    data: Mapping[str, Any] = field(default_factory=dict)
    workflow_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None
    tool_call_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: f"evt_{uuid4().hex}")

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported AgentEvent schema: {self.schema_version}")
        for field_name in ("principal_id", "session_id", "turn_id"):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be blank")
        if self.sequence < 0:
            raise ValueError("sequence must be non-negative")
        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")
        object.__setattr__(self, "data", MappingProxyType(dict(self.data)))
