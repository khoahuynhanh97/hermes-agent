"""Focused tests for queued-job retry and cancellation semantics."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from core.agent_jobs import AgentJobManager


def run_tests():
    with tempfile.TemporaryDirectory() as temp:
        manager = AgentJobManager(jobs_root=temp)
        job = {
            "job_id": "job-failed",
            "status": "failed",
            "telegram": {"user_id": 123},
            "target": {"project_slug": "test", "output_dir": temp},
        }
        manager._write_json(manager.failed_dir / "job-failed.failed.json", job)
        assert manager.retry_job("job-failed", owner_user_id=999)["reason"] == "not_owner"
        assert manager.retry_job("job-failed", owner_user_id=123)["ok"]
        assert (manager.inbox_dir / "job-failed.json").exists()

        assert manager.cancel_job("job-failed", owner_user_id=123)["ok"]
        assert (manager.cancelled_dir / "job-failed.cancelled.json").exists()
        assert not (manager.inbox_dir / "job-failed.json").exists()

        queued = {
            "job_id": "job-queued",
            "status": "pending",
            "created_at": "2026-01-01T00:00:00",
            "source": {"value": "note"},
            "target": {"project_slug": "test"},
        }
        manager._write_json(manager.inbox_dir / "job-queued.json", queued)
        visible = next(row for row in manager.list_jobs() if row["job_id"] == "job-queued")
        assert visible["status"] == "queued"
        assert visible["legacy_status"] == "pending"

        interrupted = {
            "job_id": "job-interrupted",
            "status": "processing",
            "target": {"project_slug": "test", "output_dir": temp},
        }
        manager._write_json(manager.processing_dir / "job-interrupted.json", interrupted)
        recovered = manager.recover_processing_jobs()
        assert recovered == ["job-interrupted"]
        recovered_job = manager._read_json(manager.inbox_dir / "job-interrupted.json")
        assert recovered_job["status"] == "pending"
        assert recovered_job["recovery_count"] == 1
        assert not (manager.processing_dir / "job-interrupted.json").exists()

        owned = dict(queued)
        owned["job_id"] = "job-owned"
        owned["telegram"] = {"user_id": 123}
        manager._write_json(manager.inbox_dir / "job-owned.json", owned)
        assert any(row["job_id"] == "job-owned" for row in manager.list_jobs(owner_user_id=123))
        assert not any(row["job_id"] == "job-owned" for row in manager.list_jobs(owner_user_id=999))
        assert manager.check_job_access("job-owned", owner_user_id=123) == (True, True)
        assert manager.check_job_access("job-owned", owner_user_id=999) == (True, False)
        assert manager.check_job_access("missing", owner_user_id=123) == (False, False)

        completed = {
            "job_id": "job_20260713_010203_abcdef",
            "status": "done",
            "telegram": {"user_id": 123},
            "target": {"project_slug": "test", "output_dir": temp},
        }
        archive_dir = manager.jobs_root / "done_archived"
        archive_dir.mkdir(parents=True, exist_ok=True)
        manager._write_json(archive_dir / "job_20260713_010203_abcdef.done.json", completed)
        assert manager.get_completed_job("job_20260713_010203_abcdef", owner_user_id=123)["ok"]
        assert manager.get_completed_job("job_20260713_010203_abcdef", owner_user_id=999)["reason"] == "not_owner"
        assert manager.get_completed_job("../job_20260713_010203_abcdef", owner_user_id=123)["reason"] == "invalid_job_id"

    print("job retry/cancel tests: PASS")


if __name__ == "__main__":
    run_tests()
