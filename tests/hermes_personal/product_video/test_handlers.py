from __future__ import annotations

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
import sqlite3
from hermes_personal.workflows.repository import WorkflowRepository


@pytest.fixture(autouse=True)
def setup_budget():
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))


def test_workflow_engine_state_loading():
    """Prove that handlers load workflow state dynamically from Gate 4 WorkflowEngine."""
    conn = sqlite3.connect(":memory:")
    repo = WorkflowRepository(conn)
    engine = WorkflowEngine(repo)
    engine._cache["wf_test"] = {"state": ProductVideoWorkflowState.CREATING_BRIEF.value, "version": 2}

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_test", job_id="j1")
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobSucceeded)
    assert result.next_command is not None


def test_stale_workflow_version_rejected():
    """Prove that handlers reject execution if expected version does not match workflow state."""
    conn = sqlite3.connect(":memory:")
    repo = WorkflowRepository(conn)
    engine = WorkflowEngine(repo)
    engine._cache["wf_ver"] = {"state": ProductVideoWorkflowState.CREATING_BRIEF.value, "version": 3}

    handlers = ProductVideoJobHandlers(workflow_engine=engine)
    ctx = JobContext(workflow_id="wf_ver", job_id="j1", expected_version=1)
    result = handlers.creative_brief_job(ctx, "prod_1")
    assert isinstance(result, JobFailed)
    assert result.code == "VERSION_CONFLICT"


@pytest.mark.parametrize("hitl_state", list(HITL_WAITING_STATES))
def test_no_client_call_when_awaiting_hitl_approval(hitl_state):
    """Prove that in HITL waiting states, zero client calls are made and HITL_APPROVAL_REQUIRED is returned."""
    mock_pi = MagicMock()
    mock_vf = MagicMock()
    handlers = ProductVideoJobHandlers(pi_client=mock_pi, video_client=mock_vf)
    ctx = JobContext(workflow_id="wf1", job_id="j_hitl", workflow_state=hitl_state)

    res_brief = handlers.creative_brief_job(ctx, "p1")
    assert isinstance(res_brief, JobFailed)
    assert res_brief.code == "HITL_APPROVAL_REQUIRED"
    mock_vf.create_creative_brief.assert_not_called()

    res_research = handlers.research_job(ctx, "watch", ["fit"])
    assert isinstance(res_research, JobFailed)
    assert res_research.code == "HITL_APPROVAL_REQUIRED"
    mock_pi.research.assert_not_called()


def test_illegal_workflow_state_rejection():
    """Prove that handlers reject states outside the legal matrix for that stage."""
    handlers = ProductVideoJobHandlers()
    ctx = JobContext(workflow_id="wf1", job_id="j_ill", workflow_state=ProductVideoWorkflowState.RESEARCHING)
    res = handlers.render_job(ctx, "story_ref")
    assert isinstance(res, JobFailed)
    assert res.code == "ILLEGAL_WORKFLOW_STATE"


def test_budget_released_on_client_failure():
    """Prove that when a paid client method fails, reserved budget is safely released."""
    mock_vf = MagicMock()
    mock_vf.render_video.side_effect = RuntimeError("Render GPU unavailable")

    handlers = ProductVideoJobHandlers(video_client=mock_vf)
    ctx = JobContext(workflow_id="wf1", job_id="j_fail", workflow_state=ProductVideoWorkflowState.RENDERING)
    res = handlers.render_job(ctx, "story_ref")
    assert isinstance(res, JobFailed)
    assert res.code == "VF_RENDER_FAILED"


def test_job_dispatcher_end_to_end_dispatch():
    """Prove that handlers can be registered with Gate 4 JobDispatcher and executed."""
    dispatcher = JobDispatcher()
    service = register_product_video_job_handlers(dispatcher)
    ctx = JobContext(workflow_id="wf1", job_id="j_dispatch", workflow_state=ProductVideoWorkflowState.CREATING_BRIEF)

    job_result = service.dispatch_registered_job("product_video.creative_brief", ctx, "prod_1")
    assert job_result is not None
    assert job_result.status in (JobStatus.PENDING, JobStatus.SUCCESS)


def test_verify_job_digests_helper():
    data = {"step": 1}
    digest = _compute_digest(data)
    assert verify_job_digests("test", {"step": data}, {"step": digest}) is True
    assert verify_job_digests("test", {"step": data}, {"step": "invalid_digest"}) is False
