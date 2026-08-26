from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
from pathlib import Path
from typing import Any

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.outbox_dispatcher import OutboxDispatcher
from hermes_personal.workflows.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


def default_delivery_fn(workflow_id: str, message: str) -> None:
    logger.info("Delivering workflow event [workflow_id=%s]: %s", workflow_id, message)


def run_worker(
    db_path: Path,
    poll_interval: float = 1.0,
    stop_event: threading.Event | None = None,
) -> None:
    if stop_event is None:
        stop_event = threading.Event()

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    repo = OutboxRepository(connection)
    dispatcher = OutboxDispatcher(
        repository=repo,
        delivery_fn=default_delivery_fn,
        worker_id=f"durable-worker-{os.getpid()}",
    )

    logger.info("Durable worker started (worker_id=%s, db=%s)", dispatcher.worker_id, db_path)
    try:
        while not stop_event.is_set():
            try:
                dispatcher.reclaim_expired()
                dispatcher.process_batch(batch_size=10)
            except Exception as e:
                logger.error("Error in worker polling loop: %s", e, exc_info=True)

            stop_event.wait(poll_interval)
    finally:
        logger.info("Closing database connection for durable worker...")
        try:
            connection.close()
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hermes durable background worker")
    parser.add_argument("--db-path", default=None, help="Path to SQLite database")
    parser.add_argument("--poll-interval", type=float, default=1.0, help="Poll interval in seconds")
    args = parser.parse_args(argv)

    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
    db_path = Path(args.db_path) if args.db_path else home / "hermes.db"

    stop_event = threading.Event()

    def _signal_handler(signum: int, frame: Any) -> None:
        logger.info("Received signal %s, stopping worker...", signum)
        stop_event.set()

    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except (ValueError, AttributeError):
        pass

    run_worker(db_path=db_path, poll_interval=args.poll_interval, stop_event=stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
