from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.jobs import JobDispatcher, JobResult, JobSpec, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository


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
    idempotency_key: str | None = None


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
        workflow_repository: WorkflowRepository | None = None,
        dispatcher: JobDispatcher | None = None,
    ) -> None:
        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        self.dispatcher = dispatcher

    def _get_workflow_state_and_version(self, ctx: JobContext) -> tuple[str, int] | None:
        """Load state and version through public WorkflowEngine or WorkflowRepository methods."""
        if self.workflow_engine:
            return self.workflow_engine.get_workflow_state(ctx.workflow_id)
        if self.workflow_repository:
            data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if data is not None:
                agg, ver = data
                return agg.get("state", "initial"), ver
        return None

    def _validate_state_and_version(
        self,
        ctx: JobContext,
        legal_states: set[str | ProductVideoWorkflowState],
        inputs: dict[str, Any] | None = None,
    ) -> JobFailed | None:
        res = self._get_workflow_state_and_version(ctx)
        if res is None:
            return JobFailed(
                retryable=False,
                code="WORKFLOW_NOT_FOUND",
                message=f"Workflow '{ctx.workflow_id}' not found in engine/repository",
            )

        current_state, current_version = res

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
        if current_state not in legal_state_values:
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

        # 4. Check expected digests if provided
        if ctx.expected_digests and inputs:
            if not verify_job_digests(ctx.job_id, inputs, ctx.expected_digests):
                return JobFailed(
                    retryable=False,
                    code="DIGEST_MISMATCH",
                    message="Input digest verification failed",
                )

        return None

    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str]) -> JobSucceeded | JobFailed:
        inputs = {"product_name": product_name, "keywords": keywords}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RESEARCHING}, inputs)
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
        inputs = {"research_result": research_result}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not research_result:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="research_result cannot be empty")
        try:
            result = self.pi_client.build_resource_pack(research_result)
            return JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
        except Exception as e:
            return JobFailed(retryable=True, code="PI_BUILD_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
        inputs = {"pack_dict": pack_dict}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not pack_dict:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="pack_dict cannot be empty")
        try:
            result = self.pi_client.lock_resource_pack(pack_dict, ctx.owner_user_id)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
        inputs = {"product_id": product_id, "brief_config": brief_config or {}}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_BRIEF}, inputs)
        if err:
            return err
        if not product_id:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5)
            result = self.video_client.create_creative_brief(brief_config)
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
        inputs = {"brief_ref": brief_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_SCENE_PLAN}, inputs)
        if err:
            return err
        if not brief_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5)
            result = self.video_client.create_scene_plan(brief_ref)
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))

    def storyboard_job(self, ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
        inputs = {"scene_ref": scene_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_STORYBOARD}, inputs)
        if err:
            return err
        if not scene_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 10)
            result = self.video_client.create_storyboard(scene_ref)
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

    def render_job(self, ctx: JobContext, story_ref: Any) -> JobSucceeded | JobFailed:
        inputs = {"story_ref": story_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RENDERING}, inputs)
        if err:
            return err
        if not story_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="story_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 50)
            result = self.video_client.render_video(story_ref)
            commit_budget(alloc)
            return JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

    def export_job(self, ctx: JobContext, render_ref: Any) -> JobSucceeded | JobFailed:
        inputs = {"render_ref": render_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.EXPORTING}, inputs)
        if err:
            return err
        if not render_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="render_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 20)
            result = self.video_client.export_video(render_ref)
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

    def dispatch_registered_job(self, job_name: str, ctx: JobContext, *args: Any, **kwargs: Any) -> JobResult:
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
        if not self.dispatcher:
            raise RuntimeError("No JobDispatcher attached to ProductVideoJobHandlers")
        return self.dispatcher.dispatch(spec)

    def wait_for_job(self, job_id: str, timeout: float = 2.0) -> JobResult | None:
        """Wait for a dispatched job to reach terminal state."""
        if not self.dispatcher:
            return None
        start = time.time()
        while time.time() - start < timeout:
            res = self.dispatcher.get_result(job_id)
            if res and res.status in (JobStatus.SUCCESS, JobStatus.FAILURE):
                return res
            time.sleep(0.01)
        return self.dispatcher.get_result(job_id)


def register_product_video_job_handlers(
    dispatcher: JobDispatcher | Any,
    handlers_service: ProductVideoJobHandlers | None = None,
    workflow_engine: WorkflowEngine | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
) -> ProductVideoJobHandlers:
    """Register all product-to-video pipeline job handlers with the Gate 4 dispatcher/registry."""
    if handlers_service is not None:
        service = handlers_service
        if isinstance(dispatcher, JobDispatcher):
            service.dispatcher = dispatcher
    else:
        service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            dispatcher=dispatcher if isinstance(dispatcher, JobDispatcher) else None,
        )

    if hasattr(dispatcher, "register"):
        for job_name, handler_func in service.get_handlers_map().items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(service.get_handlers_map())
    return service
