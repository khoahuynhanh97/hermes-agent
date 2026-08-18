import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from uuid import uuid4


JOB_STATUSES = ["pending", "planning", "running", "completed", "failed"]
ENGINES = [
    "ai_studio",
    "html_video",
    "mixed",
    "capcut",
    "learn_video",
    "learn_knowledge",
    "learn_hook_cta",
    "upgrade_audit",
]
DEFAULT_OUTPUTS = [
    "analysis.md",
    "product_lock.md",
    "storyboard.md",
    "image_prompts.md",
    "video_prompts.md",
    "workflow.json",
    "capcut_plan.md",
]
DEFAULT_CONSTRAINTS = {
    "aspect_ratio": "9:16",
    "scene_count": 4,
    "duration_per_scene": 8,
    "same_product": True,
    "same_background": True,
    "no_watermark": True,
    "no_text_in_video": True,
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def new_job_id():
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"job_{stamp}_{uuid4().hex[:6]}"


def create_manifest(
    job_type="tiktok_product_review",
    engine="ai_studio",
    input_data=None,
    objective="Create a TikTok content package",
    constraints=None,
    outputs_required=None,
    job_id=None,
):
    """Create a normalized Hermes Job Manifest dict."""
    if engine not in ENGINES:
        engine = "mixed"

    created_at = now_iso()
    normalized_input = {
        "product_name": "",
        "product_color": "",
        "product_images": [],
        "reference_video": "",
        "tiktok_url": "",
        "language": "vi",
        "target_platform": "tiktok",
    }
    normalized_input.update(input_data or {})

    normalized_constraints = deepcopy(DEFAULT_CONSTRAINTS)
    normalized_constraints.update(constraints or {})

    return {
        "schema_version": 1,
        "job_id": job_id or new_job_id(),
        "job_type": job_type,
        "engine": engine,
        "status": "pending",
        "input": normalized_input,
        "objective": objective,
        "constraints": normalized_constraints,
        "outputs_required": outputs_required or list(DEFAULT_OUTPUTS),
        "tasks": [],
        "artifacts": [],
        "created_at": created_at,
        "updated_at": created_at,
    }


def save_manifest(path, manifest):
    manifest = dict(manifest)
    manifest["updated_at"] = now_iso()
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_manifest(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def set_manifest_status(manifest, status):
    if status not in JOB_STATUSES:
        raise ValueError(f"Invalid manifest status: {status}")
    manifest["status"] = status
    manifest["updated_at"] = now_iso()
    return manifest
