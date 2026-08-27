from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from hermes_personal.contracts.operator import OperatorCommand
from hermes_personal.product_video import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
    start_product_video_workflow,
    transition,
)
from hermes_personal.workflows.approvals import ApprovalService, ApprovalStatus
from hermes_personal.workflows.envelope import build_envelope
from hermes_personal.workflows.repository import WorkflowRepository


def approve_and_advance_workflow(
    connection: sqlite3.Connection,
    target_id: str,
    owner_user_id: str = "local-owner",
    payload: dict[str, Any] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Approve an approval request AND advance the workflow state and outbox queue atomically."""
    approval_service = ApprovalService(connection)
    repo = WorkflowRepository(connection)

    # 1. Resolve workflow & approval request
    if target_id.startswith("wf_"):
        wf_data = repo.get_workflow(target_id)
        if wf_data is None:
            raise KeyError(f"Workflow '{target_id}' not found")
        agg, current_version = wf_data
        wf_id = target_id
        req_id = agg.get("pending_approval_id")
        if not req_id:
            raise KeyError("No pending approval for workflow")
        req = approval_service.get_request(req_id)
    else:
        req = approval_service.get_request(target_id)
        wf_id = req.payload.get("workflow_id")
        wf_data = repo.get_workflow(wf_id)
        if wf_data is None:
            raise KeyError(f"Workflow '{wf_id}' not found")
        agg, current_version = wf_data

    # 2. Check workflow version if expected_version is provided
    if expected_version is not None and expected_version != current_version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {current_version}")

    # 3. Check HITL waiting state
    curr_enum = ProductVideoWorkflowState(agg.get("state"))
    if curr_enum not in HITL_WAITING_STATES:
        raise ValueError(f"Workflow {wf_id} state {curr_enum.value} is not in HITL_WAITING_STATES")

    # 4. Validate ALL 5 bindings before any mutation
    if req.request_id != agg.get("pending_approval_id"):
        raise ValueError("Approval request ID does not match aggregate pending_approval_id")

    if req.payload.get("workflow_id") != wf_id:
        raise ValueError("Approval request workflow_id mismatch")

    req_gate = req.payload.get("gate")
    agg_gate = agg.get("pending_approval_gate")
    if req_gate != agg_gate or agg_gate != curr_enum.value:
        raise ValueError("Approval request gate mismatch")

    if req.payload.get("workflow_version") != current_version:
        raise ValueError("Approval request workflow_version mismatch")

    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Approval request {req.request_id} is already {req.status.value}")

    # 5. Determine next state & next job
    if curr_enum == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK:
        next_enum = ProductVideoWorkflowState.BUILDING_RESOURCE_PACK
        job_name = "product_video.resource_pack"
        gate_name = "AwaitingProductLock"
    elif curr_enum == ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL:
        next_enum = ProductVideoWorkflowState.CREATING_SCENE_PLAN
        job_name = "product_video.scene_plan"
        gate_name = "AwaitingBriefApproval"
    elif curr_enum == ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL:
        next_enum = ProductVideoWorkflowState.CREATING_STORYBOARD
        job_name = "product_video.storyboard"
        gate_name = "AwaitingSceneApproval"
    elif curr_enum == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL:
        next_enum = ProductVideoWorkflowState.RENDERING
        job_name = "product_video.render"
        gate_name = "AwaitingStoryboardApproval"
    elif curr_enum == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL:
        next_enum = ProductVideoWorkflowState.EXPORTING
        job_name = "product_video.export"
        gate_name = "AwaitingFinalApproval"
    else:
        raise ValueError(f"Unhandled HITL waiting state: {curr_enum}")

    args = [agg.get("latest_artifact")]

    # 6. Validate transition
    next_validated = transition(curr_enum, next_enum)

    # 7. SINGLE ATOMIC SQLITE TRANSACTION
    outbox_msg = build_envelope(
        workflow_id=wf_id,
        topic="job.dispatch",
        idempotency_key=f"idemp_{job_name}_{wf_id}_v{current_version + 1}",
        payload={
            "job_name": job_name,
            "workflow_id": wf_id,
            "args": args,
            "owner_user_id": owner_user_id,
        },
    )

    next_agg = dict(agg)
    next_agg["state"] = next_validated.value
    next_agg.pop("pending_approval_id", None)
    next_agg.pop("pending_approval_gate", None)

    with connection:
        cur = connection.cursor()
        now_iso = datetime.now(timezone.utc).isoformat()
        cur.execute(
            "UPDATE approval_request SET status = ?, updated_at = ? WHERE request_id = ?",
            (ApprovalStatus.APPROVED.value, now_iso, req.request_id),
        )
        repo.commit_workflow(
            workflow_id=wf_id,
            aggregate_json=json.dumps(next_agg),
            events=[
                {
                    "event_id": f"evt_appr_{req.request_id}",
                    "command_id": f"cmd_appr_{req.request_id}",
                    "event_type": "ApprovalGranted",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"gate": gate_name, "request_id": req.request_id},
                }
            ],
            outbox_message=outbox_msg,
            expected_version=current_version,
        )

    return {
        "request_id": req.request_id,
        "status": "approved",
        "workflow_id": wf_id,
        "new_state": next_validated.value,
        "enqueued_job": job_name,
    }


def create_operator_command_handler(
    connection: sqlite3.Connection,
    provider_mode: str = "configured",
) -> Callable[[OperatorCommand], dict[str, Any]]:
    """Create canonical operator command handler for EventsAPI."""
    repo = WorkflowRepository(connection)

    def handle_command(cmd: OperatorCommand) -> dict[str, Any]:
        if cmd.command_type == "start_workflow":
            payload = cmd.payload
            wf_id = cmd.target_id
            product_name = payload.get("product_name", "Default Product")
            keywords = payload.get("keywords", [])
            pdp_url = payload.get("pdp_url")

            start_product_video_workflow(
                workflow_repository=repo,
                workflow_id=wf_id,
                product_name=product_name,
                keywords=keywords,
                pdp_url=pdp_url,
                owner_user_id=cmd.owner_user_id,
                idempotency_key=cmd.idempotency_key,
            )
            return {"workflow_id": wf_id, "status": "started"}

        elif cmd.command_type == "approve":
            payload_dict = dict(cmd.payload) if cmd.payload else {}
            return approve_and_advance_workflow(
                connection=connection,
                target_id=cmd.target_id,
                owner_user_id=cmd.owner_user_id,
                payload=payload_dict,
                expected_version=cmd.expected_version,
            )

        elif cmd.command_type == "reject":
            approval_service = ApprovalService(connection)
            approval_service.reject(cmd.target_id)
            return {"target_id": cmd.target_id, "status": "rejected"}

        return {"target_id": cmd.target_id, "status": "accepted"}

    return handle_command
