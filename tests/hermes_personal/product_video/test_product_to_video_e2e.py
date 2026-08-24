from __future__ import annotations

import sqlite3
import pytest

from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    JobContext,
    JobSucceeded,
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
def workflow_env():
    conn = sqlite3.connect(":memory:")
    repo = WorkflowRepository(conn)
    with conn:
        conn.execute("CREATE TABLE IF NOT EXISTS workflow (workflow_id TEXT PRIMARY KEY, aggregate_json TEXT, version INTEGER)")
        conn.execute("CREATE TABLE IF NOT EXISTS processed_command (workflow_id TEXT, command_id TEXT PRIMARY KEY)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_event (event_id TEXT PRIMARY KEY, workflow_id TEXT, event_type TEXT, timestamp TEXT, payload_json TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS workflow_outbox (workflow_id TEXT, message TEXT, created_at TEXT)")
    engine = WorkflowEngine(repo)
    dispatcher = JobDispatcher()
    handlers = register_product_video_job_handlers(dispatcher, workflow_engine=engine)
    return repo, engine, dispatcher, handlers


def test_full_fourteen_state_product_to_video_e2e(workflow_env):
    """Prove the entire 14-state product-to-video workflow from PDP to export across all 5 HITL gates."""
    _, engine, dispatcher, handlers = workflow_env
    wf_id = "wf_tiktok_pdp_12345"

    state_history: list[str] = []

    def transition_to(state: ProductVideoWorkflowState, version: int):
        engine.set_workflow_state(wf_id, state.value, version=version)
        current_state, _ = engine.get_workflow_state(wf_id)
        state_history.append(current_state)

    # 1. State 1: IDLE
    transition_to(ProductVideoWorkflowState.IDLE, version=1)

    # 2. State 2: RESEARCHING
    transition_to(ProductVideoWorkflowState.RESEARCHING, version=2)
    ctx_research = JobContext(workflow_id=wf_id, job_id="job_research", expected_version=2, idempotency_key="idemp_res")
    res_research = handlers.research_job(ctx_research, "TikTok Wireless Earbuds", ["audio", "bluetooth", "noise_cancelling"])
    assert isinstance(res_research, JobSucceeded)
    research_artifact = res_research.artifact_ref
    assert "report" in research_artifact

    # 3. State 3: AwaitingProductLock (HITL 1 - Web approval)
    transition_to(ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK, version=3)
    # Verify HITL gate blocks dispatch
    blocked_dispatch = handlers.resource_pack_job(ctx_research, research_artifact)
    assert blocked_dispatch.code == "HITL_APPROVAL_REQUIRED"

    # Human approves Product Lock from Web Interface -> Resume
    # 4. State 4: BUILDING_RESOURCE_PACK
    transition_to(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, version=4)
    ctx_pack = JobContext(workflow_id=wf_id, job_id="job_pack", expected_version=4, idempotency_key="idemp_pack")
    res_pack = handlers.resource_pack_job(ctx_pack, research_artifact)
    assert isinstance(res_pack, JobSucceeded)
    pack_artifact = res_pack.artifact_ref
    assert "assets_mapping" in pack_artifact

    # Lock pack
    res_lock = handlers.lock_job(ctx_pack, pack_artifact)
    assert isinstance(res_lock, JobSucceeded)
    locked_pack = res_lock.artifact_ref
    assert locked_pack["status"] == "locked"

    # 5. State 5: CREATING_BRIEF
    transition_to(ProductVideoWorkflowState.CREATING_BRIEF, version=5)
    ctx_brief = JobContext(workflow_id=wf_id, job_id="job_brief", expected_version=5, idempotency_key="idemp_brief")
    res_brief = handlers.creative_brief_job(ctx_brief, locked_pack["resource_pack_id"], brief_config={"target_audience": "gamers"})
    assert isinstance(res_brief, JobSucceeded)
    brief_artifact = res_brief.artifact_ref
    assert "artifact_ref" in brief_artifact

    # 6. State 6: AwaitingBriefApproval (HITL 2 - CLI approval)
    transition_to(ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL, version=6)
    assert handlers.scene_plan_job(ctx_brief, brief_artifact["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"

    # Human approves Creative Brief -> Resume
    # 7. State 7: CREATING_SCENE_PLAN
    transition_to(ProductVideoWorkflowState.CREATING_SCENE_PLAN, version=7)
    ctx_scene = JobContext(workflow_id=wf_id, job_id="job_scene", expected_version=7, idempotency_key="idemp_scene")
    res_scene = handlers.scene_plan_job(ctx_scene, brief_artifact["artifact_ref"])
    assert isinstance(res_scene, JobSucceeded)
    scene_artifact = res_scene.artifact_ref

    # 8. State 8: AwaitingSceneApproval (HITL 3 - Web approval)
    transition_to(ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL, version=8)
    assert handlers.storyboard_job(ctx_scene, scene_artifact["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"

    # Human approves Scene Plan -> Resume
    # 9. State 9: CREATING_STORYBOARD
    transition_to(ProductVideoWorkflowState.CREATING_STORYBOARD, version=9)
    ctx_story = JobContext(workflow_id=wf_id, job_id="job_story", expected_version=9, idempotency_key="idemp_story")
    res_story = handlers.storyboard_job(ctx_story, scene_artifact["artifact_ref"])
    assert isinstance(res_story, JobSucceeded)
    story_artifact = res_story.artifact_ref

    # 10. State 10: AwaitingStoryboardApproval (HITL 4 - Telegram approval)
    transition_to(ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL, version=10)
    assert handlers.render_job(ctx_story, story_artifact["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"

    # Human approves Storyboard -> Resume
    # 11. State 11: RENDERING
    transition_to(ProductVideoWorkflowState.RENDERING, version=11)
    ctx_render = JobContext(workflow_id=wf_id, job_id="job_render", expected_version=11, idempotency_key="idemp_render")
    res_render = handlers.render_job(ctx_render, story_artifact["artifact_ref"])
    assert isinstance(res_render, JobSucceeded)
    render_artifact = res_render.artifact_ref

    # 12. State 12: AwaitingFinalApproval (HITL 5 - Telegram final approval)
    transition_to(ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL, version=12)
    assert handlers.export_job(ctx_render, render_artifact["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"

    # Human gives Final Approval -> Resume
    # 13. State 13: EXPORTING
    transition_to(ProductVideoWorkflowState.EXPORTING, version=13)
    ctx_export = JobContext(workflow_id=wf_id, job_id="job_export", expected_version=13, idempotency_key="idemp_export")
    res_export = handlers.export_job(ctx_export, render_artifact["artifact_ref"])
    assert isinstance(res_export, JobSucceeded)
    export_artifact = res_export.artifact_ref

    # 14. State 14: COMPLETED
    transition_to(ProductVideoWorkflowState.COMPLETED, version=14)

    # Verify exact 14 state sequence traversed in order
    expected_states = [
        "idle",
        "researching",
        "AwaitingProductLock",
        "building_resource_pack",
        "creating_brief",
        "AwaitingBriefApproval",
        "creating_scene_plan",
        "AwaitingSceneApproval",
        "creating_storyboard",
        "AwaitingStoryboardApproval",
        "rendering",
        "AwaitingFinalApproval",
        "exporting",
        "completed",
    ]
    assert state_history == expected_states
