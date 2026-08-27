from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.envelope import (
    MalformedEnvelopeError,
    OutboxEnvelope,
    build_envelope,
)
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
        provider_mode: str = "fake",
    ) -> None:
        self.provider_mode = provider_mode
        self._missing_live_provider = (
            provider_mode == "configured" and (pi_client is None or video_client is None)
        )
        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        self.dispatcher = dispatcher
        self._idempotency_cache: dict[str, JobSucceeded] = {}

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
        if getattr(self, "_missing_live_provider", False):
            raise RuntimeError(
                "MISSING_PROVIDER_CONFIG: ProductIntelligence/VideoFactory live API provider adapters "
                "are unconfigured for provider_mode='configured'. Set provider_mode='fake' for explicit "
                "offline/test verification."
            )

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

    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str], pdp_url: str | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:research:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"product_name": product_name, "keywords": keywords}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RESEARCHING}, inputs)
        if err:
            return err
        if not product_name:
            return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
        try:
            extra_kwargs = {"pdp_url": pdp_url} if pdp_url is not None else {}
            result = self.pi_client.research(
                product_name,
                keywords,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_kwargs,
            )
            if pdp_url:
                result["pdp_url"] = pdp_url
            res = JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

    def resource_pack_job(self, ctx: JobContext, research_result: dict) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:resource_pack:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"research_result": research_result}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not research_result:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="research_result cannot be empty")
        try:
            result = self.pi_client.build_resource_pack(
                research_result,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "lock_resource_pack"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            return JobFailed(retryable=True, code="PI_PACK_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:lock:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"pack_dict": pack_dict}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.BUILDING_RESOURCE_PACK}, inputs)
        if err:
            return err
        if not pack_dict:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="pack_dict cannot be empty")
        try:
            result = self.pi_client.lock_resource_pack(
                pack_dict,
                ctx.owner_user_id,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))

    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:creative_brief:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"product_id": product_id, "brief_config": brief_config or {}}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_BRIEF}, inputs)
        if err:
            return err
        if not product_id:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5, idempotency_key=cache_key)
            result = self.video_client.create_creative_brief(
                brief_config,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_scene_plan", "product_id": product_id})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_BRIEF_FAILED", message=str(e))

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:scene_plan:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"brief_ref": brief_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_SCENE_PLAN}, inputs)
        if err:
            return err
        if not brief_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 5, idempotency_key=cache_key)
            result = self.video_client.create_scene_plan(
                brief_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))

    def storyboard_job(self, ctx: JobContext, scene_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:storyboard:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"scene_ref": scene_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.CREATING_STORYBOARD}, inputs)
        if err:
            return err
        if not scene_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 10, idempotency_key=cache_key)
            result = self.video_client.create_storyboard(
                scene_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "render_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_STORYBOARD_FAILED", message=str(e))

    def render_job(self, ctx: JobContext, story_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:render:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"story_ref": story_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.RENDERING}, inputs)
        if err:
            return err
        if not story_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="story_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 50, idempotency_key=cache_key)
            result = self.video_client.render_video(
                story_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                release_budget(alloc)
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))

    def export_job(self, ctx: JobContext, render_ref: Any) -> JobSucceeded | JobFailed:
        cache_key = f"{ctx.workflow_id}:export:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        inputs = {"render_ref": render_ref}
        err = self._validate_state_and_version(ctx, {ProductVideoWorkflowState.EXPORTING}, inputs)
        if err:
            return err
        if not render_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="render_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget("video_factory", 20, idempotency_key=cache_key)
            result = self.video_client.export_video(
                render_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
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
    provider_mode: str = "fake",
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
            provider_mode=provider_mode,
        )

    if hasattr(dispatcher, "register"):
        for job_name, handler_func in service.get_handlers_map().items():
            dispatcher.register(job_name, handler_func)
    elif isinstance(dispatcher, dict):
        dispatcher.update(service.get_handlers_map())
    return service


def create_product_video_topic_handlers(
    workflow_engine: WorkflowEngine | None = None,
    workflow_repository: WorkflowRepository | None = None,
    handlers_service: ProductVideoJobHandlers | None = None,
    pi_client: ProductIntelligenceClient | None = None,
    video_client: VideoFactoryClient | None = None,
    provider_mode: str = "configured",
) -> dict[str, Callable[[OutboxEnvelope], None]]:
    """Create production topic handlers for durable outbox delivery.

    Binds topic 'job.dispatch' to ProductVideoJobHandlers.
    """
    if handlers_service is None:
        handlers_service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            workflow_repository=workflow_repository,
            provider_mode=provider_mode,
        )
    handlers_map = handlers_service.get_handlers_map()

    def handle_job_dispatch(envelope: OutboxEnvelope) -> None:
        payload = envelope.payload
        job_name = payload.get("job_name")
        if not job_name:
            raise MalformedEnvelopeError("Missing 'job_name' in job.dispatch payload")

        if job_name not in handlers_map:
            raise ValueError(f"Unconfigured product_video job handler: {job_name!r}")

        target_wf = envelope.workflow_id
        current_version = None
        if workflow_engine:
            res = workflow_engine.get_workflow_state(target_wf)
            if res is not None:
                current_version = res[1]
        elif workflow_repository:
            data = workflow_repository.get_workflow(target_wf)
            if data is not None:
                current_version = data[1]

        ctx = JobContext(
            workflow_id=target_wf,
            job_id=f"{job_name}.{envelope.message_id}",
            owner_user_id=payload.get("owner_user_id", "local-owner"),
            expected_version=current_version,
            idempotency_key=envelope.idempotency_key,
        )

        handler_fn = handlers_map[job_name]
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})

        result = handler_fn(ctx, *args, **kwargs)

        if isinstance(result, JobFailed):
            raise RuntimeError(f"Job execution failed [{result.code}]: {result.message}")

        if isinstance(result, JobSucceeded):
            repo = workflow_repository or (workflow_engine.repo if workflow_engine else None)
            if repo:
                wf_data = repo.get_workflow(target_wf)
                if wf_data:
                    agg, version = wf_data

                    JOB_STAGE_MAP = {
                        "product_video.research": (
                            ProductVideoWorkflowState.RESEARCHING,
                            ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
                            True,
                            "AwaitingProductLock",
                        ),
                        "product_video.lock": (
                            ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                            ProductVideoWorkflowState.CREATING_BRIEF,
                            False,
                            None,
                        ),
                        "product_video.resource_pack": (
                            ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                            ProductVideoWorkflowState.CREATING_BRIEF,
                            False,
                            None,
                        ),
                        "product_video.creative_brief": (
                            ProductVideoWorkflowState.CREATING_BRIEF,
                            ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
                            True,
                            "AwaitingBriefApproval",
                        ),
                        "product_video.scene_plan": (
                            ProductVideoWorkflowState.CREATING_SCENE_PLAN,
                            ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
                            True,
                            "AwaitingSceneApproval",
                        ),
                        "product_video.storyboard": (
                            ProductVideoWorkflowState.CREATING_STORYBOARD,
                            ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
                            True,
                            "AwaitingStoryboardApproval",
                        ),
                        "product_video.render": (
                            ProductVideoWorkflowState.RENDERING,
                            ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
                            True,
                            "AwaitingFinalApproval",
                        ),
                        "product_video.export": (
                            ProductVideoWorkflowState.EXPORTING,
                            ProductVideoWorkflowState.COMPLETED,
                            False,
                            None,
                        ),
                    }

                    if job_name in JOB_STAGE_MAP:
                        from hermes_personal.product_video.workflow import transition
                        curr_enum, next_enum, is_hitl, gate_name = JOB_STAGE_MAP[job_name]
                        next_validated = transition(curr_enum, next_enum)
                        next_agg = dict(agg)
                        next_agg["state"] = next_validated.value
                        if result.artifact_ref:
                            next_agg["latest_artifact"] = result.artifact_ref

                        outbox_next = None
                        if is_hitl:
                            approval_svc = ApprovalService(repo.conn)
                            req_id = approval_svc.submit_request({
                                "workflow_id": target_wf,
                                "gate": gate_name,
                                "workflow_version": version + 1,
                                "artifact_ref": result.artifact_ref,
                            })
                            next_agg["pending_approval_gate"] = gate_name
                            next_agg["pending_approval_id"] = req_id
                        else:
                            next_job_name = "product_video.creative_brief" if job_name in ("product_video.lock", "product_video.resource_pack") else None
                            if next_job_name:
                                outbox_next = build_envelope(
                                    workflow_id=target_wf,
                                    topic="job.dispatch",
                                    idempotency_key=f"idemp_{next_job_name}_{target_wf}_v{version + 1}",
                                    payload={
                                        "job_name": next_job_name,
                                        "workflow_id": target_wf,
                                        "args": [result.artifact_ref],
                                        "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                    },
                                )

                        repo.commit_workflow(
                            workflow_id=target_wf,
                            aggregate_json=json.dumps(next_agg),
                            events=[
                                {
                                    "event_id": f"evt_{envelope.message_id}",
                                    "command_id": f"cmd_{envelope.message_id}",
                                    "event_type": "JobSucceeded",
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "payload": {"job_name": job_name, "artifact_ref": result.artifact_ref},
                                }
                            ],
                            outbox_message=outbox_next,
                            expected_version=version,
                        )

    return {"job.dispatch": handle_job_dispatch}


def start_product_video_workflow(
    workflow_repository: WorkflowRepository,
    workflow_id: str,
    product_name: str,
    keywords: list[str],
    pdp_url: str | None = None,
    owner_user_id: str = "local-owner",
    idempotency_key: str | None = None,
) -> str:
    """Production entrypoint to create and enqueue a durable Product-to-Video workflow.

    Commits aggregate state 'researching', appends 'WorkflowStarted' event,
    and enqueues the 'job.dispatch' OutboxEnvelope for product_video.research.
    """
    idemp = idempotency_key or f"idemp_res_{workflow_id}"
    outbox_msg = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=idemp,
        payload={
            "job_name": "product_video.research",
            "workflow_id": workflow_id,
            "args": [product_name, keywords, pdp_url],
            "owner_user_id": owner_user_id,
        },
    )
    workflow_repository.commit_workflow(
        workflow_id=workflow_id,
        aggregate_json=json.dumps(
            {
                "state": ProductVideoWorkflowState.RESEARCHING.value,
                "owner_user_id": owner_user_id,
                "pdp_url": pdp_url,
            }
        ),
        events=[
            {
                "event_id": f"evt_start_{workflow_id}",
                "command_id": f"cmd_start_{workflow_id}",
                "event_type": "WorkflowStarted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"product_name": product_name, "keywords": keywords, "pdp_url": pdp_url},
            }
        ],
        outbox_message=outbox_msg,
        expected_version=0,
    )
    return workflow_id
