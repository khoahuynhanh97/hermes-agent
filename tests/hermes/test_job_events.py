from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from hermes.application.job_event_delivery import DeliveryConsumer, FileDeliveryAdapter
from hermes.db import Database
from hermes.domain.results import Result
from hermes.jobs import JobRepository


def _jobs(tmp_path: Path) -> JobRepository:
    return JobRepository(Database(tmp_path / "jobs.sqlite"))


def test_terminal_transition_persists_owner_scoped_event_and_redacts_path(tmp_path):
    jobs = _jobs(tmp_path)
    jobs.enqueue("job-1", "owner-1", "video.cut", {})
    jobs.claim_next()
    jobs.complete("job-1", {"output_path": r"C:\private\owner-1\cut.mp4"})

    events = jobs.list_events(owner_user_id="owner-1")
    assert len(events) == 1
    assert events[0]["event_type"] == "job.completed"
    assert events[0]["payload"]["result"]["output_path"] == "cut.mp4"
    assert jobs.list_events(owner_user_id="owner-2") == []
    assert jobs.get_event(events[0]["event_id"], owner_user_id="owner-2") is None


def test_job_transition_rolls_back_when_outbox_insert_fails(tmp_path):
    jobs = _jobs(tmp_path)
    jobs.enqueue("job-1", "owner-1", "video.cut", {})
    jobs.claim_next()

    with patch.object(JobRepository, "_append_event_in_transaction", side_effect=RuntimeError("outbox down")):
        with pytest.raises(RuntimeError, match="outbox down"):
            jobs.complete("job-1", {"output_path": "cut.mp4"})

    assert jobs.get("job-1")["state"] == "running"
    assert jobs.list_events() == []


def test_delivery_is_idempotent_and_restart_recovery_does_not_duplicate(tmp_path):
    jobs = _jobs(tmp_path)
    jobs.enqueue("job-1", "owner-1", "video.cut", {})
    jobs.claim_next()
    jobs.complete("job-1", {"output_path": "cut.mp4"})
    adapter = FileDeliveryAdapter(tmp_path / "deliveries")
    event = jobs.claim_event(worker_id="crashed-worker", lease_duration_seconds=1)
    adapter.publish(event)
    with jobs.database.transaction(immediate=True) as connection:
        connection.execute(
            "UPDATE job_events SET delivery_lease_expires_at = '2000-01-01T00:00:00+00:00' "
            "WHERE event_id = ?",
            (event["event_id"],),
        )

    delivered = DeliveryConsumer(jobs, adapter).run_once()
    assert delivered["delivery_state"] == "delivered"
    assert len(list((tmp_path / "deliveries").glob("*.json"))) == 1
    assert DeliveryConsumer(jobs, adapter).run_once() is None
    assert jobs.get("job-1")["state"] == "completed"


def test_transient_delivery_failure_is_bounded_and_does_not_fail_job(tmp_path):
    jobs = _jobs(tmp_path)
    jobs.enqueue("job-1", "owner-1", "video.cut", {})
    jobs.claim_next()
    jobs.complete("job-1", {"output_path": "cut.mp4"})

    class FlakyAdapter:
        calls = 0

        def publish(self, event):
            self.calls += 1
            if self.calls == 1:
                return Result.failure("temporary", "destination unavailable")
            return Result.success(None)

    consumer = DeliveryConsumer(jobs, FlakyAdapter())
    first = consumer.run_once()
    assert first["delivery_state"] == "pending"
    assert first["attempt_count"] == 1
    assert jobs.get("job-1")["state"] == "completed"

    second = consumer.run_once()
    assert second["delivery_state"] == "delivered"
    assert second["attempt_count"] == 2


def test_failed_and_cancelled_terminal_jobs_emit_events(tmp_path):
    jobs = _jobs(tmp_path)
    jobs.enqueue("failed", "owner", "video.cut", {}, max_attempts=1)
    jobs.claim_next()
    jobs.fail("failed", "bad input")
    jobs.enqueue("cancelled", "owner", "video.cut", {})
    jobs.cancel("cancelled", "owner")

    assert {event["event_type"] for event in jobs.list_events("owner")} == {
        "job.failed",
        "job.cancelled",
    }
