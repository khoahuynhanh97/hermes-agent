"""CLI for Hermes Product Video selection, automation, and approval."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home
from hermes_personal.application.operator_handler import (
    approve_and_advance_workflow,
    recover_unknown_keyframe_submission,
)
from hermes_personal.product_video.candidate_service import (
    CandidateItem,
    DailyCandidateService,
)
from hermes_personal.product_video.workflow import (
    HITL_WAITING_STATES,
    ProductVideoWorkflowState,
    transition,
)
from hermes_personal.product_video.automation.repository import DailyImportRepository
from hermes_personal.product_video.qc.models import QCStage
from hermes_personal.product_video.qc.image_qc import compute_artifact_digest
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.product_video.qc.service import ProductVideoQCService
from hermes_personal.product_video.qc.video_qc import compute_file_sha256
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.envelope import build_envelope
from hermes_personal.workflows.outbox_repository import OutboxRepository
from hermes_personal.workflows.repository import WorkflowRepository
from hermes_personal.workflows.worker import run_worker


def cmd_open_folder(args: argparse.Namespace) -> int:
    """Open VideoAI hub folder in Windows File Explorer."""
    import os
    import subprocess
    from hermes_personal.product_video.storage.video_hub import (
        find_latest_video,
        get_video_ai_hub_root,
    )
    
    hub_root = Path(args.hub_root) if args.hub_root else get_video_ai_hub_root()
    
    if args.latest:
        folder = find_latest_video(hub_root, brand=args.brand)
        if not folder:
            print("No video folders found in hub")
            return 1
        target = folder
    else:
        if not hub_root.exists():
            print(f"Hub root does not exist: {hub_root}")
            return 1
        target = hub_root
    
    print(f"Opening: {target}")
    
    try:
        if os.name == 'nt':
            os.startfile(str(target))
        else:
            subprocess.run(["xdg-open", str(target)], check=True)
        return 0
    except Exception as e:
        print(f"Failed to open folder: {e}")
        return 1


def cmd_sync_video_hub(args: argparse.Namespace) -> int:
    """Sync all historical exports to VideoAI hub."""
    from hermes_personal.product_video.storage.video_hub import (
        sync_all_exports_to_hub,
        get_video_ai_hub_root,
    )
    
    # Resolve exports root
    if args.exports_root:
        exports_root = Path(args.exports_root)
    else:
        workspace = Path(os.getenv("HERMES_VIDEO_FACTORY_WORKSPACE", 
                                   get_hermes_home() / "video_factory_workspace"))
        exports_root = workspace / "exports"
    
    hub_root = Path(args.hub_root) if args.hub_root else get_video_ai_hub_root()
    
    print(f"Syncing exports from: {exports_root}")
    print(f"To VideoAI hub: {hub_root}")
    print()
    
    result = sync_all_exports_to_hub(exports_root, hub_root)
    
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"✓ Synced: {result['total_synced']}")
        print(f"⊘ Skipped: {result['skipped']}")
        print(f"✗ Errors: {result['errors']}")
        
        if result['synced_folders']:
            print("\nSynced folders:")
            for item in result['synced_folders']:
                print(f"  • [{item['product']}]")
                print(f"    → {item['hub_path']}")
    
    return 0 if result['errors'] == 0 else 1


def _resolve_db_path(db_path_arg: str | None) -> Path:
    if db_path_arg:
        return Path(db_path_arg)
    return get_hermes_home() / "hermes.db"


def _normalize_file_path(path_or_url: str | Path) -> Path:
    s = str(path_or_url).strip()
    if s.startswith("file://"):
        raw = s[7:]
        while raw.startswith(("/", "\\")) and not (len(raw) >= 2 and raw[1] == ":" and raw[0].isalpha()):
            raw = raw[1:]
        return Path(raw).resolve()
    return Path(s).resolve()


def _format_status_badge(status: str) -> str:
    badges = {
        "unprocessed": "[CHƯA TẠO VIDEO]",
        "awaiting_product_lock": "[CHỜ DUYỆT PRODUCT LOCK]",
        "in_production": "[ĐANG SẢN XUẤT]",
        "completed": "[ĐÃ HOÀN TẤT VIDEO]",
        "invalid": "[KHÔNG ĐẠT TIÊU CHUẨN]",
    }
    return badges.get(status, f"[{status.upper()}]")


def _quarantined_job_error(conn: Any, workflow_id: str, state: str) -> str | None:
    """Expose a terminal worker error while the aggregate still shows its old step."""
    if state not in {
        ProductVideoWorkflowState.RESEARCHING.value,
        ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value,
    }:
        return None
    row = conn.execute(
        "SELECT state, last_error FROM workflow_outbox WHERE workflow_id = ? "
        "ORDER BY outbox_id DESC LIMIT 1",
        (workflow_id,),
    ).fetchone()
    if row is None or row["state"] != "quarantined":
        return None
    return str(row["last_error"] or "Worker job was quarantined")


def _qc_authorization_from_args(args: argparse.Namespace, workflow_id: str | None = None) -> dict[str, Any] | None:
    """Build an optional explicit QC authorization without inventing defaults."""
    run_id = getattr(args, "qc_authorization_run_id", None) or getattr(args, "authorization_run_id", None)
    scopes = getattr(args, "qc_authorization_scope", None) or getattr(args, "authorization_scope", None) or []
    expires_at = getattr(args, "qc_authorization_expires_at", None) or getattr(args, "authorization_expires_at", None)
    auth_max = getattr(args, "qc_authorization_max_cost_usd", None) or getattr(args, "authorization_max_cost_usd", None)
    if not (run_id or scopes or expires_at or auth_max is not None):
        return None
    auth: dict[str, Any] = {
        "run_id": run_id,
        "scope": list(scopes),
        "expires_at": expires_at,
        "max_cost_usd": auth_max,
    }
    campaign_id = getattr(args, "authorization_campaign_id", None) or getattr(args, "qc_authorization_campaign_id", None)
    if campaign_id:
        auth["campaign_id"] = campaign_id
    if workflow_id:
        auth["workflow_id"] = workflow_id
    return auth


def _advance_qc_waiting_workflow(
    conn: Any,
    workflow_id: str,
    stage: QCStage,
    authorization: dict[str, Any],
    qc_passed_retry: bool = False,
    qc_attempt_max_cost_usd: float | None = None,
) -> str:
    """Create the next human gate only after configured QC passed this exact wait."""
    repo = WorkflowRepository(conn)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow '{workflow_id}' was not found")
    aggregate, version = workflow
    if aggregate.get("state") != ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value:
        raise ValueError("Workflow is not waiting for QC authorization")
    if aggregate.get("operator_action") not in {
        "qc_authorization",
        "qc_retry_authorization",
    }:
        raise ValueError("Workflow is not waiting for a QC authorization")
    if aggregate.get("operator_stage") != stage.value:
        raise ValueError(f"Workflow is waiting for {aggregate.get('operator_stage')!r} QC, not {stage.value!r}")

    if (
        stage is QCStage.KEYFRAME
        and aggregate.get("operator_action") == "qc_retry_authorization"
        and not qc_passed_retry
    ):
        return _schedule_keyframe_recovery(
            conn,
            workflow_id,
            aggregate,
            version,
            authorization,
            qc_attempt_max_cost_usd=qc_attempt_max_cost_usd,
        )

    if stage is QCStage.IMAGE:
        target = ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK
        gate = ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value
        artifact = aggregate.get("resource_pack") or aggregate.get("latest_artifact")
    elif stage is QCStage.KEYFRAME:
        target = ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL
        gate = ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value
        artifact = aggregate.get("storyboard") or aggregate.get("latest_artifact")
    else:
        target = ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL
        gate = ProductVideoWorkflowState.AWAITING_FINAL_APPROVAL.value
        artifact = aggregate.get("render_result") or aggregate.get("latest_artifact")
    if not isinstance(artifact, dict):
        raise ValueError("Waiting workflow is missing its persisted stage artifact")

    artifact_id = str(
        artifact.get("artifact_id")
        or artifact.get("resource_pack_id")
        or artifact.get("storyboard_id")
        or artifact.get("render_id")
        or artifact.get("id")
        or ""
    )
    if not artifact_id:
        raise ValueError("Persisted stage artifact is missing an identifier")

    next_state = transition(ProductVideoWorkflowState.WAITING_FOR_OPERATOR, target)
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = next_state.value
    next_aggregate["qc_authorization"] = authorization
    next_aggregate.pop("operator_action", None)
    next_aggregate.pop("operator_stage", None)
    next_aggregate.pop("operator_reason", None)
    next_aggregate.pop("operator_qc_report_id", None)

    approval_svc = ApprovalService(conn)
    with conn:
        cursor = conn.cursor()
        approval_id = approval_svc.submit_request(
            {
                "workflow_id": workflow_id,
                "project_id": aggregate.get("project_id"),
                "gate": gate,
                "workflow_version": version + 1,
                "artifact_ref": artifact,
                "artifact_id": artifact_id,
                "artifact_version": artifact.get("version") or artifact.get("resource_pack_version"),
                "owner_user_id": aggregate.get("owner_user_id"),
                "qc_stage": stage.value,
            },
            cursor=cursor,
        )
        next_aggregate["pending_approval_gate"] = gate
        next_aggregate["pending_approval_id"] = approval_id
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(next_aggregate),
            events=[
                {
                    "event_id": f"evt_qc_advanced_{workflow_id}_v{version + 1}",
                    "command_id": f"cmd_qc_advance_{workflow_id}_{stage.value}_v{version + 1}",
                    "event_type": "QCCompletedAwaitingHumanApproval",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": {"stage": stage.value, "artifact_id": artifact_id},
                }
            ],
            expected_version=version,
        )
    return approval_id


def _record_failed_keyframe_qc(
    conn: Any,
    workflow_id: str,
    report: Any,
) -> None:
    """Persist a real failed QC result so the existing recovery path can resume."""
    repo = WorkflowRepository(conn)
    workflow = repo.get_workflow(workflow_id)
    if workflow is None:
        raise ValueError(f"Workflow '{workflow_id}' was not found")
    aggregate, version = workflow
    if (aggregate.get("state"), aggregate.get("operator_action"), aggregate.get("operator_stage")) != (
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value,
        "qc_authorization",
        QCStage.KEYFRAME.value,
    ):
        raise ValueError("Workflow is not waiting for keyframe QC authorization")
    storyboard = aggregate.get("storyboard") or aggregate.get("latest_artifact")
    if not isinstance(storyboard, dict) or report.artifact_digest != storyboard.get("package_digest"):
        raise ValueError("QC report does not match the current storyboard")
    recovery_plan = report.findings.get("recovery_plan") if isinstance(report.findings, dict) else None
    if not isinstance(recovery_plan, dict) or not recovery_plan.get("frames"):
        raise ValueError("Failed keyframe QC has no actionable recovery plan")
    updated = dict(aggregate)
    updated["operator_action"] = "qc_retry_authorization"
    updated["operator_qc_report_id"] = report.report_id
    updated["keyframe_recovery_plan"] = recovery_plan
    updated["operator_reason"] = "Keyframe QC failed; regenerate only the failed frames"
    with conn:
        repo.commit_workflow(
            workflow_id=workflow_id,
            aggregate_json=json.dumps(updated),
            events=[{
                "event_id": f"evt_keyframe_qc_failed_{workflow_id}_v{version + 1}",
                "command_id": f"cmd_keyframe_qc_failed_{workflow_id}_v{version + 1}",
                "event_type": "KeyframeQCRecoveryRequired",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {"report_id": report.report_id, "failed_frames": len(recovery_plan["frames"])},
            }],
            expected_version=version,
        )


def _schedule_keyframe_recovery(
    conn: Any,
    workflow_id: str,
    aggregate: dict[str, Any],
    version: int,
    authorization: dict[str, Any],
    *,
    qc_attempt_max_cost_usd: float | None = None,
) -> str:
    """Regenerate failed keyframes before spending on another QC evaluation."""

    scene_plan = aggregate.get("scene_plan")
    storyboard = aggregate.get("storyboard") or aggregate.get("latest_artifact")
    recovery_plan = aggregate.get("keyframe_recovery_plan")
    if not isinstance(scene_plan, dict):
        raise ValueError("Keyframe recovery requires the persisted approved scene plan")
    if not isinstance(storyboard, dict):
        raise ValueError("Keyframe recovery requires the previous storyboard package")
    if not isinstance(recovery_plan, dict) or not recovery_plan.get("frames"):
        raise ValueError("Keyframe recovery requires a persisted recovery plan")

    # An END generated from START must be regenerated when that START changes.
    frames = [dict(item) for item in recovery_plan["frames"] if isinstance(item, dict)]
    selected = {str(item.get("frame_id") or "") for item in frames}
    prior_ids = {
        str(item.get("frame_id") or "") for item in storyboard.get("generated_keyframes", [])
        if isinstance(item, dict)
    }
    for item in list(frames):
        frame_id = str(item.get("frame_id") or "")
        if not frame_id.endswith("-start"):
            continue
        end_id = frame_id.removesuffix("-start") + "-end"
        if end_id in prior_ids and end_id not in selected:
            frames.append({
                "frame_id": end_id,
                "scene_id": frame_id.removesuffix("-start"),
                "actions": ["regenerate_keyframe"],
                "feedback": "Regenerate END against the corrected START frame; preserve exact setting and intended end state.",
            })
            selected.add(end_id)
    recovery_plan = {**recovery_plan, "frames": frames}

    attempt = int(aggregate.get("keyframe_recovery_attempt", 0) or 0) + 1
    next_state = transition(
        ProductVideoWorkflowState.WAITING_FOR_OPERATOR,
        ProductVideoWorkflowState.CREATING_STORYBOARD,
    )
    next_aggregate = dict(aggregate)
    next_aggregate["state"] = next_state.value
    next_aggregate["qc_authorization"] = authorization
    next_aggregate["qc_max_cost_usd"] = (
        qc_attempt_max_cost_usd
        if qc_attempt_max_cost_usd is not None
        else aggregate.get("qc_max_cost_usd")
    )
    next_aggregate["keyframe_recovery_attempt"] = attempt
    next_aggregate["keyframe_recovery_plan"] = recovery_plan
    for key in (
        "operator_action",
        "operator_stage",
        "operator_reason",
        "operator_qc_report_id",
        "pending_approval_gate",
        "pending_approval_id",
    ):
        next_aggregate.pop(key, None)

    envelope = build_envelope(
        workflow_id=workflow_id,
        topic="job.dispatch",
        idempotency_key=f"idemp_storyboard_recovery_{workflow_id}_a{attempt}_v{version + 1}",
        payload={
            "job_name": "product_video.storyboard",
            "workflow_id": workflow_id,
            "args": [scene_plan],
            "kwargs": {
                "project_id": aggregate.get("project_id"),
                "qc_authorization": authorization,
                "qc_max_cost_usd": authorization.get("max_cost_usd"),
                "recovery_plan": recovery_plan,
                "recovery_attempt": attempt,
                "previous_storyboard": storyboard,
            },
            "owner_user_id": aggregate.get("owner_user_id", "local-owner"),
            "project_id": aggregate.get("project_id"),
        },
    )
    WorkflowRepository(conn).commit_workflow(
        workflow_id=workflow_id,
        aggregate_json=json.dumps(next_aggregate),
        events=[
            {
                "event_id": f"evt_keyframe_recovery_{workflow_id}_a{attempt}",
                "command_id": f"cmd_keyframe_recovery_{workflow_id}_a{attempt}",
                "event_type": "KeyframeRecoveryScheduled",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": {
                    "attempt": attempt,
                    "failed_frames": len(recovery_plan.get("frames", [])),
                },
            }
        ],
        expected_version=version,
        outbox_message=envelope,
    )
    return "recovery:" + str(json.loads(envelope)["message_id"])


def cmd_list(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        inbox_root = getattr(args, "inbox_root", None)
        source_root = getattr(args, "legacy_source_root", None) or getattr(args, "source_root", None)
        service = DailyCandidateService(conn, source_root=source_root, inbox_root=inbox_root, db_path=db_path)
        target_date = date.fromisoformat(args.date) if args.date else None
        try:
            candidates = service.get_candidates(target_date)
        except FileNotFoundError as exc:
            print(f"[LỖI EXCHANGE INBOX] {exc}", file=sys.stderr)
            return 1

        if args.status and args.status != "all":
            candidates = [c for c in candidates if c.status == args.status]

        if args.json:
            print(json.dumps([c.to_dict() for c in candidates], ensure_ascii=False, indent=2))
            return 0

        source_date = candidates[0].source_date if candidates else (args.date or "N/A")
        print(f"\n=== DANH SÁCH SẢN PHẨM PRODUCT-INTELLIGENCE ({source_date}) ===")
        print(f"Tổng số: {len(candidates)} sản phẩm | Database: {db_path}\n")

        for idx, c in enumerate(candidates, start=1):
            badge = _format_status_badge(c.status)
            print(f"[{idx:02d}] {badge} {c.name}")
            print(f"     Brand: {c.brand} | Model: {c.model} | Giá: {c.price_display}")
            print(f"     Số ảnh hợp lệ: {len(c.images)} | Key: {c.product_key[:12]}...")
            if c.status == "awaiting_product_lock":
                print(f"     -> Chờ duyệt tại Gate: {c.gate} | Approval ID: {c.approval_id} | WF: {c.workflow_id}")
            elif c.status == "in_production":
                print(f"     -> Đang sản xuất tại WF: {c.workflow_id}")
            elif c.status == "invalid":
                print(f"     -> Lý do loại: {c.rejection_reason}")
            elif c.hot_reason:
                print(f"     Hot: {c.hot_reason[:90]}...")
            print()

        return 0
    finally:
        conn.close()


def cmd_start(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        inbox_root = getattr(args, "inbox_root", None)
        source_root = getattr(args, "legacy_source_root", None) or getattr(args, "source_root", None)
        service = DailyCandidateService(conn, source_root=source_root, inbox_root=inbox_root, db_path=db_path)
        minimum_daily = int(getattr(args, "minimum_daily", 0) or 0)
        if minimum_daily < 0 or minimum_daily > args.limit:
            print("[ERROR] --minimum-daily phải nằm từ 0 đến --limit.", file=sys.stderr)
            return 1
        target_date = (
            date.today() if args.date == "today" or (minimum_daily and not args.date)
            else date.fromisoformat(args.date) if args.date else None
        )
        qc_authorization = _qc_authorization_from_args(args)
        qc_max_cost_usd = getattr(args, "qc_max_cost_usd", None)
        research_snapshot_id = getattr(args, "research_snapshot_id", None)

        try:
            if args.auto:
                print(f"[*] Bắt đầu tìm kiếm tự động sản phẩm chưa tạo video (Giới hạn: {args.limit})...")
                batch_res = service.start_auto(
                    limit=args.limit,
                    owner_user_id=args.owner_user_id,
                    target_date=target_date,
                    qc_authorization=qc_authorization,
                    qc_max_cost_usd=qc_max_cost_usd,
                    research_snapshot_id=research_snapshot_id,
                )
            elif args.product_keys:
                print(f"[*] Bắt đầu tạo video cho {len(args.product_keys)} sản phẩm theo khóa chỉ định...")
                batch_res = service.start_selection(
                    args.product_keys,
                    owner_user_id=args.owner_user_id,
                    target_date=target_date,
                    qc_authorization=qc_authorization,
                    qc_max_cost_usd=qc_max_cost_usd,
                    research_snapshot_id=research_snapshot_id,
                )
            else:
                print("[ERROR] Cần cung cấp --auto hoặc danh sách --product-keys. Hoặc dùng lệnh 'select' để chọn trực quan.")
                return 1
        except FileNotFoundError as exc:
            print(f"[LỖI EXCHANGE INBOX] {exc}", file=sys.stderr)
            return 1
        except ValueError as exc:
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 1

        if batch_res.has_errors:
            for s in batch_res.skipped:
                if s.reason.startswith(("CLAIM_ERROR", "START_FAILED", "ERROR")):
                    print(f"[LỖI KHỞI ĐỘNG] Sản phẩm {s.product_key}: {s.reason}", file=sys.stderr)
            return 1

        def report_daily_shortfall() -> bool:
            if not minimum_daily or target_date is None:
                return False
            rows = DailyImportRepository(conn).get_all_for_date(target_date.isoformat())
            daily_total = sum(row["status"] == "started" for row in rows.values())
            if daily_total < minimum_daily:
                print(
                    f"[THIẾU SẢN PHẨM] {target_date}: đã khởi động {daily_total}/{minimum_daily} "
                    "workflow từ Product-Intelligence; kiểm tra batch READY và sản phẩm hợp lệ.",
                    file=sys.stderr,
                )
                for candidate in service.get_candidates(target_date):
                    if candidate.status == "invalid":
                        print(
                            f"  - {candidate.name}: {candidate.rejection_reason or 'không hợp lệ'}",
                            file=sys.stderr,
                        )
                return True
            print(f"[MỤC TIÊU NGÀY] {target_date}: đã khởi động {daily_total} workflow.")
            return False

        started_wfs = [s.workflow_id for s in batch_res.started]
        research_wfs = list(started_wfs)
        if args.with_research and target_date is not None:
            workflow_repo = WorkflowRepository(conn)
            for row in DailyImportRepository(conn).get_all_for_date(target_date.isoformat()).values():
                if row["status"] != "started":
                    continue
                wf_id = row["workflow_id"]
                workflow = workflow_repo.get_workflow(wf_id)
                if workflow and workflow[0].get("state") in {
                    ProductVideoWorkflowState.RESEARCHING.value,
                    ProductVideoWorkflowState.BUILDING_RESOURCE_PACK.value,
                } and wf_id not in research_wfs:
                    research_wfs.append(wf_id)

        if not started_wfs and not research_wfs:
            if report_daily_shortfall():
                return 1
            benign = all(s.reason in ("ALREADY_STARTED", "ALREADY_CLAIMED") for s in batch_res.skipped)
            if (benign and batch_res.skipped) or (getattr(args, "auto", False) and not batch_res.skipped):
                print("[THÔNG BÁO] Không có sản phẩm mới nào cần khởi động (Tất cả sản phẩm đã được xử lý hoặc có video).")
                return 0
            print("[THÔNG BÁO] Không có sản phẩm mới nào được khởi động.", file=sys.stderr)
            return 1

        if started_wfs:
            print(f"[THÀNH CÔNG] Đã tạo {len(started_wfs)} workflow mới:")
            for wf_id in started_wfs:
                print(f"  + {wf_id}")
        elif research_wfs:
            print(f"[*] Tiếp tục {len(research_wfs)} workflow đã bắt đầu nhưng chưa tới Product Lock.")

        if args.with_research and research_wfs:
            print("\n[*] Đang chạy Research MCP tự động để chuẩn bị Product Lock...")
            if service._coordinator is not None:
                adv = service._coordinator.advance_to_product_lock(
                    workflow_ids=research_wfs,
                    provider_mode=args.provider_mode,
                )
                if not adv.get("succeeded"):
                    print(f"[LỖI ADVANCE TO PRODUCT LOCK] {adv.get('error')}", file=sys.stderr)
                    for wf_id, details in adv.get("workflows", {}).items():
                        print(f"  - {wf_id}: {details}", file=sys.stderr)
                    return 1
            else:
                report = run_worker(
                    db_path=db_path,
                    provider_mode=args.provider_mode,
                    once=True,
                    batch_size=len(research_wfs) * 2,
                    workflow_ids=research_wfs,
                )
                if not report or report.failed > 0:
                    print(f"[LỖI RESEARCH] {report.failed if report else 'Unknown'} lỗi xảy ra khi chạy research.", file=sys.stderr)
                    return 1
            print("[HOÀN TẤT] Các sản phẩm đã sẵn sàng tại cổng 'AwaitingProductLock' để bạn duyệt.")

        return 1 if report_daily_shortfall() else 0
    finally:
        conn.close()


def cmd_select(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        inbox_root = getattr(args, "inbox_root", None)
        source_root = getattr(args, "legacy_source_root", None) or getattr(args, "source_root", None)
        service = DailyCandidateService(conn, source_root=source_root, inbox_root=inbox_root, db_path=db_path)
        target_date = date.fromisoformat(args.date) if args.date else None
        try:
            candidates = service.get_candidates(target_date)
        except FileNotFoundError as exc:
            print(f"[LỖI EXCHANGE INBOX] {exc}", file=sys.stderr)
            return 1

        source_date = candidates[0].source_date if candidates else (args.date or "N/A")
        print(f"\n=== CHỌN SẢN PHẨM TẠO VIDEO ({source_date}) ===")
        print("Danh sách sản phẩm từ Product-Intelligence:\n")

        valid_indices: dict[int, CandidateItem] = {}
        for idx, c in enumerate(candidates, start=1):
            badge = _format_status_badge(c.status)
            prefix = f"[{idx:02d}]"
            print(f"{prefix} {badge} {c.name}")
            print(f"     Brand: {c.brand} | Model: {c.model} | Giá: {c.price_display}")
            if c.status == "unprocessed":
                valid_indices[idx] = c
                print("     >>> [HỢP LỆ ĐỂ TẠO VIDEO]")
            elif c.status == "awaiting_product_lock":
                print(f"     -> Đã research, đang chờ duyệt Product Lock (ID: {c.approval_id})")
            elif c.status == "invalid":
                print(f"     -> Không chọn được: {c.rejection_reason}")
            print()

        if not valid_indices:
            print("[THÔNG BÁO] Không còn sản phẩm mới nào ở trạng thái hợp lệ để bắt đầu.")
            return 0

        prompt = f"Nhập số thứ tự các sản phẩm muốn tạo video (1-{len(candidates)}, phân cách bằng dấu cách): "
        sys.stdout.write(prompt)
        sys.stdout.flush()
        line = sys.stdin.readline().strip()
        if not line:
            print("[HỦY BỎ] Không chọn sản phẩm nào.")
            return 0

        selected_keys: list[str] = []
        for part in line.replace(",", " ").split():
            try:
                val = int(part)
                if val in valid_indices:
                    selected_keys.append(valid_indices[val].product_key)
                else:
                    print(f"[BỎ QUA] Mục [{val}] không hợp lệ hoặc đã có video.")
            except ValueError:
                pass

        if not selected_keys:
            print("[HỦY BỎ] Không có lựa chọn hợp lệ nào.")
            return 0

        print(f"\n[*] Đang khởi động {len(selected_keys)} sản phẩm được chọn...")
        started = service.start_selection(
            selected_keys,
            owner_user_id=args.owner_user_id,
            target_date=target_date,
            qc_authorization=_qc_authorization_from_args(args),
            qc_max_cost_usd=getattr(args, "qc_max_cost_usd", None),
            research_snapshot_id=getattr(args, "research_snapshot_id", None),
        )
        print(f"[THÀNH CÔNG] Đã tạo workflow: {', '.join(started)}")

        if args.with_research:
            print("\n[*] Đang chạy Research MCP tự động để chuẩn bị Product Lock...")
            run_worker(
                db_path=db_path,
                provider_mode=args.provider_mode,
                once=True,
                batch_size=len(started) + 2,
                workflow_id_prefix="pv-daily-",
            )
            print("[HOÀN TẤT] Các sản phẩm đã sẵn sàng tại cổng 'AwaitingProductLock'. Dùng lệnh 'approve' để duyệt.")

        return 0
    finally:
        conn.close()


def _read_export_caption(artifact: dict[str, Any]) -> str | None:
    """Read the canonical export caption; status must never synthesize another one."""
    caption_path = artifact.get("caption_path")
    if not caption_path and "payload" in artifact:
        payload = artifact["payload"]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        if isinstance(payload, dict):
            caption_path = payload.get("caption_path")
    if not caption_path:
        return None
    path = _normalize_file_path(caption_path)
    if not path.is_file():
        return None
    content = path.read_text(encoding="utf-8").strip()
    return content or None


def cmd_approve(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        repo = WorkflowRepository(conn)
        approval_svc = ApprovalService(conn)

        # 1. Resolve target: could be approval request ID or workflow ID
        target_id = args.target_id
        is_approval_req = False
        try:
            req = approval_svc.get_request(target_id)
            is_approval_req = True
        except KeyError:
            is_approval_req = False

        if is_approval_req:
            wf_id = req.payload.get("workflow_id") or target_id
            gate_name = req.payload.get("gate") or ""
        else:
            wf_id = target_id
            wf_data = repo.get_workflow(wf_id)
            if not wf_data:
                print(f"[LỖI] Không tìm thấy workflow hoặc approval request '{target_id}'", file=sys.stderr)
                return 1
            agg, _ = wf_data
            gate_name = agg.get("pending_approval_gate") or ""

        # 2. Gate 4 Paid Render Cost Guard
        if gate_name == "AwaitingStoryboardApproval" or gate_name == ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value:
            if not getattr(args, "authorize_cost", False):
                print(
                    "\n[LỖI XÁC NHẬN CHI PHÍ] Cổng phê duyệt Storyboard (Gate 4) sẽ kích hoạt quá trình render video có trả phí (GPU/Vertex AI).\n"
                    "Bắt buộc phải có sự đồng ý của operator.\n"
                    "Vui lòng chạy lại lệnh với cờ '--authorize-cost' để xác nhận ủy quyền chi phí.",
                    file=sys.stderr,
                )
                return 1

        print(f"[*] Đang phê duyệt và kích hoạt bước tiếp theo cho: {target_id} (Cổng: {gate_name or 'N/A'})...")
        approval_payload: dict[str, Any] = {}
        qc_authorization = _qc_authorization_from_args(args, workflow_id=wf_id)
        if qc_authorization:
            approval_payload["qc_authorization"] = qc_authorization
        if getattr(args, "qc_max_cost_usd", None) is not None:
            approval_payload["qc_max_cost_usd"] = args.qc_max_cost_usd
        if getattr(args, "render_provider", None):
            approval_payload["render_provider_kind"] = args.render_provider
        result = approve_and_advance_workflow(
            connection=conn,
            target_id=target_id,
            owner_user_id=args.owner_user_id,
            payload=approval_payload,
        )
        print("\n[PHÊ DUYỆT THÀNH CÔNG]")
        print(f"  - Request ID:   {result.get('request_id')}")
        print(f"  - Workflow ID:  {result.get('workflow_id')}")
        print(f"  - Trạng thái:   {result.get('new_state')}")
        print(f"  - Tác vụ kế:    {result.get('enqueued_job')} (Đã enqueue vào Outbox)")

        # 3. Process workflow through worker cycles until next HITL gate or COMPLETED
        print(f"\n[*] Đang tiến hành xử lý workflow {wf_id}...")
        max_cycles = 25
        cycle = 0

        while cycle < max_cycles:
            cycle += 1
            wf_data = repo.get_workflow(wf_id)
            if not wf_data:
                break
            agg, ver = wf_data
            curr_state = agg.get("state", "")

            # If in HITL waiting state or completed, stop
            if curr_state in [s.value for s in HITL_WAITING_STATES] or curr_state == ProductVideoWorkflowState.COMPLETED.value:
                break

            # Run worker turn targeting this workflow
            report = run_worker(
                db_path=db_path,
                provider_mode=getattr(args, "provider_mode", "configured"),
                once=True,
                batch_size=2,
                workflow_ids=[wf_id],
            )

            if report and report.failed > 0:
                print(f"[LỖI XỬ LÝ] Worker ghi nhận {report.failed} tác vụ thất bại khi xử lý workflow {wf_id}.", file=sys.stderr)
                cur = conn.cursor()
                cur.execute(
                    "SELECT message, last_error FROM workflow_outbox WHERE workflow_id = ? AND last_error IS NOT NULL ORDER BY outbox_id DESC LIMIT 5",
                    (wf_id,),
                )
                for msg_json, last_err in cur.fetchall():
                    try:
                        parsed = json.loads(msg_json)
                        job_name = parsed.get("payload", {}).get("job_name", "unknown")
                    except Exception:
                        job_name = "unknown"
                    print(f"  -> Chi tiết lỗi ({job_name}): {last_err}", file=sys.stderr)
                return 1

        # Re-fetch latest aggregate
        wf_data = repo.get_workflow(wf_id)
        if not wf_data:
            print(f"[LỖI] Không tìm thấy dữ liệu workflow {wf_id} sau khi xử lý.", file=sys.stderr)
            return 1

        agg, ver = wf_data
        final_state = agg.get("state", "")

        if final_state == ProductVideoWorkflowState.COMPLETED.value:
            latest_art = dict(agg.get("latest_artifact") or {})
            if "payload" in latest_art:
                payload = latest_art["payload"]
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {}
                if isinstance(payload, dict):
                    for k in ("caption_path", "metadata_path", "file_path", "final_video_url", "video_url"):
                        if k in payload and not latest_art.get(k):
                            latest_art[k] = payload[k]
            video_url = latest_art.get("final_video_url") or latest_art.get("video_url") or ""
            video_file = latest_art.get("file_path") or video_url
            video_path = _normalize_file_path(video_file) if video_file else None

            print("\n" + "=" * 64)
            print("🎉 [XUẤT BẢN THÀNH CÔNG] VIDEO ĐÃ HOÀN TẤT VÀ SẴN SÀNG ĐĂNG TẢI")
            print("=" * 64)
            print(f"  - Workflow ID:  {wf_id}")
            print(f"  - Trạng thái:   {final_state}")
            if video_path and video_path.is_file():
                print(f"  - File MP4:       {video_path.resolve()}")
                print(f"  - Kích thước:     {video_path.stat().st_size:,} bytes")
            else:
                print(f"  - URL Video:      {video_url}")

            caption_file = latest_art.get("caption_path")
            meta_file = latest_art.get("metadata_path")
            if caption_file:
                print(f"  - File Caption:   {caption_file}")
            if meta_file:
                print(f"  - File Metadata:  {meta_file}")

            print("\n--- TIKTOK CAPTION & HASHTAGS GỢI Ý (ĐÃ XÁC THỰC) ---")
            caption = _read_export_caption(latest_art)
            print(caption or "Chưa có caption export chính thức.")
            print("-----------------------------------------------------")
            print("=" * 64 + "\n")
            return 0

        elif final_state in [s.value for s in HITL_WAITING_STATES]:
            next_gate = agg.get("pending_approval_gate")
            next_appr_id = agg.get("pending_approval_id")
            art = agg.get("latest_artifact")
            art_id = "N/A"
            if isinstance(art, dict):
                art_id = (
                    art.get("artifact_id")
                    or art.get("brief_id")
                    or art.get("scene_plan_id")
                    or art.get("storyboard_id")
                    or art.get("render_id")
                    or art.get("resource_pack_id")
                    or "N/A"
                )
            print(f"\n[DỪNG TẠI CỔNG DUYỆT TIẾP THEO]")
            print(f"  - Workflow ID:  {wf_id}")
            print(f"  - Trạng thái:   {final_state}")
            print(f"  - Cổng chờ:     {next_gate}")
            print(f"  - Approval ID:  {next_appr_id}")
            print(f"  - Artifact ID:  {art_id}")
            print(f"\nOperator kiểm tra: hermes personal video status {wf_id}")
            cost_hint = " --authorize-cost" if next_gate == "AwaitingStoryboardApproval" else ""
            print(f"Để duyệt tiếp:     hermes personal video approve {next_appr_id}{cost_hint}\n")
            return 0
        else:
            print(f"\n[THÔNG BÁO] Workflow {wf_id} đang ở trạng thái: {final_state}")
            return 0

    except Exception as exc:  # noqa: BLE001
        print(f"\n[LỖI PHÊ DUYỆT] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def cmd_status(args: argparse.Namespace) -> int:
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        repo = WorkflowRepository(conn)
        wf_data = repo.get_workflow(args.workflow_id)
        if wf_data is None:
            print(f"[LỖI] Không tìm thấy workflow '{args.workflow_id}'", file=sys.stderr)
            return 1
        agg, version = wf_data
        print(f"\n=== CHI TIẾT TRẠNG THÁI WORKFLOW: {args.workflow_id} ===")
        print(f"Version:            {version}")
        print(f"Trạng thái:         {agg.get('state')}")
        blocked_error = _quarantined_job_error(conn, args.workflow_id, str(agg.get("state") or ""))
        if blocked_error:
            print(f"Worker bị chặn:     {blocked_error}")
        print(f"Gate chờ:           {agg.get('pending_approval_gate') or 'Không'}")
        print(f"Approval ID:        {agg.get('pending_approval_id') or 'Không'}")
        if agg.get("state") == ProductVideoWorkflowState.WAITING_FOR_OPERATOR.value:
            print(f"Operator action:    {agg.get('operator_action') or 'Không'}")
            print(f"QC stage:           {agg.get('operator_stage') or 'N/A'}")
            print(f"Reason:             {agg.get('operator_reason') or 'N/A'}")
            recovery_plan = agg.get("keyframe_recovery_plan")
            if isinstance(recovery_plan, dict):
                frames = recovery_plan.get("frames") or []
                print(f"Recovery frames:    {len(frames)}")
                for frame in frames:
                    if isinstance(frame, dict):
                        actions = ", ".join(str(item) for item in frame.get("actions", []))
                        print(
                            f"  {frame.get('frame_id') or frame.get('scene_id')}: "
                            f"{actions} - {frame.get('feedback') or 'N/A'}"
                        )

        src = agg.get("source_context", {})
        if src:
            print(f"Sản phẩm:           {src.get('brand')} {src.get('model')} - {src.get('name')}")
            print(f"Giá niêm yết:       {src.get('price_display')}")
            imgs = src.get("images") or []
            print(f"Số lượng ảnh gốc:   {len(imgs)}")

        rp = agg.get("resource_pack") or {}
        if not rp and isinstance(agg.get("latest_artifact"), dict) and agg["latest_artifact"].get("schema") == "resource_pack":
            rp = agg["latest_artifact"]
        if rp:
            rp_id = rp.get("resource_pack_id") or rp.get("id") or "N/A"
            rp_st = rp.get("status") or "N/A"
            rp_digest = rp.get("digest") or rp.get("source_digest") or "N/A"
            print(f"Resource Pack ID:   {rp_id}")
            print(f"Pack Status:        {rp_st}")
            print(f"Pack Digest:        {rp_digest[:16]}..." if len(rp_digest) > 16 else f"Pack Digest:        {rp_digest}")

        art = agg.get("latest_artifact")
        if isinstance(art, dict):
            art_id = (
                art.get("artifact_id")
                or art.get("brief_id")
                or art.get("scene_plan_id")
                or art.get("storyboard_id")
                or art.get("render_id")
                or art.get("export_id")
                or art.get("resource_pack_id")
                or "N/A"
            )
            print(f"Artifact mới nhất:  {art.get('schema')} (ID: {art_id}, v{art.get('version', 1)})")

        qc_repo = QCReportRepository(conn)
        image_artifact = agg.get("resource_pack") or {}
        image_report = qc_repo.get_latest_report(
            args.workflow_id,
            QCStage.IMAGE,
            expected_artifact_digest=compute_artifact_digest(image_artifact) if image_artifact else None,
        )
        print(f"Image QC:           {image_report.verdict.value if image_report else 'pending/stale'}"
              f" ({image_report.report_id if image_report else 'N/A'})")
        if image_report and image_report.verdict.value == "fail":
            print("Cần xử lý:          Chọn hoặc nghiên cứu lại ảnh sản phẩm trước khi duyệt Product Lock")
        video_value = (art or {}).get("file_path") or (art or {}).get("final_video_url") or (art or {}).get("video_url")
        video_path = _normalize_file_path(video_value) if video_value else None
        video_report = qc_repo.get_latest_report(
            args.workflow_id,
            QCStage.VIDEO,
            expected_artifact_digest=compute_file_sha256(video_path) if video_path else None,
        )
        print(f"Video QC:           {video_report.verdict.value if video_report else 'pending/stale'}"
              f" ({video_report.report_id if video_report else 'N/A'})")

        if agg.get("state") == ProductVideoWorkflowState.COMPLETED.value:
            latest_art = agg.get("latest_artifact") or {}
            video_url = latest_art.get("final_video_url") or latest_art.get("video_url") or ""
            video_file = latest_art.get("file_path") or video_url
            video_path = _normalize_file_path(video_file) if video_file else None
            print("\n--- THÔNG TIN VIDEO HOÀN THÀNH ---")
            if video_path and video_path.is_file():
                print(f"Đường dẫn file:     {video_path.resolve()}")
                print(f"Kích thước file:    {video_path.stat().st_size:,} bytes")
            else:
                print(f"Đường dẫn file/URL: {video_url}")
            print("\n--- TIKTOK CAPTION GỢI Ý ---")
            caption = _read_export_caption(latest_art)
            print(caption or "Chưa có caption export chính thức.")

        print()
        return 0
    finally:
        conn.close()


def cmd_daily_status(args: argparse.Namespace) -> int:
    """Report actual completed exports for one Product-Intelligence day."""
    target_date = date.today() if args.date == "today" else date.fromisoformat(args.date)
    minimum = int(args.minimum)
    if minimum < 0 or minimum > 5:
        print("[ERROR] --minimum phải nằm từ 0 đến 5.", file=sys.stderr)
        return 1

    conn = connect(_resolve_db_path(args.db_path))
    try:
        rows = DailyImportRepository(conn).get_all_for_date(target_date.isoformat())
        repo = WorkflowRepository(conn)
        workflows: list[dict[str, str]] = []
        completed = 0
        for row in rows.values():
            if row["status"] != "started":
                continue
            wf_id = str(row["workflow_id"])
            wf_data = repo.get_workflow(wf_id)
            state = str(wf_data[0].get("state") or "") if wf_data else "missing"
            completed += state == ProductVideoWorkflowState.COMPLETED.value
            item = {"workflow_id": wf_id, "state": state}
            blocked_error = _quarantined_job_error(conn, wf_id, state)
            if blocked_error:
                item["blocking_error"] = blocked_error
            workflows.append(item)
        result = {
            "date": target_date.isoformat(),
            "started": len(workflows),
            "completed": completed,
            "minimum": minimum,
            "workflows": workflows,
            "ok": completed >= minimum,
        }
        if args.json:
            print(json.dumps(result, ensure_ascii=False))
        else:
            print(f"[VIDEO NGÀY] {target_date}: hoàn thành {completed}/{minimum}, đã bắt đầu {len(workflows)} workflow.")
            for item in workflows:
                print(f"  - {item['workflow_id']}: {item['state']}")
                if item.get("blocking_error"):
                    print(f"    Worker bị chặn: {item['blocking_error']}")
            if not result["ok"]:
                print("[THIẾU VIDEO] Chưa đạt mục tiêu best effort; xem trạng thái workflow và log provider/QC.", file=sys.stderr)
        return 0 if result["ok"] else 1
    finally:
        conn.close()


def cmd_qc(args: argparse.Namespace) -> int:
    """Run the governed QC producer without changing any HITL approval state."""
    db_path = _resolve_db_path(args.db_path)
    conn = connect(db_path)
    try:
        requested_stage = QCStage(args.stage)
        technical_keyframe_retry = False
        if args.advance and args.provider_mode == "configured":
            waiting = WorkflowRepository(conn).get_workflow(args.workflow_id)
            if waiting is not None:
                waiting_aggregate, _ = waiting
                if (
                    requested_stage is QCStage.KEYFRAME
                    and waiting_aggregate.get("operator_action")
                    == "qc_retry_authorization"
                ):
                    previous_id = waiting_aggregate.get("operator_qc_report_id")
                    previous = QCReportRepository(conn).get_report(str(previous_id)) if previous_id else None
                    items = previous.findings.get("items", []) if previous and isinstance(previous.findings, dict) else []
                    technical_keyframe_retry = bool(items) and all(
                        isinstance(item, dict)
                        and item.get("verdict") == "unknown"
                        and item.get("findings", {}).get("finish_reason") == "length"
                        for item in items
                    )
                if (
                    requested_stage is QCStage.KEYFRAME
                    and waiting_aggregate.get("operator_action") == "qc_retry_authorization"
                    and not technical_keyframe_retry
                ):
                    authorization = _qc_authorization_from_args(
                        args, workflow_id=args.workflow_id
                    )
                    if not args.authorize_cost or authorization is None:
                        print(
                            "[LỖI QC] Keyframe recovery cần --authorize-cost và authorization đầy đủ.",
                            file=sys.stderr,
                        )
                        return 1
                    recovery_id = _advance_qc_waiting_workflow(
                        conn,
                        args.workflow_id,
                        requested_stage,
                        authorization,
                        qc_attempt_max_cost_usd=args.max_cost_usd,
                    )
                    print(f"Keyframe recovery:  {recovery_id}")
                    return 0
        service = ProductVideoQCService(conn)
        result = service.run(
            args.workflow_id,
            requested_stage,
            provider_mode=args.provider_mode,
            authorize_cost=args.authorize_cost,
            max_cost_usd=args.max_cost_usd,
            authorization=(
                {
                    "workflow_id": args.workflow_id,
                    "run_id": args.authorization_run_id,
                    "scope": args.authorization_scope,
                    "expires_at": args.authorization_expires_at,
                    "max_cost_usd": args.authorization_max_cost_usd or args.max_cost_usd,
                    "campaign_id": args.authorization_campaign_id,
                }
                if args.authorization_run_id or args.authorization_expires_at or args.authorization_scope
                else None
            ),
        )
        print(f"QC stage:           {result['stage']}")
        print(f"QC status:           {result['status']}")
        print(f"QC report ID:        {result.get('report_id') or 'N/A'}")
        print(f"Reason:              {result.get('reason') or 'completed'}")
        if result.get("report") is not None:
            report = result["report"]
            print(f"Verdict:             {report.verdict.value}")
            print(f"Rubric score:        {report.score}")
        if result.get("eligible_count") is not None:
            print(f"Eligible references: {result['eligible_count']}")
        if args.advance:
            if args.provider_mode != "configured":
                print("[LỖI QC] --advance chỉ chấp nhận configured QC, không chấp nhận fake mode.", file=sys.stderr)
                return 1
            if result["status"] != "completed" or result.get("report") is None:
                print("[LỖI QC] Không thể advance khi QC chưa completed.", file=sys.stderr)
                return 1
            report = result["report"]
            verdict = getattr(getattr(report, "verdict", None), "value", None)
            if verdict != "pass":
                if requested_stage is QCStage.KEYFRAME and verdict == "fail":
                    _record_failed_keyframe_qc(conn, args.workflow_id, report)
                print("[LỖI QC] QC không PASS; không tạo human approval gate.", file=sys.stderr)
                return 1
            authorization = _qc_authorization_from_args(args, workflow_id=args.workflow_id)
            if not args.authorize_cost or authorization is None:
                print("[LỖI QC] --advance cần --authorize-cost và authorization đầy đủ.", file=sys.stderr)
                return 1
            approval_id = _advance_qc_waiting_workflow(
                conn,
                args.workflow_id,
                QCStage(args.stage),
                authorization,
                qc_passed_retry=technical_keyframe_retry,
            )
            print(f"Human approval ID:  {approval_id}")
        return 0 if result["status"] == "completed" else 1
    except Exception as exc:  # noqa: BLE001
        print(f"[LỖI QC] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def cmd_recover_keyframe(args: argparse.Namespace) -> int:
    """Resume a quarantined unknown keyframe after local reconciliation."""
    conn = connect(_resolve_db_path(args.db_path))
    try:
        authorization = _qc_authorization_from_args(args, workflow_id=args.workflow_id)
        result = recover_unknown_keyframe_submission(
            conn,
            workflow_id=args.workflow_id,
            owner_user_id=args.owner_user_id,
            authorization=authorization,
        )
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"[LỖI KEYFRAME RECOVERY] {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


def build_parser() -> argparse.ArgumentParser:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        prog="hermes personal video",
        description="Hermes Personal Video Factory - Quản lý, tuyển chọn và duyệt video sản phẩm hàng ngày",
    )
    parser.add_argument("--db-path", default=None, help="Đường dẫn file SQLite database")
    parser.add_argument("--inbox-root", type=Path, default=None, help="Thư mục exchange inbox chứa READY batches")
    parser.add_argument(
        "--legacy-source-root",
        dest="legacy_source_root",
        type=Path,
        default=None,
        help="[MIGRATION/DEBUG ONLY] Thư mục raw daily_runs của Product-Intelligence chứa products.json",
    )
    parser.add_argument("--source-root", dest="legacy_source_root", type=Path, default=None, help=argparse.SUPPRESS)

    subparsers = parser.add_subparsers(dest="subcommand", metavar="<lệnh>")

    # list
    p_list = subparsers.add_parser("list", help="Liệt kê danh sách sản phẩm scouted và trạng thái video")
    p_list.add_argument("--date", default=None, help="Ngày quét (YYYY-MM-DD), mặc định ngày mới nhất")
    p_list.add_argument("--status", choices=["all", "unprocessed", "awaiting_product_lock", "in_production", "completed", "invalid"], default="all")
    p_list.add_argument("--json", action="store_true", help="Xuất định dạng JSON")
    p_list.set_defaults(func=cmd_list)

    # start
    p_start = subparsers.add_parser("start", help="Khởi động workflow tạo video cho sản phẩm")
    p_start.add_argument("--auto", action="store_true", help="Tự động lấy các sản phẩm chưa tạo video")
    p_start.add_argument("--limit", type=int, default=5, help="Số lượng sản phẩm tối đa khi dùng --auto (mặc định: 5)")
    p_start.add_argument("--product-keys", nargs="+", help="Danh sách product_key cụ thể cần tạo video")
    p_start.add_argument("--date", default=None, help="Ngày quét YYYY-MM-DD hoặc today")
    p_start.add_argument("--minimum-daily", type=int, default=0, help="Báo lỗi nếu tổng workflow bắt đầu trong ngày thấp hơn mức này")
    p_start.add_argument("--owner-user-id", default="local-owner")
    p_start.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_start.add_argument("--qc-max-cost-usd", type=float, default=None, help="Hạn mức USD cho các lần QC của workflow")
    p_start.add_argument("--qc-authorization-run-id", default=None, help="Run ID trong cost authorization cho QC")
    p_start.add_argument("--qc-authorization-scope", action="append", default=[], help="Scope QC được cấp, lặp lại được")
    p_start.add_argument("--qc-authorization-expires-at", default=None, help="Thời điểm hết hạn ISO-8601 của QC authorization")
    p_start.add_argument("--qc-authorization-max-cost-usd", type=float, default=None, help="Hạn mức USD trong QC authorization")
    p_start.add_argument("--research-snapshot-id", default=None, help="Dùng snapshot PI đã lưu thay vì research lại")
    p_start.add_argument("--no-research", dest="with_research", action="store_false", help="Không tự động chạy worker research")
    p_start.set_defaults(with_research=True, func=cmd_start)

    # select
    p_select = subparsers.add_parser("select", help="Giao diện CLI trực quan để chọn sản phẩm tạo video")
    p_select.add_argument("--date", default=None, help="Ngày quét")
    p_select.add_argument("--owner-user-id", default="local-owner")
    p_select.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_select.add_argument("--qc-max-cost-usd", type=float, default=None, help="Hạn mức USD cho các lần QC của workflow")
    p_select.add_argument("--qc-authorization-run-id", default=None, help="Run ID trong cost authorization cho QC")
    p_select.add_argument("--qc-authorization-scope", action="append", default=[], help="Scope QC được cấp, lặp lại được")
    p_select.add_argument("--qc-authorization-expires-at", default=None, help="Thời điểm hết hạn ISO-8601 của QC authorization")
    p_select.add_argument("--qc-authorization-max-cost-usd", type=float, default=None, help="Hạn mức USD trong QC authorization")
    p_select.add_argument("--research-snapshot-id", default=None, help="Dùng snapshot PI đã lưu thay vì research lại")
    p_select.add_argument("--no-research", dest="with_research", action="store_false")
    p_select.set_defaults(with_research=True, func=cmd_select)

    # approve
    p_approve = subparsers.add_parser("approve", help="Phê duyệt Product Lock (hoặc gate khác) để chuyển sang bước tiếp theo")
    p_approve.add_argument("target_id", help="Approval Request ID (UUID) hoặc Workflow ID")
    p_approve.add_argument("--owner-user-id", default="local-owner")
    p_approve.add_argument(
        "--authorize-cost",
        action="store_true",
        help="Ủy quyền chi phí render (bắt buộc tại Gate 4: AwaitingStoryboardApproval)",
    )
    p_approve.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_approve.add_argument("--render-provider", choices=["google_flow", "vertex_ai"], help="Chọn nhà cung cấp render cho Gate Storyboard này")
    p_approve.add_argument("--qc-max-cost-usd", type=float, default=None, help="Hạn mức USD cho QC của workflow")
    p_approve.add_argument("--qc-authorization-run-id", default=None, help="Run ID trong cost authorization cho QC")
    p_approve.add_argument("--qc-authorization-scope", action="append", default=[], help="Scope QC được cấp, lặp lại được")
    p_approve.add_argument("--qc-authorization-expires-at", default=None, help="Thời điểm hết hạn ISO-8601 của QC authorization")
    p_approve.add_argument("--qc-authorization-max-cost-usd", type=float, default=None, help="Hạn mức USD trong QC authorization")
    p_approve.add_argument("--qc-authorization-campaign-id", default=None, help="Campaign ID của ủy quyền QC")
    p_approve.set_defaults(func=cmd_approve)

    # status
    p_status = subparsers.add_parser("status", help="Xem thông tin chi tiết trạng thái của một workflow")
    p_status.add_argument("workflow_id", help="Workflow ID (ví dụ: pv-daily-1e96ac740ec2f41f)")
    p_status.set_defaults(func=cmd_status)

    p_daily_status = subparsers.add_parser("daily-status", help="Báo số video hoàn thành theo ngày Product-Intelligence")
    p_daily_status.add_argument("--date", default="today", help="Ngày YYYY-MM-DD hoặc today")
    p_daily_status.add_argument("--minimum", type=int, default=3, help="Số video hoàn thành tối thiểu để trả exit code 0")
    p_daily_status.add_argument("--json", action="store_true")
    p_daily_status.set_defaults(func=cmd_daily_status)

    # qc
    p_qc = subparsers.add_parser("qc", help="Chạy QC governed cho một workflow; không tự phê duyệt gate")
    p_qc.add_argument("workflow_id", help="Workflow ID")
    p_qc.add_argument("--stage", choices=[stage.value for stage in QCStage], required=True)
    p_qc.add_argument("--provider-mode", default="configured", choices=["configured", "fake"])
    p_qc.add_argument("--authorize-cost", action="store_true", help="Cho phép configured QC có phí")
    p_qc.add_argument("--max-cost-usd", type=float, default=None, help="Hạn mức tối đa cho lần QC này")
    p_qc.add_argument("--authorization-run-id", default=None, help="Run ID trong cost authorization đã được operator cấp")
    p_qc.add_argument("--authorization-scope", action="append", default=[], help="Scope được cấp, lặp lại được (image, video hoặc product_video)")
    p_qc.add_argument("--authorization-expires-at", default=None, help="Thời điểm hết hạn ISO-8601 của authorization")
    p_qc.add_argument("--authorization-max-cost-usd", type=float, default=None, help="Hạn mức USD ghi trong authorization")
    p_qc.add_argument("--authorization-campaign-id", default=None, help="Campaign ID riêng cho hạn mức QC")
    p_qc.add_argument("--advance", action="store_true", help="Sau configured QC PASS, tạo human approval gate phù hợp")
    p_qc.set_defaults(func=cmd_qc)

    p_recover = subparsers.add_parser(
        "recover-keyframe", help="Reconcile a quarantined unknown keyframe and authorize a scoped replacement"
    )
    p_recover.add_argument("workflow_id")
    p_recover.add_argument("--owner-user-id", default="local-owner")
    p_recover.add_argument("--authorization-run-id", default=None)
    p_recover.add_argument("--authorization-scope", action="append", default=[])
    p_recover.add_argument("--authorization-expires-at", default=None)
    p_recover.add_argument("--authorization-max-cost-usd", type=float, default=None)
    p_recover.add_argument("--authorization-campaign-id", default=None)
    p_recover.set_defaults(func=cmd_recover_keyframe)

    # open-folder
    p_open = subparsers.add_parser("open-folder", help="Open VideoAI hub folder in File Explorer")
    p_open.add_argument("--latest", action="store_true", help="Open the most recently modified video folder")
    p_open.add_argument("--brand", default=None, help="Filter by brand name")
    p_open.add_argument("--hub-root", default=None, help="Custom VideoAI hub root directory")
    p_open.set_defaults(func=cmd_open_folder)

    # sync-video-hub
    p_sync = subparsers.add_parser("sync-video-hub", help="Sync all historical exports to VideoAI hub")
    p_sync.add_argument("--exports-root", default=None, help="Custom exports root directory")
    p_sync.add_argument("--hub-root", default=None, help="Custom VideoAI hub root directory")
    p_sync.add_argument("--json", action="store_true", help="Output results as JSON")
    p_sync.set_defaults(func=cmd_sync_video_hub)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
