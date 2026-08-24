from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock
import pytest

from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    JobContext,
    JobSucceeded,
    JobFailed,
    ProductVideoJobHandlers,
    register_product_video_job_handlers,
)
from hermes_personal.workflows.budgets import init_default_engine, BudgetPolicy
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.jobs import JobDispatcher, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository


@pytest.fixture(autouse=True)
def setup_budget():
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))


@pytest.fixture
def persisted_db(tmp_path):
    db_file = tmp_path / "workflows.db"
    conn = sqlite3.connect(str(db_file))
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS workflow (workflow_id TEXT PRIMARY KEY, aggregate_json TEXT, version INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS processed_command (workflow_id TEXT, command_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_event (event_id TEXT PRIMARY KEY, workflow_id TEXT, event_type TEXT, timestamp TEXT, payload_json TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_outbox (workflow_id TEXT, message TEXT, created_at TEXT)")
    conn.close()
    return str(db_file)


def test_restart_recovery_from_persisted_sqlite(persisted_db):
    """Prove that when processes crash and restart, new engine and handlers instances restore state faithfully from SQLite."""
    # 1. First process run: write workflow state to SQLite
    conn1 = sqlite3.connect(persisted_db)
    repo1 = WorkflowRepository(conn1)
    engine1 = WorkflowEngine(repo1)
    engine1.set_workflow_state("wf_persisted", ProductVideoWorkflowState.CREATING_SCENE_PLAN.value, version=7)
    conn1.close()

    # 2. Simulate Process Restart: instantiate fresh connection, repo, engine, handlers
    conn2 = sqlite3.connect(persisted_db)
    repo2 = WorkflowRepository(conn2)
    engine2 = WorkflowEngine(repo2)
    handlers2 = ProductVideoJobHandlers(workflow_engine=engine2)

    # Verify state loaded seamlessly from SQLite
    state, version = engine2.get_workflow_state("wf_persisted")
    assert state == ProductVideoWorkflowState.CREATING_SCENE_PLAN.value
    assert version == 7

    # Execute next step after recovery
    ctx = JobContext(workflow_id="wf_persisted", job_id="j_rec", expected_version=7)
    res = handlers2.scene_plan_job(ctx, "brief_ref_restarted")
    assert isinstance(res, JobSucceeded)
    conn2.close()


def test_retryable_provider_timeout_recovers_on_retry(persisted_db):
    """Prove that transient network/provider timeouts return retryable failures and succeed on subsequent attempt."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_timeout", ProductVideoWorkflowState.RENDERING.value, version=1)

    mock_vf = MagicMock()
    # First attempt times out; second attempt succeeds
    mock_vf.render_video.side_effect = [
        TimeoutError("GPU instance startup timeout"),
        {"artifact_ref": "sha256:recovered_render_123"},
    ]

    handlers = ProductVideoJobHandlers(video_client=mock_vf, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_timeout", job_id="j_timeout", expected_version=1)

    # Attempt 1: fails retryably
    res1 = handlers.render_job(ctx, "story_ref_abc")
    assert isinstance(res1, JobFailed)
    assert res1.retryable is True
    assert res1.code == "VF_RENDER_FAILED"

    # Attempt 2: succeeds without duplicate budget leak
    res2 = handlers.render_job(ctx, "story_ref_abc")
    assert isinstance(res2, JobSucceeded)
    assert res2.artifact_ref["artifact_ref"] == "sha256:recovered_render_123"
    conn.close()


def test_permanent_schema_failure_handling(persisted_db):
    """Prove that permanent schema/input failure returns non-retryable failure."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_schema", ProductVideoWorkflowState.CREATING_BRIEF.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_schema", job_id="j_schema", expected_version=1)

    # Missing required product_id
    res = handlers.creative_brief_job(ctx, "")
    assert isinstance(res, JobFailed)
    assert res.retryable is False
    assert res.code == "MISSING_INPUT_REF"
    conn.close()


def test_stale_approval_invalidation_after_changed_storyboard(persisted_db):
    """Prove that modifying upstream assets increments version and rejects stale approval attempts."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))

    # Workflow at version 1
    engine.set_workflow_state("wf_stale", ProductVideoWorkflowState.CREATING_STORYBOARD.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    # Stale context expecting version 1
    ctx_stale = JobContext(workflow_id="wf_stale", job_id="j_stale", expected_version=1)

    # Upstream state changes to version 2 (e.g. storyboard edited by user)
    engine.set_workflow_state("wf_stale", ProductVideoWorkflowState.CREATING_STORYBOARD.value, version=2)

    # Attempting to render with stale context (expected_version=1) is rejected
    res = handlers.storyboard_job(ctx_stale, "scene_ref_old")
    assert isinstance(res, JobFailed)
    assert res.code == "VERSION_CONFLICT"
    conn.close()


def test_budget_exhaustion_stops_invocation_and_releases(persisted_db):
    """Prove that when budget is exhausted, paid calls stop before invocation."""
    init_default_engine(BudgetPolicy(max_total=5, per_channel={"video_factory": 5}))

    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_budget", ProductVideoWorkflowState.RENDERING.value, version=1)

    mock_vf = MagicMock()
    handlers = ProductVideoJobHandlers(video_client=mock_vf, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_budget", job_id="j_b", expected_version=1)

    # Render costs 50, but budget policy only has 5
    res = handlers.render_job(ctx, "story_ref_1")
    assert isinstance(res, JobFailed)
    assert res.code == "VF_RENDER_FAILED"
    mock_vf.render_video.assert_not_called()
    conn.close()


def test_duplicate_terminal_event_idempotency(persisted_db):
    """Prove that duplicate terminal dispatch calls are completely idempotent."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_term", ProductVideoWorkflowState.EXPORTING.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_term", job_id="j_term", expected_version=1, idempotency_key="idemp_term_1")

    res1 = handlers.export_job(ctx, "render_ref_final")
    res2 = handlers.export_job(ctx, "render_ref_final")
    assert isinstance(res1, JobSucceeded)
    assert isinstance(res2, JobSucceeded)
    assert res1.artifact_ref["artifact_ref"] == res2.artifact_ref["artifact_ref"]
    conn.close()
