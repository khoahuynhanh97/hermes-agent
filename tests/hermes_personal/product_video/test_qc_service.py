import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from PIL import Image

from hermes_personal.product_video.qc.models import QCStage, QCVerdict
from hermes_personal.product_video.qc.evaluator import QCResponseParseError
from hermes_personal.product_video.qc.service import (
    ProductVideoQCService,
    _file_url_to_path,
    _reference_url_to_path,
)
from hermes_personal.product_video.cli import main
from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.budgets import BudgetError, BudgetPolicy, BudgetRepository
from hermes_personal.workflows.repository import WorkflowRepository


def _seed_image_workflow(tmp_path):
    image_one = tmp_path / "one.png"
    image_two = tmp_path / "two.png"
    Image.new("RGB", (8, 8), color="red").save(image_one)
    Image.new("RGB", (8, 8), color="blue").save(image_two)
    conn = connect(tmp_path / "qc_service.db")
    WorkflowRepository(conn).commit_workflow(
        "wf-qc-service",
        json.dumps({
            "workflow_id": "wf-qc-service",
            "project_id": "proj-wf-qc-service",
            "owner_user_id": "local-owner",
            "state": "AwaitingProductLock",
            "source_context": {"brand": "AULA", "model": "F75"},
            "resource_pack": {
                "resource_pack_id": "rp-qc-service",
                "version": 1,
                "owner_user_id": "local-owner",
                "project_id": "proj-wf-qc-service",
                "brand": "AULA",
                "model": "F75",
                "assets_mapping": {"a1": str(image_one), "a2": str(image_two)},
            },
            "latest_artifact": {
                "schema": "product_resource_pack",
                "resource_pack_id": "rp-qc-service",
                "version": 1,
                "owner_user_id": "local-owner",
                "project_id": "proj-wf-qc-service",
                "assets_mapping": {"a1": str(image_one), "a2": str(image_two)},
            },
        }),
        [],
        expected_version=None,
    )
    return conn


def test_qc_reference_path_allows_configured_exchange_root_only(tmp_path, monkeypatch):
    from hermes_personal.product_video.storage import layout

    exchange = tmp_path / "approved-exchange"
    exchange.mkdir()
    image = exchange / "reference.png"
    image.write_bytes(b"image")
    unrelated = tmp_path / "unrelated.png"
    unrelated.write_bytes(b"image")
    monkeypatch.setattr(layout, "get_trusted_exchange_roots", lambda: (exchange,))
    monkeypatch.setattr(layout, "get_workspace_layout", lambda: layout.ProductVideoWorkspaceLayout(tmp_path / "workspace"))

    assert _reference_url_to_path(image) == image.resolve()
    with pytest.raises(ValueError, match="CONTAINMENT_VIOLATION"):
        _reference_url_to_path(unrelated)
    with pytest.raises(ValueError, match="CONTAINMENT_VIOLATION"):
        _file_url_to_path(image)


def test_configured_qc_without_cost_authorization_stays_pending(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    result = ProductVideoQCService(conn, evaluator=evaluator).run(
        "wf-qc-service", QCStage.IMAGE, provider_mode="configured"
    )
    assert result["status"] == "pending"
    assert "authorization" in result["reason"].lower()
    evaluator.evaluate_image.assert_not_called()
    conn.close()


def test_fake_qc_service_runs_real_image_qc_entrypoint_and_persists_report(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "offline_test_vision"
    evaluator.evaluator_version = "1.0"
    evaluator.evaluate_image.return_value = {
        **_reference_profile(),
        "identity_score": 55,
        "clarity_score": 23,
        "usability_score": 12,
        "total_score": 90,
        "verdict": "pass",
        "eligible": True,
        "hard_failure": False,
        "source_branding_detected": False,
        "identity_mismatch": False,
        "reason": "clean",
    }
    result = ProductVideoQCService(conn, evaluator=evaluator).run(
        "wf-qc-service", QCStage.IMAGE, provider_mode="fake"
    )
    assert result["status"] == "completed"
    assert result["report"].verdict == QCVerdict.PASS
    assert result["eligible_count"] == 2
    assert result["report_id"]
    assert evaluator.evaluate_image.call_count == 2
    conn.close()


def test_cli_qc_uses_service_and_does_not_approve_gate(tmp_path, capsys):
    conn = _seed_image_workflow(tmp_path)
    conn.close()
    assert main([
        "--db-path", str(tmp_path / "qc_service.db"),
        "qc", "wf-qc-service", "--stage", "image", "--provider-mode", "fake",
    ]) == 0
    out = capsys.readouterr().out
    assert "QC status:" in out
    assert "QC report ID:" in out
    assert "Eligible references: 2" in out


def test_configured_qc_requires_scoped_expiring_authorization_and_reuses_claim(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "configured_test_vision"
    evaluator.evaluator_version = "2"
    evaluator.model = "test/vision"
    evaluator.fake_mode = False
    evaluator.evaluate_image.return_value = {
        **_reference_profile(),
        "identity_score": 55,
        "clarity_score": 23,
        "usability_score": 12,
        "total_score": 90,
        "verdict": "pass",
        "eligible": True,
        "hard_failure": False,
        "source_branding_detected": False,
        "identity_mismatch": False,
        "reason": "clean",
    }
    auth = {
        "workflow_id": "wf-qc-service",
        "run_id": "run-qc-1",
        "scope": ["image"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "max_cost_usd": 0.30,
    }
    service = ProductVideoQCService(
        conn,
        evaluator=evaluator,
        budget_policy=BudgetPolicy(max_total=100, per_channel={"video_factory": 100}),
    )
    result = service.run(
        "wf-qc-service",
        QCStage.IMAGE,
        provider_mode="configured",
        authorize_cost=True,
        max_cost_usd=0.10,
        authorization=auth,
        attempt_id="run-qc-1:image:1",
    )
    assert result["status"] == "completed"
    assert evaluator.evaluate_image.call_count == 2
    again = service.run(
        "wf-qc-service",
        QCStage.IMAGE,
        provider_mode="configured",
        authorize_cost=True,
        max_cost_usd=0.10,
        authorization=auth,
        attempt_id="run-qc-1:image:1",
    )
    assert again["report_id"] == result["report_id"]
    assert evaluator.evaluate_image.call_count == 2
    conn.close()


def test_configured_technical_unknown_retries_under_the_same_authorization_grant(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "configured_test_vision"
    evaluator.evaluator_version = "2"
    evaluator.model = "test/vision"
    evaluator.fake_mode = False
    passing = {
        **_reference_profile(),
        "identity_score": 55,
        "clarity_score": 23,
        "usability_score": 12,
        "total_score": 90,
        "verdict": "pass",
        "eligible": True,
        "hard_failure": False,
        "source_branding_detected": False,
        "identity_mismatch": False,
        "reason": "clean",
    }
    evaluator.evaluate_image.side_effect = [
        QCResponseParseError('{"identity_score": 55,', "length", "truncated"),
        QCResponseParseError('{"identity_score": 55,', "length", "truncated"),
        passing,
        passing,
    ]
    service = ProductVideoQCService(
        conn,
        evaluator=evaluator,
        budget_policy=BudgetPolicy(max_total=100, per_channel={"video_factory": 100}),
    )
    authorization = {
        "workflow_id": "wf-qc-service",
        "run_id": "run-qc-grant",
        "scope": ["image"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "max_cost_usd": 0.30,
    }
    first = service.run(
        "wf-qc-service", QCStage.IMAGE, provider_mode="configured",
        authorize_cost=True, max_cost_usd=0.10, authorization=authorization,
    )
    assert first["status"] == "completed"
    assert first["report"].verdict == QCVerdict.UNKNOWN

    retried = service.run(
        "wf-qc-service", QCStage.IMAGE, provider_mode="configured",
        authorize_cost=True, max_cost_usd=0.10, authorization=authorization,
    )
    assert retried["status"] == "completed"
    assert retried["report_id"] != first["report_id"]
    assert evaluator.evaluate_image.call_count == 4
    attempts = conn.execute(
        "SELECT attempt_number, status FROM product_video_operation_attempt ORDER BY attempt_number"
    ).fetchall()
    assert [(row["attempt_number"], row["status"]) for row in attempts] == [
        (1, "technical_unknown"),
        (2, "pass"),
    ]
    conn.close()


def test_qc_stops_after_three_total_technical_unknown_attempts(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "configured_test_vision"
    evaluator.evaluator_version = "2"
    evaluator.model = "test/vision"
    evaluator.fake_mode = False
    evaluator.evaluate_image.side_effect = QCResponseParseError("{", "length", "truncated")
    auth = {
        "workflow_id": "wf-qc-service", "run_id": "three-attempt-grant", "scope": ["image"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "max_cost_usd": 1.0,
    }
    service = ProductVideoQCService(conn, evaluator=evaluator)
    for _ in range(3):
        result = service.run("wf-qc-service", QCStage.IMAGE, provider_mode="configured",
                             authorize_cost=True, max_cost_usd=0.10, authorization=auth)
        assert result["status"] == "completed"
        assert result["report"].verdict == QCVerdict.UNKNOWN
    blocked = service.run("wf-qc-service", QCStage.IMAGE, provider_mode="configured",
                          authorize_cost=True, max_cost_usd=0.10, authorization=auth)
    assert blocked["status"] == "pending"
    assert "3 total attempts" in blocked["reason"]
    assert evaluator.evaluate_image.call_count == 6
    conn.close()


def test_hierarchical_reservation_counts_campaign_and_workflow_totals(tmp_path):
    conn = connect(tmp_path / "budget.db")
    repo = BudgetRepository(conn)
    workflow_policy = BudgetPolicy(max_total=1_000, per_channel={"video_factory": 1_000})
    first = repo.reserve_budget(
        workflow_policy, "video_factory", 900, owner_user_id="owner", scope_id="wf-1",
        idempotency_key="a1", campaign_id="campaign", campaign_max=1_000,
        authorization_id="grant", attempt_id="attempt-a1",
    )
    assert first.amount == 900
    with pytest.raises(BudgetError, match="campaign budget"):
        repo.reserve_budget(
            workflow_policy, "video_factory", 200, owner_user_id="owner", scope_id="wf-2",
            idempotency_key="a2", campaign_id="campaign", campaign_max=1_000,
            authorization_id="grant", attempt_id="attempt-a2",
        )
    with pytest.raises(BudgetError, match="exceeds its limit"):
        repo.reserve_budget(
            BudgetPolicy(max_total=1_000, per_channel={"video_factory": 1_000}),
            "video_factory", 200, owner_user_id="owner", scope_id="wf-1", idempotency_key="a3",
            campaign_id="other", campaign_max=10_000, authorization_id="grant", attempt_id="attempt-a3",
        )
    replay = repo.reserve_budget(
        workflow_policy, "video_factory", 900, owner_user_id="owner", scope_id="wf-1",
        idempotency_key="a1", campaign_id="campaign", campaign_max=1_000,
        authorization_id="grant", attempt_id="attempt-a1",
    )
    assert replay.reservation_id == first.reservation_id
    conn.close()


def test_configured_provider_429_is_retryable_technical_unknown(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "configured_test_vision"
    evaluator.evaluator_version = "2"
    evaluator.model = "test/vision"
    evaluator.fake_mode = False
    evaluator.evaluate_image.side_effect = [
        RuntimeError("MultimodalEvaluator HTTP 429: RESOURCE_EXHAUSTED"),
        RuntimeError("MultimodalEvaluator HTTP 429: RESOURCE_EXHAUSTED"),
    ]
    service = ProductVideoQCService(
        conn,
        evaluator=evaluator,
        budget_policy=BudgetPolicy(max_total=100, per_channel={"video_factory": 100}),
    )
    authorization = {
        "workflow_id": "wf-qc-service",
        "run_id": "run-qc-429",
        "scope": ["image"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "max_cost_usd": 0.30,
    }

    first = service.run(
        "wf-qc-service",
        QCStage.IMAGE,
        provider_mode="configured",
        authorize_cost=True,
        max_cost_usd=0.10,
        authorization=authorization,
    )
    assert first["report"].verdict == QCVerdict.UNKNOWN
    status = conn.execute(
        "SELECT status FROM product_video_operation_attempt WHERE authorization_id = ?",
        ("run-qc-429",),
    ).fetchone()["status"]
    assert status == "technical_unknown"
    conn.close()


def test_disabled_vertex_service_releases_qc_reservation(tmp_path):
    conn = _seed_image_workflow(tmp_path)
    evaluator = MagicMock()
    evaluator.evaluator_name = "configured_test_vision"
    evaluator.evaluator_version = "2"
    evaluator.model = "test/vision"
    evaluator.fake_mode = False
    evaluator.evaluate_image.side_effect = RuntimeError(
        'MultimodalEvaluator HTTP 403: {"reason": "SERVICE_DISABLED"}'
    )
    service = ProductVideoQCService(conn, evaluator=evaluator)
    authorization = {
        "workflow_id": "wf-qc-service",
        "run_id": "disabled-service-grant",
        "scope": ["image"],
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        "max_cost_usd": 0.30,
    }

    result = service.run(
        "wf-qc-service", QCStage.IMAGE, provider_mode="configured",
        authorize_cost=True, max_cost_usd=0.10, authorization=authorization,
    )

    assert result["status"] == "completed"
    assert result["report"].verdict == QCVerdict.UNKNOWN
    assert evaluator.evaluate_image.call_count == 2
    reservation = conn.execute(
        "SELECT state FROM budget_reservation WHERE authorization_id = ?",
        ("disabled-service-grant",),
    ).fetchone()
    attempt = conn.execute(
        "SELECT status FROM product_video_operation_attempt WHERE authorization_id = ?",
        ("disabled-service-grant",),
    ).fetchone()
    assert reservation["state"] == "released"
    assert attempt["status"] == "technical_unknown"
    conn.close()

def _reference_profile() -> dict[str, object]:
    return {
        "view_angle": "front three-quarter",
        "shot_type": "clean product",
        "visible_details": ["product body", "controls"],
        "scene_suitability": ["hero", "detail"],
        "risk_flags": [],
        "text_coverage_percent": 0,
    }
