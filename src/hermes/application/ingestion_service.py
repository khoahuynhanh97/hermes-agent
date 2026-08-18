from __future__ import annotations

import uuid
from typing import Any

from hermes.domain.ingestion import IngestionRequest
from hermes.domain.results import Result


class NotificationPort:
    def publish(self, event: dict[str, Any]) -> Result[None]:
        raise NotImplementedError


class IngestionService:
    def __init__(self, notification_port: NotificationPort | None = None):
        self.notification_port = notification_port
        self.requests: list[IngestionRequest] = []

    def submit(self, source: str, source_type: str, requested_action: str, payload: dict[str, Any] | None = None) -> Result[IngestionRequest]:
        request = IngestionRequest(
            id=str(uuid.uuid4()),
            source=source,
            source_type=source_type,
            requested_action=requested_action,
            payload=payload or {},
        )
        self.requests.append(request)
        if self.notification_port is not None:
            self.notification_port.publish({
                "event": "ingestion_submitted",
                "request_id": request.id,
                "source_type": source_type,
                "requested_action": requested_action,
            })
        return Result.success(request)