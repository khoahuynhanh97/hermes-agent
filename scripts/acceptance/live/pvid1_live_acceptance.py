"""PVID1 live acceptance: one minimal Vertex Veo scene video via canonical job.

Loads .env without printing secrets, runs the video_generate job through the
worker with VIDEO_PROVIDER=google_vertex, then prints non-secret result or the
exact provider blocker.
"""
import os
import sys
import tempfile
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
os.environ["VIDEO_MODEL"] = os.environ.get("VIDEO_MODEL", "veo-3.0-preview")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("VIDEO_MAX_WAIT_SECONDS", "600")

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.domain.job import Job
from hermes.workers.job_worker import CanonicalJobWorker

db_dir = Path(tempfile.mkdtemp())
db_path = db_dir / "jobs.db"
workspace = db_dir / "workspace"

worker = CanonicalJobWorker(str(db_path), str(workspace))
repo = CanonicalJobRepository(str(db_path))

job = Job.new("video_generate", {
    "owner_user_id": "pvid1_owner",
    "request_id": "pvid1_scene",
    "scene_id": "scene_1",
    "prompt": "A single blue water bottle on a clean table, the camera slowly pans around it, soft studio lighting",
    "duration_seconds": 5,
    "aspect_ratio": "9:16",
})
repo.submit(job)
result = worker.run_once()

print("state:", result["state"])
if result["state"] == "completed":
    payload = result["result"]
    out = Path(payload["output_path"])
    print("output_path:", out)
    print("exists:", out.exists())
    print("size_bytes:", out.stat().st_size if out.exists() else 0)
    print("provider:", payload.get("provider"))
    print("provider_operation_id:", payload.get("provider_operation_id"))
else:
    print("error:", (result.get("error") or "")[:400])
