from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.envelope import OutboxEnvelope
from hermes_personal.workflows.outbox_dispatcher import OutboxDispatcher
from hermes_personal.workflows.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


def run_worker(
    db_path: str | Path,
    poll_interval: float = 1.0,
    stop_event: Optional[threading.Event] = None,
    topic_handlers: Optional[Dict[str, Callable[[OutboxEnvelope], None]]] = None,
    delivery_fn: Optional[Callable[[str, str], None]] = None,
    worker_id: Optional[str] = None,
    tool_registry: Any | None = None,
    provider_mode: Optional[str] = None,
) -> None:
    """Run the durable outbox worker loop."""
    if stop_event is None:
        stop_event = threading.Event()

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    repo = OutboxRepository(connection)

    _provider_mode = provider_mode or os.environ.get("HERMES_PROVIDER_MODE", "configured")

    if topic_handlers is None and delivery_fn is None:
        from hermes_personal.product_video.handlers import create_product_video_topic_handlers
        from hermes_personal.workflows.engine import WorkflowEngine
        from hermes_personal.workflows.repository import WorkflowRepository

        wf_repo = WorkflowRepository(connection)
        wf_engine = WorkflowEngine(wf_repo)
        topic_handlers = create_product_video_topic_handlers(
            workflow_engine=wf_engine,
            workflow_repository=wf_repo,
            tool_registry=tool_registry,
            provider_mode=_provider_mode,
        )

    _worker_id = worker_id or f"durable-worker-{os.getpid()}"
    dispatcher = OutboxDispatcher(
        repository=repo,
        delivery_fn=delivery_fn,
        worker_id=_worker_id,
        topic_handlers=topic_handlers,
    )

    logger.info("Durable worker started (db=%s, worker_id=%s, provider_mode=%s)", db_path, _worker_id, _provider_mode)
    try:
        while not stop_event.is_set():
            try:
                dispatcher.reclaim_expired()
                dispatcher.process_batch(batch_size=10)
            except Exception as exc:  # noqa: BLE001
                logger.error("Error in durable worker polling loop: %s", exc, exc_info=True)
            stop_event.wait(poll_interval)
    finally:
        logger.info("Durable worker shutting down, closing database connection...")
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes durable background worker")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database file")
    parser.add_argument(
        "--poll-interval", type=float, default=1.0, help="Poll interval in seconds"
    )
    parser.add_argument(
        "--provider-mode",
        choices=["configured", "fake"],
        default=os.environ.get("HERMES_PROVIDER_MODE", "configured"),
        help="Provider mode ('configured' for live MCP/provider resolution, 'fake' for offline deterministic test)",
    )
    args = parser.parse_args(argv)

    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    db_path = Path(args.db_path) if args.db_path else home / "hermes.db"

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %s, stopping durable worker...", signum)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, AttributeError):
        pass

    run_worker(
        db_path=db_path,
        poll_interval=args.poll_interval,
        stop_event=stop_event,
        provider_mode=args.provider_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
