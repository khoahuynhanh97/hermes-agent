from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CorrelationContext:
    """Immutable correlation context propagated across turns, workflows, jobs, and tools."""

    owner_user_id: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    workflow_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None
    tool_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_log_fields(self) -> dict[str, Any]:
        """Convert non-empty correlation fields to a dictionary for structured logging."""
        fields: dict[str, Any] = {}
        if self.owner_user_id is not None:
            fields["owner_user_id"] = self.owner_user_id
        if self.session_id is not None:
            fields["session_id"] = self.session_id
        if self.turn_id is not None:
            fields["turn_id"] = self.turn_id
        if self.workflow_id is not None:
            fields["workflow_id"] = self.workflow_id
        if self.job_id is not None:
            fields["job_id"] = self.job_id
        if self.approval_id is not None:
            fields["approval_id"] = self.approval_id
        if self.tool_id is not None:
            fields["tool_id"] = self.tool_id
        if self.extra:
            fields.update(self.extra)
        return fields

    def with_child(self, **kwargs: Any) -> CorrelationContext:
        """Create a child correlation context inheriting parent values with overrides."""
        merged = {
            "owner_user_id": self.owner_user_id,
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "workflow_id": self.workflow_id,
            "job_id": self.job_id,
            "approval_id": self.approval_id,
            "tool_id": self.tool_id,
            "extra": dict(self.extra),
        }
        for k, v in kwargs.items():
            if k in merged and k != "extra":
                merged[k] = v
            else:
                merged["extra"][k] = v
        return CorrelationContext(**merged)
