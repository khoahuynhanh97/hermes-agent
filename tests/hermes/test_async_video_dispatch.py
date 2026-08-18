from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from hermes.application.product_resource_service import ProductResourceService
from hermes.application.workflow import WorkflowOrchestrator
from hermes.tools.product_to_video_tool import _handle_product_to_video
from hermes.workers.job_worker import CanonicalJobWorker


def _setup_test_environment(monkeypatch, tmp_path: Path):
    data_root = tmp_path / "hermes-data"
    pi_root = tmp_path / "pi-data"
    db_path = data_root / "db" / "video_factory.sqlite"
    workspace = data_root / "workspaces" / "video-factory"
    image_path = pi_root / "ProductIntelligence" / "product_scout" / "images" / "product.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (32, 32), "blue").save(image_path)

    lock = {
        "status": "locked",
        "lock_id": "lock_async_test",
        "resource_pack_id": "pack_async_test",
        "resource_pack_version": 1,
        "snapshot_id": "snap_async_test",
        "canonical_product_id": "product_async_test",
        "owner_user_id": "user",
        "product_name": "Async Test Earbuds",
        "assets": [{
            "asset_id": "asset_async_test",
            "local_path": str(image_path),
            "physical_hash_filename": image_path.name,
            "mime_type": "image/jpeg",
        }],
    }
    lock["manifest_digest"] = ProductResourceService.compute_manifest_digest(lock)
    lock_path = pi_root / "ProductResearch" / "async-test" / "machine" / "resource-pack-lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
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

    return data_root, pi_root, db_path, workspace, lock


def test_orchestrator_async_dispatch_returns_queued_job(monkeypatch, tmp_path: Path):
    data_root, pi_root, db_path, workspace, lock = _setup_test_environment(monkeypatch, tmp_path)

    orchestrator = WorkflowOrchestrator(db_path)
    res = orchestrator.dispatch_product_to_video_workflow(
        owner_user_id="user",
        prompt="Tạo video review Async Test Earbuds",
        product_query=lock["lock_id"],
        duration_seconds=30,
    )

    assert res["status"] == "queued"
    assert res["state"] == "queued"
    assert res["job_id"].startswith("job_wf_")
    assert res["project_id"].startswith("vfp_")

    worker = CanonicalJobWorker(str(db_path), str(workspace))
    executed = worker.run_once()
    assert executed is not None
    assert executed["state"] == "completed"
    assert executed["result"]["status"] == "completed"
    assert Path(executed["result"]["output_path"]).is_file()


def test_product_to_video_tool_non_blocking_dispatch(monkeypatch, tmp_path: Path):
    data_root, pi_root, db_path, workspace, lock = _setup_test_environment(monkeypatch, tmp_path)

    raw_output = _handle_product_to_video(
        prompt="Tạo video review sản phẩm chất lượng cao",
        product_query=lock["lock_id"],
        async_dispatch=True,
    )

    parsed = json.loads(raw_output)
    assert parsed["status"] == "queued"
    assert parsed["job_id"].startswith("job_wf_")
    assert parsed["project_id"].startswith("vfp_")


def test_api_workflow_dispatch_and_progress_endpoint(monkeypatch, tmp_path: Path):
    data_root, pi_root, db_path, workspace, lock = _setup_test_environment(monkeypatch, tmp_path)
    from hermes.channels.api.app import app

    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    monkeypatch.setenv("TTS_PROVIDER", "fake")

    client = TestClient(app)

    # 1. Dispatch workflow via API
    dispatch_res = client.post(
        "/api/vf/workflow/dispatch",
        json={
            "prompt": "Tạo video review Async Test Earbuds 30s",
            "product_query": lock["lock_id"],
            "duration_seconds": 30,
        },
    )
    assert dispatch_res.status_code == 200, dispatch_res.text
    body = dispatch_res.json()
    assert body["status"] == "queued"
    job_id = body["job_id"]
    project_id = body["project_id"]

    # 2. Check initial project progress
    progress_res = client.get(f"/api/vf/projects/{project_id}/progress")
    assert progress_res.status_code == 200
    prog = progress_res.json()["stages"]
    assert prog["resource_pack"]["status"] == "completed"

    # 3. Check job status via /api/jobs/{job_id}
    job_check = client.get(f"/api/jobs/{job_id}")
    assert job_check.status_code == 200
    assert job_check.json()["status"] == "QUEUED"

    # 4. Worker executes the dispatched job
    worker = CanonicalJobWorker(str(db_path), str(workspace))
    worker.run_once()

    # 5. Check completed job status
    job_check_after = client.get(f"/api/jobs/{job_id}")
    assert job_check_after.status_code == 200
    assert job_check_after.json()["status"] == "SUCCEEDED"

    # 6. Check final progress breakdown
    final_prog_res = client.get(f"/api/vf/projects/{project_id}/progress")
    assert final_prog_res.status_code == 200
    final_prog = final_prog_res.json()["stages"]
    assert final_prog["resource_pack"]["status"] == "completed"
    assert final_prog["brief"]["status"] == "completed"
    assert final_prog["scene_plan"]["status"] == "completed"
    assert final_prog["storyboard"]["status"] == "approved"
    assert final_prog["tts_voiceover"]["status"] == "completed"
    assert final_prog["video_scenes"]["status"] == "completed"
    assert final_prog["timeline_render"]["status"] == "completed"
    assert final_prog["final_export"]["status"] == "completed"
