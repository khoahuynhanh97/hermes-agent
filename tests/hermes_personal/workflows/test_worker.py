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


def test_configured_worker_wires_grounded_creative_generator(tmp_path, monkeypatch):
    """Configured workers must not silently fall back to an empty legacy brief."""
    import hermes_personal.product_video.handlers as handlers_module

    creative_generator = object()
    captured = {}
    monkeypatch.setattr(
        handlers_module,
        "create_configured_creative_generator",
        lambda: creative_generator,
        raising=False,
    )
    monkeypatch.setattr(
        handlers_module,
        "create_product_video_topic_handlers",
        lambda **kwargs: captured.update(kwargs) or {},
    )
    monkeypatch.setattr("tools.mcp_tool.discover_mcp_tools", lambda: None)

    from hermes_personal.workflows.worker import run_worker

    run_worker(
        db_path=tmp_path / "configured-worker.db",
        provider_mode="configured",
        once=True,
    )

    assert captured["creative_generator"] is creative_generator


def test_worker_main_uses_canonical_hermes_home_and_respects_explicit_db_path(tmp_path, monkeypatch):
    """Test that worker.main resolves canonical hermes home, isolates config/dotenv, and respects explicit --db-path."""
    import os
    from pathlib import Path
    import hermes_constants
    import hermes_personal.workflows.worker as worker_module

    recorded_dotenv_homes = []
    recorded_config_calls = []
    recorded_run_calls = []

    def mock_load_dotenv(hermes_home=None):
        recorded_dotenv_homes.append(hermes_home)

    def mock_load_config():
        recorded_config_calls.append(True)
        return {}

    def mock_run_worker(db_path, poll_interval=1.0, stop_event=None, delivery_fn=None, provider_mode=None, **kwargs):
        recorded_run_calls.append({
            "db_path": Path(db_path),
            "poll_interval": poll_interval,
            "provider_mode": provider_mode,
        })
        return 0

    # Stub dotenv, config, and run_worker before any worker.main execution
    monkeypatch.setattr("hermes_cli.env_loader.load_hermes_dotenv", mock_load_dotenv)
    monkeypatch.setattr("hermes_cli.config.load_config", mock_load_config)
    monkeypatch.setattr(worker_module, "run_worker", mock_run_worker)

    # 1. Unset HERMES_HOME -> delegates to canonical hermes_constants.get_hermes_home()
    monkeypatch.delenv("HERMES_HOME", raising=False)
    sentinel_home = tmp_path / "sentinel_worker_home"
    get_home_calls = []

    def mock_get_hermes_home():
        get_home_calls.append(True)
        return sentinel_home

    monkeypatch.setattr(hermes_constants, "get_hermes_home", mock_get_hermes_home)

    exit_code_unset = worker_module.main(["--provider-mode", "fake"])
    assert exit_code_unset == 0
    assert len(get_home_calls) >= 1
    assert recorded_dotenv_homes[-1] == sentinel_home
    assert recorded_run_calls[-1]["db_path"] == sentinel_home / "hermes.db"

    # 2. Explicit HERMES_HOME environment variable
    env_home = tmp_path / "env_worker_home"
    monkeypatch.setenv("HERMES_HOME", str(env_home))
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: Path(os.environ["HERMES_HOME"]))

    exit_code_env = worker_module.main(["--provider-mode", "fake"])
    assert exit_code_env == 0
    assert recorded_dotenv_homes[-1] == env_home
    assert recorded_run_calls[-1]["db_path"] == env_home / "hermes.db"

    # 3. Explicit --db-path takes precedence over home for SQLite connection
    explicit_db = tmp_path / "explicit_dir" / "my_worker.db"
    exit_code_explicit = worker_module.main(["--db-path", str(explicit_db), "--provider-mode", "fake"])
    assert exit_code_explicit == 0
    assert recorded_run_calls[-1]["db_path"] == explicit_db
    assert recorded_dotenv_homes[-1] == env_home


def test_worker_main_once_scopes_daily_work_and_returns_failure(tmp_path, monkeypatch):
    import hermes_personal.workflows.worker as worker_module
    from hermes_personal.workflows.outbox_dispatcher import DispatchReport

    monkeypatch.setattr("hermes_cli.env_loader.load_hermes_dotenv", lambda **kwargs: None)
    monkeypatch.setattr("hermes_cli.config.load_config", lambda: {})
    recorded = []

    def mock_run_worker(**kwargs):
        recorded.append(kwargs)
        return DispatchReport(claimed=1, succeeded=0, failed=1, quarantined=0)

    monkeypatch.setattr(worker_module, "run_worker", mock_run_worker)

    exit_code = worker_module.main(
        [
            "--db-path",
            str(tmp_path / "worker.db"),
            "--provider-mode",
            "fake",
            "--once",
            "--batch-size",
            "5",
            "--workflow-id-prefix",
            "pv-daily-",
        ]
    )

    assert exit_code == 1
    assert recorded[0]["once"] is True
    assert recorded[0]["batch_size"] == 5
    assert recorded[0]["workflow_id_prefix"] == "pv-daily-"
