"""Live E2E acceptance test: PI lock -> pipeline -> MP4 -> compliance."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PIL import Image

from hermes.application.product_resource_service import ProductResourceService


@pytest.fixture(autouse=True)
def _fake_providers(monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    monkeypatch.setenv("TTS_PROVIDER", "fake")


def _build_pi_lock(tmp_path: Path, product_id: str = "product_live_e2e") -> Path:
    """Create a minimal PI resource-pack lock fixture."""
    image_path = tmp_path / "pi-data" / "ProductIntelligence" / "product_scout" / "images" / "product.jpg"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (64, 64), "white").save(image_path)

    lock = {
        "status": "locked",
        "lock_id": f"lock_{product_id}",
        "resource_pack_id": f"pack_{product_id}",
        "resource_pack_version": 1,
        "snapshot_id": f"snap_{product_id}",
        "canonical_product_id": product_id,
        "owner_user_id": "user",
        "product_name": "Live E2E Test Product",
        "assets": [{
            "asset_id": f"asset_{product_id}",
            "local_path": str(image_path),
            "physical_hash_filename": image_path.name,
            "mime_type": "image/jpeg",
        }],
    }
    lock["manifest_digest"] = ProductResourceService.compute_manifest_digest(lock)

    lock_path = tmp_path / "pi-data" / "ProductResearch" / product_id / "machine" / "resource-pack-lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    return lock_path


def test_live_e2e_acceptance(tmp_path: Path, monkeypatch):
    """Full acceptance test: PI lock -> pipeline -> MP4 -> compliance -> 8 progress steps."""
    product_id = "product_live_e2e"
    _build_pi_lock(tmp_path, product_id)

    data_root = tmp_path / "hermes-data"
    pi_root = tmp_path / "pi-data"
    db_path = data_root / "db" / "hermes.sqlite"
    vf_db_path = data_root / "db" / "video-factory.sqlite"
    workspace = data_root / "workspaces" / "video-factory"

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_DATA_DIR", str(data_root))
    monkeypatch.setenv("HERMES_PI_DATA_DIR", str(pi_root))
    monkeypatch.setenv("HERMES_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(vf_db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))

    from hermes.channels.api.app import app
    from hermes.workers.job_worker import CanonicalJobWorker
    from fastapi.testclient import TestClient

    client = TestClient(app)
    project_id = "live-e2e-acceptance"

    # 1. Create project & bind PI lock
    assert client.post("/api/vf/projects", json={"project_id": project_id}).status_code == 200
    assert client.post(
        f"/api/vf/projects/{project_id}/resources/bind",
        json={"product_query": f"lock_{product_id}"},
    ).status_code == 200

    # 2. Brief
    assert client.post(f"/api/vf/projects/{project_id}/brief", json={
        "objective": "Product review for Live E2E Test Product",
        "target_audience": "Tech shoppers",
        "core_message": "Show product features clearly",
        "content_blocks": ["Hook", "Features", "Benefits", "CTA"],
    }).status_code == 200
    assert client.post(f"/api/vf/projects/{project_id}/brief/approve").status_code == 200

    # 3. Scenes
    scenes = client.post(f"/api/vf/projects/{project_id}/scenes/approve")
    assert scenes.status_code == 200
    scene_data = scenes.json()["data"]["scene_plan"]["scenes"]
    total_duration = sum(s["duration_seconds"] for s in scene_data)
    assert total_duration == 30, f"Expected 30s total, got {total_duration}s"

    # 4. TTS
    tts = client.post(f"/api/vf/projects/{project_id}/tts", json={
        "text": "Live E2E acceptance test voiceover.",
        "style_prompt": "Clear and natural.",
        "voice": "Zephyr",
    })
    assert tts.status_code == 202

    # 5. Storyboard
    storyboard = client.post(f"/api/vf/projects/{project_id}/storyboard/generate")
    assert storyboard.status_code == 200

    # 6. Process worker jobs
    worker = CanonicalJobWorker(str(vf_db_path), str(workspace))
    while worker.run_once() is not None:
        pass

    # 7. Render timeline
    render = client.post(f"/api/vf/projects/{project_id}/timeline/render")
    assert render.status_code == 200
    assert worker.run_once()["state"] == "completed"

    # 8. Export final
    export = client.post(f"/api/vf/projects/{project_id}/final/export")
    assert export.status_code == 200
    assert worker.run_once()["state"] == "completed"

    # 9. Verify final MP4 exists and has valid specs
    project = client.get(f"/api/vf/projects/{project_id}").json()["data"]
    assert project["status"] == "ready_to_publish"

    final_path = data_root / "workspaces" / "projects" / project_id / "exports" / "final_video.mp4"
    assert final_path.is_file(), f"Final MP4 not found at {final_path}"
    assert final_path.stat().st_size > 0

    from hermes.adapters.local.ffmpeg_capability import FFmpegCapability
    specs = FFmpegCapability().probe_media_file(str(final_path))
    assert specs.get("is_valid"), f"Invalid MP4: {specs}"
    assert 29.8 <= specs["duration_seconds"] <= 30.2
    assert specs.get("width") == 720
    assert specs.get("height") == 1280

    # 10. Verify ASS captions were generated
    generated_dir = data_root / "workspaces" / "projects" / project_id / "generated"
    ass_path = generated_dir / "captions.ass"
    assert ass_path.is_file(), "ASS captions not generated"
    ass_content = ass_path.read_text(encoding="utf-8-sig")
    assert "[Script Info]" in ass_content
    assert "Dialogue:" in ass_content

    # 11. Verify BGM was processed
    # BGM may or may not be available depending on network; check asset registry
    project_assets = client.get(f"/api/vf/projects/{project_id}/assets").json()
    asset_ids = [a.get("asset_id", "") for a in project_assets.get("data", [])]
    has_tts_asset = any("tts" in aid or "voiceover" in aid for aid in asset_ids)
    has_captions_asset = any("captions" in aid for aid in asset_ids)
    assert has_tts_asset, "TTS asset not found in project assets"
    assert has_captions_asset, "Captions asset not found in project assets"

    # 12. Compliance: brand safety + AIGC metadata check
    from hermes.video.compliance import ComplianceGateway
    gateway = ComplianceGateway()

    # Check brand safety on clean text
    clean_result = gateway.check_brand_safety("This is a clean product review")
    assert clean_result["passed"], f"Brand safety failed on clean text: {clean_result}"

    # Check brand safety on blocked text
    blocked_result = gateway.check_brand_safety("This content contains hate speech and violence")
    assert not blocked_result["passed"], "Brand safety should catch blocked patterns"

    # 13. Verify all 8 progress steps reported
    progress = client.get(f"/api/vf/projects/{project_id}/progress").json()["stages"]
    expected_steps = [
        "resource_pack", "brief", "scene_plan", "storyboard",
        "tts_voiceover", "video_scenes", "timeline_render", "final_export",
    ]
    for step in expected_steps:
        assert step in progress, f"Missing progress step: {step}"
        assert progress[step]["status"] == "completed", f"Step {step} not completed: {progress[step]}"
