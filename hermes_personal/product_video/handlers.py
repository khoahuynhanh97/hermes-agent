from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.jobs import JobDispatcher, JobResult, JobSpec


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
    expected_version: int | None = None
    expected_digests: dict[str, str] | None = None
    workflow_state: str | ProductVideoWorkflowState | None = None


@dataclass(frozen=True)
class JobSucceeded:
    artifact_ref: Any
    next_command: dict | None = None


@dataclass(frozen=True)
class JobFailed:
    retryable: bool
    code: str
    message: str | None = None


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


class ProductVideoJobHandlers:
    """Deterministic product-to-video job handlers with injected dependencies and workflow state loading."""

    def __init__(
        self,
        pi_client: ProductIntelligenceClient | None = None,
        video_client: VideoFactoryClient | None = None,
        workflow_engine: WorkflowEngine | None = None,
        dispatcher: JobDispatcher | None = None,
    ) -> None:
        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.dispatcher = dispatcher

    def _get_workflow_state_and_version(self, ctx: JobContext) -> tuple[str, int]:
        """Load state and version through WorkflowEngine or fallback to ctx."""
        if self.workflow_engine and ctx.workflow_id in self.workflow_engine._cache:
            cache_entry = self.workflow_engine._cache[ctx.workflow_id]
            st = cache_entry.get("state", ProductVideoWorkflowState.IDLE.value)
            ver = cache_entry.get("version", 0)
            return st, ver
        if ctx.workflow_state is not None:
            st = ctx.workflow_state.value if isinstance(ctx.workflow_state, ProductVideoWorkflowState) else str(ctx.workflow_state)
            return st, ctx.expected_version or 1
        return ProductVideoWorkflowState.IDLE.value, 1

    def _validate_state_and_version(self, ctx: JobContext, legal_states: set[str | ProductVideoWorkflowState]) -> JobFailed | None:
        current_state, current_version = self._get_workflow_state_and_version(ctx)

        # 1. Reject if state is in HITL waiting states
        for hitl_st in HITL_WAITING_STATES:
            if current_state == hitl_st.value or current_state == hitl_st:
                return JobFailed(
                    retryable=False,
                    code="HITL_APPROVAL_REQUIRED",
                    message=f"Cannot dispatch job from HITL waiting state: {current_state}",
                )

        # 2. Reject if state is not legal for this job
        legal_state_values = {s.value if isinstance(s, ProductVideoWorkflowState) else str(s) for s in legal_states}
        if current_state != ProductVideoWorkflowState.IDLE.value and current_state not in legal_state_values:
            return JobFailed(
                retryable=False,
                code="ILLEGAL_WORKFLOW_STATE",
                message=f"State '{current_state}' is not legal for this stage. Allowed: {legal_state_values}",
            )

        # 3. Check version mismatch if expected_version is provided
        if ctx.expected_version is not None and ctx.expected_version != current_version:
            return JobFailed(
                retryable=False,
                code="VERSION_CONFLICT",
                message=f"Stale workflow version: expected {ctx.expected_version}, current {current_version}",
            )

        return None

    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str]) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RESEARCHING})
        if err:
            return err
        if not product_name:
            return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
        try:
            result = self.pi_client.research(product_name, keywords)
            return JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
        except Exception as e:
            return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

    def resource_pack_job(self, ctx: JobContext, research_result: dict) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK})
        if err:
            return err
        try:
            result = self.pi_client.build_resource_pack(research_result)
            return JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
        except Exception as e:
            return JobFailed(retryable=True, code="PI_BUILD_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK})
        if err:
            return err
        try:
            result = self.pi_client.lock_resource_pack(pack_dict, ctx.owner_user_id)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_BRIEF})
        if err:
            return err
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5)
            result = self.video_client.create_creative_brief()
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_SCENE_PLAN})
        if err:
            return err
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5)
            result = self.video_client.create_scene_plan()
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))

    def storyboard_job(self, ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_STORYBOARD})
        if err:
            return err
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 10)
            result = self.video_client.create_storyboard()
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

    def render_job(self, ctx: JobContext, story_ref: Any) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RENDERING})
        if err:
            return err
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 50)
            result = self.video_client.render_video()
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

    def export_job(self, ctx: JobContext, render_ref: Any) -> JobSucceeded | JobFailed:
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.EXPORTING})
        if err:
            return err
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 20)
            result = self.video_client.export_video()
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))

    def get_handlers_map(self) -> dict[str, Callable[..., Any]]:
        return {
            "product_video.research": self.research_job,
            "product_video.resource_pack": self.resource_pack_job,
            "product_video.lock": self.lock_job,
            "product_video.creative_brief": self.creative_brief_job,
            "product_video.scene_plan": self.scene_plan_job,
            "product_video.storyboard": self.storyboard_job,
            "product_video.render": self.render_job,
            "product_video.export": self.export_job,
        }

    def __len__(self) -> int:
        return len(self.get_handlers_map())

    def __getitem__(self, item: str) -> Callable[..., Any]:
        return self.get_handlers_map()[item]

    def __contains__(self, item: str) -> bool:
        return item in self.get_handlers_map()

    def dispatch_registered_job(self, job_name: str, ctx: JobContext, *args: Any, **kwargs: Any) -> JobResult | None:
        """Create a Gate 4 JobSpec and dispatch it through JobDispatcher."""
        handlers = self.get_handlers_map()
        if job_name not in handlers:
            raise ValueError(f"Unknown job handler: {job_name}")
        handler_fn = handlers[job_name]
        spec = JobSpec(
            job_id=ctx.job_id,
            func=handler_fn,
            args=(ctx, *args),
            kwargs=kwargs,
        )
        if self.dispatcher:
            return self.dispatcher.dispatch(spec)
        return None


# Module-level default instance for simple functional access
_default_service = ProductVideoJobHandlers()

research_job = _default_service.research_job
resource_pack_job = _default_service.resource_pack_job
lock_job = _default_service.lock_job
creative_brief_job = _default_service.creative_brief_job
scene_plan_job = _default_service.scene_plan_job
storyboard_job = _default_service.storyboard_job
render_job = _default_service.render_job
export_job = _default_service.export_job
HANDLERS_MAP = _default_service.get_handlers_map()


def register_product_video_job_handlers(
    dispatcher: JobDispatcher | Any,
    handlers_service: ProductVideoJobHandlers | None = None,
) -> ProductVideoJobHandlers:
    """Register all product-to-video pipeline job handlers with the Gate 4 dispatcher/registry."""
    service = handlers_service or ProductVideoJobHandlers(dispatcher=dispatcher if isinstance(dispatcher, JobDispatcher) else None)
    if isinstance(dispatcher, JobDispatcher):
        service.dispatcher = dispatcher
    elif hasattr(dispatcher, "register"):
        for job_name, handler_func in service.get_handlers_map().items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(service.get_handlers_map())
    return service
