from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from hermes_personal.product_video.cli import _quarantined_job_error, _qc_authorization_from_args, build_parser, main
from hermes_personal.storage.sqlite import connect


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 800), color=(255, 255, 255)).save(path, format="PNG")


def _product(batch_dir: Path, index: int, *, name: str, brand: str, model: str) -> dict:
    images = []
    for image_index in range(2):
        image_path = batch_dir / "images" / f"prod-{index}" / f"img-{image_index}.png"
        _write_image(image_path)
        images.append(
            {
                "asset_id": f"asset-{index}-{image_index}",
                "absolute_path": str(image_path),
                "match_score": 1.0,
                "width": 800,
                "height": 800,
            }
        )
    return {
        "id": f"prod_{index:02d}",
        "name": name,
        "brand": brand,
        "model": model,
        "price_display": "200.000đ",
        "price_min": 200000,
        "price_max": 200000,
        "hot_reason": "Hot",
        "key_features": "Features",
        "keywords": [name],
        "image_count": len(images),
        "images": images,
    }


def test_qc_cli_preserves_campaign_id_for_budget_admission() -> None:
    args = build_parser().parse_args([
        "qc", "pv-1", "--stage", "image",
        "--authorization-run-id", "run-1",
        "--authorization-scope", "product_video",
        "--authorization-expires-at", "2026-09-26T00:00:00Z",
        "--authorization-max-cost-usd", "50",
        "--authorization-campaign-id", "campaign-1",
    ])
    assert _qc_authorization_from_args(args, workflow_id="pv-1")["campaign_id"] == "campaign-1"


def test_quarantined_worker_error_is_shown_only_for_current_blocked_step() -> None:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE workflow_outbox (outbox_id INTEGER PRIMARY KEY, workflow_id TEXT, "
        "state TEXT, last_error TEXT)"
    )
    conn.execute(
        "INSERT INTO workflow_outbox (workflow_id, state, last_error) VALUES (?, ?, ?)",
        ("pv-1", "quarantined", "NO_PRODUCT_EVIDENCE"),
    )
    assert _quarantined_job_error(conn, "pv-1", "researching") == "NO_PRODUCT_EVIDENCE"
    assert _quarantined_job_error(conn, "pv-1", "AwaitingProductLock") is None
    conn.execute(
        "INSERT INTO workflow_outbox (workflow_id, state, last_error) VALUES (?, ?, ?)",
        ("pv-1", "completed", None),
    )
    assert _quarantined_job_error(conn, "pv-1", "researching") is None


def test_cli_list_and_start_auto(tmp_path: Path, capsys) -> None:
    source_root = tmp_path / "daily_runs"
    batch_dir = source_root / "2026-09-12"
    batch_dir.mkdir(parents=True)

    products = [
        _product(batch_dir, 1, name="Quạt Jisulife Life 7", brand="Jisulife", model="Life 7"),
        _product(batch_dir, 2, name="Bàn phím AULA F75", brand="AULA", model="F75"),
    ]
    (batch_dir / "products.json").write_text(
        json.dumps({"version": "1.0", "date": "2026-09-12", "products": products}),
        encoding="utf-8",
    )
    db_path = tmp_path / "hermes.db"

    # Test list command
    exit_code = main(["--db-path", str(db_path), "--source-root", str(source_root), "list"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Quạt Jisulife Life 7" in out
    assert "Bàn phím AULA F75" in out
    assert "[CHƯA TẠO VIDEO]" in out

    # Test start auto command without research
    exit_code = main([
        "--db-path", str(db_path),
        "--source-root", str(source_root),
        "start", "--auto", "--limit", "1",
        "--no-research"
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Đã tạo 1 workflow mới" in out

    # Verify state in list again
    exit_code = main(["--db-path", str(db_path), "--source-root", str(source_root), "list"])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "[ĐANG SẢN XUẤT]" in out

    # A best-effort day reports a shortfall without undoing valid workflows.
    exit_code = main([
        "--db-path", str(db_path), "--source-root", str(source_root),
        "start", "--auto", "--limit", "5", "--minimum-daily", "3",
        "--date", "2026-09-12", "--no-research",
    ])
    output = capsys.readouterr()
    assert exit_code == 1
    assert "2/3" in output.err
    with closing(connect(db_path)) as connection:
        assert len(connection.execute(
            "SELECT workflow_id FROM daily_product_video_import WHERE source_date = '2026-09-12' AND status = 'started'"
        ).fetchall()) == 2

    status_code = main([
        "--db-path", str(db_path), "daily-status",
        "--date", "2026-09-12", "--minimum", "3", "--json",
    ])
    daily_status = json.loads(capsys.readouterr().out)
    assert status_code == 1
    assert daily_status["started"] == 2
    assert daily_status["completed"] == 0


def test_cli_start_fails_when_all_claims_error(tmp_path: Path, capsys, monkeypatch) -> None:
    inbox_root = tmp_path / "exchange_inbox"
    batch_dir = inbox_root / "2026-09-13" / "run_01"
    batch_dir.mkdir(parents=True)

    img_path = batch_dir / "products" / "test_p" / "images" / "img_1.png"
    _write_image(img_path)
    img_path2 = batch_dir / "products" / "test_p" / "images" / "img_2.png"
    _write_image(img_path2)

    manifest = {
        "schema_version": "1.0.0",
        "batch_id": "run_01",
        "target_date": "2026-09-13",
        "production_date": "2026-09-13",
        "producer_version": "1.0.0",
        "products": [
            {
                "priority": 1,
                "source_product_id": "p01",
                "name": "Jisulife Life 7",
                "brand": "Jisulife",
                "model": "Life 7",
                "canonical_product_key": "jisulife:life-7",
                "product_key": "1e96ac740ec2f41f35a92194ca77c69fa3249fd103fc4e792321eca63eafd38b",
                "price_display": "350.000đ",
                "images": [
                    {
                        "asset_id": "a01",
                        "relative_path": "products/test_p/images/img_1.png",
                        "match_score": 1.0,
                    },
                    {
                        "asset_id": "a02",
                        "relative_path": "products/test_p/images/img_2.png",
                        "match_score": 1.0,
                    }
                ],
            }
        ],
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (batch_dir / "READY").write_text("READY\n", encoding="utf-8")

    db_path = tmp_path / "hermes_claim_err.db"

    # Simulate claim failure on repository
    from hermes_personal.product_video.automation.repository import ClaimResult, DailyImportRepository
    def mock_claim(*args, **kwargs):
        return ClaimResult(status="error", product_key="test_key", workflow_id="test_wf", error="Simulated lock failure")

    monkeypatch.setattr(DailyImportRepository, "claim_product", mock_claim)

    exit_code = main([
        "--db-path", str(db_path),
        "--inbox-root", str(inbox_root),
        "start", "--auto", "--limit", "1",
        "--no-research"
    ])
    # Must fail with non-zero when claims error out
    assert exit_code != 0
    err_out = capsys.readouterr()
    assert "Tất cả sản phẩm đã được xử lý" not in err_out.out
    assert "LỖI KHỞI ĐỘNG" in err_out.err or "LỖI" in err_out.err


def test_cli_start_fails_when_advance_to_product_lock_fails(tmp_path: Path, capsys, monkeypatch) -> None:
    inbox_root = tmp_path / "exchange_inbox"
    batch_dir = inbox_root / "2026-09-13" / "run_01"
    batch_dir.mkdir(parents=True)

    img_path = batch_dir / "products" / "test_p" / "images" / "img_1.png"
    _write_image(img_path)
    img_path2 = batch_dir / "products" / "test_p" / "images" / "img_2.png"
    _write_image(img_path2)

    manifest = {
        "schema_version": "1.0.0",
        "batch_id": "run_01",
        "target_date": "2026-09-13",
        "production_date": "2026-09-13",
        "producer_version": "1.0.0",
        "products": [
            {
                "priority": 1,
                "source_product_id": "p01",
                "name": "Jisulife Life 7",
                "brand": "Jisulife",
                "model": "Life 7",
                "canonical_product_key": "jisulife:life-7",
                "product_key": "1e96ac740ec2f41f35a92194ca77c69fa3249fd103fc4e792321eca63eafd38b",
                "price_display": "350.000đ",
                "images": [
                    {
                        "asset_id": "a01",
                        "relative_path": "products/test_p/images/img_1.png",
                        "match_score": 1.0,
                    },
                    {
                        "asset_id": "a02",
                        "relative_path": "products/test_p/images/img_2.png",
                        "match_score": 1.0,
                    }
                ],
            }
        ],
    }
    (batch_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (batch_dir / "READY").write_text("READY\n", encoding="utf-8")

    db_path = tmp_path / "hermes_adv_fail.db"

    from hermes_personal.product_video.automation.coordinator import ProductVideoCoordinator
    def mock_advance(*args, **kwargs):
        return {"succeeded": False, "error": "Simulated advance failure"}

    monkeypatch.setattr(ProductVideoCoordinator, "advance_to_product_lock", mock_advance)

    exit_code = main([
        "--db-path", str(db_path),
        "--inbox-root", str(inbox_root),
        "start", "--auto", "--limit", "1",
    ])
    assert exit_code != 0
    err_out = capsys.readouterr()
    assert "HOÀN TẤT" not in err_out.out
    assert "LỖI ADVANCE TO PRODUCT LOCK" in err_out.err


def test_cli_approve_cost_guard_gate4(tmp_path: Path, capsys) -> None:
    from hermes_personal.product_video.workflow import ProductVideoWorkflowState
    from hermes_personal.workflows.approvals import ApprovalService
    from hermes_personal.workflows.repository import WorkflowRepository

    db_path = tmp_path / "cost_guard.db"
    conn = connect(db_path)

    repo = WorkflowRepository(conn)
    approval_svc = ApprovalService(conn)

    wf_id = "pv-daily-costguard"
    project_id = f"proj-{wf_id}"
    owner = "local-owner"

    # Set up workflow at Gate 4 (AwaitingStoryboardApproval)
    agg = {
        "workflow_id": wf_id,
        "project_id": project_id,
        "owner_user_id": owner,
        "state": ProductVideoWorkflowState.AWAITING_STORYBOARD_APPROVAL.value,
        "source_context": {"brand": "Jisulife", "model": "Life 7", "name": "Jisulife Life 7", "price_display": "350.000đ"},
        "latest_artifact": {
            "schema": "storyboard",
            "artifact_id": "sb_001",
            "version": 1,
        },
    }
    repo.commit_workflow(wf_id, json.dumps(agg), [], expected_version=None)

    req_id = approval_svc.submit_request({
        "workflow_id": wf_id,
        "project_id": project_id,
        "gate": "AwaitingStoryboardApproval",
        "workflow_version": 2,
        "artifact_id": "sb_001",
        "artifact_version": 1,
        "owner_user_id": owner,
    })

    agg["pending_approval_id"] = req_id
    agg["pending_approval_gate"] = "AwaitingStoryboardApproval"
    repo.commit_workflow(wf_id, json.dumps(agg), [], expected_version=1)

    from hermes_personal.application.operator_handler import _current_qc_digest
    from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
    from hermes_personal.product_video.qc.repository import QCReportRepository

    QCReportRepository(conn).save_report(
        QCReport(
            report_id=f"qc_keyframe_{wf_id}",
            workflow_id=wf_id,
            stage=QCStage.KEYFRAME,
            artifact_id="sb_001",
            artifact_version=1,
            artifact_digest=_current_qc_digest(QCStage.KEYFRAME, agg["latest_artifact"]),
            reference_digests=[],
            evaluator_name="test_seeded_qc",
            evaluator_version="1",
            rubric_version="1",
            created_at="2026-09-15T00:00:00+00:00",
            score=90,
            verdict=QCVerdict.PASS,
            findings={"seeded_for": "test_cli_approve_cost_guard_gate4"},
        )
    )
    conn.close()

    # 1. Attempt approve without --authorize-cost (non-interactive) -> MUST FAIL with code 1
    code_no_auth = main([
        "--db-path", str(db_path),
        "approve", req_id,
    ])
    assert code_no_auth != 0
    err_out = capsys.readouterr()
    assert "LỖI XÁC NHẬN CHI PHÍ" in err_out.err
    assert "--authorize-cost" in err_out.err

    # 1b. Interactive approve prompt answered 'y' -> Advances successfully
    with patch("sys.stdin.isatty", return_value=True), patch("builtins.input", return_value="y"):
        code_interactive = main([
            "--db-path", str(db_path),
            "approve", req_id,
            "--provider-mode", "fake",
        ])
    assert code_interactive == 0
    out_interactive = capsys.readouterr().out
    assert "PHÊ DUYỆT THÀNH CÔNG" in out_interactive


def test_cli_status_and_caption_completed(tmp_path: Path, capsys) -> None:
    from hermes_personal.product_video.workflow import ProductVideoWorkflowState
    from hermes_personal.workflows.repository import WorkflowRepository

    db_path = tmp_path / "status_test.db"
    conn = connect(db_path)
    repo = WorkflowRepository(conn)

    wf_id = "pv-daily-completed1"
    project_id = f"proj-{wf_id}"
    video_file = tmp_path / "export_final.mp4"
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"video data here")
    caption_file = tmp_path / "caption.txt"
    caption_file.write_text("Baseus Bowie WM02\n\n#baseus #bowiewm02", encoding="utf-8")

    agg = {
        "workflow_id": wf_id,
        "project_id": project_id,
        "owner_user_id": "local-owner",
        "state": ProductVideoWorkflowState.COMPLETED.value,
        "source_context": {
            "brand": "Baseus",
            "model": "Bowie WM02",
            "name": "Tai nghe Baseus Bowie WM02",
            "price_display": "299.000đ",
            "selling_points": ["Pin 25 giờ", "Độ trễ thấp 0.06s", "Thiết kế capsule trong suốt"],
            "images": ["img1.png", "img2.png"],
        },
        "resource_pack": {
            "resource_pack_id": "rp_test",
            "status": "locked",
            "digest": "sha256:abc1234567890123456",
        },
        "latest_artifact": {
            "schema": "video_export",
            "export_id": "exp_001",
                "version": 1,
                "file_path": str(video_file),
                "caption_path": str(caption_file),
                "final_video_url": f"file://{video_file.resolve()}",
        },
    }
    repo.commit_workflow(wf_id, json.dumps(agg), [], expected_version=None)
    conn.close()

    code = main([
        "--db-path", str(db_path),
        "status", wf_id,
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "Baseus Bowie WM02" in out
    assert "299.000đ" in out
    assert "Resource Pack ID:   rp_test" in out
    assert "THÔNG TIN VIDEO HOÀN THÀNH" in out
    assert str(video_file.resolve()) in out
    assert "TIKTOK CAPTION GỢI Ý" in out
    assert "#baseus" in out
    assert "#bowiewm02" in out


def test_cli_status_reads_canonical_export_caption_and_never_rebuilds_template(tmp_path: Path, capsys) -> None:
    from hermes_personal.product_video.workflow import ProductVideoWorkflowState
    from hermes_personal.workflows.repository import WorkflowRepository

    db_path = tmp_path / "status_caption_truth.db"
    video_file = tmp_path / "export_final.mp4"
    video_file.write_bytes(b"mp4")
    caption_file = tmp_path / "caption.txt"
    caption_file.write_text("AULA F75\n\nXem thêm thông tin sản phẩm.", encoding="utf-8")

    conn = connect(db_path)
    WorkflowRepository(conn).commit_workflow(
        "wf-caption-truth",
        json.dumps({
            "workflow_id": "wf-caption-truth",
            "project_id": "proj-wf-caption-truth",
            "owner_user_id": "local-owner",
            "state": ProductVideoWorkflowState.COMPLETED.value,
            "source_context": {
                "brand": "AULA",
                "model": "F75",
                "name": "pack_snap_016c6cfddd3641e6a9bf7384fb78079d",
                "price_display": "350.000đ",
            },
            "latest_artifact": {
                "schema": "video_export",
                "file_path": str(video_file),
                "caption_path": str(caption_file),
                "metadata_path": str(tmp_path / "metadata.json"),
            },
        }),
        [],
        expected_version=None,
    )
    conn.close()

    assert main(["--db-path", str(db_path), "status", "wf-caption-truth"]) == 0
    out = capsys.readouterr().out
    assert "AULA F75" in out
    assert "Xem thêm thông tin sản phẩm." in out
    assert "Review chân thực" not in out
    assert "chính hãng" not in out.lower()
    assert "giỏ hàng" not in out.lower()
    assert "#review" not in out


def test_cli_status_does_not_generate_caption_before_export(tmp_path: Path, capsys) -> None:
    from hermes_personal.product_video.workflow import ProductVideoWorkflowState
    from hermes_personal.workflows.repository import WorkflowRepository

    db_path = tmp_path / "status_no_caption.db"
    conn = connect(db_path)
    WorkflowRepository(conn).commit_workflow(
        "wf-no-caption",
        json.dumps({
            "workflow_id": "wf-no-caption",
            "project_id": "proj-wf-no-caption",
            "owner_user_id": "local-owner",
            "state": ProductVideoWorkflowState.COMPLETED.value,
            "source_context": {"brand": "AULA", "model": "F75", "name": "AULA F75"},
            "latest_artifact": {"schema": "video_export", "file_path": str(tmp_path / "missing.mp4")},
        }),
        [],
        expected_version=None,
    )
    conn.close()

    assert main(["--db-path", str(db_path), "status", "wf-no-caption"]) == 0
    out = capsys.readouterr().out
    assert "Chưa có caption export chính thức" in out
    assert "Review chân thực" not in out
