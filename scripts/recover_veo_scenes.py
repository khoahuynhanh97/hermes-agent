"""Recover 3 UGREEN scene videos from completed operations (fetch, no new generation)."""
import os, sys, base64
from pathlib import Path
ROOT = Path(r"D:\work\hermes-agent"); sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip("'").strip('"')
            if k and not os.environ.get(k):
                os.environ[k] = v

from google.auth import default
from google.auth.transport import requests as ar
import requests as rq

creds, proj = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
creds.refresh(ar.Request()); tok = creds.token

fetch_url = ("https://us-central1-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628/"
             "locations/us-central1/publishers/google/models/veo-3.1-generate-001:fetchPredictOperation")
VIDEO_DIR = Path(r"D:\work\hermes-agent-data\workspaces\video-factory\videos")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)

OPERATIONS = [
    ("scene_hook", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/63774879-2406-4c62-9fae-e23b35365e81"),
    ("scene_demo", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/ad63fca8-d526-4ef3-b32c-3c5df78a170a"),
    ("scene_cta",  "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/7dac665c-541e-46d0-908b-059dfa76838f"),
]

for scene_id, op in OPERATIONS:
    r = rq.post(fetch_url, headers={"Authorization": f"Bearer {tok}"}, json={"operationName": op}, timeout=60)
    b = r.json()
    if not b.get("done"):
        print(f"{scene_id}: not done:", b.get("error", {}).get("message", "")[:120])
        continue
    resp = b.get("response", {})
    vids = resp.get("videos", [])
    if not vids:
        print(f"{scene_id}: no generatedVideos in response")
        continue
    data = vids[0].get("bytesBase64Encoded")
    if not data:
        print(f"{scene_id}: no video data")
        continue
    out = VIDEO_DIR / f"scene_{scene_id}.mp4"
    out.write_bytes(base64.b64decode(data))
    print(f"OK {scene_id}: {out} ({out.stat().st_size} bytes)")

print("recovered scene videos")
