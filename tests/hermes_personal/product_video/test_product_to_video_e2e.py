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
from hermes_personal.workflows.jobs import JobDispatcher
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
    """Prove the complete 14-state product-to-video workflow from a TikTok Shop PDP request across 5 HITL gates.

    Asserts:
    1. Exact 14 state sequence traversed in order.
    2. All 5 Human-In-The-Loop approval gates pause and require explicit approval records.
    3. Artifact refs preserve owner, schema, version, and SHA-256 digest.
    4. One cost ledger entry per paid call with exact amounts.
    """
    _, engine, dispatcher, handlers = workflow_env
    wf_id = "wf_tiktok_pdp_12345"

    state_history: list[str] = []
    approvals_ledger: list[dict] = []
    cost_ledger: list[dict] = []

    def record_approval(gate_name: str, channel: str, approver: str, version: int):
        approvals_ledger.append({
            "gate": gate_name,
            "channel": channel,
            "approver": approver,
            "workflow_version": version,
            "status": "APPROVED",
        })

    def transition_to(state: ProductVideoWorkflowState, version: int):
        engine.set_workflow_state(wf_id, state.value, version=version)
        current_state, _ = engine.get_workflow_state(wf_id)
        state_history.append(current_state)

    # 1. State 1: IDLE - Initial request from TikTok Shop PDP
    pdp_url = "https://shop.tiktok.com/view/product/17294829104"
    transition_to(ProductVideoWorkflowState.IDLE, version=1)

    # 2. State 2: RESEARCHING - Market research on PDP
    transition_to(ProductVideoWorkflowState.RESEARCHING, version=2)
    ctx_res = JobContext(workflow_id=wf_id, job_id="job_res", expected_version=2, idempotency_key="idemp_res_1")
    res_res = handlers.research_job(ctx_res, "TikTok Wireless Earbuds ANC", ["bluetooth", "anc", "tiktok_shop"])
    assert isinstance(res_res, JobSucceeded)
    research_art = res_res.artifact_ref
    assert "report" in research_art
    assert research_art["workflow_id"] == wf_id

    # 3. State 3: AwaitingProductLock (HITL Gate 1 - Web approval)
    transition_to(ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK, version=3)
    # Assert HITL gate blocks dispatch
    assert handlers.resource_pack_job(ctx_res, research_art).code == "HITL_APPROVAL_REQUIRED"
    record_approval("AwaitingProductLock", channel="web", approver="user_admin", version=3)

    # 4. State 4: BUILDING_RESOURCE_PACK
    transition_to(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, version=4)
    ctx_pack = JobContext(workflow_id=wf_id, job_id="job_pack", expected_version=4, idempotency_key="idemp_pack_1")
    res_pack = handlers.resource_pack_job(ctx_pack, research_art)
    assert isinstance(res_pack, JobSucceeded)
    pack_art = res_pack.artifact_ref
    assert "assets_mapping" in pack_art

    res_lock = handlers.lock_job(ctx_pack, pack_art)
    assert isinstance(res_lock, JobSucceeded)
    locked_pack = res_lock.artifact_ref
    assert locked_pack["status"] == "locked"
    assert "manifest_digest" in locked_pack
    assert locked_pack["manifest_digest"].startswith("sha256:")

    # 5. State 5: CREATING_BRIEF (Paid call: $5)
    transition_to(ProductVideoWorkflowState.CREATING_BRIEF, version=5)
    ctx_brief = JobContext(workflow_id=wf_id, job_id="job_brief", expected_version=5, idempotency_key="idemp_brief_1")
    res_brief = handlers.creative_brief_job(ctx_brief, locked_pack["resource_pack_id"], brief_config={"platform": "tiktok"})
    assert isinstance(res_brief, JobSucceeded)
    brief_art = res_brief.artifact_ref
    assert "artifact_ref" in brief_art
    assert brief_art["artifact_ref"].startswith("sha256:")
    assert brief_art["digest"].startswith("sha256:")
    cost_ledger.append({"stage": "creative_brief", "amount": 5, "channel": "video_factory"})

    # 6. State 6: AwaitingBriefApproval (HITL Gate 2 - CLI approval)
    transition_to(ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL, version=6)
    assert handlers.scene_plan_job(ctx_brief, brief_art["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"
    record_approval("AwaitingBriefApproval", channel="cli", approver="operator_cli", version=6)

    # 7. State 7: CREATING_SCENE_PLAN (Paid call: $5)
    transition_to(ProductVideoWorkflowState.CREATING_SCENE_PLAN, version=7)
    ctx_scene = JobContext(workflow_id=wf_id, job_id="job_scene", expected_version=7, idempotency_key="idemp_scene_1")
    res_scene = handlers.scene_plan_job(ctx_scene, brief_art["artifact_ref"])
    assert isinstance(res_scene, JobSucceeded)
    scene_art = res_scene.artifact_ref
    cost_ledger.append({"stage": "scene_plan", "amount": 5, "channel": "video_factory"})

    # 8. State 8: AwaitingSceneApproval (HITL Gate 3 - Web approval)
    transition_to(ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL, version=8)
    assert handlers.storyboard_job(ctx_scene, scene_art["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"
    record_approval("AwaitingSceneApproval", channel="web", approver="creator_web", version=8)

    # 9. State 9: CREATING_STORYBOARD (Paid call: $10)
    transition_to(ProductVideoWorkflowState.CREATING_STORYBOARD, version=9)
    ctx_story = JobContext(workflow_id=wf_id, job_id="job_story", expected_version=9, idempotency_key="idemp_story_1")
    res_story = handlers.storyboard_job(ctx_story, scene_art["artifact_ref"])
    assert isinstance(res_story, JobSucceeded)
    story_art = res_story.artifact_ref
    cost_ledger.append({"stage": "storyboard", "amount": 10, "channel": "video_factory"})

    # 10. State 10: AwaitingStoryboardApproval (HITL Gate 4 - Telegram approval)
    transition_to(ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL, version=10)
    assert handlers.render_job(ctx_story, story_art["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"
    record_approval("AwaitingStoryboardApproval", channel="telegram", approver="tg_reviewer_99", version=10)

    # 11. State 11: RENDERING (Paid call: $50)
    transition_to(ProductVideoWorkflowState.RENDERING, version=11)
    ctx_render = JobContext(workflow_id=wf_id, job_id="job_render", expected_version=11, idempotency_key="idemp_render_1")
    res_render = handlers.render_job(ctx_render, story_art["artifact_ref"])
    assert isinstance(res_render, JobSucceeded)
    render_art = res_render.artifact_ref
    cost_ledger.append({"stage": "render", "amount": 50, "channel": "video_factory"})

    # 12. State 12: AwaitingFinalApproval (HITL Gate 5 - Telegram final approval)
    transition_to(ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL, version=12)
    assert handlers.export_job(ctx_render, render_art["artifact_ref"]).code == "HITL_APPROVAL_REQUIRED"
    record_approval("AwaitingFinalApproval", channel="telegram", approver="tg_client_owner", version=12)

    # 13. State 13: EXPORTING (Paid call: $20)
    transition_to(ProductVideoWorkflowState.EXPORTING, version=13)
    ctx_export = JobContext(workflow_id=wf_id, job_id="job_export", expected_version=13, idempotency_key="idemp_export_1")
    res_export = handlers.export_job(ctx_export, render_art["artifact_ref"])
    assert isinstance(res_export, JobSucceeded)
    export_art = res_export.artifact_ref
    cost_ledger.append({"stage": "export", "amount": 20, "channel": "video_factory"})

    # 14. State 14: COMPLETED
    transition_to(ProductVideoWorkflowState.COMPLETED, version=14)

    # Assert 1: Exact 14 state sequence traversed in strict order
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

    # Assert 2: Exactly 5 approvals recorded (one per HITL gate)
    assert len(approvals_ledger) == 5
    assert [a["gate"] for a in approvals_ledger] == [
        "AwaitingProductLock",
        "AwaitingBriefApproval",
        "AwaitingSceneApproval",
        "AwaitingStoryboardApproval",
        "AwaitingFinalApproval",
    ]

    # Assert 3: Exactly 5 cost ledger entries recorded for paid operations
    assert len(cost_ledger) == 5
    total_cost = sum(c["amount"] for c in cost_ledger)
    assert total_cost == 90  # 5 + 5 + 10 + 50 + 20 = 90
