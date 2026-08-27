from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Callable

from hermes_personal.contracts.operator import OperatorCommand
from hermes_personal.product_video import (
    ProductVideoWorkflowState,
    start_product_video_workflow,
    transition,
)
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.envelope import build_envelope
from hermes_personal.workflows.repository import WorkflowRepository


def approve_and_advance_workflow(
    connection: sqlite3.Connection,
    target_id: str,
    owner_user_id: str = "local-owner",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Approve an approval request AND advance the workflow state and outbox queue."""
    approval_service = ApprovalService(connection)
    repo = WorkflowRepository(connection)

    req_id = target_id
    try:
        req = approval_service.get_request(req_id)
    except KeyError:
        cur = connection.cursor()
        cur.execute(
            "SELECT request_id FROM approval_request WHERE status='pending' AND payload_json LIKE ?",
            (f'%"{target_id}"%',),
        )
        row = cur.fetchone()
        if row is None:
            raise KeyError(f"No pending approval request found for target '{target_id}'")
        req_id = row["request_id"]
        req = approval_service.get_request(req_id)

    approval_service.approve(req_id)

    wf_payload = req.payload
    wf_id = wf_payload.get("workflow_id") or target_id
    gate = wf_payload.get("gate")

    wf_data = repo.get_workflow(wf_id)
    if not wf_data:
        return {"request_id": req_id, "status": "approved", "workflow_id": wf_id}

    agg, current_version = wf_data

    GATE_TRANSITIONS = {
        "AwaitingProductLock": (
            ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK,
            ProductVideoWorkflowState.BUILDING_RESOURCE_PACK,
            "product_video.lock",
            [agg.get("latest_artifact", {}).get("payload", agg.get("latest_artifact", {}))],
        ),
        "AwaitingBriefApproval": (
            ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL,
            ProductVideoWorkflowState.CREATING_SCENE_PLAN,
            "product_video.scene_plan",
            [agg.get("latest_artifact", {})],
        ),
        "AwaitingSceneApproval": (
            ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL,
            ProductVideoWorkflowState.CREATING_STORYBOARD,
            "product_video.storyboard",
            [agg.get("latest_artifact", {})],
        ),
        "AwaitingStoryboardApproval": (
            ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL,
            ProductVideoWorkflowState.RENDERING,
            "product_video.render",
            [agg.get("latest_artifact", {})],
        ),
        "AwaitingFinalApproval": (
            ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL,
            ProductVideoWorkflowState.EXPORTING,
            "product_video.export",
            [agg.get("latest_artifact", {})],
        ),
    }

    if gate in GATE_TRANSITIONS:
        curr_enum, next_enum, job_name, job_args = GATE_TRANSITIONS[gate]
        next_validated = transition(curr_enum, next_enum)

        outbox_msg = build_envelope(
            workflow_id=wf_id,
            topic="job.dispatch",
            idempotency_key=f"idemp_{job_name}_{wf_id}_v{current_version + 1}",
            payload={
                "job_name": job_name,
                "workflow_id": wf_id,
                "args": job_args,
                "owner_user_id": owner_user_id,
            },
        )

        next_agg = dict(agg)
        next_agg["state"] = next_validated.value
        next_agg.pop("pending_approval_gate", None)

        repo.commit_workflow(
            workflow_id=wf_id,
            aggregate_json=json.dumps(next_agg),
            events=[
                {
                    "event_id": f"evt_appr_{req_id}",
                    "command_id": f"cmd_appr_{req_id}",
                    "event_type": "ApprovalGranted",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"gate": gate, "request_id": req_id},
                }
            ],
            outbox_message=outbox_msg,
            expected_version=current_version,
        )
        return {
            "request_id": req_id,
            "status": "approved",
            "workflow_id": wf_id,
            "new_state": next_validated.value,
            "enqueued_job": job_name,
        }

    return {"request_id": req_id, "status": "approved", "workflow_id": wf_id}


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
            return approve_and_advance_workflow(
                connection=connection,
                target_id=cmd.target_id,
                owner_user_id=cmd.owner_user_id,
                payload=dict(cmd.payload),
            )

        elif cmd.command_type == "reject":
            approval_service = ApprovalService(connection)
            approval_service.reject(cmd.target_id)
            return {"target_id": cmd.target_id, "status": "rejected"}

        return {"target_id": cmd.target_id, "status": "accepted"}

    return handle_command
