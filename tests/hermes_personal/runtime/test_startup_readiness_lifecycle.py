from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES
from hermes_personal.runtime.gateway_server import create_gateway_application, _health_api
from hermes_personal.runtime.startup import StartupCoordinator, StartupFailure
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

    # Health API executes startup coordinator with real DB callbacks in fake provider mode
    health_api = _health_api(connection=conn, outbox_repository=outbox_repo, provider_mode="fake")
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


def test_gateway_application_readiness_fake_mode_succeeds(tmp_path):
    db_file = tmp_path / "gateway_fake.db"
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


def test_gateway_application_readiness_configured_mode_fails_when_no_active_snapshot(tmp_path):
    """In configured mode without real tools/registry, gateway must NOT fake healthy bindings and /health/ready returns 503."""
    db_file = tmp_path / "gateway_configured.db"
    app = create_gateway_application(
        database_path=db_file,
        api_key="test_secret_key_12345",
        provider_mode="configured",
    )

    client = TestClient(app)

    # 1. /health/live remains 200 (process is live)
    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["live"] is True

    # 2. /health/ready MUST FAIL (503 Service Unavailable) with structured reason
    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 503
    data = res_ready.json()
    assert data["ready"] is False
    assert data["status"] == "not_ready"
    assert data["failure_code"] in ("CAPABILITY_ACTIVATION_FAILED", "NOT_READY")


def test_gateway_application_readiness_configured_mode_fails_with_existing_fake_snapshot_and_no_tools(tmp_path):
    """If DB was previously seeded with fake bindings, restarting in configured mode without tools must still fail closed (503)."""
    db_file = tmp_path / "gateway_restarted.db"

    # Step 1: Boot once in fake mode (seeds SQLite with baseline snapshot)
    app_fake = create_gateway_application(
        database_path=db_file,
        api_key="test_secret_key_12345",
        provider_mode="fake",
    )
    client_fake = TestClient(app_fake)
    res_fake = client_fake.get("/health/ready")
    assert res_fake.status_code == 200
    assert res_fake.json()["ready"] is True

    # Step 2: Restart against the same DB in configured mode without a tool registry
    app_configured = create_gateway_application(
        database_path=db_file,
        api_key="test_secret_key_12345",
        provider_mode="configured",
    )
    client_configured = TestClient(app_configured)

    # /health/ready MUST FAIL closed (503) — presence of leftover snapshot does not bypass validation
    res_configured = client_configured.get("/health/ready")
    assert res_configured.status_code == 503
    data = res_configured.json()
    assert data["ready"] is False
    assert data["failure_code"] in ("CAPABILITY_ACTIVATION_FAILED", "NOT_READY")


def test_gateway_application_readiness_configured_mode_succeeds_with_valid_supplied_registry(tmp_path):
    """In configured mode with a valid tool registry providing all required capabilities, gateway boots and returns 200 OK."""
    db_file = tmp_path / "gateway_configured_valid.db"

    # Construct mock registry with OpenAI-format tool definitions matching DEFAULT_WIRE_BINDING_RULES
    wires = [
        "mcp__learning__create_candidate",
        "mcp__learning__retrieve",
        "mcp__product_intelligence__research_product",
        "mcp__product_intelligence__build_resource_pack",
        "mcp__product_intelligence__lock_resource_pack",
        "mcp__video_factory__create_brief",
        "mcp__video_factory__export",
        "mcp__video_factory__render",
        "mcp__video_factory__create_scene_plan",
        "mcp__video_factory__create_storyboard",
    ]
    mock_registry = {
        wire: {
            "type": "function",
            "function": {
                "name": wire,
                "description": f"Tool for {wire}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for wire in wires
    }

    app = create_gateway_application(
        database_path=db_file,
        api_key="test_secret_key_12345",
        provider_mode="configured",
        tool_registry=mock_registry,
    )

    client = TestClient(app)

    res_live = client.get("/health/live")
    assert res_live.status_code == 200
    assert res_live.json()["live"] is True

    res_ready = client.get("/health/ready")
    assert res_ready.status_code == 200, f"Expected 200 OK but got: {res_ready.json()}"
    data = res_ready.json()
    assert data["ready"] is True
    assert data["status"] == "ready"


def test_gateway_healthz_compatibility_delegates_to_health_api_and_fails_503_in_configured_mode_without_tools(tmp_path):
    """Test that /healthz compatibility endpoint delegates to HealthAPI and returns 503 when configured mode has no tools."""
    # 1. Configured mode without tools -> both /health/ready and /healthz return 503
    app_configured = create_gateway_application(
        database_path=tmp_path / "configured.db",
        api_key="test-key-503",
        provider_mode="configured",
    )
    with TestClient(app_configured) as client:
        ready_res = client.get("/health/ready")
        assert ready_res.status_code == 503
        assert ready_res.json()["ready"] is False

        healthz_res = client.get("/healthz")
        assert healthz_res.status_code == 503
        assert healthz_res.json()["ready"] is False

    # 2. Fake mode -> both /health/ready and /healthz return 200
    app_fake = create_gateway_application(
        database_path=tmp_path / "fake.db",
        api_key="test-key-200",
        provider_mode="fake",
    )
    with TestClient(app_fake) as client:
        ready_res = client.get("/health/ready")
        assert ready_res.status_code == 200
        assert ready_res.json()["ready"] is True

        healthz_res = client.get("/healthz")
        assert healthz_res.status_code == 200
        assert healthz_res.json()["ready"] is True


def test_gateway_main_configured_forwards_in_process_registry_and_validates_readiness(tmp_path, monkeypatch):
    """Test that gateway_server.main forwards in-process registry in configured mode and verifies readiness through real factory."""
    import hermes_personal.runtime.gateway_server as gw_module

    recorded_apps = []
    captured_kwargs = []
    orig_create = gw_module.create_gateway_application

    def spy_create(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return orig_create(*args, **kwargs)

    def mock_uvicorn_run(app, host, port, log_level):
        recorded_apps.append(app)

    monkeypatch.setattr(gw_module, "create_gateway_application", spy_create)
    monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)
    monkeypatch.setenv("HERMES_API_KEY", "bootstrap-test-key")

    # 1. Configured mode with EMPTY isolated registry -> passes registry, fails readiness (503 on /health/ready and /healthz)
    empty_registry = {}
    monkeypatch.setattr("tools.registry.registry", empty_registry)
    db_empty = tmp_path / "empty_reg.db"
    exit_empty = gw_module.main(["--provider-mode", "configured", "--db-path", str(db_empty)])
    assert exit_empty == 0
    assert len(recorded_apps) == 1
    assert captured_kwargs[-1]["tool_registry"] is empty_registry

    with TestClient(recorded_apps[-1]) as client:
        res_ready = client.get("/health/ready")
        assert res_ready.status_code == 503
        assert res_ready.json()["ready"] is False

        res_healthz = client.get("/healthz")
        assert res_healthz.status_code == 503
        assert res_healthz.json()["ready"] is False

    # 2. Configured mode with POPULATED isolated registry -> passes registry, passes readiness (200 on /health/ready and /healthz)
    wires = [
        "mcp__learning__create_candidate",
        "mcp__learning__retrieve",
        "mcp__product_intelligence__research_product",
        "mcp__product_intelligence__build_resource_pack",
        "mcp__product_intelligence__lock_resource_pack",
        "mcp__video_factory__create_brief",
        "mcp__video_factory__export",
        "mcp__video_factory__render",
        "mcp__video_factory__create_scene_plan",
        "mcp__video_factory__create_storyboard",
    ]
    populated_registry = {
        wire: {
            "type": "function",
            "function": {
                "name": wire,
                "description": f"Tool for {wire}",
                "parameters": {"type": "object", "properties": {}},
            },
        }
        for wire in wires
    }
    monkeypatch.setattr("tools.registry.registry", populated_registry)
    db_pop = tmp_path / "pop_reg.db"
    exit_pop = gw_module.main(["--provider-mode", "configured", "--db-path", str(db_pop)])
    assert exit_pop == 0
    assert len(recorded_apps) == 2
    assert captured_kwargs[-1]["tool_registry"] is populated_registry

    with TestClient(recorded_apps[-1]) as client:
        res_ready = client.get("/health/ready")
        assert res_ready.status_code == 200
        assert res_ready.json()["ready"] is True

        res_healthz = client.get("/healthz")
        assert res_healthz.status_code == 200
        assert res_healthz.json()["ready"] is True

    # 3. Fake mode -> tool_registry is None
    db_fake = tmp_path / "fake_mode.db"
    exit_fake = gw_module.main(["--provider-mode", "fake", "--db-path", str(db_fake)])
    assert exit_fake == 0
    assert len(recorded_apps) == 3
    assert captured_kwargs[-1]["tool_registry"] is None


def test_gateway_main_resolves_canonical_get_hermes_home_when_env_unset(tmp_path, monkeypatch):
    """Test that gateway_server.main resolves canonical get_hermes_home when HERMES_HOME is unset."""
    import hermes_constants
    import hermes_personal.runtime.gateway_server as gw_module

    recorded_apps = []

    def mock_uvicorn_run(app, host, port, log_level):
        recorded_apps.append(app)

    monkeypatch.setattr("uvicorn.run", mock_uvicorn_run)
    monkeypatch.setenv("HERMES_API_KEY", "bootstrap-home-key")

    # 1. Unset HERMES_HOME -> delegates to hermes_constants.get_hermes_home()
    monkeypatch.delenv("HERMES_HOME", raising=False)
    sentinel_home = tmp_path / "sentinel_gw_home"
    get_home_calls = []

    def mock_get_hermes_home():
        get_home_calls.append(True)
        return sentinel_home

    monkeypatch.setattr(hermes_constants, "get_hermes_home", mock_get_hermes_home)

    exit_unset = gw_module.main(["--provider-mode", "fake"])
    assert exit_unset == 0
    assert len(get_home_calls) >= 1
    default_db = sentinel_home / "hermes.db"
    assert default_db.exists()

    # 2. Explicit HERMES_HOME environment variable
    env_home = tmp_path / "explicit_env_gw_home"
    monkeypatch.setenv("HERMES_HOME", str(env_home))
    # When HERMES_HOME is set, hermes_constants.get_hermes_home() returns Path(os.environ["HERMES_HOME"])
    monkeypatch.setattr(hermes_constants, "get_hermes_home", lambda: Path(os.environ["HERMES_HOME"]))
    exit_env = gw_module.main(["--provider-mode", "fake"])
    assert exit_env == 0
    assert (env_home / "hermes.db").exists()

    # 3. Explicit --db-path overrides default home
    explicit_db = tmp_path / "custom_dir" / "explicit_gw.db"
    exit_explicit = gw_module.main(["--provider-mode", "fake", "--db-path", str(explicit_db)])
    assert exit_explicit == 0
    assert explicit_db.exists()
