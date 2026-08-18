from __future__ import annotations

import json
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
