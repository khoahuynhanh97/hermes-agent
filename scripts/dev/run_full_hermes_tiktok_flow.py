from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from hermes.adapters.local.ffmpeg_capability import FFmpegCapability
from hermes.application.product_resource_service import ProductResourceService
from hermes.workers.job_worker import CanonicalJobWorker


OWNER_USER_ID = "user"
PROJECT_ID = os.environ.get("HERMES_FULL_FLOW_PROJECT_ID", "tiktok-mic-full-flow")
PRODUCT_NAME = "Micro thu am khong day Type-C GoChek/K9 cho TikTok livestream"
LOCK_ID = "lock_tiktok_mic_gochek_k9"


def _runtime_paths() -> tuple[Path, Path, Path, Path]:
    repo_root = Path(__file__).resolve().parents[2]
    data_root = Path(
        os.environ.get("HERMES_DATA_DIR", repo_root / ".pytest-tmp" / "full-hermes-flow")
    ).resolve()
    pi_root = Path(
        os.environ.get("HERMES_PI_DATA_DIR", data_root / "pi-data")
    ).resolve()
    db_path = Path(
        os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", data_root / "db" / "video-factory.sqlite")
    ).resolve()
    workspace = Path(
        os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", data_root / "workspaces" / "video-factory")
    ).resolve()
    return data_root, pi_root, db_path, workspace


def _configure_environment(data_root: Path, pi_root: Path, db_path: Path, workspace: Path) -> None:
    os.environ.setdefault("HERMES_HOME", str(data_root / "hermes-home"))
    os.environ["HERMES_DATA_DIR"] = str(data_root)
    os.environ["HERMES_PI_DATA_DIR"] = str(pi_root)
    os.environ["HERMES_DB_PATH"] = str(data_root / "db" / "hermes.sqlite")
    os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(db_path)
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(workspace)
    os.environ["HERMES_ALLOW_FAKE_PROVIDERS"] = "1"
    os.environ["IMAGE_PROVIDER"] = "fake"
    os.environ["VIDEO_PROVIDER"] = "fake"
    os.environ["TTS_PROVIDER"] = "fake"
    (data_root / "db").mkdir(parents=True, exist_ok=True)
    (data_root / "hermes-home").mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)


def _force_fake_providers() -> None:
    """Keep this dev runner hermetic after API startup reloads dotenv files."""
    os.environ["HERMES_ALLOW_FAKE_PROVIDERS"] = "1"
    os.environ["IMAGE_PROVIDER"] = "fake"
    os.environ["VIDEO_PROVIDER"] = "fake"
    os.environ["TTS_PROVIDER"] = "fake"


def _write_reference_image(pi_root: Path) -> Path:
    image_path = pi_root / "ProductIntelligence" / "tiktok_shop" / "images" / "micro-gochek-k9.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (720, 1280), "#f5f7fb")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((210, 260, 510, 940), radius=48, fill="#101820", outline="#303b4d", width=6)
    draw.rounded_rectangle((255, 335, 465, 465), radius=28, fill="#232f3f")
    draw.ellipse((315, 520, 405, 610), fill="#e8eef7", outline="#ffffff", width=4)
    draw.rounded_rectangle((290, 690, 430, 770), radius=22, fill="#e8eef7")
    draw.line((360, 940, 360, 1080), fill="#111827", width=10)
    draw.rounded_rectangle((300, 1080, 420, 1135), radius=14, fill="#111827")
    image.save(image_path, quality=92)
    return image_path


def _write_resource_pack_lock(pi_root: Path, image_path: Path) -> dict:
    lock = {
        "status": "locked",
        "lock_id": LOCK_ID,
        "resource_pack_id": "pack_tiktok_mic_gochek_k9",
        "resource_pack_version": 1,
        "snapshot_id": "snap_tiktok_mic_gochek_k9_20260818",
        "canonical_product_id": "tiktok-mic-gochek",
        "owner_user_id": OWNER_USER_ID,
        "product_name": PRODUCT_NAME,
        "brand": "GoChek/K9",
        "identity_constraints": {
            "brand": "GoChek/K9",
            "model": "Type-C wireless lavalier microphone",
            "product_type": "wireless microphone",
            "variant": "black compact clip-on mic with Type-C receiver",
            "distinctive_features": [
                "small clip-on transmitter",
                "Type-C receiver",
                "compact black body",
            ],
        },
        "assets": [
            {
                "asset_id": "asset_tiktok_mic_gochek_k9_ref",
                "local_path": str(image_path),
                "physical_hash_filename": image_path.name,
                "mime_type": "image/jpeg",
                "media_role": "original",
                "match_confidence": 1.0,
            }
        ],
    }
    lock["manifest_digest"] = ProductResourceService.compute_manifest_digest(lock)
    lock_path = pi_root / "ProductResearch" / "tiktok-mic-gochek" / "machine" / "resource-pack-lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, ensure_ascii=False, indent=2), encoding="utf-8")
    return lock


def _post_ok(client: TestClient, path: str, body: dict | None = None, expected: int = 200) -> dict:
    response = client.post(path, json=body) if body is not None else client.post(path)
    if response.status_code != expected:
        raise RuntimeError(f"{path} failed: {response.status_code} {response.text}")
    return response.json()


def _drain_worker(db_path: Path, workspace: Path) -> list[dict]:
    worker = CanonicalJobWorker(str(db_path), str(workspace))
    results = []
    while True:
        result = worker.run_once()
        if result is None:
            break
        results.append(dict(result))
    return results


def main() -> int:
    data_root, pi_root, db_path, workspace = _runtime_paths()
    _configure_environment(data_root, pi_root, db_path, workspace)
    image_path = _write_reference_image(pi_root)
    lock = _write_resource_pack_lock(pi_root, image_path)

    from hermes.channels.api.app import app
    _force_fake_providers()

    client = TestClient(app)
    _post_ok(client, "/api/vf/projects", {"project_id": PROJECT_ID})
    _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/resources/bind", {"product_query": lock["lock_id"]})
    _post_ok(
        client,
        f"/api/vf/projects/{PROJECT_ID}/brief",
        {
            "objective": "Create a 30-second TikTok affiliate product review",
            "target_audience": "Vietnamese TikTok creators, livestream sellers, students, and office workers",
            "core_message": "Show how a low-cost Type-C wireless microphone improves short-form video audio",
            "content_blocks": ["Hook", "Audio problem", "Before-after demo", "Who should buy", "CTA"],
        },
    )
    _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/brief/approve")
    _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/scenes/approve")
    _post_ok(
        client,
        f"/api/vf/projects/{PROJECT_ID}/tts",
        {
            "text": (
                "Thu am clip bi re thi dung voi doi dien thoai. Gan micro Type-C, "
                "quay lai cung mot canh, nghe so sanh truoc va sau, roi kiem tra "
                "gia live tren TikTok Shop truoc khi mua."
            ),
            "style_prompt": "Fast, clear, practical Vietnamese TikTok review voice",
            "voice": "Zephyr",
        },
        expected=202,
    )
    storyboard = _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/storyboard/generate")
    worker_results_1 = _drain_worker(db_path, workspace)
    progress_after_storyboard = client.get(f"/api/vf/projects/{PROJECT_ID}/progress").json()
    worker_results_2 = _drain_worker(db_path, workspace)
    progress_after_video = client.get(f"/api/vf/projects/{PROJECT_ID}/progress").json()
    _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/timeline/render")
    worker_results_3 = _drain_worker(db_path, workspace)
    progress_after_render = client.get(f"/api/vf/projects/{PROJECT_ID}/progress").json()
    _post_ok(client, f"/api/vf/projects/{PROJECT_ID}/final/export")
    worker_results_4 = _drain_worker(db_path, workspace)
    final_progress = client.get(f"/api/vf/projects/{PROJECT_ID}/progress").json()
    project = client.get(f"/api/vf/projects/{PROJECT_ID}").json()["data"]

    final_path = data_root / "workspaces" / "projects" / PROJECT_ID / "exports" / "final_video.mp4"
    specs = FFmpegCapability().probe_media_file(str(final_path)) if final_path.exists() else {}
    result = {
        "project_id": PROJECT_ID,
        "product_name": PRODUCT_NAME,
        "resource_pack_lock_id": lock["lock_id"],
        "storyboard_jobs": storyboard.get("jobs", []),
        "worker_jobs_completed": len(worker_results_1) + len(worker_results_2) + len(worker_results_3) + len(worker_results_4),
        "progress_after_storyboard": progress_after_storyboard.get("stages", {}),
        "progress_after_video": progress_after_video.get("stages", {}),
        "progress_after_render": progress_after_render.get("stages", {}),
        "final_progress": final_progress,
        "project_status": project.get("status"),
        "draft_video_asset_id": project.get("draft_video_asset_id"),
        "final_video_asset_id": project.get("final_video_asset_id"),
        "final_video_path": str(final_path),
        "final_video_exists": final_path.is_file(),
        "final_video_bytes": final_path.stat().st_size if final_path.exists() else 0,
        "video_specs": specs,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
