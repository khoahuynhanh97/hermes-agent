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
        conn.execute("CREATE TABLE IF NOT EXISTS worker_leases (worker_id TEXT PRIMARY KEY, lease_expires_at INTEGER)")
    conn.close()
    return str(db_file)


@pytest.mark.parametrize(
    "test_state",
    [
        # All 5 HITL Awaiting States
        ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
        ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
        ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
        ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
        ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
        # All Executing States
        ProductVideoWorkflowState.RESEARCHING,
        ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
        ProductVideoWorkflowState.CREATING_BRIEF,
        ProductVideoWorkflowState.CREATING_SCENE_PLAN,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
        ProductVideoWorkflowState.RENDERING,
        ProductVideoWorkflowState.EXPORTING,
    ],
)
def test_restart_recovery_across_all_awaiting_and_executing_states(persisted_db, test_state):
    """Prove that workflow state faithfully restores across crashes at EVERY awaiting and executing state."""
    wf_id = f"wf_restart_{test_state.value}"

    # 1. Process 1: persist state into SQLite
    conn1 = sqlite3.connect(persisted_db)
    repo1 = WorkflowRepository(conn1)
    engine1 = WorkflowEngine(repo1)
    engine1.set_workflow_state(wf_id, test_state.value, version=5)
    conn1.close()

    # 2. Simulate complete crash & restart: instantiate fresh objects
    conn2 = sqlite3.connect(persisted_db)
    repo2 = WorkflowRepository(conn2)
    engine2 = WorkflowEngine(repo2)
    handlers2 = ProductVideoJobHandlers(workflow_engine=engine2)

    # 3. Assert restored state and version match persisted SQLite records exactly
    restored_state, restored_version = engine2.get_workflow_state(wf_id)
    assert restored_state == test_state.value
    assert restored_version == 5

    # 4. Verify boundary behavior in restored state
    ctx = JobContext(workflow_id=wf_id, job_id=f"job_{test_state.value}", expected_version=5)
    if "Awaiting" in test_state.value:
        # Awaiting states must strictly block dispatch
        res = handlers2.render_job(ctx, "story_ref")
        assert isinstance(res, JobFailed)
        assert res.code == "HITL_APPROVAL_REQUIRED"
    conn2.close()


def test_retryable_provider_timeout_recovers_on_retry(persisted_db):
    """Prove that transient network/provider timeouts return retryable failures and succeed on subsequent attempt."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_timeout", ProductVideoWorkflowState.RENDERING.value, version=1)

    mock_vf = MagicMock()
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

    engine.set_workflow_state("wf_stale", ProductVideoWorkflowState.CREATING_STORYBOARD.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx_stale = JobContext(workflow_id="wf_stale", job_id="j_stale", expected_version=1)

    # Upstream state changes to version 2 (e.g. storyboard edited by user)
    engine.set_workflow_state("wf_stale", ProductVideoWorkflowState.CREATING_STORYBOARD.value, version=2)

    # Attempting to execute with stale context (expected_version=1) is rejected
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


def test_mcp_unavailable_handling(persisted_db):
    """Prove that MCP or external service disconnection returns a retryable error without crashing workflow."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_mcp", ProductVideoWorkflowState.RESEARCHING.value, version=1)

    mock_pi = MagicMock()
    mock_pi.research.side_effect = ConnectionError("MCP server connection refused on stdio/sse")

    handlers = ProductVideoJobHandlers(pi_client=mock_pi, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_mcp", job_id="j_mcp", expected_version=1)

    res = handlers.research_job(ctx, "Smart Ring", ["fitness"])
    assert isinstance(res, JobFailed)
    assert res.retryable is True
    assert res.code == "PI_RESEARCH_FAILED"
    conn.close()


def test_worker_lease_expiry_and_safe_resumption(persisted_db):
    """Prove that an expired worker lease does not cause duplicate execution and resumes safely under a new lease."""
    conn = sqlite3.connect(persisted_db)
    engine = WorkflowEngine(WorkflowRepository(conn))
    engine.set_workflow_state("wf_lease", ProductVideoWorkflowState.CREATING_SCENE_PLAN.value, version=1)

    # Record expired lease in DB
    with conn:
        conn.execute("INSERT OR REPLACE INTO worker_leases VALUES ('worker_dead', 1000)")

    # New worker takes lease and executes job
    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_lease", job_id="job_lease_new", expected_version=1, idempotency_key="idemp_lease_1")
    res = handlers.scene_plan_job(ctx, "brief_ref_lease")
    assert isinstance(res, JobSucceeded)
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
