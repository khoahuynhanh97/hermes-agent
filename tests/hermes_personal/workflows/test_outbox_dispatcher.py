from __future__ import annotations

import json

import pytest
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.outbox_dispatcher import (
    DispatchReport,
    OutboxDispatcher,
)
from hermes_personal.workflows.outbox_repository import OutboxClaim, OutboxRepository


def test_dispatcher_delivers_and_acks_message():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, created_at)
        VALUES ('wf1', 'hello outbox', 'pending', '2026-01-01T00:00:00Z')
        """
    )

    delivered: list[tuple[str, str]] = []

    def delivery_fn(workflow_id: str, message: str) -> None:
        delivered.append((workflow_id, message))

    dispatcher = OutboxDispatcher(repo, delivery_fn, worker_id="worker-1")
    report = dispatcher.process_batch(now_iso="2026-01-01T00:00:00Z")

    assert report == DispatchReport(claimed=1, succeeded=1, failed=0, quarantined=0)
    assert delivered == [("wf1", "hello outbox")]

    cur.execute("SELECT COUNT(*) as cnt FROM workflow_outbox")
    assert cur.fetchone()["cnt"] == 0


def test_dispatcher_handles_delivery_failure_with_retry_backoff():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, created_at)
        VALUES ('wf1', 'fail msg', 'pending', '2026-01-01T00:00:00Z')
        """
    )

    def failing_delivery(workflow_id: str, message: str) -> None:
        raise RuntimeError("Transient delivery error")

    dispatcher = OutboxDispatcher(
        repo, failing_delivery, worker_id="worker-1", backoff_base_seconds=2.0
    )

    t0 = "2026-01-01T00:00:00Z"
    report1 = dispatcher.process_batch(now_iso=t0)
    assert report1 == DispatchReport(claimed=1, succeeded=0, failed=1, quarantined=0)

    cur.execute(
        "SELECT state, attempt_count, last_error, next_attempt_at FROM workflow_outbox"
    )
    row = cur.fetchone()
    assert row["state"] == "pending"
    assert row["attempt_count"] == 1
    assert row["last_error"] == "Transient delivery error"
    assert row["next_attempt_at"] is not None

    # Before backoff expires (t + 1s), should not be claimed
    t_before = "2026-01-01T00:00:01Z"
    report_before = dispatcher.process_batch(now_iso=t_before)
    assert report_before == DispatchReport(
        claimed=0, succeeded=0, failed=0, quarantined=0
    )

    # After backoff expires (t + 3s), should be claimed again
    t_after = "2026-01-01T00:00:03Z"
    report_after = dispatcher.process_batch(now_iso=t_after)
    assert report_after == DispatchReport(
        claimed=1, succeeded=0, failed=1, quarantined=0
    )

    cur.execute("SELECT attempt_count FROM workflow_outbox")
    assert cur.fetchone()["attempt_count"] == 2


def test_dispatcher_competing_workers_no_duplicate_delivery():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, created_at)
        VALUES ('wf1', 'competing msg', 'pending', '2026-01-01T00:00:00Z')
        """
    )

    delivered1: list[tuple[str, str]] = []
    delivered2: list[tuple[str, str]] = []

    dispatcher1 = OutboxDispatcher(
        repo, lambda wf, msg: delivered1.append((wf, msg)), worker_id="worker-1"
    )
    dispatcher2 = OutboxDispatcher(
        repo, lambda wf, msg: delivered2.append((wf, msg)), worker_id="worker-2"
    )

    # Worker 1 claims manually first
    claims1 = repo.claim(
        worker_id="worker-1",
        lease_duration_seconds=30.0,
        batch_size=10,
        now_iso="2026-01-01T00:00:00Z",
    )
    assert len(claims1) == 1

    # Worker 2 tries to process batch at same time
    report2 = dispatcher2.process_batch(now_iso="2026-01-01T00:00:00Z")
    assert report2 == DispatchReport(claimed=0, succeeded=0, failed=0, quarantined=0)
    assert delivered2 == []


def test_dispatcher_expired_lease_reclaim_and_redelivery():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, created_at)
        VALUES ('wf1', 'expired lease msg', 'pending', '2026-01-01T00:00:00Z')
        """
    )

    # Worker 1 claims with short lease (10 seconds)
    t0 = "2026-01-01T00:00:00Z"
    claims = repo.claim(
        "worker-1", lease_duration_seconds=10.0, batch_size=10, now_iso=t0
    )
    assert len(claims) == 1

    # Worker 1 crashes / fails to ack

    # At t + 5s, lease is not expired
    t_mid = "2026-01-01T00:00:05Z"
    reclaimed_mid = repo.reclaim_expired(now_iso=t_mid)
    assert reclaimed_mid == 0

    # At t + 15s, lease is expired
    t_exp = "2026-01-01T00:00:15Z"
    reclaimed_count = repo.reclaim_expired(now_iso=t_exp)
    assert reclaimed_count == 1

    # Worker 2 can now claim and deliver
    delivered2: list[tuple[str, str]] = []
    dispatcher2 = OutboxDispatcher(
        repo, lambda wf, msg: delivered2.append((wf, msg)), worker_id="worker-2"
    )
    report2 = dispatcher2.process_batch(now_iso=t_exp)
    assert report2 == DispatchReport(claimed=1, succeeded=1, failed=0, quarantined=0)
    assert delivered2 == [("wf1", "expired lease msg")]


def test_dispatcher_poison_message_quarantined_after_max_attempts():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, max_attempts, created_at)
        VALUES ('wf1', 'poison msg', 'pending', 2, '2026-01-01T00:00:00Z')
        """
    )

    def poison_delivery(workflow_id: str, message: str) -> None:
        raise ValueError("Fatal payload error")

    dispatcher = OutboxDispatcher(
        repo, poison_delivery, worker_id="worker-1", backoff_base_seconds=2.0
    )

    # Attempt 1 -> fails
    t0 = "2026-01-01T00:00:00Z"
    report1 = dispatcher.process_batch(now_iso=t0)
    assert report1 == DispatchReport(claimed=1, succeeded=0, failed=1, quarantined=0)

    # Attempt 2 -> hits max_attempts (2) -> quarantined
    t_next = "2026-01-01T00:00:05Z"
    report2 = dispatcher.process_batch(now_iso=t_next)
    assert report2 == DispatchReport(claimed=1, succeeded=0, failed=0, quarantined=1)

    cur.execute("SELECT state, attempt_count, lease_token FROM workflow_outbox")
    row = cur.fetchone()
    assert row["state"] == "quarantined"
    assert row["attempt_count"] == 2
    assert row["lease_token"] is None

    # Subsequent claim ignores quarantined message
    report3 = dispatcher.process_batch(now_iso="2026-01-01T00:00:10Z")
    assert report3 == DispatchReport(claimed=0, succeeded=0, failed=0, quarantined=0)


def test_dispatcher_stale_ack_rejected():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO workflow_outbox (workflow_id, message, state, created_at)
        VALUES ('wf1', 'stale ack msg', 'pending', '2026-01-01T00:00:00Z')
        """
    )

    t0 = "2026-01-01T00:00:00Z"
    claims1 = repo.claim(
        "worker-1", lease_duration_seconds=5.0, batch_size=10, now_iso=t0
    )
    assert len(claims1) == 1
    claim1 = claims1[0]

    # Lease expires and is reclaimed
    t_exp = "2026-01-01T00:00:10Z"
    repo.reclaim_expired(now_iso=t_exp)

    # Worker 2 claims message
    claims2 = repo.claim(
        "worker-2", lease_duration_seconds=30.0, batch_size=10, now_iso=t_exp
    )
    assert len(claims2) == 1
    claim2 = claims2[0]
    assert claim1.lease_token != claim2.lease_token

    # Worker 1 tries to ACK with old stale token -> rejected (returns False)
    stale_ack = repo.ack(
        claim1.outbox_id, claim1.lease_token, "worker-1", now_iso=t_exp
    )
    assert stale_ack is False

    # Worker 2 ACKs with valid token -> succeeded (returns True)
    valid_ack = repo.ack(
        claim2.outbox_id, claim2.lease_token, "worker-2", now_iso=t_exp
    )
    assert valid_ack is True

    cur.execute("SELECT COUNT(*) as cnt FROM workflow_outbox")
    assert cur.fetchone()["cnt"] == 0


def test_successful_delivery_with_stale_ack_not_counted_as_succeeded():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    repo.enqueue("wf1", "stale delivery msg")

    t0 = "2026-01-01T00:00:00Z"
    t_exp = "2026-01-01T00:00:15Z"

    def delivery_fn(workflow_id: str, message: str) -> None:
        repo.reclaim_expired(now_iso=t_exp)
        repo.claim("worker-2", now_iso=t_exp)

    dispatcher = OutboxDispatcher(
        repo, delivery_fn, worker_id="worker-1", lease_duration_seconds=10.0
    )
    report = dispatcher.process_batch(now_iso=t0)

    assert report.succeeded == 0


def test_competing_workers_do_not_deliver_same_active_lease():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)
    repo.enqueue("wf1", "active lease msg")

    t0 = "2026-01-01T00:00:00Z"

    claims1 = repo.claim(
        "worker-1", lease_duration_seconds=30.0, batch_size=10, now_iso=t0
    )
    assert len(claims1) == 1

    delivered2: list[tuple[str, str]] = []
    dispatcher2 = OutboxDispatcher(
        repo, lambda wf, msg: delivered2.append((wf, msg)), worker_id="worker-2"
    )
    report2 = dispatcher2.process_batch(now_iso=t0)

    assert report2 == DispatchReport(claimed=0, succeeded=0, failed=0, quarantined=0)
    assert delivered2 == []
    assert len(repo.claim("worker-2", now_iso=t0)) == 0
