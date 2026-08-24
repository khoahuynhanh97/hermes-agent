from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget


class ProductVideoWorkflowState(str, Enum):
    IDLE = "idle"
    RESEARCHING = "researching"
    AWAITING_PRODUCT_LOCK = "AwaitingProductLock"
    BUILDING_RESOURCE_PACK = "building_resource_pack"
    CREATING_BRIEF = "creating_brief"
    AWAITING_BRIEF_APPROVAL = "AwaitingBriefApproval"
    CREATING_SCENE_PLAN = "creating_scene_plan"
    AWAITING_SCENE_APPROVAL = "AwaitingSceneApproval"
    CREATING_STORYBOARD = "creating_storyboard"
    AWAITING_STORYBOARD_APPROVAL = "AwaitingStoryboardApproval"
    RENDERING = "rendering"
    AWAITING_FINAL_APPROVAL = "AwaitingFinalApproval"
    EXPORTING = "exporting"
    COMPLETED = "completed"


HITL_WAITING_STATES = {
    ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
    ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
    ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
    ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
    ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
}


@dataclass(frozen=True)
class JobContext:
    workflow_id: str
    job_id: str
    owner_user_id: str = "user"
    workflow_state: str | ProductVideoWorkflowState = ProductVideoWorkflowState.IDLE
    version: int = 1
    expected_digests: dict[str, str] | None = None


@dataclass(frozen=True)
class JobSucceeded:
    artifact_ref: Any
    next_command: dict | None = None


@dataclass(frozen=True)
class JobFailed:
    retryable: bool
    code: str
    message: str | None = None


_pi_client = ProductIntelligenceClient()
_video_client = VideoFactoryClient()


def _compute_digest(obj: Any) -> str:
    payload = json.dumps(obj, sort_keys=True).encode()
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verify_job_digests(job_name: str, inputs: dict[str, Any], expected_digests: dict[str, str]) -> bool:
    for key, expected in expected_digests.items():
        if key not in inputs:
            return False
        if _compute_digest(inputs[key]) != expected:
            return False
    return True


def _validate_state(ctx: JobContext, legal_states: set[str | ProductVideoWorkflowState]) -> JobFailed | None:
    state_str = ctx.workflow_state.value if isinstance(ctx.workflow_state, ProductVideoWorkflowState) else str(ctx.workflow_state)
    for hitl_st in HITL_WAITING_STATES:
        if state_str == hitl_st.value or state_str == hitl_st:
            return JobFailed(retryable=False, code="HITL_APPROVAL_REQUIRED", message=f"Cannot dispatch job from HITL waiting state: {state_str}")
    legal_state_values = {s.value if isinstance(s, ProductVideoWorkflowState) else str(s) for s in legal_states}
    if state_str != ProductVideoWorkflowState.IDLE.value and state_str not in legal_state_values:
        return JobFailed(retryable=False, code="ILLEGAL_WORKFLOW_STATE", message=f"State {state_str} is not legal for this stage")
    return None


# --- Handlers ---

def research_job(ctx: JobContext, product_name: str, keywords: list[str]) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.RESEARCHING})
    if err:
        return err
    if not product_name:
        return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
    try:
        result = _pi_client.research(product_name, keywords)
        return JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
    except Exception as e:
        return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))


def resource_pack_job(ctx: JobContext, research_result: dict) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK})
    if err:
        return err
    try:
        result = _pi_client.build_resource_pack(research_result)
        return JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
    except Exception as e:
        return JobFailed(retryable=True, code="PI_BUILD_FAILED", message=str(e))


def lock_job(ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK})
    if err:
        return err
    try:
        result = _pi_client.lock_resource_pack(pack_dict, ctx.owner_user_id)
        return JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
    except Exception as e:
        return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))


def creative_brief_job(ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.CREATING_BRIEF})
    if err:
        return err
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 5)
        result = _video_client.create_creative_brief()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))


def scene_plan_job(ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.CREATING_SCENE_PLAN})
    if err:
        return err
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 5)
        result = _video_client.create_scene_plan()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))


def storyboard_job(ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.CREATING_STORYBOARD})
    if err:
        return err
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 10)
        result = _video_client.create_storyboard()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))


def render_job(ctx: JobContext, story_ref: Any) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.RENDERING})
    if err:
        return err
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 50)
        result = _video_client.render_video()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))


def export_job(ctx: JobContext, render_ref: Any) -> JobSucceeded | JobFailed:
    err = _validate_state(ctx, {ProductVideoWorkflowState.EXPORTING})
    if err:
        return err
    alloc = None
    try:
        alloc = reserve_budget("video_factory", 20)
        result = _video_client.export_video()
        commit_budget(alloc)
        return JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
    except Exception as e:
        if alloc:
            release_budget(alloc)
        return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))


HANDLERS_MAP: dict[str, Callable[..., Any]] = {
    "product_video.research": research_job,
    "product_video.resource_pack": resource_pack_job,
    "product_video.lock": lock_job,
    "product_video.creative_brief": creative_brief_job,
    "product_video.scene_plan": scene_plan_job,
    "product_video.storyboard": storyboard_job,
    "product_video.render": render_job,
    "product_video.export": export_job,
}


def register_product_video_job_handlers(dispatcher: Any) -> dict[str, Callable[..., Any]]:
    """Register all product-to-video pipeline job handlers with the Gate 4 dispatcher/registry."""
    if hasattr(dispatcher, "register"):
        for job_name, handler_func in HANDLERS_MAP.items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(HANDLERS_MAP)
    elif hasattr(dispatcher, "_specs"):
        # Gate 4 JobDispatcher instance
        if not hasattr(dispatcher, "handler_registry"):
            dispatcher.handler_registry = {}
        dispatcher.handler_registry.update(HANDLERS_MAP)
    return HANDLERS_MAP
