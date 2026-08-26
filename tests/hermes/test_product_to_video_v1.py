from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from hermes.application.product_resource_service import ProductResourceService


def _write_pi_lock(root: Path) -> dict:
    image = root / "ProductIntelligence" / "product_scout" / "images" / "product.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"test-image")
    lock = {
        "status": "locked",
        "lock_id": "lock_test_product_v1",
        "resource_pack_id": "pack_test_product_v1",
        "resource_pack_version": 1,
        "snapshot_id": "snap_test_product_v1",
        "canonical_product_id": "prod_test_product",
        "owner_user_id": "user",
        "product_name": "Test Product",
        "brand": "Example",
        "assets": [{
            "asset_id": "asset_test_product_01",
            "local_path": str(image),
            "physical_hash_filename": "product.jpg",
            "mime_type": "image/jpeg",
            "media_role": "original",
            "match_confidence": 1.0,
        }],
    }
    lock["manifest_digest"] = ProductResourceService.compute_manifest_digest(lock)
    target = root / "ProductResearch" / "test-product" / "machine" / "resource-pack-lock.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(lock), encoding="utf-8")
    return lock


def _configure_runtime(monkeypatch, tmp_path: Path) -> tuple[Path, dict]:
    data_root = tmp_path / "hermes-data"
    pi_root = tmp_path / "pi-data"
    lock = _write_pi_lock(pi_root)
    monkeypatch.setenv("HERMES_DATA_DIR", str(data_root))
    monkeypatch.setenv("HERMES_PI_DATA_DIR", str(pi_root))
    monkeypatch.setenv("HERMES_DB_PATH", str(data_root / "db" / "hermes.sqlite"))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(data_root / "db" / "video-factory.sqlite"))
    return pi_root, lock


def test_api_resolves_persisted_lock_without_leaking_local_paths(monkeypatch, tmp_path):
    _, lock = _configure_runtime(monkeypatch, tmp_path)
    from hermes.channels.api.app import app

    client = TestClient(app)
    products = client.get("/api/products").json()["products"]
    assert products[0]["resource_pack_lock_id"] == lock["lock_id"]

    project_id = "proj_test_product"
    assert client.post("/api/vf/projects", json={"project_id": project_id}).status_code == 200
    bound = client.post(
        f"/api/vf/projects/{project_id}/resources/bind",
        json={"product_query": lock["lock_id"]},
    )
    assert bound.status_code == 200, bound.text
    payload = bound.json()["data"]
    reference = payload["resource_pack"]["product_references"][0]
    assert reference["uri"] == f"/api/assets/{reference['asset_id']}/content"
    assert str(tmp_path) not in bound.text

    assets = client.get("/api/assets").json()["assets"]
    assert "local_path" not in assets[0]
    assert client.get(f"/api/assets/{reference['asset_id']}/content").status_code == 200


def test_workflow_orchestrator_creates_bound_project_and_journal(monkeypatch, tmp_path):
    pi_root, lock = _configure_runtime(monkeypatch, tmp_path)
    from hermes.application.workflow import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(tmp_path / "workflow.sqlite", pi_data_root=pi_root)
    result = orchestrator.create_video_project("user", "proj_orchestrated", lock["canonical_product_id"])
    assert result["resource_pack_lock_id"] == lock["lock_id"]
    assert result["snapshot_id"] == lock["snapshot_id"]
    assert orchestrator.get_project_status("user", "proj_orchestrated")["state"] == "resource_ready"
    assert orchestrator.journal.get_entry(result["run_id"]).project_id == "proj_orchestrated"


def test_user_governed_workflow_stops_at_creative_brief_approval(monkeypatch, tmp_path):
    pi_root, lock = _configure_runtime(monkeypatch, tmp_path)
    from hermes.application.workflow import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(tmp_path / "workflow.sqlite", pi_data_root=pi_root)
    result = orchestrator.run_product_to_video_workflow(
        owner_user_id="user",
        prompt="Create a TikTok review for Test Product",
        product_query=lock["canonical_product_id"],
        approval_policy="require_user",
    )

    project = orchestrator.vf_service.get_project("user", result["project_id"])
    assert result["status"] == "approval_required"
    assert result["approval_stage"] == "creative_brief"
    assert result["approve_tool"] == "creative_brief_approve"
    assert result["approval_command"] == f"/vf_approve {result['project_id']} creative_brief"
    assert project.creative_brief is not None
    assert project.brief_approval == "pending"
    assert project.scene_plan is None


def test_user_governed_workflow_resumes_through_review_checkpoints(monkeypatch, tmp_path):
    pi_root, lock = _configure_runtime(monkeypatch, tmp_path)
    from hermes.application.workflow import WorkflowOrchestrator

    monkeypatch.setattr(
        "hermes.application.workflow.render_beat_keyframe",
        lambda output_path, **_: Path(output_path).write_bytes(b"generated-frame"),
    )
    orchestrator = WorkflowOrchestrator(tmp_path / "workflow.sqlite", pi_data_root=pi_root)
    orchestrator.worker.run_once = lambda: None
    common = {
        "owner_user_id": "user",
        "prompt": "Create a TikTok review for Test Product",
        "product_query": lock["canonical_product_id"],
        "approval_policy": "require_user",
    }

    brief = orchestrator.run_product_to_video_workflow(**common)
    resume = {
        "owner_user_id": "user",
        "prompt": "continue",
        "approval_policy": "require_user",
        "project_id": brief["project_id"],
        "run_id": brief["run_id"],
    }
    orchestrator.vf_service.approve_creative_brief("user", brief["project_id"])
    scenes = orchestrator.run_product_to_video_workflow(**resume)
    assert scenes["approval_stage"] == "scene_plan"
    scene_project = orchestrator.vf_service.get_project("user", brief["project_id"])
    assert all("continue" not in scene.content.lower() for scene in scene_project.scene_plan.scenes)
    assert "Test Product" in scene_project.scene_plan.scenes[0].content

    orchestrator.vf_service.approve_scene_plan("user", brief["project_id"])
    storyboard = orchestrator.run_product_to_video_workflow(**resume)
    project = orchestrator.vf_service.get_project("user", brief["project_id"])

    assert storyboard["approval_stage"] == "storyboard"
    assert storyboard["approve_tool"] == "storyboard_approve"
    assert project.storyboard is not None
    assert project.storyboard.approval_status.value == "pending"
    assert project.generated_scenes == ()


def test_existing_draft_waits_for_final_approval_then_exports_without_regeneration(monkeypatch, tmp_path):
    pi_root, lock = _configure_runtime(monkeypatch, tmp_path)
    from hermes.application.workflow import WorkflowOrchestrator

    orchestrator = WorkflowOrchestrator(tmp_path / "workflow.sqlite", pi_data_root=pi_root)
    created = orchestrator.create_video_project("user", "proj_final_gate", lock["canonical_product_id"])
    draft_path = tmp_path / "draft.mp4"
    draft_path.write_bytes(b"draft-video")
    draft_asset_id = "draft_asset_final_gate"
    orchestrator.asset_repository.save_asset({
        "asset_id": draft_asset_id,
        "owner_user_id": "user",
        "project_id": created["project_id"],
        "scene_id": "draft_video",
        "job_id": "job_draft",
        "provider": "fake",
        "resource_lock_id": lock["lock_id"],
        "output_path": str(draft_path),
    })
    project = orchestrator.vf_service.get_project("user", created["project_id"])
    orchestrator.repo.save(replace(project, draft_video_asset_id=draft_asset_id))

    pending = orchestrator.run_product_to_video_workflow(
        owner_user_id="user",
        prompt="Create video for Test Product",
        product_query=lock["canonical_product_id"],
        project_id=created["project_id"],
        run_id=created["run_id"],
        approval_policy="require_user",
    )
    assert pending["approval_stage"] == "final_video"

    orchestrator.vf_service.approve_final_video("user", created["project_id"])
    monkeypatch.setattr(
        orchestrator,
        "_export_approved_draft",
        lambda **kwargs: {"status": "ok", "draft_mp4_path": kwargs["draft_mp4_path"]},
    )
    completed = orchestrator.run_product_to_video_workflow(
        owner_user_id="user",
        prompt="Create video for Test Product",
        product_query=lock["canonical_product_id"],
        project_id=created["project_id"],
        run_id=created["run_id"],
        approval_policy="require_user",
    )

    assert completed == {"status": "ok", "draft_mp4_path": str(draft_path)}


def test_acceptance_fixture_ids_are_not_embedded_in_production_workflow():
    root = Path(__file__).resolve().parents[2]
    paths = [
        root / "src" / "hermes" / "application" / "workflow.py",
        root / "src" / "hermes" / "channels" / "api" / "routes" / "video_factory.py",
        root / "apps" / "web" / "src" / "features" / "video-factory" / "VideoFactoryPage.tsx",
        root / "apps" / "web" / "src" / "features" / "product-research" / "ProductResearchStudio.tsx",
    ]
    forbidden = ("orig_baseus", "lock_baseus", "snap_baseus", "prod_baseus", "bowie ma10", "bowie wm02")
    offenders = []
    for path in paths:
        if path.exists():
            text = path.read_text(encoding="utf-8").lower()
            offenders.extend(f"{path.name}:{token}" for token in forbidden if token in text)
    assert offenders == []
