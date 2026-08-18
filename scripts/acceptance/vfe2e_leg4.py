"""VF-E2E Leg 4: approve storyboard, save B7 video prompt, run 1 real Veo
generation (image-to-video from approved frame) via canonical worker/job.
Stops at next HITL gate."""
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

os.environ["VIDEO_PROVIDER"] = "google_vertex"
os.environ["VIDEO_MODEL"] = "veo-3.1-generate-001"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import (
    GeneratedScene, ProjectStatus, VideoPrompt,
)
from hermes.workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

# 1) Approve storyboard (authorized)
project = service.get_project(OWNER, PROJECT_ID)
if project.storyboard is None:
    print("STORYBOARD_MISSING")
    raise SystemExit(2)
if project.storyboard.approval_status.value != "approved":
    project = service.approve_storyboard(OWNER, PROJECT_ID, "approved for VF-E2E")
print("storyboard approval:", project.storyboard.approval_status.value, "status:", project.status.value)
assert project.status == ProjectStatus.STORYBOARD_APPROVED

# Approved storyboard frame -> video first frame
frame = project.storyboard.frames[0]
approved_frame_path = WORKSPACE / "images" / "vfe2e_frame_1.png"
if not approved_frame_path.is_file():
    # locate any generated frame image in workspace/images
    candidates = list((WORKSPACE / "images").glob("*.png"))
    if not candidates:
        print("FRAME_IMAGE_MISSING")
        raise SystemExit(2)
    approved_frame_path = candidates[0]
print("video first frame:", approved_frame_path, "size:", approved_frame_path.stat().st_size)

# 2) B7 video prompt per scene
video_prompt = VideoPrompt(
    scene_id="scene_1",
    duration_seconds=4,
    start_visual_state="bottle centered on a clean table",
    end_visual_state="bottle centered on a clean table",
    subject_action="bottle stands still",
    product_action="bottle visible, identity preserved",
    camera_movement="slow pan around the bottle",
    camera_framing="medium, product-focused",
    environment_motion="none, calm",
    motion_constraints="gentle, stable",
    identity_constraints="blue water bottle, clean minimal design, smooth body",
    reference_frame_ids=(frame.frame_id,),
    dialogue_or_vo="",
    negative_constraints="",
    provider_options={"resolution": "720p", "sampleCount": 1},
)
scene = GeneratedScene(
    scene_id="scene_1",
    video_prompt=video_prompt,
)
project = service.save_generated_scene(OWNER, PROJECT_ID, scene)
print("generated scene saved, status:", project.status.value)
assert project.status == ProjectStatus.SCENES_GENERATED

# 3) Canonical video_generate job -> worker -> real Veo
worker = CanonicalJobWorker(str(DB_PATH), str(WORKSPACE))
repo = CanonicalJobRepository(str(DB_PATH))

# skip if scene already has a completed video
existing = next((s for s in project.generated_scenes if s.scene_id == "scene_1"), None)
if existing and existing.generated_asset_id and existing.generation_status.value == "completed":
    print("scene video already generated:", existing.generated_asset_id)
    video_out = list((WORKSPACE / "videos").glob("*.mp4"))
    for v in video_out:
        print("existing mp4:", v, v.stat().st_size)
else:
    job = Job.new("video_generate", {
        "owner_user_id": OWNER,
        "request_id": "vfe2e_scene_1",
        "scene_id": "scene_1",
        "prompt": (
            "A single blue water bottle on a clean table, the camera slowly pans "
            "around it, soft studio lighting"
        ),
        "duration_seconds": 4,
        "aspect_ratio": "9:16",
        "reference_image_paths": [str(approved_frame_path)],
        "provider_options": {"resolution": "720p", "sampleCount": 1},
        "max_attempts": 200,
    })
    repo.submit(job)

    result = None
    for _ in range(200):
        result = worker.run_once()
        if result is None:
            print("NO_VIDEO_JOB_CLAIMED")
            raise SystemExit(2)
        if result["state"] in ("completed", "failed"):
            break
        time.sleep(15)

    print("video job state:", result["state"])
    if result["state"] != "completed":
        print("video error:", (result.get("error") or "")[:500])
        raise SystemExit(2)

    vp = result["result"]
    vpath = Path(vp["output_path"])
    print("generated video:", vpath)
    print("video size:", vpath.stat().st_size if vpath.exists() else 0)
    print("video provider:", vp.get("provider"))
    print("video op:", vp.get("provider_operation_id"))

    # persist scene generation result
    project = service.update_scene_generation_status(
        OWNER, PROJECT_ID, "scene_1", "completed",
        asset_id=f"scene_asset_scene_1",
        job_id=job.id,
        provider_operation_id=vp.get("provider_operation_id"),
    )

print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
