from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from hermes_personal.contracts import AgentEvent


class TranscriptStore(Protocol):
    def load_transcript(self, session_id: str) -> list[dict[str, Any]]: ...

    def append_to_transcript(
        self, session_id: str, message: dict[str, Any], skip_db: bool = False
    ) -> None: ...


class UpstreamTranscriptAdapter:
    def __init__(self, store: TranscriptStore, session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            MappingProxyType(deepcopy(message))
            for message in self._store.load_transcript(self._session_id)
        )

    def append_user_turn(self, text: str) -> None:
        self._store.append_to_transcript(
            self._session_id, {"role": "user", "content": text}, skip_db=False
        )

    def append_event(self, event: AgentEvent) -> None:
        text = event.data.get("text", "")
        message = {
            "role": "assistant",
            "content": text if isinstance(text, str) else "",
            "timestamp": event.occurred_at.isoformat(),
            "event_metadata": {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "turn_id": event.turn_id,
                "sequence": event.sequence,
                "workflow_id": event.workflow_id,
                "job_id": event.job_id,
                "approval_id": event.approval_id,
                "tool_call_id": event.tool_call_id,
                "data": dict(event.data),
            },
        }
        self._store.append_to_transcript(self._session_id, message, skip_db=False)
