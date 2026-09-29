from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from hermes_personal.application.operator_handler import _current_qc_digest
from hermes_personal.product_video.automation.contracts import compute_product_key
from hermes_personal.product_video.automation.importer import publish_daily_run_to_exchange
from hermes_personal.product_video.handlers import (
    ProductVideoWorkflowState,
    start_product_video_workflow,
)
from hermes_personal.product_video.qc.models import QCReport, QCStage, QCVerdict
from hermes_personal.product_video.qc.repository import QCReportRepository
from hermes_personal.runtime.gateway_server import create_gateway_application
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.approvals import ApprovalService
from hermes_personal.workflows.envelope import parse_envelope
from hermes_personal.workflows.repository import WorkflowRepository


def _write_image(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (400, 400), color=(200, 200, 200)).save(path, format="PNG")


def _seed_pass_image_qc(conn, workflow_id: str, artifact: dict) -> None:
    QCReportRepository(conn).save_report(
        QCReport(
            report_id=f"qc_image_{workflow_id}",
            workflow_id=workflow_id,
            stage=QCStage.IMAGE,
            artifact_id=str(artifact.get("artifact_id") or workflow_id),
            artifact_version=1,
            artifact_digest=_current_qc_digest(QCStage.IMAGE, artifact),
            reference_digests=[],
            evaluator_name="test_seeded_qc",
            evaluator_version="1",
            rubric_version="1",
            created_at="2026-09-15T00:00:00+00:00",
            score=90,
            verdict=QCVerdict.PASS,
            findings={"seeded_for": "operator console approval guard"},
        )
    )


def _setup_test_exchange_batch(tmp_path: Path) -> tuple[Path, Path]:
    src_run = tmp_path / "src_run"
    src_run.mkdir(parents=True, exist_ok=True)

    products = []
    # 3 valid products + 1 invalid product (only 1 image)
    for i, (brand, model) in enumerate([
        ("Jisulife", "Life 7"),
        ("AULA", "F75"),
        ("Baseus", "Bowie WM02"),
    ], start=1):
        img1 = src_run / f"img_{i}_1.png"
        img2 = src_run / f"img_{i}_2.png"
        _write_image(img1)
        _write_image(img2)
        products.append({
            "id": f"prod_{i:02d}",
            "name": f"{brand} {model}",
            "brand": brand,
            "model": model,
            "price_display": f"{i * 100}.000đ",
            "hot_reason": f"Trending product #{i}",
            "key_features": "Fast, durable, wireless",
            "keywords": [f"{brand} {model}"],
            "images": [
                {"asset_id": f"a_{i}_1", "absolute_path": str(img1), "match_score": 1.0},
                {"asset_id": f"a_{i}_2", "absolute_path": str(img2), "match_score": 1.0},
            ],
        })

    # Product 4: Invalid (only 1 image)
    img_inv = src_run / "img_inv_1.png"
    _write_image(img_inv)
    products.append({
        "id": "prod_04_inv",
        "name": "Generic Invalid Earbuds",
        "brand": "Generic",
        "model": "BadPack",
        "price_display": "50.000đ",
        "hot_reason": "Cheap",
        "images": [{"asset_id": "a_inv_1", "absolute_path": str(img_inv), "match_score": 1.0}],
    })

    (src_run / "products.json").write_text(
        json.dumps({"version": "1.0", "date": "2026-09-12", "products": products}, ensure_ascii=False),
        encoding="utf-8",
    )

    inbox = tmp_path / "exchange_inbox"
    publish_daily_run_to_exchange(src_run, inbox, batch_id="run_console_test")
    return src_run, inbox


def test_operator_console_full_lifecycle(tmp_path: Path, monkeypatch) -> None:
    _, inbox = _setup_test_exchange_batch(tmp_path)
    monkeypatch.setenv("HERMES_EXCHANGE_INBOX", str(inbox))

    db_path = tmp_path / "runtime.sqlite3"
    app = create_gateway_application(
        database_path=db_path,
        api_key="test-api-key",
        provider_mode="fake",
    )

    with TestClient(app) as client:
        # 1. Console HTML route serves valid operator page
        console_res = client.get("/personal/product-video")
        assert console_res.status_code == 200
        assert "Product Video Operator Console" in console_res.text
        assert "Auto Start" in console_res.text

        # 2. Candidate list rendering / API mapping
        res = client.get("/api/personal/product-video/candidates")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        candidates = data["candidates"]
        assert len(candidates) == 4

        # Check statuses: 3 unprocessed, 1 invalid
        unprocessed = [c for c in candidates if c["status"] == "unprocessed"]
        invalid = [c for c in candidates if c["status"] == "invalid"]
        assert len(unprocessed) == 3
        assert len(invalid) == 1
        assert "fewer than two" in invalid[0]["rejection_reason"]

        # 3. Invalid product cannot start
        inv_key = invalid[0]["product_key"]
        inv_start = client.post(
            "/api/personal/product-video/start-batch",
            json={"product_keys": [inv_key]},
        )
        assert inv_start.status_code == 200
        inv_data = inv_start.json()
        assert inv_data["ok"] is True
        assert len(inv_data["started"]) == 0
        assert len(inv_data["skipped"]) == 1
        assert "INVALID_ADMISSION" in inv_data["skipped"][0]["reason"]

        # 4. Start selected with partial stale-selection handling
        p1_key = unprocessed[0]["product_key"]
        stale_key = "non_existent_key_12345"

        batch_res = client.post(
            "/api/personal/product-video/start-batch",
            json={"product_keys": [p1_key, stale_key]},
        )
        assert batch_res.status_code == 200
        batch_data = batch_res.json()
        assert batch_data["ok"] is True
        assert len(batch_data["started"]) == 1
        assert batch_data["started"][0]["product_key"] == p1_key
        assert len(batch_data["skipped"]) == 1
        assert batch_data["skipped"][0]["reason"] == "NOT_FOUND_IN_MANIFEST"
        started_wf_id = batch_data["started"][0]["workflow_id"]

        # 5. Duplicate start does not create another workflow (idempotency)
        dup_res = client.post(
            "/api/personal/product-video/start-batch",
            json={"product_keys": [p1_key]},
        )
        assert dup_res.status_code == 200
        dup_data = dup_res.json()
        assert len(dup_data["started"]) == 0
        assert len(dup_data["skipped"]) == 1
        assert "ALREADY" in dup_data["skipped"][0]["reason"]

        # 6. Auto-start picks remaining eligible products in priority order
        auto_res = client.post(
            "/api/personal/product-video/start-batch",
            json={"auto": True, "limit": 2},
        )
        assert auto_res.status_code == 200
        auto_data = auto_res.json()
        assert auto_data["ok"] is True
        assert len(auto_data["started"]) == 1
        # Preserves priority: second product (AULA F75) was started
        assert auto_data["started"][0]["canonical_product_key"] == "aula:f75"

        # 7. Workflow detail endpoint GET /api/personal/product-video/workflows/{workflow_id}
        wf_res = client.get(f"/api/personal/product-video/workflows/{started_wf_id}")
        assert wf_res.status_code == 200
        wf_data = wf_res.json()
        assert wf_data["ok"] is True
        wf = wf_data["workflow"]
        assert wf["workflow_id"] == started_wf_id
        assert wf["state"] == "researching"
        assert wf["source_context"] is not None
        assert wf["source_context"]["brand"] == "Jisulife"

        # 8. Setup workflow into AWAITING_PRODUCT_LOCK and verify review details
        conn = connect(db_path)
        wf_repo = WorkflowRepository(conn)
        app_svc = ApprovalService(conn)

        # Mock research completion into AwaitingProductLock
        research_dossier = {
            "summary": "Top selling handheld fan with LED screen",
            "snapshot_id": "snap_test_123",
            "status": "researched",
            "selling_points": ["5000mAh battery", "19h runtime", "Pocket foldable"],
            "competitors": ["Baseus Mini", "Xiaomi Fan"],
        }
        req_id = app_svc.submit_request({
            "workflow_id": started_wf_id,
            "project_id": f"proj-{started_wf_id}",
            "gate": ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value,
            "workflow_version": 2,
            "artifact_id": "snap_test_123",
            "artifact_version": 1,
            "artifact_ref": {"report": json.dumps(research_dossier), "summary": "Top selling"},
            "owner_user_id": "local-owner",
        })
        agg_lock = {
            "state": ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value,
            "project_id": f"proj-{started_wf_id}",
            "owner_user_id": "local-owner",
            "product_key": p1_key,
            "pending_approval_id": req_id,
            "pending_approval_gate": ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value,
            "latest_artifact": {"report": json.dumps(research_dossier), "summary": "Top selling"},
            "source_context": wf["source_context"],
        }
        wf_repo.commit_workflow(started_wf_id, json.dumps(agg_lock), [], expected_version=1)
        _seed_pass_image_qc(conn, started_wf_id, agg_lock["latest_artifact"])
        conn.close()

        # Check candidate list now displays AWAITING_PRODUCT_LOCK
        c_refresh = client.get("/api/personal/product-video/candidates").json()
        jisulife_cand = next(c for c in c_refresh["candidates"] if c["product_key"] == p1_key)
        assert jisulife_cand["status"] == "awaiting_product_lock"
        assert jisulife_cand["approval_id"] == req_id

        # 9. GET workflow detail exposes research snapshot evidence and approval
        wf_lock_res = client.get(f"/api/personal/product-video/workflows/{started_wf_id}")
        assert wf_lock_res.status_code == 200
        wf_lock = wf_lock_res.json()["workflow"]
        assert wf_lock["state"] == "AwaitingProductLock"
        assert wf_lock["pending_approval_id"] == req_id
        assert wf_lock["approval"] is not None
        assert wf_lock["approval"]["status"] == "pending"
        assert wf_lock["research_snapshot"] is not None
        assert wf_lock["research_snapshot"]["snapshot_id"] == "snap_test_123"
        assert "5000mAh battery" in wf_lock["research_snapshot"]["selling_points"]

        # 10. Approve Product Lock advances workflow to BUILDING_RESOURCE_PACK & enqueues outbox
        approve_res = client.post(
            "/api/personal/product-video/approve-lock",
            json={"target_id": req_id},
        )
        assert approve_res.status_code == 200
        approve_data = approve_res.json()
        assert approve_data["ok"] is True

        # Verify state in DB
        wf_after_res = client.get(f"/api/personal/product-video/workflows/{started_wf_id}")
        wf_after = wf_after_res.json()["workflow"]
        assert wf_after["state"] == "locking_resource_pack"
        assert wf_after["pending_approval_id"] is None

        # Verify Outbox task
        conn2 = connect(db_path)
        outbox_row = conn2.execute("SELECT message FROM workflow_outbox WHERE workflow_id = ? ORDER BY rowid DESC LIMIT 1", (started_wf_id,)).fetchone()
        assert outbox_row is not None
        env = parse_envelope(outbox_row[0])
        assert env.topic == "job.dispatch"
        assert env.payload["approval_request_id"] == req_id
        conn2.close()


def test_operator_console_asset_serving_and_path_traversal_protection(tmp_path: Path, monkeypatch) -> None:
    src_run, inbox_root = _setup_test_exchange_batch(tmp_path)
    monkeypatch.setenv("HERMES_EXCHANGE_INBOX", str(inbox_root))

    db_path = tmp_path / "hermes_assets.db"
    app = create_gateway_application(
        database_path=db_path,
        api_key="test-api-key",
        provider_mode="fake",
    )
    with TestClient(app) as client:
        # Discover candidate to get real asset_url
        cands_res = client.get("/api/personal/product-video/candidates")
        assert cands_res.status_code == 200
        candidates = cands_res.json()["candidates"]
        jisulife = next(c for c in candidates if c["model"] == "Life 7")
        assert len(jisulife["images"]) >= 2

        asset_url = jisulife["images"][0]["asset_url"]
        assert asset_url.startswith("/api/personal/product-video/assets/")

        # 1. Valid asset fetch -> HTTP 200 with image MIME type
        asset_res = client.get(asset_url)
        assert asset_res.status_code == 200
        assert asset_res.headers["content-type"].startswith("image/")
        assert len(asset_res.content) > 0

        # 2. Path traversal attempt using .. -> HTTP 403 Forbidden
        date_part = jisulife["source_date"]
        batch_part = jisulife["source_batch_id"]
        traversal_url = f"/api/personal/product-video/assets/{date_part}/{batch_part}/../../secret.txt"
        bad_res = client.get(traversal_url)
        assert bad_res.status_code in (403, 404)

        # 3. Path traversal outside batch directory -> rejected (400 Bad Request or 403 Forbidden)
        outside_res = client.get(f"/api/personal/product-video/assets/{date_part}/{batch_part}/../manifest.json")
        assert outside_res.status_code in (400, 403)

        # 4. Invalid date / batch regex format -> HTTP 400 Bad Request
        invalid_format_res = client.get(f"/api/personal/product-video/assets/invalid-date/{batch_part}/img.png")
        assert invalid_format_res.status_code == 400

        # 5. Unsupported file extension (non-image) -> HTTP 400 Bad Request
        text_file = inbox_root / date_part / batch_part / "notes.txt"
        text_file.write_text("unsupported file", encoding="utf-8")
        non_img_res = client.get(f"/api/personal/product-video/assets/{date_part}/{batch_part}/notes.txt")
        assert non_img_res.status_code == 400


def test_operator_console_anti_xss_and_rendering_safety() -> None:
    from hermes_personal.product_video.operator_console import render_operator_console_html

    hostile_candidates = [
        {
            "priority": 1,
            "source_date": "2026-09-12",
            "source_batch_id": "run_test",
            "source_product_id": "p_xss",
            "canonical_product_key": "xss:test",
            "product_key": "key_xss_123",
            "name": '<script>alert("pwned_name")</script>',
            "brand": '<b>EvilBrand</b>',
            "model": '<img src=x onerror=alert(1)>',
            "variant": '"><script>alert(2)</script>',
            "price_display": '<script>alert(3)</script>',
            "hot_reason": '"><svg onload=alert(4)>',
            "key_features": "test features",
            "keywords": ["test"],
            "images": [
                {
                    "asset_id": "img1",
                    "asset_url": "javascript:alert(5)",
                    "original_url": "javascript:alert(6)",
                }
            ],
            "status": "unprocessed",
        }
    ]

    html = render_operator_console_html(hostile_candidates)

    # 1. Script tag breakout is strictly neutralized in JSON injection (< -> \u003c)
    assert '<script>alert' not in html
    assert r'\u003cscript>alert' in html

    # 2. escapeHtml and sanitizeUrl helpers are embedded in the client script
    assert "function escapeHtml" in html
    assert "function sanitizeUrl" in html
    assert "safePkey" in html
    assert "safeName" in html
    assert "safeBrand" in html
