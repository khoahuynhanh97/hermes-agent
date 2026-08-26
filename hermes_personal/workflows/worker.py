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
) -> None:
    """Run the durable outbox worker loop.

    Preferred usage: pass ``topic_handlers`` for typed envelope routing.
    The worker claims pending outbox rows, routes each to the appropriate
    topic handler, and ACKs on success.

    If neither ``topic_handlers`` nor ``delivery_fn`` is provided the worker
    runs **fail-closed**: every claim raises ``delivery_unconfigured``,
    triggering ``record_failure``.  Messages remain durable and exhaust
    ``max_attempts`` before quarantine.  This is the correct behaviour when no
    concrete consumer has been registered yet (e.g. HP-007 scope before the
    JobRepository consumer is wired in HP-008).

    ``delivery_fn`` is accepted for backward-compatibility with existing tests
    that pass a plain ``(workflow_id, message) -> None`` callable.
    """
    if stop_event is None:
        stop_event = threading.Event()

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = connect(db_path)
    repo = OutboxRepository(connection)

    _worker_id = worker_id or f"durable-worker-{os.getpid()}"
    dispatcher = OutboxDispatcher(
        repository=repo,
        delivery_fn=delivery_fn,
        worker_id=_worker_id,
        topic_handlers=topic_handlers,
    )

    logger.info("Durable worker started (db=%s, worker_id=%s)", db_path, _worker_id)
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
        # Not in main thread or platform doesn't support signals.
        pass

    # No topic_handlers registered for HP-007 – worker runs fail-closed.
    # The concrete JobRepository consumer will be wired in HP-008.
    run_worker(db_path=db_path, poll_interval=args.poll_interval, stop_event=stop_event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
