from __future__ import annotations

import pytest

from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    HITL_WAITING_STATES,
    JobContext,
    JobSucceeded,
    JobFailed,
    research_job,
    resource_pack_job,
    lock_job,
    creative_brief_job,
    scene_plan_job,
    storyboard_job,
    render_job,
    export_job,
    verify_job_digests,
    _compute_digest,
    register_product_video_job_handlers,
    HANDLERS_MAP,
)
from hermes_personal.workflows.budgets import init_default_engine, BudgetPolicy
from hermes_personal.workflows.jobs import JobDispatcher


@pytest.fixture(autouse=True)
def setup_budget():
    init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))


def test_research_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j1", workflow_state=ProductVideoWorkflowState.RESEARCHING)
    result = research_job(ctx, "Smart Watch", ["health", "fitness"])
    assert isinstance(result, JobSucceeded)
    assert "summary" in result.artifact_ref
    assert result.next_command is not None


def test_resource_pack_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j2", workflow_state=ProductVideoWorkflowState.BUILDING_RESOURCE_PACK)
    research_result = {"report": '{"product_name": "Watch", "keywords": ["fitness"]}'}
    result = resource_pack_job(ctx, research_result)
    assert isinstance(result, JobSucceeded)
    assert "assets_mapping" in result.artifact_ref


def test_lock_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j3", workflow_state=ProductVideoWorkflowState.BUILDING_RESOURCE_PACK)
    pack_dict = {"summary": "test pack", "assets_mapping": {"a1": "url1"}}
    result = lock_job(ctx, pack_dict)
    assert isinstance(result, JobSucceeded)
    assert result.artifact_ref["status"] == "locked"


def test_creative_brief_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j4", workflow_state=ProductVideoWorkflowState.CREATING_BRIEF)
    result = creative_brief_job(ctx, "p1")
    assert isinstance(result, JobSucceeded)
    assert "artifact_ref" in result.artifact_ref


def test_scene_plan_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j5", workflow_state=ProductVideoWorkflowState.CREATING_SCENE_PLAN)
    result = scene_plan_job(ctx, "brief_ref")
    assert isinstance(result, JobSucceeded)


def test_storyboard_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j6", workflow_state=ProductVideoWorkflowState.CREATING_STORYBOARD)
    result = storyboard_job(ctx, "scene_ref")
    assert isinstance(result, JobSucceeded)


def test_render_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j7", workflow_state=ProductVideoWorkflowState.RENDERING)
    result = render_job(ctx, "story_ref")
    assert isinstance(result, JobSucceeded)


def test_export_job_success():
    ctx = JobContext(workflow_id="wf1", job_id="j8", workflow_state=ProductVideoWorkflowState.EXPORTING)
    result = export_job(ctx, "render_ref")
    assert isinstance(result, JobSucceeded)


@pytest.mark.parametrize("hitl_state", list(HITL_WAITING_STATES))
def test_no_job_dispatch_from_hitl_approval_states(hitl_state):
    """Prove that no job is dispatched when awaiting HITL approval."""
    ctx = JobContext(workflow_id="wf1", job_id="j_hitl", workflow_state=hitl_state)

    res_research = research_job(ctx, "Watch", ["fit"])
    assert isinstance(res_research, JobFailed)
    assert res_research.code == "HITL_APPROVAL_REQUIRED"

    res_brief = creative_brief_job(ctx, "p1")
    assert isinstance(res_brief, JobFailed)
    assert res_brief.code == "HITL_APPROVAL_REQUIRED"

    res_scene = scene_plan_job(ctx, "brief_ref")
    assert isinstance(res_scene, JobFailed)
    assert res_scene.code == "HITL_APPROVAL_REQUIRED"

    res_story = storyboard_job(ctx, "scene_ref")
    assert isinstance(res_story, JobFailed)
    assert res_story.code == "HITL_APPROVAL_REQUIRED"

    res_render = render_job(ctx, "story_ref")
    assert isinstance(res_render, JobFailed)
    assert res_render.code == "HITL_APPROVAL_REQUIRED"

    res_export = export_job(ctx, "render_ref")
    assert isinstance(res_export, JobFailed)
    assert res_export.code == "HITL_APPROVAL_REQUIRED"


def test_illegal_workflow_state_rejection():
    """Prove that a handler rejects execution if workflow is in a mismatched active state."""
    # Attempting to render when workflow is only in researching state
    ctx = JobContext(workflow_id="wf1", job_id="j_illegal", workflow_state=ProductVideoWorkflowState.RESEARCHING)
    res = render_job(ctx, "story_ref")
    assert isinstance(res, JobFailed)
    assert res.code == "ILLEGAL_WORKFLOW_STATE"


def test_register_product_video_job_handlers():
    """Prove that concrete job handlers register into dispatcher/registry."""
    dispatcher = JobDispatcher()
    registered = register_product_video_job_handlers(dispatcher)
    assert len(registered) == 8
    assert "product_video.research" in registered
    assert "product_video.creative_brief" in registered
    assert "product_video.render" in registered
    assert registered.dispatcher is dispatcher


def test_job_idempotency_via_deterministic_clients():
    ctx = JobContext(workflow_id="wf1", job_id="j9", workflow_state=ProductVideoWorkflowState.CREATING_BRIEF)
    res1 = creative_brief_job(ctx, "p1")
    res2 = creative_brief_job(ctx, "p1")
    assert res1.artifact_ref["artifact_ref"] == res2.artifact_ref["artifact_ref"]


def test_verify_job_digests():
    data = {"key": "value"}
    digest = _compute_digest(data)
    assert verify_job_digests("test", {"key": data}, {"key": digest}) is True
    assert verify_job_digests("test", {"key": data}, {"key": "wrong"}) is False


def test_budget_exhaustion_fails_job():
    init_default_engine(BudgetPolicy(max_total=10, per_channel={"video_factory": 5}))
    ctx = JobContext(workflow_id="wf1", job_id="j10", workflow_state=ProductVideoWorkflowState.RENDERING)
    # Render job requires 50 budget, which exceeds 5
    result = render_job(ctx, "story_ref")
    assert isinstance(result, JobFailed)
    assert result.code == "VF_RENDER_FAILED"
