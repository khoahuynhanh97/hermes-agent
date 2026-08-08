"""Independent, bounded delivery for canonical job outbox events."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Protocol

from hermes.domain.results import Result
from hermes.jobs import JobRepository
from hermes.adapters.telegram.notification_adapter import TelegramNotificationAdapter


class EventDeliveryAdapter(Protocol):
    def publish(self, event: dict[str, Any]) -> Result[None]: ...


class FileDeliveryAdapter:
    """Deterministic local destination used by CLI/GUI integrations and tests."""

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def publish(self, event: dict[str, Any]) -> Result[None]:
        event_id = str(event["event_id"])
        destination = self.root / f"{event_id}.json"
        if destination.exists():
            return Result.success(None)
        fd, temporary = tempfile.mkstemp(prefix=f"{event_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(_public_event(event), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            os.replace(temporary, destination)
        except Exception as error:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            return Result.failure("delivery_failed", str(error))
        return Result.success(None)


class TelegramEventDeliveryAdapter:
    """Deterministic Telegram transport wrapper; it does not choose next work."""

    def __init__(self, bot):
        self.transport = TelegramNotificationAdapter(bot)

    def publish(self, event: dict[str, Any]) -> Result[None]:
        payload = event.get("payload") or {}
        chat_id = payload.get("chat_id")
        if not chat_id:
            return Result.failure("destination_missing", "No Telegram chat is associated with this job.")
        status = payload.get("status", "completed")
        message = f"Job {event['aggregate_id']} {status}: {payload.get('task_type', 'job')}"
        return self.transport.publish({"chat_id": chat_id, "message": message})


class DeliveryConsumer:
    def __init__(self, repository: JobRepository, adapter: EventDeliveryAdapter, worker_id: str = "delivery-worker"):
        self.repository = repository
        self.adapter = adapter
        self.worker_id = worker_id

    def run_once(self) -> dict | None:
        event = self.repository.claim_event(worker_id=self.worker_id)
        if not event:
            return None
        try:
            result = self.adapter.publish(event)
            if result.ok:
                return self.repository.complete_event(event["event_id"])
            return self.repository.fail_event(
                event["event_id"], result.message or result.error_code or "delivery failed"
            )
        except Exception as error:
            return self.repository.fail_event(event["event_id"], str(error))


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    payload = dict(event.get("payload") or {})
    payload.pop("chat_id", None)
    return {
        "event_id": event["event_id"],
        "event_type": event["event_type"],
        "aggregate_type": event["aggregate_type"],
        "aggregate_id": event["aggregate_id"],
        "owner_user_id": event["owner_user_id"],
        "occurred_at": event["occurred_at"],
        "payload": payload,
    }
