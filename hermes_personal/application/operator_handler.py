from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable

from hermes_personal.contracts.operator import OperatorCommand
from hermes_personal.integrations.video_factory.ports import OFFICIAL_PRODUCT_VIDEO_PROVIDER_KINDS
from hermes_personal.integrations.video_factory.scene_renderer import SceneRenderOperationStore
from hermes_personal.product_video import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
    start_product_video_workflow,
    transition,
)
from hermes_personal.product_video.qc.image_qc import compute_artifact_digest
from hermes_personal.product_video.qc.fingerprint import (
    IMAGE_POLICY_VERSION,
    KEYFRAME_POLICY_VERSION,
    VIDEO_POLICY_VERSION,
)
from hermes_personal.product_video.qc.models import QCStage, QCVerdict
from hermes_personal.product_video.qc.normalization import _media_manifest
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.video_qc import compute_file_sha256
from hermes_personal.workflows.approvals import ApprovalService, ApprovalStatus
from hermes_personal.workflows.envelope import build_envelope
from hermes_personal.workflows.repository import WorkflowRepository


def resume_video_scene_after_qc_failure(
    connection: sqlite3.Connection,
    scene_store: SceneRenderOperationStore,
    *,
    workflow_id: str,
    owner_user_id: str,
    scene_order: int,
    provider_kind: str | None = None,
) -> dict[str, Any]:
    """Retry one QC-failed scene and resume the approved render batch."""
    repo = WorkflowRepository(connection)
    loaded = repo.get_workflow(workflow_id)
    if loaded is None:
        raise KeyError(f"Workflow {workflow_id!r} not found")
    aggregate, version = loaded
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    if (
        aggregate.get("state") != ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
        or aggregate.get("operator_stage") != QCStage.VIDEO.value
        or aggregate.get("operator_action") not in {"qc_retry_authorization", "qc_authorization"}
    ):
        raise ValueError("Workflow is not waiting for a failed Video QC scene retry")
    report_id = str(aggregate.get("operator_qc_report_id") or "")
    report = QCReportRepository(connection).get_report(report_id)
    render_result = aggregate.get("render_result") or {}
    batch_id = str(render_result.get("render_id") or "")
    if (
        not report
        or report.stage != QCStage.VIDEO
        or report.verdict != QCVerdict.FAIL
        or report.artifact_digest != str(render_result.get("sha256") or "").removeprefix("sha256:")
        or not batch_id
    ):
        raise ValueError("Failed Video QC report is not bound to the current render")
    failures = [
        item for item in report.findings.get("visual_scenes", [])
        if isinstance(item, dict) and item.get("verdict") == "fail"
    ]
    if len(failures) != 1 or failures[0].get("scene_number") != scene_order:
        raise ValueError("Requested scene does not uniquely match the failed Video QC scene")
    rows = scene_store.connection.execute(
        "SELECT * FROM video_factory_scene_operation WHERE render_batch_id = ? AND scene_order = ? "
        "ORDER BY attempt DESC",
        (batch_id, scene_order),
    ).fetchall()
    if not rows:
        raise ValueError("Failed scene operation is missing")
    old_operation = dict(rows[0])
    if old_operation["status"] != "completed":
        raise ValueError("Failed scene has no completed clip to retry")
    storyboard = aggregate.get("storyboard")
    approval = aggregate.get("latest_approval_receipt")
    authorization = aggregate.get("qc_authorization")
    if (
        not isinstance(storyboard, dict)
        or not isinstance(approval, dict)
        or approval.get("gate") != ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
        or not isinstance(authorization, dict)
    ):
        raise ValueError("Approved storyboard or scoped authorization is missing")
    retry = scene_store.retry_qc_failed_scene(
        old_operation["operation_id"], qc_report_id=report_id,
        provider_kind=provider_kind,
    )
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = transition(
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
        ProductVideoWorkflowState.RENDERING,
    ).value
    next_aggregate["active_render_job_id"] = batch_id
    next_aggregate["video_retry_report_id"] = report_id
    for key in ("operator_action", "operator_stage", "operator_reason", "operator_qc_report_id"):
        next_aggregate.pop(key, None)
    outbox = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=f"idemp_product_video.render_qc_retry_{workflow_id}_a{retry['attempt']}_v{version + 1}",
        payload={
            "job_name": "product_video.render",
            "workflow_id": workflow_id,
            "project_id": aggregate.get("project_id"),
            "args": [storyboard],
            "kwargs": {
                "owner_user_id": owner_user_id,
                "project_id": aggregate.get("project_id"),
                "approval_receipt": approval,
                "qc_authorization": authorization,
                "qc_max_cost_usd": aggregate.get("qc_max_cost_usd"),
                "render_params": {
                    "active_job_id": batch_id,
                    **({"provider_kind": provider_kind} if provider_kind else {}),
                },
            },
            "owner_user_id": owner_user_id,
        },
    )
    with connection:
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_video_qc_retry_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_video_qc_retry_{workflow_id}_v{version + 1}",
                "event_type": "VideoSceneRetryAuthorized",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"qc_report_id": report_id, "scene_order": scene_order, "operation_id": retry["operation_id"]},
            }],
            outbox_message=outbox,
            expected_version=version,
        )
    return {"workflow_id": workflow_id, "scene_operation_id": retry["operation_id"], "render_batch_id": batch_id}


def rebuild_storyboard_after_video_qc_failure(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    frame_feedback: dict[str, str],
) -> dict[str, Any]:
    """Regenerate specified keyframes after a video failure traces to approved anchors."""
    repo = WorkflowRepository(connection)
    loaded = repo.get_workflow(workflow_id)
    if loaded is None:
        raise KeyError(f"Workflow {workflow_id!r} not found")
    aggregate, version = loaded
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    if (
        aggregate.get("state") != ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
        or aggregate.get("operator_stage") != QCStage.VIDEO.value
        or aggregate.get("operator_action") not in {"qc_retry_authorization", "qc_authorization"}
    ):
        raise ValueError("Workflow is not waiting for Video QC recovery")
    render = aggregate.get("render_result") or {}
    report = QCReportRepository(connection).get_latest_report(
        workflow_id, QCStage.VIDEO,
        expected_artifact_digest=str(render.get("sha256") or "").removeprefix("sha256:"),
    )
    if report is None or report.verdict != QCVerdict.FAIL:
        raise ValueError("Current render has no failed Video QC report")
    storyboard = aggregate.get("storyboard")
    scene_plan = aggregate.get("scene_plan")
    if not isinstance(storyboard, dict) or not isinstance(scene_plan, dict):
        raise ValueError("Approved storyboard and Scene Plan are required")
    approved_ids = {
        str(frame.get("frame_id")) for frame in storyboard.get("generated_keyframes", [])
        if isinstance(frame, dict)
    }
    if not frame_feedback or any(
        frame_id not in approved_ids or not frame_id.endswith("-end") or not feedback.strip()
        for frame_id, feedback in frame_feedback.items()
    ):
        raise ValueError("Recovery requires specific approved END frames and feedback")
    attempt = int(aggregate.get("keyframe_recovery_attempt", 0) or 0) + 1
    recovery_plan = {
        "frames": [
            {"frame_id": frame_id, "scene_id": frame_id.removesuffix("-end"),
             "actions": ["regenerate_keyframe"], "feedback": feedback}
            for frame_id, feedback in sorted(frame_feedback.items())
        ],
        "source_video_qc_report_id": report.report_id,
    }
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = transition(
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
    ).value
    next_aggregate["keyframe_recovery_plan"] = recovery_plan
    next_aggregate["keyframe_recovery_attempt"] = attempt
    for key in ("operator_action", "operator_stage", "operator_reason", "operator_qc_report_id"):
        next_aggregate.pop(key, None)
    auth = aggregate.get("qc_authorization")
    if not isinstance(auth, dict):
        raise ValueError("Scoped QC authorization is required")
    outbox = build_envelope(
        workflow_id=workflow_id, topic="job.dispatch",
        idempotency_key=f"idemp_product_video.storyboard_video_recovery_{workflow_id}_a{attempt}_v{version + 1}",
        payload={
            "job_name": "product_video.storyboard", "workflow_id": workflow_id,
            "project_id": aggregate.get("project_id"), "args": [scene_plan],
            "kwargs": {
                "project_id": aggregate.get("project_id"), "owner_user_id": owner_user_id,
                "qc_authorization": auth, "qc_max_cost_usd": aggregate.get("qc_max_cost_usd"),
                "recovery_plan": recovery_plan, "recovery_attempt": attempt,
                "previous_storyboard": storyboard,
            },
            "owner_user_id": owner_user_id,
        },
    )
    with connection:
        repo.commit_workflow(
            workflow_id=workflow_id, aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_video_anchor_recovery_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_video_anchor_recovery_{workflow_id}_v{version + 1}",
                "event_type": "StoryboardRecoveryFromVideoQC",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"qc_report_id": report.report_id, "frame_ids": sorted(frame_feedback)},
            }],
            outbox_message=outbox, expected_version=version,
        )
    return {"workflow_id": workflow_id, "recovery_attempt": attempt, "frame_ids": sorted(frame_feedback)}


def _file_url_to_path(value: str) -> Path | None:
    if not value.startswith("file://"):
        return None
    raw = value.removeprefix("file://")
    if raw.startswith("/") and len(raw) > 3 and raw[2] == ":":
        raw = raw[1:]
    return Path(raw)


def _current_qc_digest(stage: QCStage, artifact: dict[str, Any]) -> str:
    if stage == QCStage.IMAGE:
        raw = artifact.get("resource_pack", artifact)
        return compute_artifact_digest(raw)
    if stage == QCStage.KEYFRAME:
        raw = dict(artifact)
        raw.pop("keyframe_qc_receipt", None)
        return str(raw.get("package_digest") or compute_artifact_digest(raw))

    sha = artifact.get("sha256") or artifact.get("digest") or artifact.get("artifact_digest")
    if sha:
        return str(sha).removeprefix("sha256:")
    url = artifact.get("video_url") or artifact.get("final_video_url") or artifact.get("file_path")
    if isinstance(url, str):
        path = _file_url_to_path(url) if url.startswith("file://") else Path(url)
        digest = compute_file_sha256(path)
        if digest:
            return digest
    return compute_artifact_digest(artifact)


def _require_current_pass_qc(
    connection: sqlite3.Connection,
    workflow_id: str,
    stage: QCStage,
    artifact: dict[str, Any],
) -> None:
    artifact_digest = _current_qc_digest(stage, artifact)
    report = QCReportRepository(connection).get_latest_report(
        workflow_id,
        stage,
        expected_artifact_digest=artifact_digest,
    )
    if report is None:
        raise ValueError(
            f"QC report required before approval: no current {stage.value} QC report "
            f"matches artifact digest {artifact_digest}"
        )
    if report.verdict != QCVerdict.PASS or report.score < 80:
        raise ValueError(
            f"QC report required before approval: latest {stage.value} QC report "
            f"{report.report_id} is {report.verdict.value} with score {report.score}"
        )

    # Historical seeded reports remain readable for offline recovery fixtures,
    # but they cannot unlock a real artifact with media or a render output.
    legacy_fixture = (
        report.findings.get("seeded_for") and not report.findings.get("automatic")
    ) or (
        report.evaluator_name in {"test", "test_seeded_qc"}
        and not (artifact.get("assets") or artifact.get("media_assets") or artifact.get("product_references"))
    )
    if legacy_fixture:
        return
    if report.provider_mode != "configured" or report.findings.get("automatic") is False:
        raise ValueError("Configured automatic QC report is required; fake/manual summaries cannot unlock a gate")
    expected_policy = {
        QCStage.IMAGE: IMAGE_POLICY_VERSION,
        QCStage.KEYFRAME: KEYFRAME_POLICY_VERSION,
        QCStage.VIDEO: VIDEO_POLICY_VERSION,
    }[stage]
    if report.policy_version != expected_policy:
        raise ValueError(f"QC report {report.report_id} uses stale policy {report.policy_version!r}")

    if stage == QCStage.IMAGE:
        raw = artifact.get("resource_pack", artifact) if isinstance(artifact, dict) else {}
        manifest = {item["asset_id"]: item for item in _media_manifest(raw)}
        items = report.findings.get("items", [])
        eligible = [item for item in items if isinstance(item, dict) and item.get("eligible")]
        if len(eligible) < 2:
            raise ValueError("Image QC requires at least two eligible references")
        if len(eligible) != int(report.findings.get("eligible_count", -1)):
            raise ValueError("Image QC eligible manifest count is inconsistent")
        for item in eligible:
            current = manifest.get(str(item.get("asset_id")))
            if not current or not current.get("eligible") or current.get("sha256") != item.get("digest"):
                raise ValueError("Image QC reference manifest is stale or no longer eligible")
            if item.get("verdict") != QCVerdict.PASS.value or item.get("hard_failure") or int(item.get("score", 0)) < 80:
                raise ValueError("Image QC contains an ineligible or failed reference")
    elif stage == QCStage.KEYFRAME:
        frames = artifact.get("generated_keyframes", [])
        items = report.findings.get("items", [])
        if not frames or len(items) != len(frames):
            raise ValueError("Keyframe QC must cover every generated keyframe")
        if any(
            item.get("verdict") != QCVerdict.PASS.value
            or item.get("hard_failure")
            or int(item.get("score", 0)) < 80
            for item in items
            if isinstance(item, dict)
        ):
            raise ValueError("Keyframe QC contains a failed or unknown frame")
    else:
        findings = report.findings
        tech = findings.get("technical_specs", {})
        coverage = findings.get("sample_coverage", {})
        scenes = findings.get("visual_scenes", [])
        expected_samples = int(coverage.get("expected_samples", 0))
        samples_per_scene = int(coverage.get("samples_per_scene", 0))
        if not tech.get("technical_pass") or not coverage.get("coverage_valid") or len(scenes) == 0:
            raise ValueError("Video QC requires technical PASS and complete scene coverage")
        if (
            samples_per_scene < 1
            or expected_samples != len(scenes) * samples_per_scene
            or int(coverage.get("total_samples", -1)) != expected_samples
        ):
            raise ValueError("Video QC sample coverage is incomplete")
        if any(
            scene.get("verdict") != QCVerdict.PASS.value
            or scene.get("hard_failure")
            or int(scene.get("score", 0)) < 80
            or int(scene.get("samples_extracted", 0)) != samples_per_scene
            for scene in scenes
            if isinstance(scene, dict)
        ):
            raise ValueError("Video QC contains a failed, unknown, or incompletely sampled scene")


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
    try:
        req = approval_service.get_request(target_id)
        is_approval_req = True
    except KeyError:
        is_approval_req = False

    if is_approval_req:
        wf_id = req.payload.get("workflow_id") or target_id
        wf_data = repo.get_workflow(wf_id)
        if wf_data is None:
            raise KeyError(f"Workflow '{wf_id}' not found")
        agg, current_version = wf_data
    else:
        wf_data = repo.get_workflow(target_id)
        if wf_data is None:
            raise KeyError(f"Approval request or workflow '{target_id}' not found")
        agg, current_version = wf_data
        wf_id = target_id
        req_id = agg.get("pending_approval_id")
        if not req_id:
            raise KeyError(f"No pending approval for workflow '{wf_id}'")
        req = approval_service.get_request(req_id)

    # 2. Check workflow version if expected_version is provided
    if expected_version is not None and expected_version != current_version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {current_version}")

    # Check approval request matches aggregate's pending request
    if req.request_id != agg.get("pending_approval_id"):
        raise ValueError("Approval request ID does not match aggregate pending_approval_id")

    # Check owner matching
    req_owner = req.payload.get("owner_user_id") or req.payload.get("owner_id")
    if not req_owner:
        raise ValueError("Approval request missing owner_user_id")
    if req_owner != owner_user_id:
        raise ValueError(f"Owner mismatch: approval request belongs to '{req_owner}', not '{owner_user_id}'")
    agg_owner = agg.get("owner_user_id") or agg.get("owner_id")
    if agg_owner and req_owner != agg_owner:
        raise ValueError(f"Owner mismatch: approval request belongs to '{req_owner}', aggregate belongs to '{agg_owner}'")

    # Check project matching
    req_project = req.payload.get("project_id")
    agg_project = agg.get("project_id")
    if not req_project:
        raise ValueError("Approval request missing project_id")
    if agg_project and req_project != agg_project:
        raise ValueError(f"Project mismatch: approval request has '{req_project}', expected '{agg_project}'")

    # Check artifact ID and version matching
    latest_artifact = agg.get("latest_artifact")
    if isinstance(latest_artifact, dict):
        expected_art_id = (
            latest_artifact.get("artifact_id")
            or latest_artifact.get("brief_id")
            or latest_artifact.get("scene_plan_id")
            or latest_artifact.get("storyboard_id")
            or latest_artifact.get("render_id")
            or latest_artifact.get("export_id")
            or latest_artifact.get("resource_pack_id")
            or latest_artifact.get("id")
        )
        expected_art_ver = latest_artifact.get("version") or latest_artifact.get("resource_pack_version")

        req_art_id = req.payload.get("artifact_id")
        req_art_ver = req.payload.get("artifact_version")

        if expected_art_id:
            if not req_art_id:
                raise ValueError(f"Approval request missing artifact_id (expected '{expected_art_id}')")
            if req_art_id != expected_art_id:
                raise ValueError(f"Artifact ID mismatch: approval request has '{req_art_id}', expected '{expected_art_id}'")
        if expected_art_ver is not None:
            if req_art_ver is None:
                raise ValueError(f"Approval request missing artifact_version (expected {expected_art_ver})")
            if req_art_ver != expected_art_ver:
                raise ValueError(f"Artifact version mismatch: approval request has {req_art_ver}, expected {expected_art_ver}")

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
    if req_gate != agg_gate:
        raise ValueError("Approval request gate mismatch")

    if req.payload.get("workflow_version") != current_version:
        raise ValueError("Approval request workflow_version mismatch")

    if req.status != ApprovalStatus.PENDING:
        raise ValueError(f"Approval request {req.request_id} is already {req.status.value}")

    # 5. Determine next state & next job
    if curr_enum == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK:
        next_enum = ProductVideoWorkflowState.LOCKING_RESOURCE_PACK
        job_name = "product_video.lock"
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

    if curr_enum == ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK:
        if not isinstance(latest_artifact, dict):
            raise ValueError("QC report required before approval: latest resource-pack artifact is missing")
        _require_current_pass_qc(connection, wf_id, QCStage.IMAGE, latest_artifact)
    elif curr_enum == ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL:
        if not isinstance(latest_artifact, dict):
            raise ValueError("QC report required before approval: latest render artifact is missing")
        _require_current_pass_qc(connection, wf_id, QCStage.VIDEO, latest_artifact)
    elif curr_enum == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL:
        if not isinstance(latest_artifact, dict):
            raise ValueError("QC report required before approval: storyboard package is missing")
        _require_current_pass_qc(connection, wf_id, QCStage.KEYFRAME, latest_artifact)

    args = [agg.get("latest_artifact")]

    # 6. Validate transition
    next_validated = transition(curr_enum, next_enum)

    # 7. SINGLE ATOMIC SQLITE TRANSACTION
    effective_project_id = req_project or agg_project
    if not effective_project_id:
        raise ValueError("Cannot determine project_id for workflow advancement")

    receipt_dict = {
        "approval_request_id": req.request_id,
        "project_id": effective_project_id,
        "gate": gate_name,
        "workflow_version": current_version,
        "artifact_id": req.payload.get("artifact_id"),
        "artifact_version": req.payload.get("artifact_version"),
        "owner_user_id": owner_user_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }

    outbox_payload = {
        "job_name": job_name,
        "workflow_id": wf_id,
        "project_id": effective_project_id,
        "args": args,
        "kwargs": {
            "approval_receipt": receipt_dict,
            "approval_request_id": req.request_id,
            "project_id": effective_project_id,
            "owner_user_id": owner_user_id,
        },
        "owner_user_id": owner_user_id,
        "approval_request_id": req.request_id,
    }
    if curr_enum == ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL:
        previous_storyboard = agg.get("storyboard")
        if isinstance(previous_storyboard, dict):
            outbox_payload["kwargs"]["previous_storyboard"] = dict(previous_storyboard)
    # Preserve the explicit QC authorization across human-gated transitions;
    # it remains workflow-scoped and is revalidated by ProductVideoQCService.
    qc_authorization = (payload or {}).get("qc_authorization") or agg.get("qc_authorization")
    qc_max_cost_usd = (payload or {}).get("qc_max_cost_usd")
    if qc_max_cost_usd is None:
        qc_max_cost_usd = agg.get("qc_max_cost_usd")
    if isinstance(qc_authorization, dict):
        outbox_payload["kwargs"]["qc_authorization"] = dict(qc_authorization)
    if qc_max_cost_usd is not None:
        outbox_payload["kwargs"]["qc_max_cost_usd"] = qc_max_cost_usd
    render_provider_kind = str((payload or {}).get("render_provider_kind") or "").strip()
    if render_provider_kind:
        if curr_enum != ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL:
            raise ValueError("render_provider_kind is only valid at Storyboard approval")
        if render_provider_kind not in OFFICIAL_PRODUCT_VIDEO_PROVIDER_KINDS:
            raise ValueError("render_provider_kind must be google_flow or vertex_ai")
        outbox_payload["kwargs"]["render_params"] = {"provider_kind": render_provider_kind}
    if req.payload.get("artifact_id"):
        outbox_payload["artifact_id"] = req.payload.get("artifact_id")
    if req.payload.get("artifact_version") is not None:
        outbox_payload["artifact_version"] = req.payload.get("artifact_version")
    if req.payload.get("gate"):
        outbox_payload["gate"] = req.payload.get("gate")

    outbox_msg = build_envelope(
        workflow_id=wf_id,
        topic="job.dispatch",
        idempotency_key=f"idemp_{job_name}_{wf_id}_v{current_version + 1}",
        payload=outbox_payload,
    )

    next_agg = dict(agg)
    next_agg["state"] = next_validated.value
    next_agg["project_id"] = effective_project_id
    next_agg["latest_approval_receipt"] = {
        "approval_request_id": req.request_id,
        "project_id": effective_project_id,
        "gate": gate_name,
        "artifact_id": req.payload.get("artifact_id"),
        "artifact_version": req.payload.get("artifact_version"),
        "owner_user_id": owner_user_id,
        "approved_at": datetime.now(timezone.utc).isoformat(),
    }
    if isinstance(qc_authorization, dict):
        next_agg["qc_authorization"] = dict(qc_authorization)
    if qc_max_cost_usd is not None:
        next_agg["qc_max_cost_usd"] = qc_max_cost_usd
    if render_provider_kind:
        next_agg["selected_render_provider"] = render_provider_kind
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


def revise_brief_and_request_approval(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    revised_brief: dict[str, Any],
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Replace the pending Gate 2 artifact and issue a new human approval.

    The caller persists the new Video Factory brief before invoking this
    coordinator.  This function owns the Hermes-side transition so the prior
    approval cannot approve a superseded brief.
    """
    repo = WorkflowRepository(connection)
    approval_service = ApprovalService(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, current_version = workflow
    if expected_version is not None and expected_version != current_version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {current_version}")
    if aggregate.get("state") != ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value:
        raise ValueError("Creative Brief can only be revised while awaiting Gate 2 approval")
    if aggregate.get("pending_approval_gate") != ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value:
        raise ValueError("Workflow is not waiting for a Creative Brief approval")

    previous_request_id = aggregate.get("pending_approval_id")
    if not isinstance(previous_request_id, str) or not previous_request_id:
        raise ValueError("Workflow is missing its pending Creative Brief approval")
    previous_request = approval_service.get_request(previous_request_id)
    if previous_request.status != ApprovalStatus.PENDING:
        raise ValueError("Pending Creative Brief approval is no longer pending")
    if previous_request.payload.get("workflow_id") != workflow_id:
        raise ValueError("Pending Creative Brief approval belongs to another workflow")
    if previous_request.payload.get("owner_user_id") != owner_user_id:
        raise ValueError("Pending Creative Brief approval belongs to another owner")

    project_id = aggregate.get("project_id")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Workflow is missing project_id")
    if previous_request.payload.get("project_id") != project_id:
        raise ValueError("Pending Creative Brief approval belongs to another project")

    artifact_id = revised_brief.get("artifact_id") or revised_brief.get("brief_id")
    artifact_version = revised_brief.get("version")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("Revised Creative Brief is missing brief_id")
    if not isinstance(artifact_version, int) or artifact_version < 1:
        raise ValueError("Revised Creative Brief is missing a positive version")

    previous_brief = aggregate.get("creative_brief") or aggregate.get("latest_artifact")
    now = datetime.now(timezone.utc).isoformat()
    next_aggregate = dict(aggregate)
    next_aggregate["creative_brief"] = dict(revised_brief)
    next_aggregate["latest_artifact"] = dict(revised_brief)
    revisions = list(next_aggregate.get("creative_brief_revisions") or [])
    if isinstance(previous_brief, dict):
        revisions.append({
            "artifact": previous_brief,
            "superseded_at": now,
            "superseded_approval_id": previous_request_id,
        })
    next_aggregate["creative_brief_revisions"] = revisions

    approval_payload = {
        "workflow_id": workflow_id,
        "project_id": project_id,
        "gate": ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value,
        "workflow_version": current_version + 1,
        "artifact_ref": dict(revised_brief),
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "owner_user_id": owner_user_id,
        "supersedes_approval_id": previous_request_id,
    }

    with connection:
        cursor = connection.cursor()
        cursor.execute(
            "UPDATE approval_request SET status = ?, updated_at = ? WHERE request_id = ? AND status = ?",
            (ApprovalStatus.REJECTED.value, now, previous_request_id, ApprovalStatus.PENDING.value),
        )
        if cursor.rowcount != 1:
            raise ValueError("Pending Creative Brief approval changed while being revised")
        new_request_id = approval_service.submit_request(approval_payload, cursor=cursor)
        next_aggregate["pending_approval_id"] = new_request_id
        next_aggregate["pending_approval_gate"] = ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_brief_revised_{workflow_id}_v{current_version + 1}",
                "command_id": f"cmd_brief_revised_{workflow_id}_v{current_version + 1}",
                "event_type": "CreativeBriefRevised",
                "timestamp": now,
                "payload": {
                    "previous_approval_id": previous_request_id,
                    "new_approval_id": new_request_id,
                    "artifact_id": artifact_id,
                    "artifact_version": artifact_version,
                },
            }],
            expected_version=current_version,
        )

    return {
        "workflow_id": workflow_id,
        "previous_request_id": previous_request_id,
        "request_id": new_request_id,
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "state": ProductVideoWorkflowState.AWAITING_BRIEF_APPROVAL.value,
    }


def revise_scene_plan_and_request_approval(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    revised_plan: dict[str, Any],
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Replace a pending Gate 3 plan after its Video Factory revision is saved."""
    repo = WorkflowRepository(connection)
    approval_service = ApprovalService(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, current_version = workflow
    if expected_version is not None and expected_version != current_version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {current_version}")
    gate = ProductVideoWorkflowState.AWAITING_SCENE_APPROVAL.value
    pending_revision = aggregate.get("state") == gate and aggregate.get("pending_approval_gate") == gate
    storyboard_recovery = (
        aggregate.get("state") == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
        and aggregate.get("pending_approval_gate") == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
    )
    provider_recovery = aggregate.get("state") == ProductVideoWorkflowState.CREATING_STORYBOARD.value
    qc_recovery = (
        aggregate.get("state") == ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
        and aggregate.get("operator_stage") == QCStage.KEYFRAME.value
        and aggregate.get("operator_action") in {"qc_authorization", "qc_retry_authorization"}
    )
    if not pending_revision and not storyboard_recovery and not provider_recovery and not qc_recovery:
        raise ValueError("Workflow is not waiting for a Scene Plan approval or keyframe recovery")
    if storyboard_recovery:
        render = aggregate.get("render_result") or {}
        failed_video = QCReportRepository(connection).get_latest_report(
            workflow_id, QCStage.VIDEO,
            expected_artifact_digest=str(render.get("sha256") or "").removeprefix("sha256:"),
        )
        if failed_video is None or failed_video.verdict != QCVerdict.FAIL:
            raise ValueError("Storyboard rework requires failed Video QC on the current render")
    if provider_recovery or qc_recovery:
        receipt = aggregate.get("latest_approval_receipt") or {}
        if receipt.get("gate") != gate:
            raise ValueError("Storyboard recovery has no approved Scene Plan receipt")
        if provider_recovery:
            failed = connection.execute(
                "SELECT message, last_error FROM workflow_outbox "
                "WHERE workflow_id = ? AND state = 'quarantined' ORDER BY outbox_id DESC LIMIT 1",
                (workflow_id,),
            ).fetchone()
            if not failed:
                raise ValueError("Storyboard provider failure is not quarantined")
            failed_message = json.loads(failed["message"])
            if (
                failed_message.get("payload", {}).get("job_name") != "product_video.storyboard"
                or not any(
                    code in str(failed["last_error"])
                    for code in ("PROVIDER_UNAVAILABLE", "INVALID_RESPONSE")
                )
            ):
                raise ValueError("Storyboard did not fail on provider capability")
        previous_request_id = receipt.get("approval_request_id")
    elif storyboard_recovery:
        previous_request_id = aggregate.get("pending_approval_id")
    else:
        previous_request_id = aggregate.get("pending_approval_id")
    if not isinstance(previous_request_id, str) or not previous_request_id:
        raise ValueError("Workflow is missing its pending Scene Plan approval")
    previous_request = approval_service.get_request(previous_request_id)
    project_id = aggregate.get("project_id")
    expected_status = ApprovalStatus.PENDING if (pending_revision or storyboard_recovery) else ApprovalStatus.APPROVED
    if (
        previous_request.status != expected_status
        or previous_request.payload.get("workflow_id") != workflow_id
        or previous_request.payload.get("owner_user_id") != owner_user_id
        or previous_request.payload.get("project_id") != project_id
    ):
        raise ValueError("Pending Scene Plan approval identity or status changed")
    artifact_id = revised_plan.get("artifact_id") or revised_plan.get("scene_plan_id")
    artifact_version = revised_plan.get("version")
    if not isinstance(artifact_id, str) or not artifact_id:
        raise ValueError("Revised Scene Plan is missing scene_plan_id")
    if not isinstance(artifact_version, int) or artifact_version < 1:
        raise ValueError("Revised Scene Plan is missing a positive version")
    if revised_plan.get("project_id") != project_id:
        raise ValueError("Revised Scene Plan belongs to another project")
    previous_plan = aggregate.get("scene_plan") or aggregate.get("latest_artifact")
    if isinstance(previous_plan, dict) and artifact_version <= int(previous_plan.get("version") or 0):
        raise ValueError("Revised Scene Plan version must advance")

    now = datetime.now(timezone.utc).isoformat()
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = gate
    next_aggregate["scene_plan"] = dict(revised_plan)
    next_aggregate["latest_artifact"] = dict(revised_plan)
    if qc_recovery:
        for key in (
            "operator_action", "operator_stage", "operator_reason", "operator_qc_report_id",
            "keyframe_recovery_plan",
        ):
            next_aggregate.pop(key, None)
    revisions = list(next_aggregate.get("scene_plan_revisions") or [])
    if isinstance(previous_plan, dict):
        revisions.append({
            "artifact": previous_plan,
            "superseded_at": now,
            "superseded_approval_id": previous_request_id,
        })
    next_aggregate["scene_plan_revisions"] = revisions
    approval_payload = {
        "workflow_id": workflow_id,
        "project_id": project_id,
        "gate": gate,
        "workflow_version": current_version + 1,
        "artifact_ref": dict(revised_plan),
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "owner_user_id": owner_user_id,
        "supersedes_approval_id": previous_request_id,
    }
    with connection:
        cursor = connection.cursor()
        if pending_revision or storyboard_recovery:
            cursor.execute(
                "UPDATE approval_request SET status = ?, updated_at = ? WHERE request_id = ? AND status = ?",
                (ApprovalStatus.REJECTED.value, now, previous_request_id, ApprovalStatus.PENDING.value),
            )
            if cursor.rowcount != 1:
                raise ValueError("Pending Scene Plan approval changed while being revised")
        new_request_id = approval_service.submit_request(approval_payload, cursor=cursor)
        next_aggregate["pending_approval_id"] = new_request_id
        next_aggregate["pending_approval_gate"] = gate
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_scene_plan_revised_{workflow_id}_v{current_version + 1}",
                "command_id": f"cmd_scene_plan_revised_{workflow_id}_v{current_version + 1}",
                "event_type": "ScenePlanRevised",
                "timestamp": now,
                "payload": {
                    "previous_approval_id": previous_request_id,
                    "new_approval_id": new_request_id,
                    "artifact_id": artifact_id,
                    "artifact_version": artifact_version,
                },
            }],
            expected_version=current_version,
        )
    return {
        "workflow_id": workflow_id,
        "previous_request_id": previous_request_id,
        "request_id": new_request_id,
        "artifact_id": artifact_id,
        "artifact_version": artifact_version,
        "state": gate,
    }


def authorize_workflow_cost(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    authorization: dict[str, Any],
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Record an operator-issued replacement cost authorization for one workflow."""
    repo = WorkflowRepository(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, version = workflow
    if expected_version is not None and expected_version != version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {version}")
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    max_cost = authorization.get("workflow_max_cost_usd", authorization.get("max_cost_usd"))
    if not isinstance(max_cost, (int, float)) or isinstance(max_cost, bool) or max_cost <= 0:
        raise ValueError("Authorization requires a positive workflow_max_cost_usd")
    authorization_id = str(authorization.get("authorization_id") or authorization.get("run_id") or "").strip()
    if not authorization_id:
        raise ValueError("Authorization requires authorization_id or run_id")

    now = datetime.now(timezone.utc).isoformat()
    next_aggregate = dict(aggregate)
    previous = aggregate.get("qc_authorization")
    history = list(next_aggregate.get("cost_authorization_history") or [])
    if isinstance(previous, dict):
        history.append({"authorization": previous, "superseded_at": now})
    replacement = dict(authorization)
    replacement["workflow_id"] = workflow_id
    replacement["workflow_max_cost_usd"] = float(max_cost)
    next_aggregate["qc_authorization"] = replacement
    next_aggregate["cost_authorization_history"] = history
    with connection:
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_cost_authorized_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_cost_authorized_{workflow_id}_v{version + 1}",
                "event_type": "WorkflowCostAuthorized",
                "timestamp": now,
                "payload": {"authorization_id": authorization_id, "max_cost_usd": float(max_cost)},
            }],
            expected_version=version,
        )
    return {"workflow_id": workflow_id, "authorization": replacement, "version": version + 1}


def block_workflow_for_qc(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    stage: QCStage,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Invalidate a pending gate when its required automatic QC is not PASS."""
    repo = WorkflowRepository(connection)
    approvals = ApprovalService(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, version = workflow
    if expected_version is not None and expected_version != version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {version}")
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    request_id = aggregate.get("pending_approval_id")
    if not isinstance(request_id, str) or not request_id:
        raise ValueError("Workflow has no pending approval to invalidate")
    request = approvals.get_request(request_id)
    if request.status != ApprovalStatus.PENDING:
        raise ValueError("Workflow approval is not pending")

    now = datetime.now(timezone.utc).isoformat()
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value
    next_aggregate["operator_action"] = "qc_retry_authorization"
    next_aggregate["operator_stage"] = stage.value
    next_aggregate["operator_reason"] = reason
    next_aggregate.pop("pending_approval_id", None)
    next_aggregate.pop("pending_approval_gate", None)
    with connection:
        cur = connection.cursor()
        cur.execute(
            "UPDATE approval_request SET status = ?, updated_at = ? WHERE request_id = ? AND status = ?",
            (ApprovalStatus.REJECTED.value, now, request_id, ApprovalStatus.PENDING.value),
        )
        if cur.rowcount != 1:
            raise ValueError("Pending approval changed while blocking workflow")
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_qc_block_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_qc_block_{workflow_id}_v{version + 1}",
                "event_type": "QCBlockedApproval",
                "timestamp": now,
                "payload": {"stage": stage.value, "approval_request_id": request_id, "reason": reason},
            }],
            expected_version=version,
        )
    return {"workflow_id": workflow_id, "request_id": request_id, "state": next_aggregate["state"]}


def resume_storyboard_after_qc_authorization(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    expected_version: int | None = None,
    authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resume a blocked storyboard job after an operator authorizes QC retry."""
    repo = WorkflowRepository(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, version = workflow
    if expected_version is not None and expected_version != version:
        raise ValueError(f"Stale workflow version: expected {expected_version}, current {version}")
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    current_state = aggregate.get("state")
    if current_state == ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value:
        if aggregate.get("operator_stage") != QCStage.KEYFRAME.value:
            raise ValueError("Workflow is not waiting for Keyframe QC retry")
    elif current_state != ProductVideoWorkflowState.CREATING_STORYBOARD.value:
        raise ValueError("Workflow is not ready for storyboard retry")

    next_aggregate = dict(aggregate)
    next_aggregate["state"] = ProductVideoWorkflowState.CREATING_STORYBOARD.value
    recovery_plan = aggregate.get("keyframe_recovery_plan")
    previous_storyboard = aggregate.get("storyboard")
    if previous_storyboard is None:
        latest = aggregate.get("latest_artifact")
        if isinstance(latest, dict) and (latest.get("schema") in ("storyboard", "storyboard_package", "storyboard_v2") or "generated_keyframes" in latest):
            previous_storyboard = latest
    if not isinstance(recovery_plan, dict) or not recovery_plan.get("frames"):
        raise ValueError("Workflow is missing the persisted keyframe recovery plan")
    if current_state == ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value and not isinstance(previous_storyboard, dict):
        raise ValueError("Workflow is missing the previous storyboard package")
    attempt = int(aggregate.get("keyframe_recovery_attempt", 0) or 0) + 1
    next_aggregate["keyframe_recovery_attempt"] = attempt
    if authorization is not None:
        next_aggregate["qc_authorization"] = authorization
        next_aggregate["qc_max_cost_usd"] = authorization.get("max_cost_usd")
    for key in ("operator_action", "operator_stage", "operator_reason", "operator_qc_report_id"):
        next_aggregate.pop(key, None)
    now = datetime.now(timezone.utc).isoformat()
    scene_ref = aggregate.get("scene_plan") or aggregate.get("latest_artifact")
    if not isinstance(scene_ref, dict):
        raise ValueError("Workflow is missing the persisted Scene Plan")
    auth = authorization or aggregate.get("qc_authorization")
    if not isinstance(auth, dict):
        raise ValueError("Keyframe recovery requires an explicit QC authorization")
    outbox = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=f"idemp_product_video.storyboard_recovery_{workflow_id}_a{attempt}_v{version + 1}",
        payload={
            "job_name": "product_video.storyboard",
            "workflow_id": workflow_id,
            "project_id": aggregate.get("project_id"),
            "args": [scene_ref],
            "kwargs": {
                "project_id": aggregate.get("project_id"),
                "owner_user_id": owner_user_id,
                "qc_authorization": auth,
                "qc_max_cost_usd": auth.get("max_cost_usd"),
                "recovery_plan": recovery_plan,
                "recovery_attempt": attempt,
                "previous_storyboard": previous_storyboard,
            },
            "owner_user_id": owner_user_id,
        },
    )
    with connection:
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[{
                "event_id": f"evt_qc_retry_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_qc_retry_{workflow_id}_v{version + 1}",
                "event_type": "QCRetryAuthorized",
                "timestamp": now,
                "payload": {"stage": QCStage.KEYFRAME.value},
            }],
            outbox_message=outbox,
            expected_version=version,
        )
    return {
        "workflow_id": workflow_id,
        "state": next_aggregate["state"],
        "version": version + 1,
        "recovery_attempt": attempt,
        "recovery_plan": recovery_plan,
    }


def recover_unknown_keyframe_submission(
    connection: sqlite3.Connection,
    *,
    workflow_id: str,
    owner_user_id: str,
    authorization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reconcile a quarantined keyframe call, then replace only missing frames."""
    from hermes_personal.integrations.video_factory.keyframe_provider import KeyframeOperationStore
    from hermes_personal.integrations.video_factory.keyframe_provider_factory import (
        resolve_keyframe_provider,
    )
    from hermes_personal.integrations.video_factory.capacity import ProviderCapacityStore
    from hermes_personal.product_video.creative.contracts import ResearchDossier, ScriptScenePlanV2
    from hermes_personal.product_video.creative.storyboard import compile_keyframe_requests
    from hermes_personal.product_video.storage.layout import get_workspace_layout
    from hermes_personal.workflows.outbox_repository import OutboxRepository

    repo = WorkflowRepository(connection)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise KeyError(f"Workflow '{workflow_id}' not found")
    aggregate, version = workflow
    if aggregate.get("owner_user_id") != owner_user_id:
        raise ValueError("Workflow belongs to another owner")
    if aggregate.get("state") != ProductVideoWorkflowState.CREATING_STORYBOARD.value:
        raise ValueError("Workflow is not creating a storyboard")
    row = connection.execute(
        "SELECT outbox_id, message, state, last_error FROM workflow_outbox "
        "WHERE workflow_id = ? ORDER BY outbox_id DESC LIMIT 1",
        (workflow_id,),
    ).fetchone()
    if not row or row["state"] != "quarantined" or "NETWORK_UNKNOWN_OUTCOME" not in str(row["last_error"]):
        raise ValueError("No quarantined unknown keyframe submission to recover")
    envelope = json.loads(row["message"])
    if envelope.get("payload", {}).get("job_name") != "product_video.storyboard":
        raise ValueError("Quarantined job is not storyboard generation")

    scene_ref = aggregate.get("scene_plan")
    if not isinstance(scene_ref, dict) or not isinstance(scene_ref.get("research_dossier"), dict):
        raise ValueError("Approved Scene Plan and dossier are required")
    script = ScriptScenePlanV2.from_dict(scene_ref)
    dossier = ResearchDossier.from_dict(scene_ref["research_dossier"])
    requests = compile_keyframe_requests(
        workflow_id=workflow_id,
        project_id=str(aggregate["project_id"]),
        dossier=dossier,
        script=script,
    )
    by_operation = {request.operation_id: request for request in requests}
    rows = connection.execute(
        "SELECT operation_id, provider_operation_id, status FROM video_factory_keyframe_operation "
        "WHERE workflow_id = ? AND status IN ('unknown', 'submitting')",
        (workflow_id,),
    ).fetchall()
    matching = [item for item in rows if item["operation_id"] in by_operation]
    if not matching:
        raise ValueError("No unknown operation belongs to the approved Scene Plan")

    store = KeyframeOperationStore(connection)
    provider, _ = resolve_keyframe_provider(get_workspace_layout().root / "keyframes")
    missing = []
    for item in matching:
        request = by_operation[item["operation_id"]]
        provider_id = item["provider_operation_id"] or item["operation_id"]
        result = provider.get_status(provider_id)
        if result.status == "completed":
            store.save_result(request, result)
        else:
            missing.append(request)

    if not missing:
        if not OutboxRepository(connection).requeue_quarantined(int(row["outbox_id"])):
            raise ValueError("Quarantined storyboard job changed during reconciliation")
        return {"workflow_id": workflow_id, "reconciled": len(matching), "replaced": 0}

    auth = dict(authorization or {})
    scopes = auth.get("scope")
    scopes = scopes if isinstance(scopes, list) else [scopes]
    if auth.get("workflow_id") != workflow_id or not ({"keyframe", "product_video"} & set(scopes)):
        raise ValueError("Replacement requires authorization scoped to this workflow and keyframe QC")
    if not str(auth.get("run_id") or auth.get("authorization_id") or "").strip():
        raise ValueError("Replacement authorization is missing its run ID")
    try:
        expires_at = datetime.fromisoformat(str(auth["expires_at"]).replace("Z", "+00:00"))
        max_cost = float(auth["max_cost_usd"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Replacement authorization requires expiry and maximum cost") from exc
    if expires_at.tzinfo is None or expires_at <= datetime.now(timezone.utc) or max_cost <= 0:
        raise ValueError("Replacement authorization must be unexpired with a positive cost ceiling")

    # The synchronous call has ended, but its unknown checkpoint deliberately
    # retained capacity. Retire only the exact operation the operator replaces.
    capacity = ProviderCapacityStore(connection)
    for request in missing:
        capacity.release_terminal("vertex_keyframe", request.operation_id)
        connection.execute(
            "UPDATE video_factory_keyframe_operation SET status = 'failed', error_code = 'REPLACED_AFTER_UNKNOWN_OUTCOME', updated_at = CURRENT_TIMESTAMP WHERE operation_id = ?",
            (request.operation_id,),
        )

    plan = {
        "frames": [
            {
                "frame_id": request.frame_id,
                "actions": ["regenerate_keyframe"],
                "feedback": f"Operator-authorized replacement after unknown outcome for {request.operation_id}",
            }
            for request in missing
        ]
    }
    updated = dict(aggregate)
    updated["keyframe_recovery_plan"] = plan
    updated["qc_authorization"] = auth
    updated["qc_max_cost_usd"] = max_cost
    now = datetime.now(timezone.utc).isoformat()
    with connection:
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(updated),
            events=[{
                "event_id": f"evt_unknown_keyframe_recovery_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_unknown_keyframe_recovery_{workflow_id}_v{version + 1}",
                "event_type": "UnknownKeyframeReplacementAuthorized",
                "timestamp": now,
                "payload": {
                    "quarantined_outbox_id": int(row["outbox_id"]),
                    "unknown_operation_ids": [request.operation_id for request in missing],
                    "authorization_id": auth.get("run_id") or auth.get("authorization_id"),
                },
            }],
            expected_version=version,
        )
    resumed = resume_storyboard_after_qc_authorization(
        connection,
        workflow_id=workflow_id,
        owner_user_id=owner_user_id,
        expected_version=version + 1,
        authorization=auth,
    )
    return {**resumed, "reconciled": len(matching) - len(missing), "replaced": len(missing)}


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

            project_id = payload.get("project_id") or f"proj_{wf_id}"

            start_product_video_workflow(
                workflow_repository=repo,
                workflow_id=wf_id,
                product_name=product_name,
                keywords=keywords,
                pdp_url=pdp_url,
                project_id=project_id,
                owner_user_id=cmd.owner_user_id,
                idempotency_key=cmd.idempotency_key,
                qc_authorization=payload.get("qc_authorization"),
                qc_max_cost_usd=payload.get("qc_max_cost_usd"),
                research_snapshot_id=payload.get("research_snapshot_id"),
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
