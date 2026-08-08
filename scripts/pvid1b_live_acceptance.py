"""PVID1B live acceptance: one Veo image-to-video via canonical worker/job.

Loads .env without printing secrets, runs the video_generate job through the
worker with VIDEO_PROVIDER=google_vertex + model veo-3.1-generate-001,
using the PIMG1 storyboard image as the first frame.
"""
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and not os.environ.get(key):
            os.environ[key] = value

os.environ["VIDEO_PROVIDER"] = "google_vertex"
os.environ["VIDEO_MODEL"] = "veo-3.1-generate-001"
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.domain.job import Job
from workers.job_worker import CanonicalJobWorker

# PIMG1 storyboard image (first frame)
src_img = Path(r"C:\Users\ninak\AppData\Local\Temp\opencode\vf-ws\dbg3.png")
if not src_img.is_file():
    print("REFERENCE_IMAGE_MISSING", src_img)
    raise SystemExit(2)

db_dir = Path(tempfile.mkdtemp())
db_path = db_dir / "jobs.db"
workspace = db_dir / "workspace"
workspace.mkdir(parents=True, exist_ok=True)
ref_in_workspace = workspace / "frame.png"
shutil.copy2(src_img, ref_in_workspace)

worker = CanonicalJobWorker(str(db_path), str(workspace))
repo = CanonicalJobRepository(str(db_path))

job = Job.new("video_generate", {
    "owner_user_id": "pvid1b_owner",
    "request_id": "pvid1b_scene",
    "scene_id": "scene_1",
    "prompt": "A single blue water bottle on a clean table, the camera slowly pans around it, soft studio lighting",
    "duration_seconds": 4,
    "aspect_ratio": "9:16",
    "reference_image_paths": [str(ref_in_workspace)],
    "provider_options": {"resolution": "720p", "sampleCount": 1},
    "max_attempts": 200,
})
repo.submit(job)

# Run worker repeatedly until the job reaches a terminal state (single-shot async)
# Poll cadence lives in this driver (worker does one step per claim), not in Hermes.
max_claims = 200
result = None
print("job_id:", job.id)
for _ in range(max_claims):
    result = worker.run_once()
    if result is None:
        print("NO_JOB_CLAIMED")
        raise SystemExit(2)
    if result["state"] in ("completed", "failed"):
        break
    print("claim state:", result["state"], "| err:", (result.get("error") or "")[:60])
    time.sleep(15)

print("final state:", result["state"])
if result["state"] == "completed":
    payload = result["result"]
    out = Path(payload["output_path"])
    print("output_path:", out)
    print("exists:", out.exists())
    print("size_bytes:", out.stat().st_size if out.exists() else 0)
    print("provider:", payload.get("provider"))
    print("provider_operation_id:", payload.get("provider_operation_id"))
    print("scene_id:", payload.get("scene_id"))
else:
    print("error:", (result.get("error") or "")[:500])
