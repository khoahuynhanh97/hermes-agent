from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from hermes_personal.contracts import AgentEvent, AgentEventType, AgentTurnRequest


class AuthorizationError(PermissionError):
    """The authenticated principal is not authorized for the requested turn."""


@dataclass(frozen=True)
class AgentOutput:
    event_type: AgentEventType
    data: Mapping[str, Any]
    workflow_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None
    tool_call_id: str | None = None


class UpstreamAgentPort(Protocol):
    def run(
        self,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
    ) -> Iterator[AgentOutput]: ...


class TranscriptPort(Protocol):
    @property
    def history(self) -> tuple[Mapping[str, Any], ...]: ...

    def append_user_turn(self, text: str) -> None: ...

    def append_event(self, event: AgentEvent) -> None: ...


class TranscriptFactory(Protocol):
    def for_session(self, session_id: str) -> TranscriptPort: ...
