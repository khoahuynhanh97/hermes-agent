"""VF-E2E Leg 5: B9 timeline composition + deterministic draft render.

Stops before B10 final review HITL gate."""
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
from hermes.domain.video_factory import (
    ProjectStatus, Timeline, TimelineClip,
)
from workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

project = service.get_project(OWNER, PROJECT_ID)
scene = next(s for s in project.generated_scenes if s.scene_id == "scene_1")
print("scene generation:", scene.generation_status.value, "asset:", scene.generated_asset_id)

# Locate the real generated scene video
videos = sorted((WORKSPACE / "videos").glob("*.mp4"))
if not videos:
    print("SCENE_VIDEO_MISSING")
    raise SystemExit(2)
scene_video = videos[0]
print("scene video:", scene_video, scene_video.stat().st_size)

# 1) B9 timeline referencing the generated asset by stable id
if project.timeline is None:
    timeline = Timeline(
        timeline_id="timeline_1",
        project_id=PROJECT_ID,
        clips=(
            TimelineClip(
                clip_id="clip_1",
                order=1,
                source_asset_id=scene.generated_asset_id or "scene_asset_scene_1",
                duration_seconds=4.0,
                transition="none",
            ),
        ),
    )
    project = service.save_timeline(OWNER, PROJECT_ID, timeline)
    print("timeline saved, status:", project.status.value)
else:
    print("timeline already saved, version:", project.timeline.version)
assert project.status == ProjectStatus.TIMELINE_READY

# 2) deterministic render via canonical video.render job
worker = CanonicalJobWorker(str(DB_PATH), str(WORKSPACE))
repo = CanonicalJobRepository(str(DB_PATH))

if project.draft_video_asset_id:
    print("draft already saved:", project.draft_video_asset_id)
else:
    project = service.update_timeline_status(OWNER, PROJECT_ID, "rendering")
    render_job = Job.new("video.render", {
        "owner_user_id": OWNER,
        "asset_id": str(scene_video),
        "output_path": str(WORKSPACE / "videos" / "draft_video.mp4"),
        "output_format": "mp4",
        "max_attempts": 3,
    })
    repo.submit(render_job)

    result = None
    for _ in range(10):
        result = worker.run_once()
        if result is None:
            print("NO_RENDER_JOB_CLAIMED")
            raise SystemExit(2)
        if result["state"] in ("completed", "failed"):
            break
        time.sleep(3)

    print("render state:", result["state"])
    if result["state"] != "completed":
        print("render error:", (result.get("error") or "")[:400])
        raise SystemExit(2)

    project = service.update_timeline_status(OWNER, PROJECT_ID, "completed")
    project = service.save_draft_video(OWNER, PROJECT_ID, "draft_asset_1")
    print("draft saved, status:", project.status.value, "draft_asset:", project.draft_video_asset_id)

draft_path = WORKSPACE / "videos" / "draft_video.mp4"
print("draft mp4:", draft_path, "size:", draft_path.stat().st_size if draft_path.exists() else 0)
print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
