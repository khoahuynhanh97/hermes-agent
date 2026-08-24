from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from hermes_personal.contracts.events import AgentEvent
from hermes_personal.contracts.operator import OperatorCommand, OperatorCommandType
from hermes_personal.contracts.principal import PrincipalContext


@dataclass(frozen=True)
class ArtifactRecord:
    """Canonical artifact metadata with immutable versioning and owning context."""

    artifact_id: str
    owner_user_id: str
    artifact_type: str
    version: int
    digest: str
    delivery_ref: str
    metadata: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "owner_user_id": self.owner_user_id,
            "artifact_type": self.artifact_type,
            "version": self.version,
            "digest": self.digest,
            "delivery_ref": self.delivery_ref,
            "metadata": dict(self.metadata),
        }


class EventsAPI:
    """Events, Operator Command, and Artifact Metadata API service for Web and Omni ingress."""

    def __init__(
        self,
        event_store: list[AgentEvent] | None = None,
        artifact_store: dict[str, ArtifactRecord] | None = None,
        command_handler: Callable[[OperatorCommand], dict[str, Any]] | None = None,
        auth_validator: Callable[[str, str], bool] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._events: list[AgentEvent] = event_store if event_store is not None else []
        self._artifacts: dict[str, ArtifactRecord] = artifact_store if artifact_store is not None else {}
        self._command_handler = command_handler
        self._auth_validator = auth_validator or (lambda token, owner: bool(token and token.strip()))
        self._clock = clock

    def add_event(self, event: AgentEvent) -> None:
        self._events.append(event)

    def add_artifact(self, artifact: ArtifactRecord) -> None:
        self._artifacts[artifact.artifact_id] = artifact

    def get_events(
        self,
        owner_id: str,
        after_seq: int = 0,
        limit: int = 100,
        auth_token: str = "",
    ) -> tuple[int, dict[str, Any]]:
        """Fetch committed events by owner and monotonic sequence for replay/resume."""
        if not self._auth_validator(auth_token, owner_id):
            return 403, {"error": "unauthorized", "message": "Invalid authentication credentials"}

        matched = [
            e
            for e in self._events
            if (e.principal_id == owner_id or getattr(e, "owner_user_id", None) == owner_id)
            and e.sequence > after_seq
        ]
        matched.sort(key=lambda e: e.sequence)
        slice_events = matched[:limit]

        events_data = [
            {
                "event_id": e.event_id,
                "event_type": e.event_type,
                "principal_id": e.principal_id,
                "session_id": e.session_id,
                "turn_id": e.turn_id,
                "sequence": e.sequence,
                "data": dict(e.data),
                "workflow_id": e.workflow_id,
                "job_id": e.job_id,
                "approval_id": e.approval_id,
                "occurred_at": e.occurred_at.isoformat(),
            }
            for e in slice_events
        ]
        next_seq = slice_events[-1].sequence if slice_events else after_seq
        return 200, {
            "events": events_data,
            "next_cursor": next_seq,
            "count": len(events_data),
        }

    def format_sse_event(self, event: AgentEvent) -> str:
        """Format an AgentEvent into a Server-Sent Event frame."""
        data_payload = json.dumps({
            "event_id": event.event_id,
            "event_type": event.event_type,
            "principal_id": event.principal_id,
            "session_id": event.session_id,
            "turn_id": event.turn_id,
            "sequence": event.sequence,
            "data": dict(event.data),
            "workflow_id": event.workflow_id,
            "job_id": event.job_id,
            "approval_id": event.approval_id,
            "occurred_at": event.occurred_at.isoformat(),
        })
        return f"id: {event.sequence}\nevent: {event.event_type}\ndata: {data_payload}\n\n"

    def format_sse_heartbeat(self) -> str:
        """Format a separate SSE heartbeat ping."""
        data_payload = json.dumps({"timestamp": self._clock()})
        return f"event: heartbeat\ndata: {data_payload}\n\n"

    def handle_operator_command(
        self,
        auth_token: str,
        owner_id: str,
        command_type: OperatorCommandType,
        target_id: str,
        expected_version: int,
        payload: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        """Submit an authenticated operator command (approval, rejection, pause, etc.)."""
        if not self._auth_validator(auth_token, owner_id):
            return 403, {"error": "forbidden", "message": "Operator authentication failed"}

        if not target_id:
            return 400, {"error": "bad_request", "message": "target_id required"}

        principal = PrincipalContext(
            actor_id=owner_id,
            owner_user_id=owner_id,
            channel="web",
            session_id=f"op_{owner_id}",
        )
        cmd = OperatorCommand(
            principal=principal,
            command_type=command_type,
            target_id=target_id,
            expected_version=expected_version,
            payload=payload or {},
        )

        if self._command_handler is not None:
            try:
                res = self._command_handler(cmd)
                return 200, {"status": "ok", "command_id": cmd.command_id, "result": res}
            except Exception as ex:
                return 400, {"error": "command_failed", "message": str(ex)}

        return 200, {"status": "accepted", "command_id": cmd.command_id}

    def get_artifact(
        self,
        artifact_id: str,
        owner_id: str,
        auth_token: str = "",
    ) -> tuple[int, dict[str, Any]]:
        """Retrieve canonical artifact metadata with owner isolation."""
        if not self._auth_validator(auth_token, owner_id):
            return 403, {"error": "forbidden", "message": "Authentication required"}

        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            return 404, {"error": "not_found", "message": f"Artifact '{artifact_id}' not found"}

        if artifact.owner_user_id != owner_id:
            return 403, {"error": "forbidden", "message": "Access denied to foreign artifact"}

        return 200, artifact.as_dict()
