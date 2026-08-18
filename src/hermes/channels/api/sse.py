from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter()

_subscribers: dict[str, list[dict[str, Any]]] = defaultdict(list)


def publish(event_type: str, data: dict[str, Any]) -> None:
    for subscriber in _subscribers.get(event_type, []):
        subscriber["queue"].append({"type": event_type, "data": data})


@router.get("/events")
async def sse_events(event_type: str | None = None):
    import asyncio
    queue: list[dict[str, Any]] = []

    if event_type:
        _subscribers[event_type].append({"queue": queue})

    async def event_generator():
        try:
            while True:
                if queue:
                    event = queue.pop(0)
                    yield f"event: {event['type']}\ndata: {event['data']}\n\n"
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass
        finally:
            if event_type and {"queue": queue} in _subscribers.get(event_type, []):
                _subscribers[event_type].remove({"queue": queue})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )