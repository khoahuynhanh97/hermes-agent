from __future__ import annotations

import json
import logging
from typing import Any

from hermes_personal.workflows.budgets import reserve_budget, commit_budget, release_budget, get_reservation
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
    ProductVideoWorkflowState,
)


# Import helper functions from common module
from hermes_personal.product_video.handlers.common import (
    _paid_budget_kwargs,
)

logger = logging.getLogger(__name__)



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

