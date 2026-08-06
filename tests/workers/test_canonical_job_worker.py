from __future__ import annotations

import sqlite3
from pathlib import Path

import cv2
import imageio_ffmpeg
import numpy as np

from hermes.db import Database
from hermes.jobs import JobRepository
from mcp_servers.video import server as video_server
from workers.job_worker import CanonicalJobWorker


def _repository(tmp_path: Path) -> JobRepository:
    return JobRepository(Database(tmp_path / "jobs.sqlite"))


def test_canonical_claim_is_atomic_and_leased(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("one", "owner", "video.cut", {})
    first = jobs.claim_next(worker_id="worker-1", lease_duration_seconds=60)
    second = jobs.claim_next(worker_id="worker-2", lease_duration_seconds=60)

    assert first["id"] == "one"
    assert first["state"] == "running"
    assert first["attempts"] == 1
    assert first["worker_id"] == "worker-1"
    assert first["lease_expires_at"]
    assert second is None


def test_retry_is_bounded_and_failed_history_is_inspectable(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("retry", "owner", "video.cut", {}, max_attempts=2)

    jobs.claim_next()
    assert jobs.fail("retry", "temporary", retryable=True)["state"] == "queued"
    jobs.claim_next()
    failed = jobs.fail("retry", "permanent", retryable=True)

    assert failed["state"] == "failed"
    assert failed["attempts"] == 2
    assert failed["error"] == "permanent"
    assert jobs.get("retry")["state"] == "failed"


def test_cancel_is_owner_scoped_and_running_cancel_is_cooperative(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("queued", "owner-1", "video.cut", {})
    assert jobs.cancel("queued", "owner-2") is None
    assert jobs.cancel("queued", "owner-1")["state"] == "cancelled"

    jobs.enqueue("running", "owner-1", "video.cut", {})
    jobs.claim_next()
    requested = jobs.cancel("running", "owner-1")
    assert requested["state"] == "running"
    assert requested["cancel_requested"] is True
    assert jobs.acknowledge_cancel("running")["state"] == "cancelled"


def test_worker_does_not_claim_queued_cancelled_job(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("cancelled", "owner", "video.cut", {})
    jobs.cancel("cancelled", "owner")
    worker = CanonicalJobWorker(str(tmp_path / "jobs.sqlite"), str(tmp_path / "workspace"))

    assert worker.run_once() is None
    assert jobs.get("cancelled")["state"] == "cancelled"


def test_expired_lease_is_requeued_and_cancelled_job_is_not_claimed(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("stale", "owner", "video.cut", {})
    jobs.claim_next(lease_duration_seconds=1)
    with jobs.database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE jobs SET lease_expires_at = '2000-01-01T00:00:00+00:00' WHERE id = 'stale'"
        )

    assert jobs.recover_expired() == ["stale"]
    assert jobs.get("stale")["state"] == "queued"
    assert jobs.claim_next()["id"] == "stale"


def test_worker_rejects_unsupported_and_malformed_payloads(tmp_path):
    jobs = _repository(tmp_path)
    jobs.enqueue("unsupported", "owner", "unknown.task", {})
    jobs.enqueue("malformed", "owner", "video.cut", {"asset_id": ""})
    worker = CanonicalJobWorker(str(tmp_path / "jobs.sqlite"), str(tmp_path / "workspace"))

    assert worker.run_once()["state"] == "failed"
    assert worker.run_once()["state"] == "failed"


def _fixture(path: Path) -> None:
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 4.0, (160, 120))
    assert writer.isOpened()
    for value in (0, 80, 160, 240):
        writer.write(np.full((120, 160, 3), value, dtype=np.uint8))
    writer.release()


def test_video_mcp_runs_through_canonical_worker_and_reads_result(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    asset = workspace / "source.mp4"
    _fixture(asset)
    db_path = tmp_path / "jobs.sqlite"
    monkeypatch.setenv("HERMES_VIDEO_WORKSPACE", str(workspace))
    monkeypatch.setenv("HERMES_VIDEO_DB_PATH", str(db_path))

    created = video_server.video_create_job(
        "owner-1", "cut", str(asset), output_name="cut.mp4", start_seconds=0, end_seconds=1
    )
    worker = CanonicalJobWorker(str(db_path), str(workspace))
    worker.runtime.ffmpeg.ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    completed = worker.run_once()
    result = video_server.video_get_job("owner-1", created["job"]["job_id"])["job"]

    assert completed["state"] == "completed"
    assert result["status"] == "succeeded"
    assert result["result"]["task_type"] == "video.cut"
    assert Path(result["result"]["output_path"]).is_file()
    assert Path(result["result"]["output_path"]).parent == workspace


def test_build_worker_overrides_env_defaults(tmp_path, monkeypatch):
    from workers.job_worker import build_worker

    env_db = tmp_path / "env_db.sqlite"
    env_ws = tmp_path / "env_ws"
    monkeypatch.setenv("HERMES_VIDEO_DB_PATH", str(env_db))
    monkeypatch.setenv("HERMES_VIDEO_WORKSPACE", str(env_ws))

    custom_db = tmp_path / "custom_db.sqlite"
    custom_ws = tmp_path / "custom_ws"

    worker = build_worker(db_path=str(custom_db), workspace=str(custom_ws))
    assert worker.workspace == custom_ws.resolve()


def test_worker_cli_uses_explicit_database_and_workspace(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys
    from hermes.db import Database
    from hermes.jobs import JobRepository

    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    custom_db = tmp_path / "cli_db.sqlite"
    custom_ws = tmp_path / "cli_ws"

    jobs = JobRepository(Database(custom_db))
    jobs.enqueue(
        "job-cli-1", "owner-cli", "image_generate",
        {"request_id": "req-1", "prompt": "a test prompt", "owner_user_id": "owner-cli"}
    )

    env = dict(os.environ)
    env["IMAGE_PROVIDER"] = "fake"
    env["HERMES_ALLOW_FAKE_PROVIDERS"] = "1"
    cmd = [
        sys.executable, "-m", "workers.job_worker", "--once",
        "--db-path", str(custom_db),
        "--workspace", str(custom_ws),
    ]
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[2]))
    assert proc.returncode == 0

    fetched = jobs.get("job-cli-1")
    assert fetched["state"] == "completed", f"job failed with error: {fetched.get('error')} | stderr: {proc.stderr} | stdout: {proc.stdout}"
    output_path = Path(fetched["result"]["output_paths"][0])
    assert output_path.is_file()
    assert custom_ws in output_path.parents
