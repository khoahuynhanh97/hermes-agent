from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from hermes.application.product_resource_service import ProductResourceService


def test_product_to_video_api_flow_renders_30_seconds(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "hermes-data"
    pi_root = tmp_path / "pi-data"
    db_path = data_root / "db" / "video-factory.sqlite"
    workspace = data_root / "workspaces" / "video-factory"
    image_path = pi_root / "ProductIntelligence" / "product_scout" / "images" / "product.jpg"
    image_path.parent.mkdir(parents=True)
    Image.new("RGB", (32, 32), "white").save(image_path)

    lock = {
        "status": "locked",
        "lock_id": "lock_fake_e2e",
        "resource_pack_id": "pack_fake_e2e",
        "resource_pack_version": 1,
        "snapshot_id": "snap_fake_e2e",
        "canonical_product_id": "product_fake_e2e",
        "owner_user_id": "user",
        "product_name": "Fake E2E Product",
        "assets": [{
            "asset_id": "asset_fake_e2e",
            "local_path": str(image_path),
            "physical_hash_filename": image_path.name,
            "mime_type": "image/jpeg",
        }],
    }
    lock["manifest_digest"] = ProductResourceService.compute_manifest_digest(lock)
    lock_path = pi_root / "ProductResearch" / "fake-e2e" / "machine" / "resource-pack-lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(json.dumps(lock), encoding="utf-8")
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("HERMES_DATA_DIR", str(data_root))
    monkeypatch.setenv("HERMES_PI_DATA_DIR", str(pi_root))
    monkeypatch.setenv("HERMES_DB_PATH", str(data_root / "db" / "hermes.sqlite"))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(db_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(workspace))
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    monkeypatch.setenv("TTS_PROVIDER", "fake")

    from hermes.channels.api.app import app
    from hermes.workers.job_worker import CanonicalJobWorker

    client = TestClient(app)
    project_id = "fake-e2e-30s"
    assert client.post("/api/vf/projects", json={"project_id": project_id}).status_code == 200
    assert client.post(
        f"/api/vf/projects/{project_id}/resources/bind",
        json={"product_query": lock["lock_id"]},
    ).status_code == 200
    assert client.post(f"/api/vf/projects/{project_id}/brief", json={
        "objective": "Create a concise product review",
        "target_audience": "Technology shoppers",
        "core_message": "Show the product clearly",
        "content_blocks": ["Hook", "Use case", "Highlights", "CTA"],
    }).status_code == 200
    assert client.post(f"/api/vf/projects/{project_id}/brief/approve").status_code == 200
    scenes = client.post(f"/api/vf/projects/{project_id}/scenes/approve")
    assert scenes.status_code == 200
    assert sum(scene["duration_seconds"] for scene in scenes.json()["data"]["scene_plan"]["scenes"]) == 30

    tts = client.post(f"/api/vf/projects/{project_id}/tts", json={
        "text": "A short product review voiceover.",
        "style_prompt": "Clear and natural.",
        "voice": "Zephyr",
    })
    storyboard = client.post(f"/api/vf/projects/{project_id}/storyboard/generate")
    assert tts.status_code == 202
    assert storyboard.status_code == 200

    worker = CanonicalJobWorker(str(db_path), str(workspace))
    while worker.run_once() is not None:
        pass
    project = client.get(f"/api/vf/projects/{project_id}").json()["data"]
    assert project["storyboard"]["approval_status"] == "approved"

    while worker.run_once() is not None:
        pass
    project = client.get(f"/api/vf/projects/{project_id}").json()["data"]
    assert len(project["generated_scenes"]) == 4
    assert all(scene["generation_status"] == "completed" for scene in project["generated_scenes"])

    render = client.post(f"/api/vf/projects/{project_id}/timeline/render")
    assert render.status_code == 200, render.text
    assert worker.run_once()["state"] == "completed"
    project = client.get(f"/api/vf/projects/{project_id}").json()["data"]
    assert project["draft_video_asset_id"]

    export = client.post(f"/api/vf/projects/{project_id}/final/export")
    assert export.status_code == 200, export.text
    assert worker.run_once()["state"] == "completed"
    project = client.get(f"/api/vf/projects/{project_id}").json()["data"]
    assert project["status"] == "ready_to_publish"

    final_path = data_root / "workspaces" / "projects" / project_id / "exports" / "final_video.mp4"
    assert final_path.is_file() and final_path.stat().st_size > 0
    from hermes.adapters.local.ffmpeg_capability import FFmpegCapability
    specs = FFmpegCapability().probe_media_file(str(final_path))
    assert 29.8 <= specs["duration_seconds"] <= 30.2
