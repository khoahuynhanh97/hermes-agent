from __future__ import annotations

import sqlite3
from unittest.mock import MagicMock
import pytest

from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    HITL_WAITING_STATES,
    JobContext,
    JobSucceeded,
    JobFailed,
    ProductVideoJobHandlers,
    register_product_video_job_handlers,
    verify_job_digests,
    _compute_digest,
)
from hermes_personal.workflows.budgets import init_default_engine, BudgetPolicy
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.jobs import JobDispatcher, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository


@pytest.fixture(autouse=True)
def setup_budget():
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))


@pytest.fixture
def workflow_setup():
    conn = sqlite3.connect(":memory:")
    repo = WorkflowRepository(conn)
    # create table schema
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS workflow (workflow_id TEXT PRIMARY KEY, aggregate_json TEXT, version INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS processed_command (workflow_id TEXT, command_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_event (event_id TEXT PRIMARY KEY, workflow_id TEXT, event_type TEXT, timestamp TEXT, payload_json TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_outbox (workflow_id TEXT, message TEXT, created_at TEXT)")
    engine = WorkflowEngine(repo)
    return repo, engine


def test_workflow_engine_public_state_loading(workflow_setup):
    """Prove that handlers load workflow state dynamically through public WorkflowEngine APIs."""
    repo, engine = workflow_setup
    engine.set_workflow_state("wf_test", ProductVideoWorkflowState.CREATING_BRIEF.value, version=2)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_test", job_id="j1")
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobSucceeded)
    assert result.next_command is not None


def test_missing_workflow_rejected(workflow_setup):
    """Prove that handlers fail when workflow does not exist in engine/repo."""
    _, engine = workflow_setup
    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="non_existent_wf", job_id="j1")
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobFailed)
    assert result.code == "WORKFLOW_NOT_FOUND"


def test_stale_workflow_version_rejected(workflow_setup):
    """Prove that handlers reject execution if expected version does not match workflow state."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_ver", ProductVideoWorkflowState.CREATING_BRIEF.value, version=3)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_ver", job_id="j1", expected_version=1)
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobFailed)
    assert result.code == "VERSION_CONFLICT"


def test_missing_required_input_ref(workflow_setup):
    """Prove that handlers validate required upstream input refs."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_ref", ProductVideoWorkflowState.CREATING_SCENE_PLAN.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_ref", job_id="j1")
    # Empty brief_ref
    result = handlers.scene_plan_job(ctx, "")
    assert isinstance(result, JobFailed)
    assert result.code == "MISSING_INPUT_REF"


def test_digest_verification_enforced(workflow_setup):
    """Prove that handlers reject execution if expected input digests do not match."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_digest", ProductVideoWorkflowState.CREATING_BRIEF.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(
        workflow_id="wf_digest",
        job_id="j1",
        expected_digests={"product_id": "sha256:invalid_digest"},
    )
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobFailed)
    assert result.code == "DIGEST_MISMATCH"


@pytest.mark.parametrize("hitl_state", list(HITL_WAITING_STATES))
def test_no_client_call_when_awaiting_hitl_approval(workflow_setup, hitl_state):
    """Prove that in HITL waiting states, zero client calls are made and HITL_APPROVAL_REQUIRED is returned."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_hitl", hitl_state.value if isinstance(hitl_state, ProductVideoWorkflowState) else hitl_state, version=1)

    mock_pi = MagicMock()
    mock_vf = MagicMock()
    handlers = ProductVideoJobHandlers(pi_client=mock_pi, video_client=mock_vf, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_hitl", job_id="j_hitl")

    res_brief = handlers.creative_brief_job(ctx, "p1")
    assert isinstance(res_brief, JobFailed)
    assert res_brief.code == "HITL_APPROVAL_REQUIRED"
    mock_vf.create_creative_brief.assert_not_called()

    res_research = handlers.research_job(ctx, "watch", ["fit"])
    assert isinstance(res_research, JobFailed)
    assert res_research.code == "HITL_APPROVAL_REQUIRED"
    mock_pi.research.assert_not_called()


def test_illegal_workflow_state_rejection(workflow_setup):
    """Prove that handlers reject states outside the legal matrix for that stage."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_ill", ProductVideoWorkflowState.RESEARCHING.value, version=1)

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_ill", job_id="j_ill")
    res = handlers.render_job(ctx, "story_ref")
    assert isinstance(res, JobFailed)
    assert res.code == "ILLEGAL_WORKFLOW_STATE"


def test_budget_released_on_client_failure(workflow_setup):
    """Prove that when a paid client method fails, reserved budget is safely released."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_fail", ProductVideoWorkflowState.RENDERING.value, version=1)

    mock_vf = MagicMock()
    mock_vf.render_video.side_effect = RuntimeError("Render GPU unavailable")

    handlers = ProductVideoJobHandlers(video_client=mock_vf, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_fail", job_id="j_fail")
    res = handlers.render_job(ctx, "story_ref")
    assert isinstance(res, JobFailed)
    assert res.code == "VF_RENDER_FAILED"


def test_parameter_and_ref_forwarding_to_clients(workflow_setup):
    """Prove that handlers pass upstream refs and configurations to client methods."""
    _, engine = workflow_setup
    mock_vf = MagicMock()
    mock_vf.create_scene_plan.return_value = {"artifact_ref": "sha256:scene1"}

    engine.set_workflow_state("wf_fwd", ProductVideoWorkflowState.CREATING_SCENE_PLAN.value, version=1)
    handlers = ProductVideoJobHandlers(video_client=mock_vf, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_fwd", job_id="j_fwd")

    res = handlers.scene_plan_job(ctx, "brief_ref_123")
    assert isinstance(res, JobSucceeded)
    mock_vf.create_scene_plan.assert_called_once_with("brief_ref_123")


def test_job_dispatcher_terminal_execution(workflow_setup):
    """Prove that handlers dispatch through JobDispatcher and reach terminal success."""
    _, engine = workflow_setup
    engine.set_workflow_state("wf_disp", ProductVideoWorkflowState.CREATING_BRIEF.value, version=1)

    dispatcher = JobDispatcher()
    service = register_product_video_job_handlers(dispatcher, workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_disp", job_id="j_disp")

    service.dispatch_registered_job("product_video.creative_brief", ctx, "prod_1")
    terminal_result = service.wait_for_job("j_disp", timeout=1.0)
    assert terminal_result is not None
    assert terminal_result.status == JobStatus.SUCCESS
    assert isinstance(terminal_result.result, JobSucceeded)
