"""PIMG1B live acceptance: one minimal Vertex Gemini storyboard frame generation.

Loads .env without printing secrets, runs the canonical image_generate job
through the worker with IMAGE_PROVIDER=google_vertex, then prints non-secret
asset metadata or the exact blocker.
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

os.environ["IMAGE_PROVIDER"] = "google_vertex"
os.environ["IMAGE_MODEL"] = os.environ.get("IMAGE_MODEL", "gemini-3.1-flash-lite-image")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.domain.job import Job
from workers.job_worker import CanonicalJobWorker

db_dir = Path(tempfile.mkdtemp())
db_path = db_dir / "jobs.db"
workspace = db_dir / "workspace"

worker = CanonicalJobWorker(str(db_path), str(workspace))
repo = CanonicalJobRepository(str(db_path))

job = Job.new("image_generate", {
    "owner_user_id": "pimg1b_owner",
    "request_id": "pimg1b_storyboard_frame",
    "prompt": "Minimal 9:16 storyboard frame: a single blue water bottle on a clean table, soft studio lighting, product-focused composition, no text, no watermark",
    "negative_prompt": "text, watermark, logo, people",
    "aspect_ratio": "9:16",
})
repo.submit(job)
result = worker.run_once()

print("state:", result["state"])
if result["state"] == "completed":
    payload = result["result"]
    out = Path(payload["output_paths"][0])
    print("output_path:", out)
    print("exists:", out.exists())
    print("size_bytes:", out.stat().st_size if out.exists() else 0)
    print("provider:", payload.get("provider"))
    print("provider_operation_id:", payload.get("provider_operation_id"))
else:
    print("error:", (result.get("error") or "")[:500])
