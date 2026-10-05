from __future__ import annotations

import logging
from typing import Any

from hermes_personal.product_video.job_contracts import (
    JobContext,
    JobFailed,
    JobSucceeded,
    TerminalJobError,
)
from hermes_personal.product_video.workflow_state import (
    ProductVideoWorkflowState,
)


# Import helper functions from common module

logger = logging.getLogger(__name__)



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
            qc_verdict = qc_result.get("verdict") if isinstance(qc_result, dict) else (qc_result.verdict.value if hasattr(qc_result.verdict, 'value') else str(qc_result.verdict))
            qc_score = qc_result.get("score") if isinstance(qc_result, dict) else getattr(qc_result, "score", 0)
            qc_findings = qc_result.get("findings", {}) if isinstance(qc_result, dict) else getattr(qc_result, "findings", {})
            if not isinstance(qc_findings, dict):
                qc_findings = {}
            result_with_qc["_initial_qc_preview"] = {
                "verdict": qc_verdict,
                "score": qc_score,
                "is_cleanable": is_cleanable_failure(qc_result),
                "findings_summary": {
                    "eligible_count": len(qc_eligible) if qc_eligible is not None else 0,
                    "total_items": len(qc_findings.get("items", [])),
                }
            }
            
            verdict_str = qc_verdict.value if hasattr(qc_verdict, "value") else str(qc_verdict)
            if verdict_str.lower() == "fail" and is_cleanable_failure(qc_result):
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

