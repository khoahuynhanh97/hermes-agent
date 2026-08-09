"""VF-E2E Leg 6: final review approval (authorized) + B10 deterministic export.

No image/video regeneration. Creates final MP4 via canonical video.render,
then save_final_export -> ready_to_publish."""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

E2E_ROOT = Path(r"D:\work\hermes-agent-data\acceptance\vf-e2e")
DB_PATH = E2E_ROOT / "e2e.db"
WORKSPACE = E2E_ROOT / "workspace"
OWNER = "e2e_owner"
PROJECT_ID = "vfe2e_project"

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip("'").strip('"')
            if k and not os.environ.get(k):
                os.environ[k] = v

os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)
os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(DB_PATH)
ffmpeg = os.environ.get("FFMPEG_PATH", "")
if ffmpeg:
    os.environ["HERMES_FFMPEG_PATH"] = ffmpeg

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import ProjectStatus
from workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))
project = service.get_project(OWNER, PROJECT_ID)

# 1) Final review approval (authorized)
if project.final_approval.value != "approved":
    project = service.approve_final_video(OWNER, PROJECT_ID, "approved for VF-E2E export")
print("final_approval:", project.final_approval.value)
assert project.final_approval.value == "approved"

# 2) Deterministic final export from draft
if project.final_video_asset_id:
    print("final already exported:", project.final_video_asset_id)
else:
    draft_path = WORKSPACE / "videos" / "draft_video.mp4"
    assert draft_path.is_file(), "draft video missing"
    final_path = WORKSPACE / "videos" / "final_video.mp4"

    worker = CanonicalJobWorker(str(DB_PATH), str(WORKSPACE))
    repo = CanonicalJobRepository(str(DB_PATH))
    export_job = Job.new("video.render", {
        "owner_user_id": OWNER,
        "asset_id": str(draft_path),
        "output_path": str(final_path),
        "output_format": "mp4",
        "max_attempts": 3,
    })
    repo.submit(export_job)
    result = None
    for _ in range(10):
        result = worker.run_once()
        if result is None:
            print("NO_EXPORT_JOB_CLAIMED")
            raise SystemExit(2)
        if result["state"] in ("completed", "failed"):
            break
        time.sleep(3)
    print("export state:", result["state"])
    if result["state"] != "completed":
        print("export error:", (result.get("error") or "")[:400])
        raise SystemExit(2)

    project = service.save_final_export(OWNER, PROJECT_ID, "final_asset_1")
    print("final_asset:", project.final_video_asset_id)

final_path = WORKSPACE / "videos" / "final_video.mp4"
print("final export path:", final_path)
print("final export size:", final_path.stat().st_size if final_path.exists() else 0)
print("exists:", final_path.exists(), "non-empty:", final_path.exists() and final_path.stat().st_size > 0)
print("project status:", project.status.value)
print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
