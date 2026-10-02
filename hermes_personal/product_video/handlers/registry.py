from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.capabilities.snapshots import CatalogSnapshot
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.workflows.envelope import (
    MalformedEnvelopeError,
    OutboxEnvelope,
    build_envelope,
)
from hermes_personal.product_video.job_contracts import (
    JobContext,
    JobDispatchError,
    JobFailed,
    JobSucceeded,
    TerminalJobError,
)
from hermes_personal.product_video.workflow_state import (
    ProductVideoWorkflowState,
)

from hermes_personal.workflows.jobs import JobDispatcher
from hermes_personal.workflows.repository import WorkflowRepository

from hermes_personal.product_video.handlers.common import (
    _is_qc_pass,
    _locked_research_dossier,
    _qc_context,
    _qc_report_payload,
)

# Import the ProductVideoJobHandlers class
from hermes_personal.product_video.handlers._base import ProductVideoJobHandlers

logger = logging.getLogger(__name__)



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
    tool_registry: Any | None = None,
    provider_mode: str = "configured",
    poll_timeout: float = 60.0,
    poll_interval: float = 0.5,
    creative_generator: Any | None = None,
    keyframe_runtime_factory: Callable[[], Any] | None = None,
    qc_service_factory: Callable[[Any], Any] | None = None,
    capability_snapshot: CatalogSnapshot | None = None,
) -> dict[str, Callable[[OutboxEnvelope], None]]:
    """Create production topic handlers for durable outbox delivery.

    Binds topic 'job.dispatch' to ProductVideoJobHandlers.
    """
    if (
        provider_mode == "configured"
        and capability_snapshot is None
        and workflow_repository is not None
    ):
        from hermes_personal.capabilities.discovery import CapabilityDiscovery
        from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository

        snapshot_repository = CapabilitySnapshotRepository(workflow_repository.conn)
        capability_snapshot = snapshot_repository.get_active()
        if capability_snapshot is None and tool_registry is not None and hasattr(
            tool_registry, "get_all_tool_names"
        ):
            # This is composition-root discovery, before any workflow handler
            # runs. Handlers receive only the resulting immutable snapshot and
            # never select an alias from the live registry.
            capability_snapshot = snapshot_repository.save_and_activate(
                CapabilityDiscovery().scan(tool_registry).bindings
            )
    if handlers_service is None:
        if provider_mode == "configured" and keyframe_runtime_factory is None and workflow_repository is not None:
            from hermes_personal.integrations.video_factory.keyframe_provider import (
                KeyframeOperationStore,
                KeyframeRuntime,
                VertexKeyframeProvider,
            )
            from hermes_personal.integrations.video_factory.capacity import (
                ProviderCapacityStore, configured_capacity,
            )

            from hermes_personal.product_video.storage.layout import get_workspace_layout
            workspace = get_workspace_layout().root
            keyframe_output = workspace / "keyframes"
            keyframe_runtime_factory = lambda: KeyframeRuntime(
                store=KeyframeOperationStore(workflow_repository.conn),
                provider=VertexKeyframeProvider(output_dir=keyframe_output),
                capacity_store=ProviderCapacityStore(workflow_repository.conn),
                capacity_limit=configured_capacity("vertex_keyframe"),
            )
        handlers_service = ProductVideoJobHandlers(
            pi_client=pi_client,
            video_client=video_client,
            workflow_engine=workflow_engine,
            workflow_repository=workflow_repository,
            tool_registry=tool_registry,
            provider_mode=provider_mode,
            poll_timeout=poll_timeout,
            poll_interval=poll_interval,
            creative_generator=creative_generator,
            keyframe_runtime_factory=keyframe_runtime_factory,
            capability_snapshot=capability_snapshot,
        )
    handlers_map = handlers_service.get_handlers_map()

    def _create_qc_service(connection: Any) -> Any:
        if qc_service_factory is not None:
            return qc_service_factory(connection)
        from hermes_personal.product_video.qc.service import ProductVideoQCService

        return ProductVideoQCService(connection)

    def handle_job_dispatch(envelope: OutboxEnvelope, heartbeat_fn: Callable[[], bool] | None = None) -> None:
        payload = envelope.payload
        job_name = payload.get("job_name")
        if not job_name:
            raise MalformedEnvelopeError("Missing 'job_name' in job.dispatch payload")

        if job_name not in handlers_map:
            raise ValueError(f"Unconfigured product_video job handler: {job_name!r}")

        target_wf = envelope.workflow_id
        repo = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        if repo:
            with repo.conn:
                cur = repo.conn.cursor()
                cur.execute(
                    "SELECT command_id FROM processed_command WHERE workflow_id = ? AND command_id = ?",
                    (target_wf, f"cmd_{envelope.message_id}"),
                )
                if cur.fetchone():
                    return

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
            heartbeat_fn=heartbeat_fn,
        )

        handler_fn = handlers_map[job_name]
        args = payload.get("args", [])
        kwargs = payload.get("kwargs", {})

        result = handler_fn(ctx, *args, **kwargs)

        if isinstance(result, JobFailed):
            if not result.retryable:
                raise TerminalJobError(f"Job execution failed [{result.code}]: {result.message}", code=result.code)
            raise JobDispatchError(f"Job execution failed [{result.code}]: {result.message}", code=result.code, retryable=True)

        if isinstance(result, JobSucceeded):
            if repo:
                wf_data = repo.get_workflow(target_wf)
                if wf_data:
                    agg, version = wf_data
                    from hermes_personal.product_video.workflow import transition
                    from hermes_personal.product_video.qc.models import QCStage

                    stage_key_map = {
                        "product_video.research": "research_result",
                        "product_video.resource_pack": "resource_pack",
                        "product_video.lock": "locked_pack",
                        "product_video.creative_brief": "creative_brief",
                        "product_video.scene_plan": "scene_plan",
                        "product_video.storyboard": "storyboard",
                        "product_video.render": "render_result",
                        "product_video.export": "export_result",
                    }
                    next_agg = dict(agg)
                    st_key = stage_key_map.get(job_name)
                    if st_key and result.artifact_ref is not None:
                        next_agg[st_key] = result.artifact_ref
                    if result.artifact_ref is not None:
                        next_agg["latest_artifact"] = result.artifact_ref

                    next_agg.pop("active_render_job_id", None)
                    next_agg.pop("active_export_job_id", None)

                    is_hitl = False
                    gate_name = None
                    outbox_next = None

                    forward_kwargs: dict[str, Any] = {}
                    if agg.get("project_id"):
                        forward_kwargs["project_id"] = agg["project_id"]
                    if agg.get("qc_authorization"):
                        forward_kwargs["qc_authorization"] = agg["qc_authorization"]
                    if agg.get("qc_max_cost_usd") is not None:
                        forward_kwargs["qc_max_cost_usd"] = agg["qc_max_cost_usd"]

                    if job_name == "product_video.research":
                        next_validated = transition(ProductVideoWorkflowState.RESEARCHING, ProductVideoWorkflowState.BUILDING_RESOURCE_PACK)
                        next_agg["state"] = next_validated.value
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_pack_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.resource_pack",
                                "workflow_id": target_wf,
                                "args": [result.artifact_ref],
                                "kwargs": forward_kwargs,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                "project_id": agg.get("project_id"),
                            },
                        )
                    elif job_name == "product_video.resource_pack":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            if heartbeat_fn is not None and not heartbeat_fn():
                                raise RuntimeError("Storyboard lease expired before keyframe QC")
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.IMAGE,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.IMAGE.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires explicit cost authorization")
                                is_hitl = False
                            elif isinstance(qc_res, dict) and qc_res.get("status") == "completed" and not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.IMAGE.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingProductLock"
                        else:
                            next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingProductLock"
                    elif job_name == "product_video.retry_image_qc":
                        # Transitions back to AwaitingProductLock if retry passed, or terminal fail
                        next_validated = transition(ProductVideoWorkflowState.RETRYING_IMAGE_QC, ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingProductLock"
                    elif job_name == "product_video.lock":
                        next_validated = transition(ProductVideoWorkflowState.BUILDING_RESOURCE_PACK, ProductVideoWorkflowState.CREATING_BRIEF)
                        next_agg["state"] = next_validated.value
                        rp_dict = result.artifact_ref.get("resource_pack", result.artifact_ref) if isinstance(result.artifact_ref, dict) else {}
                        product_id = str(rp_dict.get("product_id") or rp_dict.get("resource_pack_id") or rp_dict.get("id") or f"prod_{target_wf}")
                        brief_config: dict[str, Any] = {
                            "resource_pack": result.artifact_ref,
                            "project_id": agg.get("project_id"),
                        }
                        if provider_mode == "configured":
                            from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator

                            if isinstance(handlers_service.creative_generator, SingleModelCreativeGenerator):
                                brief_config["research_dossier"] = _locked_research_dossier(
                                    workflow_id=target_wf,
                                    aggregate=agg,
                                    locked_pack=result.artifact_ref,
                                    connection=repo.conn,
                                )
                        outbox_next = build_envelope(
                            workflow_id=target_wf,
                            topic="job.dispatch",
                            idempotency_key=f"idemp_brief_{target_wf}_v{version + 1}",
                            payload={
                                "job_name": "product_video.creative_brief",
                                "workflow_id": target_wf,
                                "args": [product_id, brief_config],
                                "kwargs": forward_kwargs,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                                "project_id": agg.get("project_id"),
                            },
                        )
                    elif job_name == "product_video.creative_brief":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_BRIEF, ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingBriefApproval"
                    elif job_name == "product_video.scene_plan":
                        next_validated = transition(ProductVideoWorkflowState.CREATING_SCENE_PLAN, ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL)
                        next_agg["state"] = next_validated.value
                        is_hitl = True
                        gate_name = "AwaitingSceneApproval"
                    elif job_name == "product_video.storyboard":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.KEYFRAME,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.KEYFRAME.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires authorization")
                                is_hitl = False
                            elif not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.KEYFRAME.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                failed_report = _qc_report_payload(qc_res)
                                failed_findings = (
                                    failed_report.get("findings", {})
                                    if isinstance(failed_report, dict)
                                    else {}
                                )
                                recovery_plan = (
                                    failed_findings.get("recovery_plan")
                                    if isinstance(failed_findings, dict)
                                    else None
                                )
                                if isinstance(recovery_plan, dict):
                                    next_agg["keyframe_recovery_plan"] = recovery_plan
                                next_agg["operator_reason"] = qc_res.get(
                                    "reason",
                                    "Keyframe QC failed; apply the persisted recovery plan before regenerating and rerunning QC",
                                )
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.CREATING_STORYBOARD, ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingStoryboardApproval"
                                rep = _qc_report_payload(qc_res)
                                expected_artifact = dict(result.artifact_ref)
                                expected_artifact["keyframe_qc_receipt"] = rep if rep else qc_res
                                next_agg["storyboard"] = expected_artifact
                                next_agg["latest_artifact"] = expected_artifact
                                next_agg.pop("keyframe_recovery_plan", None)
                                result = JobSucceeded(artifact_ref=expected_artifact, next_command=result.next_command)
                        else:
                            next_validated = transition(ProductVideoWorkflowState.CREATING_STORYBOARD, ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingStoryboardApproval"
                    elif job_name == "product_video.render":
                        if provider_mode == "configured":
                            repo.commit_workflow(
                                workflow_id=target_wf,
                                aggregate_json=json.dumps(next_agg),
                                events=[],
                                expected_version=version,
                            )
                            version += 1
                            qc_svc = _create_qc_service(repo.conn)
                            qc_auth = agg.get("qc_authorization") or forward_kwargs.get("qc_authorization")
                            qc_max = agg.get("qc_max_cost_usd") or forward_kwargs.get("qc_max_cost_usd")
                            if qc_auth and isinstance(qc_auth, dict) and "max_cost_usd" in qc_auth and qc_max is None:
                                qc_max = qc_auth.get("max_cost_usd")
                            qc_res = qc_svc.run(
                                target_wf,
                                stage=QCStage.VIDEO,
                                provider_mode=provider_mode,
                                authorize_cost=bool(qc_auth),
                                max_cost_usd=float(qc_max) if qc_max is not None else None,
                                authorization=qc_auth,
                            )
                            if isinstance(qc_res, dict) and qc_res.get("status") == "pending":
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_authorization"
                                next_agg["operator_stage"] = QCStage.VIDEO.value
                                next_agg["operator_reason"] = qc_res.get("reason", "Configured QC requires explicit cost authorization")
                                is_hitl = False
                            elif not _is_qc_pass(qc_res):
                                next_agg["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
                                next_agg["operator_action"] = "qc_retry_authorization"
                                next_agg["operator_stage"] = QCStage.VIDEO.value
                                next_agg["operator_qc_report_id"] = qc_res.get("report_id") or (_qc_report_payload(qc_res).get("report_id"))
                                next_agg["operator_reason"] = qc_res.get("reason", "Video QC did not produce a PASS verdict")
                                is_hitl = False
                            else:
                                next_validated = transition(ProductVideoWorkflowState.RENDERING, ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL)
                                next_agg["state"] = next_validated.value
                                is_hitl = True
                                gate_name = "AwaitingFinalApproval"
                        else:
                            next_validated = transition(ProductVideoWorkflowState.RENDERING, ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL)
                            next_agg["state"] = next_validated.value
                            is_hitl = True
                            gate_name = "AwaitingFinalApproval"
                    elif job_name == "product_video.export":
                        next_validated = transition(ProductVideoWorkflowState.EXPORTING, ProductVideoWorkflowState.COMPLETED)
                        next_agg["state"] = next_validated.value
                    else:
                        raise ValueError(f"Unknown job_name in handle_job_dispatch: {job_name}")

                    with repo.conn:
                        cur = repo.conn.cursor()
                        if is_hitl and gate_name:
                            approval_svc = ApprovalService(repo.conn)
                            proj_id = agg.get("project_id") or payload.get("project_id") or f"proj_{target_wf}"
                            art_dict = result.artifact_ref if isinstance(result.artifact_ref, dict) else {}
                            art_id = (
                                art_dict.get("artifact_id")
                                or art_dict.get("brief_id")
                                or art_dict.get("scene_plan_id")
                                or art_dict.get("storyboard_id")
                                or art_dict.get("render_id")
                                or art_dict.get("export_id")
                                or art_dict.get("resource_pack_id")
                                or art_dict.get("id")
                            )
                            art_ver = art_dict.get("version") or art_dict.get("resource_pack_version")
                            approval_payload = {
                                "workflow_id": target_wf,
                                "project_id": proj_id,
                                "gate": gate_name,
                                "workflow_version": version + 1,
                                "artifact_ref": result.artifact_ref,
                                "owner_user_id": payload.get("owner_user_id", "local-owner"),
                            }
                            if art_id is not None:
                                approval_payload["artifact_id"] = art_id
                            if art_ver is not None:
                                approval_payload["artifact_version"] = art_ver
                            req_id = approval_svc.submit_request(
                                approval_payload,
                                cursor=cur,
                            )
                            next_agg["pending_approval_gate"] = gate_name
                            next_agg["pending_approval_id"] = req_id
                        else:
                            next_agg.pop("pending_approval_gate", None)
                            next_agg.pop("pending_approval_id", None)

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
    project_id: str | None = None,
    source_context: dict[str, Any] | None = None,
    qc_authorization: dict[str, Any] | None = None,
    qc_max_cost_usd: float | None = None,
    research_snapshot_id: str | None = None,
) -> str:
    """Production entrypoint to create and enqueue a durable Product-to-Video workflow.

    Commits aggregate state 'researching', appends 'WorkflowStarted' event,
    and enqueues the 'job.dispatch' OutboxEnvelope for product_video.research.
    """
    if not project_id or not str(project_id).strip():
        raise ValueError("project_id is required")
    effective_project_id = str(project_id).strip()
    idemp = idempotency_key or f"idemp_res_{workflow_id}"
    effective_kwargs: dict[str, Any] = {"project_id": effective_project_id}
    if source_context:
        for k in ("canonical_product_key", "brand", "model", "variant", "images", "source_product_id"):
            if k in source_context and source_context[k] is not None:
                effective_kwargs[k] = source_context[k]
    effective_kwargs.update(_qc_context({
        "qc_authorization": qc_authorization,
        "qc_max_cost_usd": qc_max_cost_usd,
    }, workflow_id=workflow_id))
    if research_snapshot_id:
        effective_kwargs["research_snapshot_id"] = str(research_snapshot_id)

    outbox_msg = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=idemp,
        payload={
            "job_name": "product_video.research",
            "workflow_id": workflow_id,
            "project_id": effective_project_id,
            "args": [product_name, keywords, pdp_url],
            "owner_user_id": owner_user_id,
            "kwargs": effective_kwargs,
        },
    )
    aggregate: dict[str, Any] = {
        "state": ProductVideoWorkflowState.RESEARCHING.value,
        "project_id": effective_project_id,
        "owner_user_id": owner_user_id,
        "pdp_url": pdp_url,
    }
    if source_context is not None:
        aggregate["source_context"] = source_context
        aggregate["product_key"] = source_context.get("product_key")
    aggregate.update(_qc_context({
        "qc_authorization": qc_authorization,
        "qc_max_cost_usd": qc_max_cost_usd,
    }, workflow_id=workflow_id))
    if research_snapshot_id:
        aggregate["research_snapshot_id"] = str(research_snapshot_id)

    workflow_repository.commit_workflow(
        workflow_id=workflow_id,
        aggregate_json=json.dumps(aggregate),
        events=[
            {
                "event_id": f"evt_start_{workflow_id}",
                "command_id": f"cmd_start_{workflow_id}",
                "event_type": "WorkflowStarted",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"product_name": product_name, "keywords": keywords, "pdp_url": pdp_url, "project_id": effective_project_id},
            }
        ],
        outbox_message=outbox_msg,
        expected_version=0,
    )
    return workflow_id
