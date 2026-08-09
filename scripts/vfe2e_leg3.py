"""VF-E2E Leg 3: approve scene plan, build B5 storyboard, run 1 real image
generation via canonical worker/job. Stop at Storyboard HITL gate."""
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

os.environ["IMAGE_PROVIDER"] = "google_vertex"
os.environ["IMAGE_MODEL"] = os.environ.get("IMAGE_MODEL", "gemini-2.5-flash-image")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import (
    FramePrompt, ProjectStatus, Storyboard, StoryboardFrame,
)
from workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

# 1) Approve scene plan (authorized)
project = service.get_project(OWNER, PROJECT_ID)
if project.scene_plan_approval != "approved":
    project = service.approve_scene_plan(OWNER, PROJECT_ID)
print("scene_plan_approval:", project.scene_plan_approval, "status:", project.status.value)
assert project.status in (ProjectStatus.READY_FOR_STORYBOARD, ProjectStatus.STORYBOARD_READY)

# 2) B5 Storyboard: one frame for scene_1 (skip if already saved)
if project.storyboard is None:
    frame = StoryboardFrame(
        frame_id="frame_1",
        scene_id="scene_1",
        order=1,
        label="bottle_establish",
        purpose="Establish the blue water bottle on a clean table",
        visual_state="bottle centered on a clean table, soft studio lighting",
        subject_action="static",
        product_state="blue water bottle, centered, product identity preserved",
        character_state="",
        context="clean table, soft studio lighting",
        camera_intention="front, centered, 9:16",
        required_resource_ids=("asset_prod_1",),
        prompt=FramePrompt(
            positive_prompt=(
                "A single blue water bottle on a clean table, soft studio lighting, "
                "product-focused composition, centered, 9:16, no text, no watermark"
            ),
            negative_constraints="",
            product_identity_constraints="blue water bottle, clean minimal design, smooth body",
            composition="centered product shot",
            camera="front, eye level",
            lighting="soft studio lighting",
            environment="clean table, minimal background",
            action="none, static",
            reference_asset_ids=("asset_prod_1",),
            aspect_ratio="9:16",
            provider_options={},
        ),
        generation_status="planned",
    )
    storyboard = Storyboard(
        storyboard_id="storyboard_1",
        project_id=PROJECT_ID,
        frames=(frame,),
    )
    project = service.save_storyboard(OWNER, PROJECT_ID, storyboard)
else:
    frame = project.storyboard.frames[0]
    print("storyboard already saved, version:", project.storyboard.version)
assert project.status == ProjectStatus.STORYBOARD_READY

# 3) Canonical image_generate job -> worker -> real Gemini
worker = CanonicalJobWorker(str(DB_PATH), str(WORKSPACE))
repo = CanonicalJobRepository(str(DB_PATH))

ref_in_ws = WORKSPACE / "product_ref.png"
assert ref_in_ws.is_file(), f"missing product ref: {ref_in_ws}"

# Skip if this frame already has a completed generation
if frame.generated_asset_id and frame.generation_status.value == "completed":
    print("frame already generated:", frame.generated_asset_id)
    img_path = WORKSPACE / "images" / "vfe2e_frame_1.png"
    print("image size:", img_path.stat().st_size if img_path.exists() else 0)
else:
    job = Job.new("image_generate", {
        "owner_user_id": OWNER,
        "request_id": "vfe2e_frame_1",
        "prompt": frame.prompt.positive_prompt,
        "negative_prompt": "",
        "aspect_ratio": "9:16",
        "reference_image_paths": [str(ref_in_ws)],
        "max_attempts": 3,
    })
    repo.submit(job)

    image_result = None
    for _ in range(20):
        image_result = worker.run_once()
        if image_result is None:
            print("NO_IMAGE_JOB_CLAIMED")
            raise SystemExit(2)
        if image_result["state"] in ("completed", "failed"):
            break
        time.sleep(5)

    print("image job state:", image_result["state"])
    if image_result["state"] != "completed":
        print("image error:", (image_result.get("error") or "")[:400])
        raise SystemExit(2)

    img_payload = image_result["result"]
    img_path = Path(img_payload["output_paths"][0])
    print("generated image:", img_path)
    print("image size:", img_path.stat().st_size if img_path.exists() else 0)
    print("image provider:", img_payload.get("provider"))

    # 4) Persist frame generation result
    project = service.update_frame_generation_status(
        OWNER, PROJECT_ID, "frame_1", "completed",
        asset_id=f"frame_asset_frame_1",
        job_id=job.id,
    )
    frame_now = next(f for f in project.storyboard.frames if f.frame_id == "frame_1")
    print("frame status:", str(frame_now.generation_status), "asset:", frame_now.generated_asset_id)

print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
