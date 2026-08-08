"""UGREEN live run - Leg 3: approve scene plan, save storyboard (3 frames),
run exactly 3 Gemini Image generations (reference = real product image),
apply_job each. Stop at Storyboard HITL gate."""
import os, sys, time, json
from pathlib import Path
ROOT = Path(r"D:\work\hermes-agent"); sys.path.insert(0, str(ROOT))

DB_PATH = r"D:\work\hermes-agent-data\db\video_factory.sqlite"
WORKSPACE = Path(r"D:\work\hermes-agent-data\workspaces\video-factory")

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip("'").strip('"')
            if k and not os.environ.get(k):
                os.environ[k] = v

os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = DB_PATH
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)
os.environ["IMAGE_PROVIDER"] = "google_vertex"
os.environ["IMAGE_MODEL"] = "gemini-2.5-flash-image"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.pop("HERMES_ALLOW_FAKE_PROVIDERS", None)  # real provider only

OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import FramePrompt, ProjectStatus, Storyboard, StoryboardFrame
from workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(DB_PATH))))
project = service.get_project(OWNER, PROJECT_ID)
if project.scene_plan_approval != "approved":
    project = service.approve_scene_plan(OWNER, PROJECT_ID)
print("scene_plan:", project.scene_plan_approval, "status:", project.status.value)

# resource asset -> real path map (workspace containment)
asset_to_path = {}
for ref in project.resource_pack.product_references:
    rel = (ref.uri or "").removeprefix("asset://")
    candidate = (WORKSPACE / rel).resolve()
    if candidate.is_file():
        asset_to_path[ref.asset_id] = str(candidate)

# B5 storyboard: one frame per scene
frame_specs = [
    ("frame_hook_01", "scene_hook",
     "A single UGREEN Nexode Robot UNO GaN charger standing on a clean desk, robot face LED visible, "
     "soft studio lighting, product-focused hero shot, centered, 9:16, no text, no watermark"),
    ("frame_demo_01", "scene_demo",
     "A UGREEN Nexode Robot UNO GaN charger on a clean desk with a USB-C cable connected, phone nearby, "
     "soft studio lighting, natural product-use scene, 9:16, no text, no watermark"),
    ("frame_cta_01", "scene_cta",
     "A clean close-up beauty shot of the UGREEN Nexode Robot UNO GaN charger, robot face LED, "
     "soft studio lighting, product-centered, 9:16, no text, no watermark"),
]

frames = []
for frame_id, scene_id, prompt in frame_specs:
    refs = project.resource_pack.product_references[0].asset_id  # primary reference for identity
    frames.append(StoryboardFrame(
        frame_id=frame_id, scene_id=scene_id, order=len(frames) + 1, label=frame_id,
        purpose=prompt[:60], visual_state="product on clean desk", subject_action="static",
        product_state="UGREEN charger, identity preserved", character_state="", context="clean desk, soft light",
        camera_intention="product-focused", required_resource_ids=(refs,),
        prompt=FramePrompt(
            positive_prompt=prompt, negative_constraints="",
            product_identity_constraints="UGREEN Nexode Robot UNO GaN charger, robot face, keep product identity",
            composition="centered product shot", camera="product hero", lighting="soft studio lighting",
            environment="clean desk, minimal background", action="none, static",
            reference_asset_ids=(refs,), aspect_ratio="9:16", provider_options={},
        ),
        generation_status="planned",
    ))

if project.storyboard is None:
    project = service.save_storyboard(OWNER, PROJECT_ID, Storyboard(
        storyboard_id="storyboard_live", project_id=PROJECT_ID, frames=tuple(frames)))
else:
    print("storyboard already saved, version:", project.storyboard.version)
project = service.get_project(OWNER, PROJECT_ID)
print("storyboard frames:", [(f.frame_id, f.scene_id) for f in project.storyboard.frames])

# Run 3 Gemini image jobs (exactly one per planned frame), real provider
worker = CanonicalJobWorker(DB_PATH, str(WORKSPACE))
repo = CanonicalJobRepository(DB_PATH)
jobs = []
for frame in project.storyboard.frames:
    if frame.generated_asset_id and frame.generation_status.value == "completed":
        print("skip already-generated:", frame.frame_id)
        continue
    refs_paths = [asset_to_path[r] for r in frame.required_resource_ids if r in asset_to_path]
    job = Job.new("image_generate", {
        "owner_user_id": OWNER,
        "request_id": f"ugreen_{frame.frame_id}",
        "prompt": frame.prompt.positive_prompt,
        "negative_prompt": "",
        "aspect_ratio": "9:16",
        "reference_image_paths": refs_paths,
        "max_attempts": 1,
    })
    repo.submit(job)
    jobs.append((frame.frame_id, job.id))
print("enqueued image jobs:", jobs)

def _claim_once():
    for _ in range(30):
        res = worker.run_once()
        if res is not None:
            return res
        time.sleep(0.5)
    return None

completed = 0
for frame_id, job_id in jobs:
    res = _claim_once()
    if res is None:
        print("NO_CLAIM", frame_id); continue
    if res["state"] != "completed":
        print("IMAGE FAIL", frame_id, res.get("error", "")[:300])
        raise SystemExit(2)
    # apply_job equivalent: update frame status from completed job
    service.update_frame_generation_status(OWNER, PROJECT_ID, frame_id, "completed",
                                           asset_id=f"frame_asset_{frame_id}", job_id=job_id)
    completed += 1
    print(f"[OK] frame {frame_id} -> frame_asset_{frame_id}")

print("images completed:", completed, "/", len(frame_specs))
project = service.get_project(OWNER, PROJECT_ID)
for f in project.storyboard.frames:
    print("  frame:", f.frame_id, str(f.generation_status), "asset:", f.generated_asset_id)
print("status:", project.status.value)
print("PROJECT_ID:", PROJECT_ID)
