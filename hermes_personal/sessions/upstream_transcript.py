from __future__ import annotations

from copy import deepcopy
from types import MappingProxyType
from typing import Any, Mapping, Protocol

from hermes_personal.contracts import AgentEvent, to_primitive


class TranscriptStore(Protocol):
    def load_transcript(self, session_id: str) -> list[dict[str, Any]]: ...

    def append_to_transcript(
        self, session_id: str, message: dict[str, Any], skip_db: bool = False
    ) -> None: ...


def _freeze_transcript_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {key: _freeze_transcript_value(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_transcript_value(item) for item in value)
    return value


class UpstreamTranscriptAdapter:
    def __init__(self, store: TranscriptStore, session_id: str) -> None:
        self._store = store
        self._session_id = session_id

    @property
    def history(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(
            _freeze_transcript_value(deepcopy(message))
            for message in self._store.load_transcript(self._session_id)
        )

    def append_user_turn(self, text: str) -> None:
        self._store.append_to_transcript(
            self._session_id, {"role": "user", "content": text}, skip_db=False
        )

    def append_event(self, event: AgentEvent) -> None:
        event_metadata = to_primitive(event)
        text = event_metadata["data"].get("text", "")
        message = {
            "role": "assistant",
            "content": text if isinstance(text, str) else "",
            "timestamp": event.occurred_at.isoformat(),
            "event_metadata": event_metadata,
        }
        self._store.append_to_transcript(self._session_id, message, skip_db=False)
