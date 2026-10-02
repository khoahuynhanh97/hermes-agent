from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget
from hermes_personal.product_video.handlers.common import verify_job_digests
from hermes_personal.product_video.job_contracts import (
    JobContext,
    JobFailed,
    JobSucceeded,
)
from hermes_personal.product_video.workflow_state import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
)


# Import helper functions from common module

logger = logging.getLogger(__name__)



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

