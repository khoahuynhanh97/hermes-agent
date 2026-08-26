from __future__ import annotations

import sqlite3
import pytest

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.outbox_repository import OutboxRepository


def test_enqueue_and_atomic_claim():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    msg = repo.enqueue("wf_1", "payload_1", max_attempts=3)
    assert msg.outbox_id > 0
    assert msg.workflow_id == "wf_1"
    assert msg.message == "payload_1"
    assert msg.state == "pending"

    claims = repo.claim("worker_1", lease_duration_seconds=30)
    assert len(claims) == 1
    c = claims[0]
    assert c.outbox_id == msg.outbox_id
    assert c.workflow_id == "wf_1"
    assert c.message == "payload_1"
    assert c.lease_owner == "worker_1"
    assert c.lease_token.startswith("claim_")

    # Second claim while lease is active should return empty
    empty_claims = repo.claim("worker_2", lease_duration_seconds=30)
    assert len(empty_claims) == 0


def test_competing_workers_isolation():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    for i in range(5):
        repo.enqueue(f"wf_{i}", f"msg_{i}")

    claims_w1 = repo.claim("worker_1", batch_size=3)
    assert len(claims_w1) == 3

    claims_w2 = repo.claim("worker_2", batch_size=3)
    assert len(claims_w2) == 2

    w1_ids = {c.outbox_id for c in claims_w1}
    w2_ids = {c.outbox_id for c in claims_w2}
    assert w1_ids.isdisjoint(w2_ids)


def test_ack_success_and_stale_ack_rejection():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    msg = repo.enqueue("wf_1", "msg_1")
    now = "2026-01-01T10:00:00+00:00"
    claims = repo.claim("worker_1", lease_duration_seconds=10, now_iso=now)
    assert len(claims) == 1
    c = claims[0]

    # Stale ACK: wrong worker
    assert not repo.ack(c.outbox_id, c.lease_token, "worker_2", now_iso=now)

    # Stale ACK: wrong token
    assert not repo.ack(c.outbox_id, "wrong_token", "worker_1", now_iso=now)

    # Stale ACK: expired lease (15 seconds later)
    expired_now = "2026-01-01T10:00:15+00:00"
    assert not repo.ack(c.outbox_id, c.lease_token, "worker_1", now_iso=expired_now)

    # Valid ACK within lease time
    assert repo.ack(c.outbox_id, c.lease_token, "worker_1", now_iso=now)

    # Duplicate ACK returns False
    assert not repo.ack(c.outbox_id, c.lease_token, "worker_1", now_iso=now)


def test_retry_backoff_calculation():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    msg = repo.enqueue("wf_1", "msg_1", max_attempts=3)
    now_1 = "2026-01-01T10:00:00+00:00"
    claims = repo.claim("worker_1", now_iso=now_1)
    c = claims[0]

    # 1st failure: attempt_count becomes 1. Backoff = 2.0 ** 0 = 1s -> next_attempt_at = 10:00:01
    status = repo.record_failure(
        c.outbox_id,
        c.lease_token,
        "worker_1",
        "Error 1",
        backoff_base_seconds=2.0,
        now_iso=now_1,
    )
    assert status == "retry_scheduled"

    # Claim before next_attempt_at should return empty
    now_before = "2026-01-01T10:00:00.500000+00:00"
    assert len(repo.claim("worker_1", now_iso=now_before)) == 0

    # Claim after next_attempt_at should succeed
    now_2 = "2026-01-01T10:00:02+00:00"
    claims_2 = repo.claim("worker_1", now_iso=now_2)
    assert len(claims_2) == 1
    c2 = claims_2[0]
    assert c2.attempt_count == 1

    # 2nd failure: attempt_count becomes 2. Backoff = 2.0 ** 1 = 2s -> next_attempt_at = 10:00:04
    status_2 = repo.record_failure(
        c2.outbox_id,
        c2.lease_token,
        "worker_1",
        "Error 2",
        backoff_base_seconds=2.0,
        now_iso=now_2,
    )
    assert status_2 == "retry_scheduled"


def test_poison_quarantine_after_max_attempts():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    msg = repo.enqueue("wf_1", "msg_1", max_attempts=2)
    now = "2026-01-01T10:00:00+00:00"

    claims = repo.claim("worker_1", now_iso=now)
    c1 = claims[0]

    # 1st failure
    status_1 = repo.record_failure(c1.outbox_id, c1.lease_token, "worker_1", "Err 1", now_iso=now)
    assert status_1 == "retry_scheduled"

    # Claim for 2nd attempt
    now_retry = "2026-01-01T10:00:10+00:00"
    claims_2 = repo.claim("worker_1", now_iso=now_retry)
    c2 = claims_2[0]

    # 2nd failure -> hits max_attempts=2 -> quarantined
    status_2 = repo.record_failure(c2.outbox_id, c2.lease_token, "worker_1", "Err 2", now_iso=now_retry)
    assert status_2 == "quarantined"

    # Should not be claimable now
    now_future = "2026-01-01T10:01:00+00:00"
    assert len(repo.claim("worker_1", now_iso=now_future)) == 0

    # Requeue quarantined item
    assert repo.requeue_quarantined(c1.outbox_id, now_iso=now_future)
    claims_requeued = repo.claim("worker_1", now_iso=now_future)
    assert len(claims_requeued) == 1
    assert claims_requeued[0].attempt_count == 0


def test_expired_lease_reclaim():
    conn = connect(":memory:")
    repo = OutboxRepository(conn)

    repo.enqueue("wf_1", "msg_1")
    now_start = "2026-01-01T10:00:00+00:00"
    claims = repo.claim("worker_1", lease_duration_seconds=10, now_iso=now_start)
    assert len(claims) == 1

    # Not expired at 10:00:05
    assert repo.reclaim_expired(now_iso="2026-01-01T10:00:05+00:00") == 0

    # Expired at 10:00:15 -> reclaimed
    assert repo.reclaim_expired(now_iso="2026-01-01T10:00:15+00:00") == 1

    # Now worker_2 can claim it
    claims_w2 = repo.claim("worker_2", now_iso="2026-01-01T10:00:16+00:00")
    assert len(claims_w2) == 1
    assert claims_w2[0].lease_owner == "worker_2"


def test_schema_migration_for_outbox():
    raw_conn = sqlite3.connect(":memory:")
    raw_conn.executescript("""
        CREATE TABLE workflow_outbox (
            outbox_id INTEGER PRIMARY KEY AUTOINCREMENT,
            workflow_id TEXT NOT NULL,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        INSERT INTO workflow_outbox (workflow_id, message, created_at)
        VALUES ('wf_old', 'msg_old', '2026-01-01T00:00:00Z');
    """)

    # Connect using our storage connect helper (runs _migrate_schema)
    from hermes_personal.storage.sqlite import _migrate_schema
    raw_conn.row_factory = sqlite3.Row
    _migrate_schema(raw_conn)

    repo = OutboxRepository(raw_conn)
    claims = repo.claim("worker_migrated")
    assert len(claims) == 1
    assert claims[0].workflow_id == "wf_old"
    assert claims[0].message == "msg_old"
