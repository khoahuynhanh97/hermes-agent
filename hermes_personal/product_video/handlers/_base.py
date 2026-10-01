from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import asdict, is_dataclass, replace
from pathlib import Path
from typing import Any, Callable

from hermes_personal.integrations.product_intelligence.client import ProductIntelligenceClient
from hermes_personal.integrations.video_factory.client import VideoFactoryClient
from hermes_personal.capabilities.snapshots import CatalogSnapshot
from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget, get_reservation
from hermes_personal.workflows.engine import WorkflowEngine
from hermes_personal.product_video.qc.models import QCStage
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.job_contracts import (
    ExecutionBindingPreflightError,
    JobContext,
    JobFailed,
    JobSucceeded,
    LeaseLostError,
    TerminalJobError,
)
from hermes_personal.product_video.workflow_state import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
)
from hermes_personal.product_video.provider_runtime import (
    validate_polling_setting,
    validate_provider_mode,
)
from hermes_personal.product_video.mcp_adapters import (
    MCPProductIntelligenceAdapter,
    MCPVideoFactoryAdapter,
    _get_global_tool_registry,
    _resolve_snapshot_execution_wire,
)

from hermes_personal.workflows.jobs import JobDispatcher, JobResult, JobSpec, JobStatus
from hermes_personal.workflows.repository import WorkflowRepository

# Import helper functions from common module (used by merged methods)
from hermes_personal.product_video.handlers.common import (
    _paid_budget_kwargs,
    _video_factory_brief_config,
    verify_job_digests,
    _recover_creative_brief,
    _require_configured_execution_binding,
    _resolve_durable_resume_job_id,
)

logger = logging.getLogger(__name__)



class ProductVideoJobHandlers:
    """Deterministic product-to-video job handlers with injected dependencies and workflow state loading."""

    def __init__(
        self,
        pi_client: ProductIntelligenceClient | None = None,
        video_client: VideoFactoryClient | None = None,
        workflow_engine: WorkflowEngine | None = None,
        workflow_repository: WorkflowRepository | None = None,
        dispatcher: JobDispatcher | None = None,
        tool_registry: Any | None = None,
        provider_mode: str = "fake",
        poll_timeout: float = 60.0,
        poll_interval: float = 0.5,
        creative_generator: Any | None = None,
        keyframe_runtime_factory: Callable[[], Any] | None = None,
        capability_snapshot: CatalogSnapshot | None = None,
    ) -> None:
        self.provider_mode = validate_provider_mode(provider_mode)
        self.tool_registry = tool_registry
        self.poll_timeout = validate_polling_setting("poll_timeout", poll_timeout, 60.0)
        self.poll_interval = validate_polling_setting("poll_interval", poll_interval, 0.5)
        self.creative_generator = creative_generator
        self.keyframe_runtime_factory = keyframe_runtime_factory
        self.capability_snapshot = capability_snapshot

        if self.provider_mode == "configured":
            if pi_client is None:
                pi_client = self._resolve_pi_adapter(tool_registry)
            if video_client is None:
                video_client = self._resolve_video_adapter(tool_registry)

            self._missing_pi_provider = pi_client is None
            self._missing_video_provider = video_client is None
            self._missing_live_provider = (
                self._missing_pi_provider or self._missing_video_provider
            )
            if self._missing_live_provider:
                missing = []
                if pi_client is None:
                    missing.append("ProductIntelligence active capability binding")
                if video_client is None:
                    missing.append("VideoFactory active capability binding (canonical mcp__video_factory__render required)")
                self._missing_provider_details = ", ".join(missing)
            else:
                self._missing_provider_details = None
        else:
            self._missing_pi_provider = False
            self._missing_video_provider = False
            self._missing_live_provider = False
            self._missing_provider_details = None

        self.pi_client = pi_client or ProductIntelligenceClient()
        self.video_client = video_client or VideoFactoryClient()
        self.workflow_engine = workflow_engine
        self.workflow_repository = workflow_repository or (workflow_engine.repo if workflow_engine else None)
        self.dispatcher = dispatcher
        self._idempotency_cache: dict[str, JobSucceeded] = {}

    def _resolve_pi_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None or self.capability_snapshot is None:
            return None
        capability_keys = {
            "research": "product.research",
            "build_resource_pack": "product.resource_pack.build",
            "lock_resource_pack": "product.resource_pack.lock",
        }
        resolved = {
            key: _resolve_snapshot_execution_wire(self.capability_snapshot, capability_id)
            for key, capability_id in capability_keys.items()
        }
        return MCPProductIntelligenceAdapter(
            effective_registry,
            {
                key: wire for key, (wire, _reason) in resolved.items() if wire
            } | {"get_research": "mcp__product_intelligence__get_product_research"},
            {key: reason for key, (_wire, reason) in resolved.items() if reason},
        )

    def _resolve_video_adapter(self, registry: Any | None) -> Any | None:
        effective_registry = registry or _get_global_tool_registry()
        if effective_registry is None or self.capability_snapshot is None:
            return None
        capability_keys = {
            "brief": "video.brief.create",
            "scene_plan": "video.scene_plan.create",
            "storyboard": "video.storyboard.create",
            "render": "video.render",
            "export": "video.export",
        }
        resolved = {
            key: _resolve_snapshot_execution_wire(self.capability_snapshot, capability_id)
            for key, capability_id in capability_keys.items()
        }
        # Execution-stage wires come only from the active snapshot. The
        # remaining static names are non-capability factory maintenance/status
        # calls and are never selected by alias preference.
        wire_map = {
            key: wire for key, (wire, _reason) in resolved.items() if wire
        }
        render_wire = wire_map.get("render")
        if render_wire is not None and render_wire != "mcp__video_factory__render":
            wire_map.pop("render")
        wire_map.update(
            {
                "project_create": "mcp__video_factory__video_project_create",
                "resource_pack_save": "mcp__video_factory__resource_pack_save",
                "resource_pack_lock": "mcp__video_factory__resource_pack_lock",
                "creative_brief_get": "mcp__video_factory__creative_brief_get",
                "brief_approve": "mcp__video_factory__creative_brief_approve",
                "scene_plan_approve": "mcp__video_factory__scene_plan_approve",
                "storyboard_approve": "mcp__video_factory__storyboard_approve",
                "final_video_approve": "mcp__video_factory__final_video_approve",
                "get_job_status": "mcp__video_factory__get_job_status",
            }
        )
        return MCPVideoFactoryAdapter(
            effective_registry,
            wire_map,
            poll_timeout=self.poll_timeout,
            poll_interval=self.poll_interval,
            binding_reasons={key: reason for key, (_wire, reason) in resolved.items() if reason},
        )

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




    # Methods from qc_handler.py
    def retry_image_qc_job(self, ctx: JobContext, resource_pack: dict, **kwargs: Any) -> JobSucceeded | JobFailed:
        """Auto-retry Image QC with image cleaning for recoverable failures."""
        from hermes_personal.product_video.qc.auto_retry_helpers import (
            extract_artifacts_from_qc,
            is_cleanable_failure,
            replace_images_in_resource_pack,
        )
        
        # 1. Validate state
        err = self._validate_state_and_version(
            ctx,
            {ProductVideoWorkflowState.RETRYING_IMAGE_QC, ProductVideoWorkflowState.BUILDING_RESOURCE_PACK},
            {"resource_pack": resource_pack},
        )
        if err:
            return err
        
        # 2. Extract original QC report
        initial_qc = resource_pack.get("initial_qc_report")
        if not initial_qc or initial_qc.get("verdict") != "FAIL":
            return JobFailed(
                retryable=False,
                code="INVALID_STATE",
                message="retry_image_qc_job requires a FAIL QC report"
            )
        
        # 3. Check retry count (max 1 retry to avoid infinite loops)
        retry_count = resource_pack.get("image_qc_retry_count", 0)
        if retry_count >= 1:
            return JobFailed(
                retryable=False,
                code="MAX_RETRIES_EXCEEDED",
                message="Image QC already retried once; manual review required"
            )
        
        # 4. Check if failure is cleanable
        if not is_cleanable_failure(initial_qc):
            return JobFailed(
                retryable=False,
                code="NON_CLEANABLE_FAILURE",
                message="Image QC failure is terminal; manual review required"
            )
        
        # 5. Run Image Cleaner
        from hermes_personal.product_video.preprocessing.image_cleaner import ProductImageCleaner
        
        cleaner = ProductImageCleaner()
        cleaning_result = cleaner.clean_resource_pack(
            resource_pack=resource_pack,
            output_dir=None,  # Auto-generates in workspace
            detected_artifacts=extract_artifacts_from_qc(initial_qc),
        )
        
        if not cleaning_result.get("cleaned_images"):
            return JobFailed(
                retryable=False,
                code="CLEANING_FAILED",
                message="Image Cleaner produced no cleaned images"
            )
        
        # 6. Update resource pack with cleaned images
        cleaned_pack = replace_images_in_resource_pack(
            resource_pack=resource_pack,
            cleaned_images=cleaning_result["cleaned_images"]
        )
        cleaned_pack["image_qc_retry_count"] = retry_count + 1
        cleaned_pack["cleaning_summary"] = cleaning_result.get("summary")
        
        # 7. Re-run Image QC on cleaned images
        from hermes_personal.product_video.qc.image_qc import run_image_qc
        from hermes_personal.product_video.qc.contracts import QCVerdict
        from hermes_personal.product_video.qc.repository import QCReportRepository
        
        product = resource_pack.get("research_snapshot", {}).get("product")
        retry_qc_report, retry_eligible = run_image_qc(
            workflow_id=ctx.workflow_id,
            resource_pack=cleaned_pack,
            product=product,
            repo=QCReportRepository(ctx.connection) if hasattr(ctx, 'connection') else None,
            attempt_id=f"retry_{retry_count + 1}",
        )
        
        cleaned_pack["retry_qc_report"] = retry_qc_report.to_dict() if hasattr(retry_qc_report, 'to_dict') else retry_qc_report
        
        if retry_qc_report.verdict == QCVerdict.PASS:
            # SUCCESS: Cleaned images passed QC
            return JobSucceeded(
                artifact_ref=cleaned_pack,
                next_command={"command": "lock_resource_pack"}
            )
        else:
            # FAIL: Cleaning did not fix the issue -> terminal failure
            return JobFailed(
                retryable=False,
                code="IMAGE_QC_TERMINAL_FAILURE",
                message=f"Image QC failed after cleaning: {retry_qc_report.findings.get('recovery_reason', 'unknown')}"
            )

    def _resolve_keyframe_provider(self) -> KeyframeGenerationPort:
        """Resolve Google Flow Keyframe Provider for storyboard generation."""
        from hermes_personal.integrations.video_factory.google_flow_keyframe_provider import GoogleFlowKeyframeProvider
        # Path resolved from hermes config.yaml (standard hermes-personal location)
        return GoogleFlowKeyframeProvider(
            profile_path=Path.home() / ".config" / "hermes" / "google-flow-profile",
            chrome_profile_directory="Default",
        )


    def _validate_state_and_version(
        self,
        ctx: JobContext,
        legal_states: set[str | ProductVideoWorkflowState],
        inputs: dict[str, Any] | None = None,
        *,
        provider_family: str | None = None,
    ) -> JobFailed | None:
        missing_provider = (
            provider_family == "product_intelligence" and self._missing_pi_provider
        ) or (provider_family == "video_factory" and self._missing_video_provider)
        if missing_provider:
            details = getattr(self, "_missing_provider_details", None) or "live API provider adapters unconfigured"
            raise RuntimeError(
                f"MISSING_PROVIDER_CONFIG: {details} for provider_mode='configured'. "
                "Register the required MCP tools in config.yaml under 'mcp_servers' or set provider_mode='fake' for explicit offline/test verification."
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

    def _run_preview_image_qc(
        self,
        workflow_id: str,
        resource_pack: dict,
        product_metadata: dict | None = None,
        owner_user_id: str = "",
        project_id: str = "",
    ) -> tuple[dict, list]:
        """Run preview Image QC on resource pack to determine if retry is needed."""
        from hermes_personal.product_video.qc.image_qc import run_image_qc
        from hermes_personal.product_video.qc.repository import QCReportRepository
        
        # Extract connection from workflow repository if available
        connection = self.workflow_repository.conn if self.workflow_repository else None
        repo = QCReportRepository(connection) if connection else None
        
        # If not provided, try to extract from resource pack
        if not owner_user_id:
            owner_user_id = resource_pack.get("owner_user_id", "test_user")
        if not project_id:
            project_id = resource_pack.get("project_id", f"proj_{workflow_id}")
        
        qc_report, eligible_items = run_image_qc(
            workflow_id=workflow_id,
            resource_pack=resource_pack,
            product=product_metadata,
            repo=repo,
            attempt_id="preview_qc",
            owner_user_id=owner_user_id,
            project_id=project_id,
        )
        
        return qc_report.to_dict() if hasattr(qc_report, 'to_dict') else qc_report, eligible_items


    # Methods from research_handler.py
    def research_job(self, ctx: JobContext, product_name: str, keywords: list[str], pdp_url: str | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"product_name": product_name, "keywords": keywords}
        err = self._validate_state_and_version(
            ctx,
            {ProductVideoWorkflowState.RESEARCHING},
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:research:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:research:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not product_name:
            return JobFailed(retryable=False, code="INVALID_INPUT", message="product_name cannot be empty")
        try:
            extra_kwargs = {
                key: kwargs[key]
                for key in ("brand", "model", "variant", "canonical_product_key", "research_snapshot_id")
                if kwargs.get(key) is not None
            }
            if pdp_url is not None:
                extra_kwargs["pdp_url"] = pdp_url
            result = self.pi_client.research(
                product_name,
                keywords,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_kwargs,
            )
            if pdp_url and not result.get("pdp_url"):
                result["pdp_url"] = pdp_url
            res = JobSucceeded(artifact_ref=result, next_command={"command": "build_resource_pack", "product_name": product_name})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="INVALID_INPUT", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_RESEARCH_FAILED", message=str(e))

    def resource_pack_job(self, ctx: JobContext, research_result: dict, **kwargs: Any) -> JobSucceeded | JobFailed:
        from hermes_personal.product_video.qc.auto_retry_helpers import (
            extract_product_from_resource_pack,
            is_cleanable_failure,
        )
        from hermes_personal.product_video.qc.models import QCVerdict
        
        inputs = {"research_result": research_result}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                ProductVideoWorkflowState.RESEARCHING,
            },
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:resource_pack:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:resource_pack:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not research_result:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="research_result cannot be empty")

        # In configured provider_mode, validate research snapshot persistence prerequisite before dispatch
        if getattr(self, "provider_mode", "fake") == "configured":
            snapshot_id = research_result.get("snapshot_id")
            persistence_status = research_result.get("persistence_status")
            if not snapshot_id:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Missing snapshot_id in research_result for configured mode",
                )
            if persistence_status not in ("saved", "persisted"):
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message=f"Research snapshot is not successfully persisted (persistence_status={persistence_status!r})",
                )

        try:
            result = self.pi_client.build_resource_pack(
                research_result,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
            )
            # Auto-run Image QC to check if cleanable failures exist
            # This is a preview QC run - not persisted yet, just for routing decision
            # Skip QC if in fake/test mode or missing required metadata
            qc_result = None
            qc_eligible = []
            
            # Only run preview QC if we have minimum required metadata
            has_required_metadata = (
                result.get("resource_pack_id") 
                and result.get("version")
                and ctx.owner_user_id
            )
            
            if has_required_metadata and getattr(self, "provider_mode", "fake") == "configured":
                try:
                    qc_result, qc_eligible = self._run_preview_image_qc(
                        workflow_id=ctx.workflow_id,
                        resource_pack=result,
                        product_metadata=extract_product_from_resource_pack(result),
                        owner_user_id=ctx.owner_user_id,
                        project_id=kwargs.get("project_id", f"proj_{ctx.workflow_id}"),
                    )
                except Exception as e:
                    # If preview QC fails, log but don't block the workflow
                    logger.warning(f"Preview Image QC failed for {ctx.workflow_id}: {e}")

            # Store QC metadata for retry handler
            result_with_qc = dict(result)
            
            if qc_result:
                result_with_qc["_initial_qc_preview"] = {
                    "verdict": qc_result.get("verdict") if isinstance(qc_result, dict) else (qc_result.verdict.value if hasattr(qc_result.verdict, 'value') else str(qc_result.verdict)),
                    "score": qc_result.get("score") if isinstance(qc_result, dict) else qc_result.score,
                    "is_cleanable": is_cleanable_failure(qc_result),
                    "findings_summary": {
                        "eligible_count": len(qc_eligible),
                        "total_items": len((qc_result.get("findings", {}) if isinstance(qc_result, dict) else qc_result.findings).get("items", [])),
                    }
                }
                
                verdict = qc_result.get("verdict") if isinstance(qc_result, dict) else qc_result.verdict
                if verdict == QCVerdict.FAIL and is_cleanable_failure(qc_result):
                    # Cleanable failure - trigger auto-retry with image cleaning
                    res = JobSucceeded(
                        artifact_ref=result_with_qc,
                        next_command={"command": "retry_image_qc"}
                    )
                else:
                    # Pass or terminal failure - proceed to normal flow
                    res = JobSucceeded(
                        artifact_ref=result_with_qc,
                        next_command={"command": "lock_resource_pack"}
                    )
            else:
                # No QC result (fake mode or missing metadata) - proceed to normal flow
                res = JobSucceeded(
                    artifact_ref=result_with_qc,
                    next_command={"command": "lock_resource_pack"}
                )

            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_PACK_FAILED", message=str(e))

    def lock_job(self, ctx: JobContext, pack_dict: dict, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"pack_dict": pack_dict}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
                ProductVideoWorkflowState.RETRYING_IMAGE_QC,
            },
            inputs,
            provider_family="product_intelligence",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:lock:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:lock:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not pack_dict:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="pack_dict cannot be empty")

        resource_pack_id = pack_dict.get("resource_pack_id") or pack_dict.get("id") or pack_dict.get("pack_id")
        if not resource_pack_id:
            if getattr(self, "provider_mode", "fake") == "fake":
                resource_pack_id = f"pack_{ctx.workflow_id}"
            else:
                return JobFailed(
                    retryable=False,
                    code="PREREQUISITE_FAILED",
                    message="Cannot lock resource pack: missing resource_pack_id in pack_dict",
                )

        pack_status = pack_dict.get("pack_status") or pack_dict.get("status")
        if pack_status in ("needs_review", "incomplete", "rejected", "unknown") or (getattr(self, "provider_mode", "fake") == "configured" and pack_status != "ready_to_lock"):
            return JobFailed(
                retryable=False,
                code="NON_LOCKABLE_STATUS",
                message=f"Cannot lock resource pack with non-lockable status '{pack_status}': pack is not ready_to_lock",
            )

        proj_id = kwargs.get("project_id")
        if not proj_id and self.workflow_repository:
            try:
                wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                if wf_d:
                    proj_id = wf_d[0].get("project_id")
            except Exception:
                pass
        if not proj_id:
            proj_id = f"proj_{ctx.workflow_id}"

        try:
            result = self.pi_client.lock_resource_pack(
                pack_dict,
                ctx.owner_user_id,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                project_id=proj_id,
            )
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_creative_brief"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as e:
            return JobFailed(retryable=False, code=e.code, message=str(e))
        except ValueError as e:
            return JobFailed(retryable=False, code="PREREQUISITE_FAILED", message=str(e))
        except Exception as e:
            return JobFailed(retryable=True, code="PI_LOCK_FAILED", message=str(e))


    # Methods from creative_handler.py
    def creative_brief_job(self, ctx: JobContext, product_id: str, brief_config: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"product_id": product_id, "brief_config": brief_config or {}}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_BRIEF,
                ProductVideoWorkflowState.LOCKING_RESOURCE_PACK,
                ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:creative_brief:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:creative_brief:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not product_id:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="product_id cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                5,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.creative_brief", kwargs, cache_key),
            )
            proj_id = (brief_config or {}).get("project_id") or kwargs.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            cfg = dict(brief_config or {})
            cfg.setdefault("project_id", proj_id)

            if self.creative_generator is not None:
                dossier_data = cfg.get("research_dossier")
                if self.workflow_repository is not None:
                    from hermes_personal.product_video.creative.generator import SingleModelCreativeGenerator

                    if isinstance(self.creative_generator, SingleModelCreativeGenerator):
                        workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
                        if workflow_data is not None:
                            aggregate, _ = workflow_data
                            locked_pack = aggregate.get("locked_pack")
                            if isinstance(locked_pack, dict):
                                # The queued brief job may contain a dossier
                                # built before the approved lock was mirrored.
                                # Rebuild from the durable lock and current
                                # passing QC instead of trusting that stale copy.
                                dossier_data = _locked_research_dossier(
                                    workflow_id=ctx.workflow_id,
                                    aggregate=aggregate,
                                    locked_pack=locked_pack,
                                    connection=self.workflow_repository.conn,
                                )
                                cfg["research_dossier"] = dossier_data
                dossier = None
                if dossier_data:
                    from hermes_personal.product_video.creative.contracts import ResearchDossier
                    dossier = ResearchDossier.from_dict(dossier_data) if isinstance(dossier_data, dict) else dossier_data
                if dossier is None:
                    dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is not None:
                    recovered_brief = None
                    if isinstance(self.video_client, MCPVideoFactoryAdapter):
                        workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
                        if workflow_data is None:
                            raise ValueError("workflow state is required to synchronize the approved Product Lock")
                        aggregate, _ = workflow_data
                        locked_pack = aggregate.get("locked_pack")
                        approval_receipt = aggregate.get("latest_approval_receipt")
                        if not isinstance(locked_pack, dict) or not isinstance(approval_receipt, dict):
                            raise ValueError("approved Product Lock artifact and receipt are required before creative generation")
                        dossier_dict = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier
                        if not isinstance(dossier_dict, dict):
                            raise ValueError("grounded dossier must be serializable")
                        self.video_client.ensure_project_locked(
                            owner_user_id=ctx.owner_user_id,
                            project_id=proj_id,
                            resource_pack=locked_pack,
                            dossier=dossier_dict,
                            approval_receipt=approval_receipt,
                            workflow_id=ctx.workflow_id,
                            # This downstream mirror is created after the
                            # approval transition, so the current workflow
                            # version is newer than the approved artifact.
                            workflow_version=None,
                        )
                        recovered_brief = _recover_creative_brief(
                            self.video_client.get_existing_creative_brief(
                                owner_user_id=ctx.owner_user_id,
                                project_id=proj_id,
                            ) or {},
                            dossier,
                        )
                    brief_v2 = recovered_brief or self.creative_generator.create_direction(dossier)
                    sent_config = _video_factory_brief_config(dict(cfg), brief_v2)
                    result = (
                        {"project_id": proj_id, "brief_id": f"brief_{product_id}"}
                        if recovered_brief is not None
                        else self.video_client.create_creative_brief(
                            product_id=product_id,
                            brief_config=sent_config,
                            workflow_id=ctx.workflow_id,
                            job_id=ctx.job_id,
                            project_id=proj_id,
                            owner_user_id=ctx.owner_user_id,
                            idempotency_key=ctx.idempotency_key,
                        )
                    )
                    res_dict = dict(brief_v2.to_dict())
                    res_dict["schema_version"] = "creative-brief-v2"
                    res_dict["contract_version"] = 2
                    res_dict["brief_digest"] = brief_v2.digest()
                    res_dict["project_id"] = proj_id
                    res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_data
                    if isinstance(result, dict):
                        if "version" in result:
                            res_dict["version"] = result["version"]
                        if "brief_id" in result:
                            res_dict["brief_id"] = result["brief_id"]
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_scene_plan", "product_id": product_id})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_brief_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_brief_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_brief_kw["owner_user_id"] = kwargs["owner_user_id"]

            result = self.video_client.create_creative_brief(
                product_id=product_id,
                brief_config=cfg,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_brief_kw,
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

    def scene_plan_job(self, ctx: JobContext, brief_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"brief_ref": brief_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_SCENE_PLAN,
                ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:scene_plan:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:scene_plan:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not brief_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="brief_ref cannot be empty")
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                5,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.scene_plan", kwargs, cache_key),
            )
            proj_id = kwargs.get("project_id")
            if not proj_id and isinstance(brief_ref, dict):
                proj_id = brief_ref.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            if self.creative_generator is not None:
                brief_dict = brief_ref if isinstance(brief_ref, dict) else {}
                dossier_dict = brief_dict.get("research_dossier")
                from hermes_personal.product_video.creative.contracts import (
                    CreativeBriefV2, ResearchDossier, ScriptScenePlanV2,
                )
                dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is None and dossier_dict:
                    dossier = ResearchDossier.from_dict(dossier_dict)
                brief_v2 = getattr(self.creative_generator, "brief", None)
                if brief_v2 is None and brief_dict:
                    try:
                        brief_v2 = CreativeBriefV2.from_dict(brief_dict)
                    except Exception:
                        pass
                if dossier and brief_v2:
                    script_v2 = self.creative_generator.create_script(dossier, brief_v2)
                    legacy_scenes = [
                        {
                            "scene_id": s.scene_id,
                            "order": s.order,
                            "title": f"Scene {s.order}: {s.story_role}",
                            "objective": s.visual_objective,
                            "content": s.narration,
                            "main_action": s.subject_action,
                            "duration_seconds": s.duration_seconds,
                            "start_state": s.start_state,
                            "end_state": s.end_state,
                            "camera_intention": s.camera_movement,
                        }
                        for s in script_v2.scenes
                    ]
                    sent_brief = dict(brief_dict)
                    sent_brief["scenes"] = legacy_scenes
                    sent_brief.setdefault("project_id", proj_id)
                    appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
                    result = self.video_client.create_scene_plan(
                        sent_brief,
                        workflow_id=ctx.workflow_id,
                        job_id=ctx.job_id,
                        project_id=proj_id,
                        owner_user_id=ctx.owner_user_id,
                        idempotency_key=ctx.idempotency_key,
                        approval_request_id=appr_id,
                        approval_receipt=kwargs.get("approval_receipt"),
                    )
                    res_dict = dict(script_v2.to_dict())
                    res_dict["schema_version"] = "script-scene-plan-v2"
                    # Hash the exact serialized payload handed to the next
                    # worker. A digest of the in-memory object can diverge if
                    # its nested scene data was normalized during generation.
                    res_dict["script_digest"] = ScriptScenePlanV2.from_dict(
                        {**res_dict, "script_digest": ""}
                    ).digest()
                    res_dict["project_id"] = proj_id
                    res_dict["research_dossier"] = dossier.to_dict() if hasattr(dossier, "to_dict") else dossier_dict
                    if isinstance(result, dict) and "scene_plan_id" in result:
                        res_dict["scene_plan_id"] = result["scene_plan_id"]
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=res_dict, next_command={"command": "create_storyboard"})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_scene_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_scene_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_scene_kw["owner_user_id"] = kwargs["owner_user_id"]
            if kwargs.get("approval_request_id"):
                extra_scene_kw["approval_request_id"] = kwargs["approval_request_id"]
            if kwargs.get("approval_receipt"):
                extra_scene_kw["approval_receipt"] = kwargs["approval_receipt"]

            result = self.video_client.create_scene_plan(
                brief_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_scene_kw,
            )
            commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "create_storyboard"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except Exception as e:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_SCENE_FAILED", message=str(e))


    def storyboard_job(self, ctx: JobContext, scene_ref: Any, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"scene_ref": scene_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.CREATING_STORYBOARD,
                ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err

        res_info = self._get_workflow_state_and_version(ctx)
        cur_ver = res_info[1] if res_info else 1
        cache_key = f"{ctx.workflow_id}:storyboard:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:storyboard:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        if not scene_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="scene_ref cannot be empty")
        if self.workflow_repository:
            workflow_data = self.workflow_repository.get_workflow(ctx.workflow_id)
            if workflow_data is not None and isinstance(workflow_data[0].get("qc_authorization"), dict):
                kwargs = dict(kwargs)
                kwargs["qc_authorization"] = dict(workflow_data[0]["qc_authorization"])
        alloc = None
        try:
            alloc = reserve_budget(
                "video_factory",
                10,
                idempotency_key=cache_key,
                **_paid_budget_kwargs(ctx, "product_video.storyboard", kwargs, cache_key),
            )
            proj_id = kwargs.get("project_id")
            if not proj_id and isinstance(scene_ref, dict):
                proj_id = scene_ref.get("project_id")
            if not proj_id and self.workflow_repository:
                try:
                    wf_d = self.workflow_repository.get_workflow(ctx.workflow_id)
                    if wf_d:
                        proj_id = wf_d[0].get("project_id")
                except Exception:
                    pass
            if not proj_id:
                proj_id = f"proj_{ctx.workflow_id}"

            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")

            if self.keyframe_runtime_factory is not None:
                runtime = self.keyframe_runtime_factory()
                from hermes_personal.product_video.creative.contracts import ResearchDossier, ScriptScenePlanV2
                from hermes_personal.product_video.creative.storyboard import (
                    compile_keyframe_requests,
                    storyboard_package_digest,
                )
                dossier = getattr(self.creative_generator, "dossier", None)
                if dossier is None and isinstance(scene_ref, dict) and "research_dossier" in scene_ref:
                    dossier = ResearchDossier.from_dict(scene_ref["research_dossier"])
                if dossier and isinstance(scene_ref, dict):
                    eligible_ids = [asset.asset_id for asset in dossier.eligible_assets]
                    for scene in scene_ref.get("scenes", []) or []:
                        if isinstance(scene, dict) and not scene.get("reference_asset_ids"):
                            scene["reference_asset_ids"] = eligible_ids[:2]
                script = getattr(self.creative_generator, "script", None)
                if script is None and isinstance(scene_ref, dict):
                    try:
                        script = ScriptScenePlanV2.from_dict(scene_ref)
                    except (KeyError, TypeError, ValueError) as exc:
                        if scene_ref.get("schema_version") == "script-scene-plan-v2":
                            release_budget(alloc)
                            return JobFailed(
                                retryable=False, code="INVALID_SCRIPT_DIGEST",
                                message=f"Stored V2 scene plan failed validation: {exc}",
                            )
                if dossier and script:
                    vf_storyboard = self.video_client.create_storyboard(
                        scene_ref,
                        workflow_id=ctx.workflow_id,
                        job_id=ctx.job_id,
                        project_id=proj_id,
                        owner_user_id=ctx.owner_user_id,
                        idempotency_key=ctx.idempotency_key,
                        approval_request_id=appr_id,
                        approval_receipt=kwargs.get("approval_receipt"),
                    )
                    _confirm_vf_storyboard_write(
                        vf_storyboard,
                        owner_user_id=ctx.owner_user_id,
                        project_id=proj_id,
                        scene_ids=tuple(scene.scene_id for scene in script.scenes),
                    )
                    requests = compile_keyframe_requests(
                        workflow_id=ctx.workflow_id,
                        project_id=proj_id,
                        dossier=dossier,
                        script=script,
                        recovery_plan=(
                            kwargs.get("recovery_plan")
                            if isinstance(kwargs.get("recovery_plan"), dict)
                            else None
                        ),
                        recovery_attempt=int(kwargs.get("recovery_attempt", 0) or 0),
                        previous_package=(
                            kwargs.get("previous_storyboard")
                            if isinstance(kwargs.get("previous_storyboard"), dict)
                            else None
                        ),
                    )
                    previous_package = kwargs.get("previous_storyboard")
                    recovery_plan = kwargs.get("recovery_plan")
                    recovery_frame_ids = {
                        str(item.get("frame_id"))
                        for item in (recovery_plan or {}).get("frames", [])
                        if isinstance(item, dict) and item.get("frame_id")
                    } if isinstance(recovery_plan, dict) else set()
                    previous_frames: dict[str, dict[str, Any]] = {}
                    unchanged_scene_ids: set[str] = set()
                    if isinstance(previous_package, dict) and (
                        previous_package.get("workflow_id") == ctx.workflow_id
                        and previous_package.get("project_id") == proj_id
                        and previous_package.get("package_digest") == storyboard_package_digest(previous_package)
                        and isinstance(previous_package.get("script"), dict)
                    ):
                        old_script = ScriptScenePlanV2.from_dict(previous_package["script"])
                        old_scenes = {scene.scene_id: scene for scene in old_script.scenes}
                        unchanged_scene_ids = {
                            scene.scene_id for scene in script.scenes
                            if old_scenes.get(scene.scene_id) == scene
                        }
                        previous_frames = {
                            str(item["frame_id"]): item
                            for item in previous_package.get("generated_keyframes", [])
                            if isinstance(item, dict) and item.get("frame_id")
                        }
                    generated_keyframes = []
                    for req in requests:
                        prior = previous_frames.get(req.frame_id)
                        scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                        if prior is not None and scene_id in unchanged_scene_ids and req.frame_id not in recovery_frame_ids:
                            prior_path = Path(str(prior.get("image_path") or ""))
                            if (
                                prior.get("status") == "completed"
                                and prior_path.is_file()
                                and hashlib.sha256(prior_path.read_bytes()).hexdigest() == prior.get("sha256")
                            ):
                                generated_keyframes.append(dict(prior))
                                continue
                        conditioning_start_sha = ""
                        if req.frame_role == "end":
                            start_frame = next(
                                (
                                    item for item in generated_keyframes
                                    if item.get("frame_id") == f"{scene_id}-start"
                                ),
                                None,
                            )
                            if not isinstance(start_frame, dict):
                                raise ValueError("END keyframe requires its completed START frame")
                            start_path = Path(str(start_frame.get("image_path") or ""))
                            conditioning_start_sha = str(start_frame.get("sha256") or "")
                            if (
                                not start_path.is_file()
                                or hashlib.sha256(start_path.read_bytes()).hexdigest() != conditioning_start_sha
                            ):
                                raise ValueError("END keyframe START conditioning image changed")
                            req = replace(
                                req,
                                prompt=(
                                    req.prompt
                                    + "\nThe first attached image is the approved START frame of this same scene. "
                                    "Keep its exact table material, shape, furniture layout, camera context, "
                                    "product surface and pool position. Show only the specified action and end state. "
                                    "If water is specified near but not on the product, keep the product completely dry."
                                ),
                                reference_image_paths=(str(start_path), *req.reference_image_paths)[:4],
                            )
                        if ctx.heartbeat_fn is not None and not ctx.heartbeat_fn():
                            release_budget(alloc)
                            return JobFailed(retryable=True, code="STALE_LEASE", message="Storyboard lease expired before keyframe generation")
                        kf_res = runtime.run(req)
                        if kf_res.status != "completed" or not kf_res.image_path:
                            release_budget(alloc)
                            if kf_res.error_code == "PROVIDER_CAPACITY_WAIT":
                                return JobFailed(
                                    retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                    message=kf_res.error_message or "Keyframe provider is at capacity",
                                )
                            if str(kf_res.error_code or "").upper() in {
                                "HTTP_429", "HTTP_500", "HTTP_502", "HTTP_503", "HTTP_504",
                            }:
                                return JobFailed(
                                    retryable=True, code="PROVIDER_CAPACITY_WAIT",
                                    message=kf_res.error_message or (
                                        f"Keyframe provider returned {kf_res.error_code}; retry later"
                                    ),
                                )
                            if kf_res.status in {"submitted", "running"} and kf_res.provider_operation_id:
                                return JobFailed(
                                    retryable=True, code="KEYFRAME_PENDING",
                                    message="Keyframe operation is pending under its existing provider ID",
                                )
                            return JobFailed(
                                retryable=False,
                                code=kf_res.error_code or "RECONCILIATION_REQUIRED",
                                message=kf_res.error_message or "Keyframe operation did not complete",
                            )
                        ref_shas = [
                            hashlib.sha256(Path(path).read_bytes()).hexdigest()
                            for path in req.reference_image_paths
                        ]
                        scene_id = req.frame_id.removesuffix("-start").removesuffix("-end")
                        kf_p = Path(kf_res.image_path) if kf_res.image_path else None
                        kf_sha = hashlib.sha256(kf_p.read_bytes()).hexdigest() if (kf_p and kf_p.is_file()) else ""
                        generated_keyframes.append({
                            "frame_id": req.frame_id,
                            "scene_id": scene_id,
                            "frame_role": req.frame_role,
                            "image_path": kf_res.image_path,
                            "sha256": kf_sha,
                            "status": kf_res.status,
                            "prompt": req.prompt,
                            "negative_prompt": req.negative_prompt,
                            "reference_image_paths": list(req.reference_image_paths),
                            "reference_sha256s": ref_shas,
                            "conditioning_start_sha256": conditioning_start_sha,
                        })
                    package_dict = {
                        "schema_version": "storyboard-package-v2",
                        "storyboard_id": f"sb_{proj_id}",
                        "version": 1,
                        "owner_user_id": ctx.owner_user_id,
                        "generated_keyframes": generated_keyframes,
                        "storyboard_frames": [
                            {
                                "scene_id": scene.scene_id,
                                "keyframe_image_path": next(
                                    (
                                        item["image_path"]
                                        for item in generated_keyframes
                                        if item["scene_id"] == scene.scene_id
                                        and item["frame_role"] == "start"
                                    ),
                                    None,
                                ),
                                "reference_image_paths": list(
                                    next(
                                        (
                                            req.reference_image_paths
                                            for req in requests
                                            if req.frame_id == f"{scene.scene_id}-start"
                                        ),
                                        (),
                                    )
                                ),
                                "visual_objective": scene.visual_objective,
                                "overlay_text": scene.overlay_text,
                                "text_policy": "post_production_only",
                            }
                            for scene in script.scenes
                        ],
                        "project_id": proj_id,
                        "workflow_id": ctx.workflow_id,
                        "script": script.to_dict() if hasattr(script, "to_dict") else (asdict(script) if is_dataclass(script) else script),
                        "scenes": [s.to_dict() if hasattr(s, "to_dict") else (asdict(s) if is_dataclass(s) else s) for s in script.scenes],
                        "recovery_attempt": int(kwargs.get("recovery_attempt", 0) or 0),
                        "end_keyframe_omissions": [
                            {
                                "scene_id": s.scene_id,
                                "policy": s.end_keyframe_policy,
                                "reason": s.end_keyframe_omission_reason,
                            }
                            for s in script.scenes
                            if s.end_keyframe_policy == "omitted"
                        ],
                    }
                    package_dict["package_digest"] = storyboard_package_digest(package_dict)
                    commit_budget(alloc)
                    res = JobSucceeded(artifact_ref=package_dict, next_command={"command": "render_video"})
                    if cache_key:
                        self._idempotency_cache[cache_key] = res
                    return res

            extra_sb_kw: dict[str, Any] = {}
            if kwargs.get("project_id"):
                extra_sb_kw["project_id"] = kwargs["project_id"]
            if kwargs.get("owner_user_id"):
                extra_sb_kw["owner_user_id"] = kwargs["owner_user_id"]
            if appr_id:
                extra_sb_kw["approval_request_id"] = appr_id
            if isinstance(kwargs.get("approval_receipt"), dict):
                extra_sb_kw["approval_receipt"] = kwargs["approval_receipt"]

            result = self.video_client.create_storyboard(
                scene_ref,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                **extra_sb_kw,
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


    # Methods from render_handler.py
    def render_job(self, ctx: JobContext, story_ref: Any, render_params: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"story_ref": story_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.RENDERING,
                ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err
        if not story_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="story_ref cannot be empty")

        params = dict(render_params or {})
        wf_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
        agg = wf_data[0] if wf_data else {}
        cur_ver = wf_data[1] if wf_data else 1
        try:
            active_job_id = _resolve_durable_resume_job_id(
                params,
                agg,
                "active_render_job_id",
                ("job_id", "export_id"),
            )
        except TerminalJobError as exc:
            return JobFailed(retryable=False, code=exc.code, message=str(exc))

        cache_key = f"{ctx.workflow_id}:render:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:render:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        disp_status = agg.get("render_dispatch_status")
        if disp_status in ("DISPATCHING", "UNKNOWN_OUTCOME"):
            return JobFailed(retryable=False, code="UNKNOWN_PAID_OUTCOME", message=f"Cannot resume from unconfirmed dispatch status '{disp_status}'")
        if disp_status == "COMPLETED":
            res_id = agg.get("render_budget_reservation_id")
            if not res_id or res_id == "absent":
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message="Completed render missing valid budget reservation")
            res_obj = get_reservation(res_id)
            if not res_obj:
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message=f"Reservation '{res_id}' not found")
            commit_budget(res_obj)
            return JobSucceeded(artifact_ref=agg.get("render_result", {}), next_command={"command": "export_video"})

        if getattr(self, "provider_mode", "fake") == "configured" and not active_job_id:
            try:
                _require_configured_execution_binding(
                    self.video_client,
                    "render",
                    "video.render",
                )
            except TerminalJobError as exc:
                return JobFailed(
                    retryable=False,
                    code=exc.code,
                    message=str(exc),
                )
            except ExecutionBindingPreflightError as exc:
                return JobFailed(
                    retryable=exc.retryable,
                    code=exc.code,
                    message=str(exc),
                )
            qc_auth = kwargs.get("qc_authorization") or params.get("qc_authorization") or agg.get("qc_authorization")
            if not qc_auth or not isinstance(qc_auth, dict):
                return JobFailed(retryable=False, code="COST_AUTHORIZATION_REQUIRED", message="Configured render requires scoped qc_authorization")
            max_cost = qc_auth.get("max_cost_usd", qc_auth.get("workflow_max_cost_usd"))
            if max_cost is None or float(max_cost) < 0.50:
                return JobFailed(retryable=False, code="COST_AUTHORIZATION_REQUIRED", message=f"Authorization max_cost_usd {max_cost} is below durable admission threshold (0.50)")

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg_data, ver = data
                agg_dict = dict(agg_data)
                agg_dict["active_render_job_id"] = prov_job_id
                if alloc:
                    agg_dict["render_budget_reservation_id"] = alloc.reservation_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        provider_call_started = False
        try:
            proj_id = kwargs.get("project_id") or agg.get("project_id") or f"proj_{ctx.workflow_id}"
            if not active_job_id:
                alloc = reserve_budget(
                    "video_factory",
                    50,
                    idempotency_key=cache_key,
                    **_paid_budget_kwargs(ctx, "product_video.render", kwargs, cache_key),
                )
                params["admission_context"] = {
                    "reservation_id": alloc.reservation_id,
                    "budget_reservation_id": alloc.reservation_id,
                    "workflow_id": ctx.workflow_id,
                }
            elif agg.get("render_budget_reservation_id"):
                alloc = get_reservation(agg["render_budget_reservation_id"])
                if alloc is None or alloc.state == "released":
                    return JobFailed(
                        retryable=False, code="BUDGET_RECOVERY_FAILED",
                        message="Accepted render budget reservation is missing or released",
                    )
            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
            story_dict = dict(story_ref) if isinstance(story_ref, dict) else {}
            if story_dict.get("schema_version") == "storyboard-package-v2":
                curr_rcpt = story_dict.get("keyframe_qc_receipt")
                if not isinstance(curr_rcpt, dict) or curr_rcpt.get("artifact_digest") != story_dict.get("package_digest"):
                    qc_repo = QCReportRepository(self.workflow_repository.conn)
                    latest_qc = qc_repo.get_latest_report(ctx.workflow_id, QCStage.KEYFRAME)
                    if latest_qc and getattr(latest_qc.verdict, "value", str(latest_qc.verdict)).lower() == "pass":
                        story_dict["keyframe_qc_receipt"] = {
                            "report_id": latest_qc.report_id,
                            "workflow_id": latest_qc.workflow_id,
                            "stage": getattr(latest_qc.stage, "value", str(latest_qc.stage)),
                            "verdict": getattr(latest_qc.verdict, "value", str(latest_qc.verdict)),
                            "score": latest_qc.score,
                            "artifact_id": latest_qc.artifact_id,
                            "artifact_version": latest_qc.artifact_version,
                            "artifact_digest": latest_qc.artifact_digest,
                            "findings": latest_qc.findings,
                            "hard_failure": getattr(latest_qc, "hard_failure", False),
                        }
                    elif not curr_rcpt:
                        story_dict["keyframe_qc_receipt"] = kwargs.get("approval_receipt") or {
                            "approval_request_id": appr_id or "appr_auto",
                            "gate": "AwaitingStoryboardApproval",
                            "status": "approved",
                        }
            provider_call_started = True
            result = self.video_client.render_video(
                story_dict,
                render_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
                owner_user_id=ctx.owner_user_id,
                project_id=proj_id,
                approval_request_id=appr_id,
            )

            if alloc:
                commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "export_video"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            uncertain_paid_codes = {
                "RECONCILIATION_REQUIRED",
                "VF_CHECKPOINT_FAILED",
                "MISSING_JOB_ID",
                "MISSING_POLLING_TOOL",
                "RENDER_LINEAGE_INVALID",
                "RENDER_LINEAGE_MISMATCH",
            }
            if alloc and not (
                provider_call_started
                and self.provider_mode == "configured"
                and te.code in uncertain_paid_codes
            ):
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc and not (provider_call_started and self.provider_mode == "configured"):
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if provider_call_started and self.provider_mode == "configured":
                durable_job = None
                if self.workflow_repository:
                    try:
                        resumed = self.workflow_repository.get_workflow(ctx.workflow_id)
                        durable_job = resumed[0].get("active_render_job_id") if resumed else None
                    except Exception:
                        durable_job = None
                if not durable_job:
                    return JobFailed(
                        retryable=False, code="UNKNOWN_PAID_OUTCOME",
                        message=f"Render outcome is ambiguous; reconcile the provider before retrying: {e}",
                    )
                return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_RENDER_FAILED", message=str(e))


    # Methods from export_handler.py
    def export_job(self, ctx: JobContext, render_ref: Any, export_params: dict | None = None, **kwargs: Any) -> JobSucceeded | JobFailed:
        inputs = {"render_ref": render_ref}
        err = self._validate_state_and_version(
            ctx,
            {
                ProductVideoWorkflowState.EXPORTING,
                ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
            },
            inputs,
            provider_family="video_factory",
        )
        if err:
            return err
        if not render_ref:
            return JobFailed(retryable=False, code="MISSING_INPUT_REF", message="render_ref cannot be empty")

        params = dict(export_params or {})
        wf_data = self.workflow_repository.get_workflow(ctx.workflow_id) if self.workflow_repository else None
        agg = wf_data[0] if wf_data else {}
        cur_ver = wf_data[1] if wf_data else 1
        try:
            active_job_id = _resolve_durable_resume_job_id(
                params,
                agg,
                "active_export_job_id",
                ("job_id", "export_id"),
            )
        except TerminalJobError as exc:
            return JobFailed(retryable=False, code=exc.code, message=str(exc))

        cache_key = f"{ctx.workflow_id}:export:v{cur_ver}:{ctx.idempotency_key}" if ctx.idempotency_key else None
        alt_key = f"{ctx.workflow_id}:export:{ctx.idempotency_key}" if ctx.idempotency_key else None
        if cache_key and cache_key in self._idempotency_cache:
            return self._idempotency_cache[cache_key]
        if alt_key and alt_key in self._idempotency_cache:
            return self._idempotency_cache[alt_key]

        disp_status = agg.get("export_dispatch_status")
        if disp_status in ("DISPATCHING", "UNKNOWN_OUTCOME"):
            return JobFailed(retryable=False, code="UNKNOWN_PAID_OUTCOME", message=f"Cannot resume from unconfirmed dispatch status '{disp_status}'")
        if disp_status == "COMPLETED":
            res_id = agg.get("export_budget_reservation_id")
            if not res_id or res_id == "absent":
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message="Completed export missing valid budget reservation")
            res_obj = get_reservation(res_id)
            if not res_obj:
                return JobFailed(retryable=False, code="BUDGET_RECOVERY_FAILED", message=f"Reservation '{res_id}' not found")
            commit_budget(res_obj)
            return JobSucceeded(artifact_ref=agg.get("export_result", {}), next_command={"command": "complete"})

        def _checkpoint_accepted(job_type: str, prov_job_id: str) -> None:
            if not self.workflow_repository or not ctx.workflow_id:
                return
            try:
                data = self.workflow_repository.get_workflow(ctx.workflow_id)
                if not data:
                    raise RuntimeError(f"Workflow '{ctx.workflow_id}' not found during checkpoint")
                agg_data, ver = data
                agg_dict = dict(agg_data)
                agg_dict["active_export_job_id"] = prov_job_id
                self.workflow_repository.commit_workflow(
                    workflow_id=ctx.workflow_id,
                    aggregate_json=json.dumps(agg_dict),
                    events=[],
                    expected_version=ver,
                )
            except Exception as ex:
                raise TerminalJobError(
                    f"CHECKPOINT_PERSISTENCE_FAILED: Failed to checkpoint accepted provider job_id '{prov_job_id}' in workflow repository: {ex}. "
                    "Auto-resubmission halted to prevent duplicate provider job submission.",
                    code="VF_CHECKPOINT_FAILED",
                ) from ex

        alloc = None
        try:
            proj_id = kwargs.get("project_id") or agg.get("project_id") or f"proj_{ctx.workflow_id}"
            appr_id = kwargs.get("approval_request_id") or (kwargs.get("approval_receipt") or {}).get("approval_request_id")
            if getattr(self, "provider_mode", "fake") == "configured" and not active_job_id:
                try:
                    _require_configured_execution_binding(
                        self.video_client,
                        "export",
                        "video.export",
                    )
                except TerminalJobError as exc:
                    return JobFailed(
                        retryable=False,
                        code=exc.code,
                        message=str(exc),
                    )
                except ExecutionBindingPreflightError as exc:
                    return JobFailed(
                        retryable=exc.retryable,
                        code=exc.code,
                        message=str(exc),
                    )
            if not active_job_id:
                alloc = reserve_budget(
                    "video_factory",
                    20,
                    idempotency_key=cache_key,
                    **_paid_budget_kwargs(ctx, "product_video.export", kwargs, cache_key),
                )
            result = self.video_client.export_video(
                render_ref,
                export_params=params,
                workflow_id=ctx.workflow_id,
                job_id=ctx.job_id,
                idempotency_key=ctx.idempotency_key,
                on_job_accepted=_checkpoint_accepted,
                heartbeat_fn=ctx.heartbeat_fn,
                owner_user_id=ctx.owner_user_id,
                project_id=proj_id,
                approval_request_id=appr_id,
            )

            if alloc:
                commit_budget(alloc)
            res = JobSucceeded(artifact_ref=result, next_command={"command": "complete"})
            if cache_key:
                self._idempotency_cache[cache_key] = res
            return res
        except TerminalJobError as te:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code=te.code, message=str(te))
        except LeaseLostError as le:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=False, code="LEASE_LOST", message=str(le))
        except Exception as e:
            if alloc:
                try:
                    release_budget(alloc)
                except Exception:
                    pass
            return JobFailed(retryable=True, code="VF_EXPORT_FAILED", message=str(e))


    def get_handlers_map(self) -> dict[str, Callable[..., Any]]:
        return {
            "product_video.research": self.research_job,
            "product_video.resource_pack": self.resource_pack_job,
            "product_video.retry_image_qc": self.retry_image_qc_job,
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


