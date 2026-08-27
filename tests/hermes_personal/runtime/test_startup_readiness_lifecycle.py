from __future__ import annotations

import sqlite3
import pytest
from fastapi.testclient import TestClient

from hermes_personal.runtime.gateway_server import create_gateway_application, _health_api
from hermes_personal.runtime.startup import StartupCoordinator, StartupStep, StartupFailure
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.outbox_repository import OutboxRepository


def test_startup_coordinator_executes_real_migration_and_lease_reclaim(tmp_path):
    db_file = tmp_path / "startup_test.db"
    conn = connect(db_file)
    outbox_repo = OutboxRepository(conn)

    # Insert an expired lease directly
    conn.execute(
        """
        INSERT INTO workflow_outbox (
            workflow_id, message, state, lease_token, lease_owner, lease_expires_at,
            attempt_count, max_attempts, created_at, updated_at
        ) VALUES (
            'wf_startup_1', 'msg1', 'leased', 'token_old', 'worker_dead', '2026-01-01T00:00:00+00:00',
            1, 5, '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00'
        )
        """
    )
    conn.commit()

    # Health API executes startup coordinator with real DB callbacks
    health_api = _health_api(connection=conn, outbox_repository=outbox_repo)
    status_code, body = health_api.handle_ready()
    assert status_code == 200
    assert body["ready"] is True

    # Verify expired lease was automatically reclaimed to pending
    cur = conn.execute("SELECT state, lease_token FROM workflow_outbox WHERE workflow_id = 'wf_startup_1'")
    row = cur.fetchone()
    assert row["state"] == "pending"
    assert row["lease_token"] is None

    conn.close()


def test_startup_coordinator_blocks_readiness_on_dependency_probe_failure():
    # Coordinator with failing dependency probe
    coordinator = StartupCoordinator(
        dependency_prober=lambda: False,
    )
    report = coordinator.prepare()
    assert report.is_ready is False
    assert report.failure_code == "DEPENDENCY_PROBE_FAILED"


def test_gateway_application_readiness_endpoint(tmp_path):
    db_file = tmp_path / "gateway_health.db"
    app = create_gateway_application(
        database_path=db_file,
        api_key="test_secret_key_12345",
        provider_mode="fake",
    )

    client = TestClient(app)

    # 1. /health/live -> 200 OK
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["status"] == "ok"
    assert res_live.json()["live"] is True

    # 2. /health/ready -> 200 OK
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200, f"res_ready failed with: {res_ready.json()}"
    assert res_ready.json()["status"] == "ready"
    assert res_ready.json()["ready"] is True
