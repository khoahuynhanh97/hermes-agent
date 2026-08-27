from __future__ import annotations

import sqlite3
import threading
import time
from typing import Callable, List, Tuple

import pytest

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.outbox_dispatcher import OutboxDispatcher
from hermes_personal.workflows.outbox_repository import OutboxRepository


def run_worker(
    db_path: str,
    poll_interval: float = 0.1,
    stop_event: threading.Event | None = None,
    delivery_fn: Callable[[str, str], None] | None = None,
    worker_id: str = "worker-1",
) -> None:
    if stop_event is None:
        stop_event = threading.Event()
    if delivery_fn is None:
        delivery_fn = lambda wf, msg: None

    conn = connect(db_path)
    repo = OutboxRepository(conn)
    dispatcher = OutboxDispatcher(repo, delivery_fn, worker_id=worker_id)

    while not stop_event.is_set():
        dispatcher.reclaim_expired()
        dispatcher.process_batch()
        stop_event.wait(timeout=poll_interval)


def test_worker_process_startup_delivery_ack_and_clean_shutdown(tmp_path):
    db_file = tmp_path / "worker_test.db"
    db_path = str(db_file)

    # Initialize DB and enqueue messages
    conn = connect(db_path)
    repo = OutboxRepository(conn)
    repo.enqueue("wf_w1", "msg_w1")
    repo.enqueue("wf_w2", "msg_w2")
    conn.close()

    delivered: List[Tuple[str, str]] = []
    lock = threading.Lock()

    def delivery_fn(workflow_id: str, message: str) -> None:
        with lock:
            delivered.append((workflow_id, message))

    stop_evt = threading.Event()
    worker_thread = threading.Thread(
        target=run_worker,
        args=(db_path,),
        kwargs={
            "poll_interval": 0.05,
            "stop_event": stop_evt,
            "delivery_fn": delivery_fn,
            "worker_id": "integration-worker",
        },
        daemon=True,
    )

    worker_thread.start()

    # Wait for worker loop to claim, deliver, and ACK messages
    deadline = time.time() + 5.0
    while time.time() < deadline:
        with lock:
            if len(delivered) >= 2:
                break
        time.sleep(0.05)

    with lock:
        assert delivered == [("wf_w1", "msg_w1"), ("wf_w2", "msg_w2")]

    # Verify messages are ACKed and outbox table is empty
    verify_conn = connect(db_path)
    cur = verify_conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM workflow_outbox")
    assert cur.fetchone()["cnt"] == 0
    verify_conn.close()

    # Clean shutdown via stop_evt.set()
    stop_evt.set()
    worker_thread.join(timeout=2.0)
    assert not worker_thread.is_alive()


def test_worker_stops_on_fatal_persistence_error(tmp_path):
    """Test that FatalPersistenceError in durable worker polling loop halts the worker immediately."""
    from hermes_personal.workflows.worker import run_worker
    from hermes_personal.workflows.outbox_dispatcher import FatalPersistenceError

    db_file = tmp_path / "fatal_db.db"
    conn = connect(db_file)
    repo = OutboxRepository(conn)
    repo.enqueue("wf_fatal_1", "msg_1")
    conn.close()

    def faulty_delivery(wf_id, msg):
        raise ValueError("Simulated delivery error")

    orig_record = OutboxRepository.record_failure

    def broken_record_failure(self, *args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error during record_failure")

    OutboxRepository.record_failure = broken_record_failure  # type: ignore
    try:
        stop_evt = threading.Event()
        with pytest.raises(FatalPersistenceError, match="Failed to persist outbox error state"):
            run_worker(
                db_path=db_file,
                poll_interval=0.01,
                stop_event=stop_evt,
                delivery_fn=faulty_delivery,
                provider_mode="fake",
            )
    finally:
        OutboxRepository.record_failure = orig_record  # type: ignore
