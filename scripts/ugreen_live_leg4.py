"""UGREEN live run - Leg 4: approve storyboard, save video prompts,
run exactly 3 Veo image-to-video (from generated frames), apply_job each.
Stop at Final Review HITL gate."""
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
os.environ["VIDEO_PROVIDER"] = "google_vertex"
os.environ["VIDEO_MODEL"] = "veo-3.1-generate-001"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.pop("HERMES_ALLOW_FAKE_PROVIDERS", None)  # real only

OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import (
    GeneratedScene, ProjectStatus, VideoPrompt,
)
from workers.job_worker import CanonicalJobWorker

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(DB_PATH))))
project = service.get_project(OWNER, PROJECT_ID)
if project.storyboard.approval_status.value != "approved":
    project = service.approve_storyboard(OWNER, PROJECT_ID, "approved via live run")
print("storyboard:", project.storyboard.approval_status.value, "status:", project.status.value)

# frame -> generated image path
frame_img = {}
img_dir = WORKSPACE / "images"
for f in project.storyboard.frames:
    cand = img_dir / f"ugreen_{f.frame_id}.png"
    if cand.is_file():
        frame_img[f.scene_id] = str(cand)
print("frame images:", {k: Path(v).stat().st_size for k, v in frame_img.items()})

# B7 video prompts per scene + enqueue 3 Veo jobs
scene_prompts = {
    "scene_hook": "The camera slowly pushes in toward the charger on the desk, product centered, stable and calm",
    "scene_demo": "A USB-C cable is gently plugged into the charger, natural hand motion, gentle camera movement",
    "scene_cta": "Slow stable zoom toward the charger close-up, soft light, product centered",
}
scenes = project.scene_plan.scenes
worker = CanonicalJobWorker(DB_PATH, str(WORKSPACE))
repo = CanonicalJobRepository(DB_PATH)

jobs = []
for scene in scenes:
    vp = VideoPrompt(
        scene_id=scene.scene_id,
        duration_seconds=scene.duration_seconds,
        start_visual_state=scene.start_state,
        end_visual_state=scene.end_state,
        subject_action=scene.main_action,
        product_action="charger visible, identity preserved",
        camera_movement=scene.camera_intention,
        camera_framing="product-focused",
        environment_motion="none, calm",
        motion_constraints="gentle, stable",
        identity_constraints="UGREEN Nexode Robot UNO GaN charger, robot face",
        reference_frame_ids=tuple(f.frame_id for f in project.storyboard.frames if f.scene_id == scene.scene_id),
        provider_options={"resolution": "720p", "sampleCount": 1},
    )
    service.save_generated_scene(OWNER, PROJECT_ID, GeneratedScene(scene_id=scene.scene_id, video_prompt=vp))
    job = Job.new("video_generate", {
        "owner_user_id": OWNER,
        "request_id": f"ugreen_vid_{scene.scene_id}",
        "scene_id": scene.scene_id,
        "prompt": scene_prompts[scene.scene_id],
        "duration_seconds": scene.duration_seconds,
        "aspect_ratio": "9:16",
        "reference_image_paths": [frame_img[scene.scene_id]] if scene.scene_id in frame_img else [],
        "provider_options": {"resolution": "720p", "sampleCount": 1},
        "max_attempts": 300,
    })
    repo.submit(job)
    jobs.append((scene.scene_id, job.id))
print("enqueued Veo jobs:", jobs)

def _claim_once():
    for _ in range(30):
        res = worker.run_once()
        if res is not None:
            return res
        time.sleep(15)
    return None

def _wait_terminal(job_id, max_claims=300):
    result = None
    for _ in range(max_claims):
        result = worker.run_once()
        if result is None:
            time.sleep(15)
            continue
        if result["state"] in ("completed", "failed"):
            return result
        time.sleep(15)
    return result

completed = 0
for scene_id, job_id in jobs:
    res = _wait_terminal(job_id)
    if res is None:
        print("NO_TERMINAL", scene_id); raise SystemExit(2)
    if res["state"] != "completed":
        print("VEO FAIL", scene_id, res.get("error", "")[:400])
        raise SystemExit(2)
    vp = res["result"]
    service.update_scene_generation_status(OWNER, PROJECT_ID, scene_id, "completed",
                                           asset_id=f"scene_asset_{scene_id}", job_id=job_id,
                                           provider_operation_id=vp.get("provider_operation_id"))
    completed += 1
    print(f"[OK] scene {scene_id} -> scene_asset_{scene_id} | op {vp.get('provider_operation_id','')[:40]}")

print("videos completed:", completed, "/", len(scenes))
project = service.get_project(OWNER, PROJECT_ID)
for s in project.generated_scenes:
    print("  scene:", s.scene_id, str(s.generation_status), "asset:", s.generated_asset_id)
print("status:", project.status.value)
print("PROJECT_ID:", PROJECT_ID)
