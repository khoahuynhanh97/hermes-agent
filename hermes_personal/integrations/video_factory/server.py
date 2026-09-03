"""F1-F5 Video Factory MCP Server with canonical tools and Hermes wire compatibility."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any
from typing_extensions import TypedDict

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    from mcp.server import MCPServer as FastMCP

from hermes_personal.integrations.video_factory.repository import SQLiteVideoFactoryRepository
from hermes_personal.integrations.video_factory.service import VideoFactoryService
from hermes_personal.integrations.video_factory.domain import (
    AssetReference, Claim, ClaimStatus, CreativeBrief, FinalApprovalStatus,
    FrameGenerationStatus, FramePrompt, GeneratedScene, ProjectStatus, RawIdea,
    ResourceIdentity, ResourcePack, Scene, ScenePlan, Storyboard,
    StoryboardApprovalStatus, StoryboardFrame, Timeline, TimelineClip,
    TimelineStatus, VideoFactoryProject, VideoGenerationStatus, VideoPrompt,
)

mcp = FastMCP("video-factory")


from hermes_constants import get_hermes_home, display_hermes_home


def _db_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return get_hermes_home() / "data" / "video_factory.sqlite"


def _workspace_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return get_hermes_home() / "workspaces" / "video-factory"


def _service() -> VideoFactoryService:
    repo = SQLiteVideoFactoryRepository(_db_path())
    return VideoFactoryService(repo)


class VideoFactoryProjectSummary(TypedDict):
    project_id: str
    owner_user_id: str
    status: str
    brief_approval: str
    scene_plan_approval: str
    final_approval: str
    updated_at: str


def _project_summary(project: VideoFactoryProject) -> VideoFactoryProjectSummary:
    return VideoFactoryProjectSummary(
        project_id=project.id,
        owner_user_id=project.owner_user_id,
        status=project.status.value,
        brief_approval=project.brief_approval,
        scene_plan_approval=project.scene_plan_approval,
        final_approval=project.final_approval.value,
        updated_at=project.updated_at,
    )


class CreativeBriefInput(TypedDict, total=False):
    objective: str
    target_audience: str
    core_message: str
    tone: str
    pace: str
    cta: str
    content_blocks: list[str]
    verified_selling_points: list[dict[str, Any]]
    restrictions: list[str]
    required_content: list[str]
    platform: str
    aspect_ratio: str
    target_duration_seconds: int


class ResourcePackInput(TypedDict, total=False):
    id: str
    product_references: list[dict[str, Any]]
    primary_product_asset_id: str
    product_identity_description: str
    locked_product_identity: dict[str, Any]
    character_references: list[dict[str, Any]]
    primary_character_asset_id: str
    character_identity_description: str
    locked_character_identity: dict[str, Any]
    default_outfit: str
    context: str
    visual_style: str
    locked_at: str
    version: int


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    return value


def _result(project: VideoFactoryProject) -> dict[str, Any]:
    return {"ok": True, "project": _primitive(asdict(project))}


def _asset(value: dict[str, Any]) -> AssetReference:
    data = dict(value)
    data["metadata"] = data.get("metadata", {})
    return AssetReference(**data)


def _identity(value: dict[str, Any] | None) -> ResourceIdentity | None:
    if not value:
        return None
    data = dict(value)
    data["distinctive_features"] = tuple(data.get("distinctive_features", []))
    return ResourceIdentity(**data)


def _pack(value: dict[str, Any], owner_user_id: str) -> ResourcePack:
    data = dict(value)
    data["owner_user_id"] = owner_user_id
    data["product_references"] = tuple(_asset(item) for item in data.get("product_references", []))
    data["character_references"] = tuple(_asset(item) for item in data.get("character_references", []))
    data["locked_product_identity"] = _identity(data.get("locked_product_identity"))
    data["locked_character_identity"] = _identity(data.get("locked_character_identity"))
    return ResourcePack(**data)


def _idea(value: dict[str, Any]) -> RawIdea:
    data = dict(value)
    data["required_elements"] = tuple(data.get("required_elements", []))
    return RawIdea(**data)


def _brief(value: dict[str, Any]) -> CreativeBrief:
    data = dict(value)
    allowed = {
        "objective", "target_audience", "core_message", "tone", "pace", "cta",
        "content_blocks", "verified_selling_points", "restrictions",
        "required_content", "platform", "aspect_ratio", "target_duration_seconds",
    }
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise ValueError(
            "creative_brief contains unsupported fields: "
            f"{', '.join(unknown)}. Allowed fields: {', '.join(sorted(allowed))}"
        )
    required = (
        "objective", "target_audience", "core_message", "tone", "pace", "cta",
        "content_blocks",
    )
    missing = [key for key in required if not data.get(key)]
    if missing:
        raise ValueError("creative_brief missing required fields: " + ", ".join(missing))

    for key in required[:-1]:
        data[key] = str(data[key]).strip()
    content_blocks = data["content_blocks"]
    if not isinstance(content_blocks, (list, tuple)) or not all(
        isinstance(item, str) and item.strip() for item in content_blocks
    ):
        raise ValueError("creative_brief content_blocks must be a non-empty list of strings")
    data["content_blocks"] = tuple(content_blocks)

    for key in ("restrictions", "required_content"):
        data[key] = tuple(data.get(key, []))

    vsp = []
    for item in data.get("verified_selling_points", []):
        if not isinstance(item, dict) or not item.get("claim") or not item.get("status"):
            raise ValueError("creative_brief verified_selling_points entries require claim and canonical status")
        try:
            status = ClaimStatus(item["status"])
        except (TypeError, ValueError) as exc:
            raise ValueError("creative_brief verified_selling_points contains an invalid status") from exc
        vsp.append(
            Claim(
                claim=str(item["claim"]).strip(),
                status=status,
                evidence_refs=tuple(item.get("evidence_refs", [])),
                restriction_reason=str(item.get("restriction_reason", "")),
            )
        )
    data["verified_selling_points"] = tuple(vsp)
    return CreativeBrief(**data)


def _scene_plan(value: dict[str, Any]) -> ScenePlan:
    scenes = []
    for item in value.get("scenes", []):
        data = dict(item)
        data["required_resources"] = tuple(data.get("required_resources", []))
        scenes.append(Scene(**data))
    return ScenePlan(tuple(scenes))


def _frame_prompt(value: dict[str, Any] | None) -> FramePrompt | None:
    if not value:
        return None
    data = dict(value)
    data["reference_asset_ids"] = tuple(data.get("reference_asset_ids", []))
    data["provider_options"] = data.get("provider_options", {})
    return FramePrompt(**data)


def _storyboard_frame(value: dict[str, Any]) -> StoryboardFrame:
    data = dict(value)
    data["required_resource_ids"] = tuple(data.get("required_resource_ids", []))
    data["prompt"] = _frame_prompt(data.get("prompt"))
    data["generation_status"] = FrameGenerationStatus(data.get("generation_status", "planned"))
    return StoryboardFrame(**data)


def _storyboard(value: dict[str, Any]) -> Storyboard:
    data = dict(value)
    data["frames"] = tuple(_storyboard_frame(item) for item in data.get("frames", []))
    data["approval_status"] = StoryboardApprovalStatus(data.get("approval_status", "pending"))
    return Storyboard(**data)


def _video_prompt(value: dict[str, Any]) -> VideoPrompt:
    data = dict(value)
    data["reference_frame_ids"] = tuple(data.get("reference_frame_ids", []))
    data["provider_options"] = data.get("provider_options", {})
    return VideoPrompt(**data)


def _generated_scene(value: dict[str, Any]) -> GeneratedScene:
    data = dict(value)
    data["video_prompt"] = _video_prompt(data["video_prompt"])
    data["generation_status"] = VideoGenerationStatus(data.get("generation_status", "pending"))
    return GeneratedScene(**data)


def _timeline_clip(value: dict[str, Any]) -> TimelineClip:
    data = dict(value)
    data["audio_metadata"] = data.get("audio_metadata", {})
    return TimelineClip(**data)


def _timeline(value: dict[str, Any]) -> Timeline | None:
    if not value or not value.get("clips"):
        return None
    data = dict(value)
    data["clips"] = tuple(_timeline_clip(item) for item in data["clips"])
    data["status"] = TimelineStatus(data.get("status", "draft"))
    return Timeline(**data)


# ---------------------------------------------------------------------------
# 17 CANONICAL PUBLIC MCP TOOLS
# ---------------------------------------------------------------------------

def video_project_create(owner_user_id: str, project_id: str = "") -> dict[str, Any]:
    """Create a new Video Factory project for an owner."""
    return _result(_service().create_project(owner_user_id, project_id))


def video_project_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Get an existing Video Factory project by owner and project ID."""
    return _result(_service().get_project(owner_user_id, project_id))


def resource_pack_save(owner_user_id: str, project_id: str, resource_pack: ResourcePackInput) -> dict[str, Any]:
    """Save a Resource Pack with product references and identity description."""
    return _result(_service().save_resource_pack(owner_user_id, project_id, _pack(resource_pack, owner_user_id)))


def resource_pack_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Get the current Resource Pack for a project."""
    project = _service().get_project(owner_user_id, project_id)
    if project.resource_pack is None:
        raise ValueError("RESOURCE_PACK_NOT_FOUND")
    return _result(project)


def resource_pack_lock(
    owner_user_id: str,
    project_id: str,
    product_identity: dict[str, Any],
    character_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Lock resource pack identity descriptions before proceeding."""
    p_id = _identity(product_identity)
    if p_id is None:
        raise ValueError("product_identity is required")
    return _result(_service().lock_resource_pack(owner_user_id, project_id, p_id, _identity(character_identity)))


def resource_pack_unlock(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Unlock resource pack identity descriptions."""
    return _result(_service().unlock_resource_pack(owner_user_id, project_id))


def raw_idea_save(owner_user_id: str, project_id: str, raw_idea: dict[str, Any]) -> dict[str, Any]:
    """Save raw idea seed text for a project."""
    return _result(_service().save_raw_idea(owner_user_id, project_id, _idea(raw_idea)))


def creative_brief_save(owner_user_id: str, project_id: str, creative_brief: CreativeBriefInput) -> dict[str, Any]:
    """Save a Creative Brief using objective, target_audience, core_message,
    tone, pace, cta, and content_blocks. Optional fields are
    verified_selling_points, restrictions, required_content, platform,
    aspect_ratio, and target_duration_seconds.
    """
    return _result(_service().save_creative_brief(owner_user_id, project_id, _brief(creative_brief)))


def creative_brief_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Get the Creative Brief for a project."""
    project = _service().get_project(owner_user_id, project_id)
    if project.creative_brief is None:
        raise ValueError("CREATIVE_BRIEF_NOT_FOUND")
    return _result(project)


def creative_brief_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Approve the Creative Brief for a project."""
    return _result(_service().approve_creative_brief(owner_user_id, project_id))


def scene_plan_save(owner_user_id: str, project_id: str, scene_plan: dict[str, Any]) -> dict[str, Any]:
    """Save Scene Plan with structured scenes."""
    return _result(_service().save_scene_plan(owner_user_id, project_id, _scene_plan(scene_plan)))


def scene_plan_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Get the Scene Plan for a project."""
    project = _service().get_project(owner_user_id, project_id)
    if project.scene_plan is None:
        raise ValueError("SCENE_PLAN_NOT_FOUND")
    return _result(project)


def scene_plan_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Approve the Scene Plan for a project."""
    return _result(_service().approve_scene_plan(owner_user_id, project_id))


def storyboard_generate(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Generate or initialize storyboard frames from approved scene plan."""
    project = _service().get_project(owner_user_id, project_id)
    if not project.scene_plan:
        raise ValueError("SCENE_PLAN_NOT_FOUND")
    frames = []
    for idx, scene in enumerate(project.scene_plan.scenes, start=1):
        frames.append(
            StoryboardFrame(
                frame_id=f"frame_{idx:02d}",
                scene_id=scene.scene_id,
                order=idx,
                label=scene.title,
                purpose=scene.objective,
                visual_state=scene.start_state or scene.content,
                subject_action=scene.main_action,
                product_state="default",
                character_state="default",
                context=scene.context,
                camera_intention=scene.camera_intention,
            )
        )
    sb = Storyboard(storyboard_id=f"sb_{project_id}", project_id=project_id, frames=tuple(frames))
    return _result(_service().save_storyboard(owner_user_id, project_id, sb))


def timeline_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Retrieve the project timeline composition."""
    project = _service().get_project(owner_user_id, project_id)
    if project.timeline is None:
        raise ValueError("TIMELINE_NOT_FOUND")
    return _result(project)


def export_submit(owner_user_id: str, project_id: str) -> dict[str, Any]:
    """Submit the project timeline for final export rendering."""
    project = _service().get_project(owner_user_id, project_id)
    if not project.timeline:
        raise ValueError("TIMELINE_NOT_FOUND")
    return _result(_service().update_timeline_status(owner_user_id, project_id, TimelineStatus.RENDERING))


def video_factory_runtime_info() -> dict[str, Any]:
    """Return runtime diagnostic paths and configuration info."""
    db_file = _db_path()
    ws_dir = _workspace_path()
    return {
        "database_path": str(db_file.resolve()),
        "workspace_path": str(ws_dir.resolve()),
        "python_executable": sys.executable,
        "module_file": __file__,
        "canonical_tool_count": 17,
    }


# ---------------------------------------------------------------------------
# HERMES WIRE TOOLS COMPATIBILITY ADAPTERS
# ---------------------------------------------------------------------------

def create_brief(
    product_id: str = "",
    brief_config: dict[str, Any] | None = None,
    owner_user_id: str = "default_user",
    project_id: str = "",
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for create_creative_brief.

    Validates and persists caller-supplied creative brief inputs into durable
    VideoFactoryService state. Requires an existing project with a locked Resource Pack.
    Does not fabricate default marketing copy or synthetic resource pack provenance.
    """
    cfg = dict(brief_config or {})
    proj_id = project_id.strip() or f"proj_{product_id or 'default'}"
    srv = _service()

    required = ("objective", "target_audience", "core_message", "tone", "pace", "cta", "content_blocks")
    missing = [k for k in required if not str(cfg.get(k, "")).strip()]
    if missing:
        return {
            "ok": False,
            "status": "failed",
            "error": f"creative_brief missing required fields: {', '.join(missing)}",
            "code": "INVALID_INPUT",
        }

    try:
        project = srv.get_project(owner_user_id, proj_id)
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "error": f"PROJECT_NOT_FOUND: Project '{proj_id}' does not exist for owner '{owner_user_id}'",
            "code": "PROJECT_NOT_FOUND",
        }

    if not project.resource_pack or not project.resource_pack.locked_at:
        return {
            "ok": False,
            "status": "failed",
            "error": f"RESOURCE_PACK_LOCKED_REQUIRED: Project '{proj_id}' must have a locked Resource Pack before creating a creative brief",
            "code": "RESOURCE_PACK_LOCKED_REQUIRED",
        }

    try:
        brief = _brief(cfg)
        saved_project = srv.save_creative_brief(owner_user_id, proj_id, brief)
        brief_id = cfg.get("brief_id") or f"brief_{product_id or proj_id}"
        return {
            "ok": True,
            "brief_id": brief_id,
            "id": brief_id,
            "product_id": product_id,
            "project_id": proj_id,
            "objective": brief.objective,
            "target_audience": brief.target_audience,
            "core_message": brief.core_message,
            "script": brief.core_message,
            "tone": brief.tone,
            "pace": brief.pace,
            "cta": brief.cta,
            "content_blocks": list(brief.content_blocks),
            "project": _primitive(asdict(saved_project)),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "INVALID_INPUT",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "PERSISTENCE_ERROR",
        }


def create_scene_plan(
    brief_result: dict[str, Any] | None = None,
    owner_user_id: str = "default_user",
    project_id: str = "",
    scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for create_scene_plan.

    Persists caller-supplied scenes for a project with an approved Creative Brief.
    Does not auto-approve brief/scene plan or invent synthetic scene plans.
    """
    b_data = dict(brief_result or {})
    proj_id = project_id.strip() or b_data.get("project_id", "") or f"proj_{b_data.get('product_id', 'default')}"
    srv = _service()

    scenes_data = scenes or b_data.get("scenes") or b_data.get("steps")
    if not scenes_data or not isinstance(scenes_data, (list, tuple)):
        return {
            "ok": False,
            "status": "failed",
            "error": "scene_plan missing required caller-supplied scenes",
            "code": "INVALID_INPUT",
        }

    try:
        project = srv.get_project(owner_user_id, proj_id)
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "error": f"PROJECT_NOT_FOUND: Project '{proj_id}' does not exist for owner '{owner_user_id}'",
            "code": "PROJECT_NOT_FOUND",
        }

    if not project.creative_brief:
        return {
            "ok": False,
            "status": "failed",
            "error": f"CREATIVE_BRIEF_REQUIRED: Project '{proj_id}' must have a creative brief before creating a scene plan",
            "code": "CREATIVE_BRIEF_REQUIRED",
        }

    if project.brief_approval != "approved":
        return {
            "ok": False,
            "status": "failed",
            "error": f"BRIEF_APPROVAL_REQUIRED: Creative brief for project '{proj_id}' must be explicitly approved before creating scene plan",
            "code": "BRIEF_APPROVAL_REQUIRED",
        }

    try:
        scene_plan = _scene_plan({"scenes": scenes_data})
        saved_project = srv.save_scene_plan(owner_user_id, proj_id, scene_plan)
        sp_id = f"scene_{proj_id}"
        return {
            "ok": True,
            "scene_plan_id": sp_id,
            "id": sp_id,
            "scenes": [_primitive(asdict(s)) for s in scene_plan.scenes],
            "steps": [_primitive(asdict(s)) for s in scene_plan.scenes],
            "total_duration_seconds": scene_plan.total_duration_seconds,
            "project": _primitive(asdict(saved_project)),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "INVALID_INPUT",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "PERSISTENCE_ERROR",
        }


def create_storyboard(
    scene_plan_result: dict[str, Any] | None = None,
    owner_user_id: str = "default_user",
    project_id: str = "",
    frames: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for create_storyboard.

    Persists caller-supplied frames or generates frames from an explicitly approved
    Scene Plan. Does not auto-approve scene plans or fabricate unpersisted frames.
    """
    sp_data = dict(scene_plan_result or {})
    proj_id = project_id.strip() or sp_data.get("project_id", "") or "proj_default"
    srv = _service()

    try:
        project = srv.get_project(owner_user_id, proj_id)
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "error": f"PROJECT_NOT_FOUND: Project '{proj_id}' does not exist for owner '{owner_user_id}'",
            "code": "PROJECT_NOT_FOUND",
        }

    if not project.scene_plan:
        return {
            "ok": False,
            "status": "failed",
            "error": f"SCENE_PLAN_REQUIRED: Project '{proj_id}' must have a scene plan before creating a storyboard",
            "code": "SCENE_PLAN_REQUIRED",
        }

    if project.scene_plan_approval != "approved":
        return {
            "ok": False,
            "status": "failed",
            "error": f"SCENE_PLAN_APPROVAL_REQUIRED: Scene plan for project '{proj_id}' must be explicitly approved before creating storyboard",
            "code": "SCENE_PLAN_APPROVAL_REQUIRED",
        }

    try:
        frames_data = frames or sp_data.get("frames")
        if frames_data and isinstance(frames_data, (list, tuple)):
            sb = _storyboard({"storyboard_id": f"sb_{proj_id}", "project_id": proj_id, "frames": frames_data})
            saved_project = srv.save_storyboard(owner_user_id, proj_id, sb)
        else:
            storyboard_generate(owner_user_id, proj_id)
            saved_project = srv.get_project(owner_user_id, proj_id)

        sb_frames = saved_project.storyboard.frames if saved_project.storyboard else ()
        sb_id = f"sb_{proj_id}"
        return {
            "ok": True,
            "storyboard_id": sb_id,
            "id": sb_id,
            "frames": [_primitive(asdict(f)) for f in sb_frames],
            "scenes": [_primitive(asdict(f)) for f in sb_frames],
            "project": _primitive(asdict(saved_project)),
        }
    except ValueError as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "INVALID_INPUT",
        }
    except Exception as exc:
        return {
            "ok": False,
            "status": "failed",
            "error": str(exc),
            "code": "PERSISTENCE_ERROR",
        }


def _video_provider(
    provider_override: Any | None = None,
    output_dir: Path | str | None = None,
) -> Any | None:
    """Lazy provider constructor.

    Never mints tokens or performs I/O at import time.
    Returns None if provider is unconfigured or unavailable.
    """
    if provider_override is not None:
        return provider_override

    # Config / env resolution
    provider_name = os.environ.get("HERMES_VIDEO_FACTORY_PROVIDER", "").strip().lower()
    if not provider_name:
        try:
            from hermes_cli.config import load_config

            cfg = load_config()
            vf_cfg = cfg.get("video_factory") if isinstance(cfg, dict) else {}
            if isinstance(vf_cfg, dict):
                provider_name = str(vf_cfg.get("provider", "")).strip().lower()
        except Exception:
            provider_name = ""

    # If google_vertex is configured or vertex credentials exist
    if provider_name in ("google_vertex", "vertex", "vertex_ai"):
        try:
            from hermes_personal.integrations.video_factory.vertex_provider import VertexVideoProvider

            ws = Path(output_dir) if output_dir else _workspace_path()
            return VertexVideoProvider(output_dir=ws)
        except Exception:
            return None

    return None


def render(
    storyboard_result: dict[str, Any] | None = None,
    render_params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    owner_user_id: str = "default_user",
    project_id: str = "",
    provider: Any | None = None,
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for video rendering.

    Validates approved project storyboard and reference image before submitting
    to the configured video provider. Supports active_job_id for no-resubmit polling.
    """
    sb_data = dict(storyboard_result or {})
    params = dict(render_params or {})
    proj_id = project_id.strip() or sb_data.get("project_id", "") or "proj_default"

    # 1. Check for active_job_id resume (no-resubmit guarantee)
    active_job_id = params.get("active_job_id") or params.get("job_id")
    if active_job_id:
        return {
            "ok": True,
            "status": "pending",
            "job_id": active_job_id,
            "id": active_job_id,
            "render_id": f"render_{active_job_id.rsplit('/', 1)[-1]}",
        }

    # 2. Validate project state & storyboard approval
    srv = _service()
    try:
        project = srv.get_project(owner_user_id, proj_id)
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "error": f"PROJECT_NOT_FOUND: Project '{proj_id}' does not exist for owner '{owner_user_id}'",
            "code": "PROJECT_NOT_FOUND",
        }

    if not project.storyboard or not project.storyboard.frames:
        return {
            "ok": False,
            "status": "failed",
            "error": f"STORYBOARD_REQUIRED: Project '{proj_id}' must have a valid storyboard before rendering",
            "code": "STORYBOARD_REQUIRED",
        }

    if project.storyboard.approval_status != StoryboardApprovalStatus.APPROVED:
        return {
            "ok": False,
            "status": "failed",
            "error": f"STORYBOARD_APPROVAL_REQUIRED: Storyboard for project '{proj_id}' must be approved before rendering",
            "code": "STORYBOARD_APPROVAL_REQUIRED",
        }

    # 3. Resolve reference image and prompt from storyboard frames / params
    first_frame = project.storyboard.frames[0]
    prompt_text = params.get("prompt") or (
        getattr(first_frame.prompt, "positive_prompt", "") or getattr(first_frame.prompt, "prompt", "")
        if first_frame.prompt else ""
    )
    if not prompt_text and project.creative_brief:
        prompt_text = project.creative_brief.core_message

    ref_images: list[str] = []
    if params.get("reference_image_paths"):
        ref_images.extend(params["reference_image_paths"])
    elif first_frame.prompt and getattr(first_frame.prompt, "reference_image_assets", None):
        for ref in getattr(first_frame.prompt, "reference_image_assets", ()):
            if hasattr(ref, "uri") and ref.uri:
                ref_images.append(str(ref.uri))
            elif isinstance(ref, dict) and ref.get("uri"):
                ref_images.append(str(ref["uri"]))
            elif hasattr(ref, "path") and ref.path:
                ref_images.append(str(ref.path))
            elif isinstance(ref, dict) and ref.get("path"):
                ref_images.append(str(ref["path"]))

    # Also check project locked resource pack for asset file path
    if not ref_images and project.resource_pack and project.resource_pack.product_references:
        for prod_ref in project.resource_pack.product_references:
            if hasattr(prod_ref, "uri") and prod_ref.uri:
                ref_images.append(str(prod_ref.uri))
            elif isinstance(prod_ref, dict) and prod_ref.get("uri"):
                ref_images.append(str(prod_ref["uri"]))

    # Validate reference image exists on disk if provided
    valid_ref_images: list[str] = []
    for img_p in ref_images:
        cleaned = img_p.removeprefix("file://")
        if Path(cleaned).is_file():
            valid_ref_images.append(str(Path(cleaned).resolve()))

    # 4. Resolve video provider
    video_prov = _video_provider(provider_override=provider)
    if video_prov is None:
        return {
            "ok": False,
            "status": "failed",
            "error": "PROVIDER_UNAVAILABLE: No live video render provider configured or active",
            "code": "VF_PROVIDER_UNAVAILABLE",
        }

    # 5. Build request and submit
    from hermes_personal.integrations.video_factory.ports import VideoGenerationRequest

    req_id = idempotency_key or f"render_{proj_id}_{first_frame.frame_id}"
    duration = int(params.get("duration_seconds", 4))
    if duration not in (4, 6, 8):
        duration = 4
    aspect_ratio = str(params.get("aspect_ratio", "9:16"))

    req = VideoGenerationRequest(
        request_id=req_id,
        owner_user_id=owner_user_id,
        project_id=proj_id,
        scene_id=first_frame.scene_id,
        prompt=prompt_text or "Cinematic product showcase video",
        duration_seconds=duration,
        aspect_ratio=aspect_ratio if aspect_ratio in ("9:16", "16:9") else "9:16",
        reference_image_paths=tuple(valid_ref_images),
        provider_options=params.get("provider_options") or {},
    )

    result = video_prov.submit(req)
    if result.status == "submitted" and result.provider_operation_id:
        return {
            "ok": True,
            "status": "pending",
            "job_id": result.provider_operation_id,
            "id": result.provider_operation_id,
            "render_id": f"render_{result.provider_operation_id.rsplit('/', 1)[-1]}",
        }

    return {
        "ok": False,
        "status": "failed",
        "error": f"RENDER_SUBMIT_FAILED: {result.error_message or result.error_code}",
        "code": result.error_code or "RENDER_SUBMIT_FAILED",
    }


def get_job_status(
    job_id: str,
    provider: Any | None = None,
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for polling asynchronous video job status."""
    if not job_id or not str(job_id).strip():
        return {
            "ok": False,
            "status": "failed",
            "error": "MISSING_JOB_ID: job_id is required",
            "code": "MISSING_JOB_ID",
        }

    video_prov = _video_provider(provider_override=provider)
    if video_prov is None:
        return {
            "ok": False,
            "status": "failed",
            "job_id": job_id,
            "error": "PROVIDER_UNAVAILABLE: No live video render provider configured or active",
            "code": "VF_PROVIDER_UNAVAILABLE",
        }

    res = video_prov.get_status(job_id)
    if res.status == "running":
        return {
            "ok": True,
            "status": "running",
            "job_id": job_id,
            "id": job_id,
        }

    if res.status == "completed" and res.video_path:
        video_p = Path(res.video_path)
        if video_p.is_file() and video_p.stat().st_size > 0:
            render_id = f"render_{job_id.rsplit('/', 1)[-1]}"
            return {
                "ok": True,
                "status": "completed",
                "job_id": job_id,
                "id": render_id,
                "render_id": render_id,
                "video_url": f"file://{video_p.resolve()}",
                "output_url": f"file://{video_p.resolve()}",
                "file_path": str(video_p.resolve()),
                "file_size": video_p.stat().st_size,
            }
        return {
            "ok": False,
            "status": "failed",
            "job_id": job_id,
            "error": "EMPTY_OUTPUT: Generated video file is missing or empty",
            "code": "VF_EMPTY_OUTPUT",
        }

    return {
        "ok": False,
        "status": "failed",
        "job_id": job_id,
        "error": res.error_message or f"Operation failed with code {res.error_code}",
        "code": res.error_code or "VF_JOB_FAILED",
    }


def export(
    render_result: dict[str, Any] | None = None,
    export_params: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
    owner_user_id: str = "default_user",
    project_id: str = "",
) -> dict[str, Any]:
    """Hermes wire compatibility adapter for deterministic local video export.

    Promotes a completed, verified local MP4 from render output to workspace exports.
    Performs zero provider calls and is strictly idempotent.
    """
    rend_data = dict(render_result or {})
    params = dict(export_params or {})
    proj_id = project_id.strip() or rend_data.get("project_id", "") or "proj_default"

    # Extract source video path from render result
    raw_video_url = rend_data.get("video_url") or rend_data.get("output_url") or rend_data.get("file_path") or params.get("video_url")
    if not raw_video_url:
        return {
            "ok": False,
            "status": "failed",
            "error": "MISSING_RENDER_OUTPUT: render_result must contain video_url or file_path",
            "code": "MISSING_RENDER_OUTPUT",
        }

    src_path_str = str(raw_video_url).removeprefix("file://")
    src_path = Path(src_path_str).resolve()

    if not src_path.is_file() or src_path.stat().st_size == 0:
        return {
            "ok": False,
            "status": "failed",
            "error": f"FILE_NOT_FOUND: Source video file does not exist or is empty: {src_path}",
            "code": "FILE_NOT_FOUND",
        }

    if src_path.suffix.lower() != ".mp4":
        return {
            "ok": False,
            "status": "failed",
            "error": f"INVALID_FORMAT: Video file must be an .mp4 file, got '{src_path.suffix}'",
            "code": "INVALID_FORMAT",
        }

    # Verify workspace containment or promote to workspace exports directory
    ws_root = _workspace_path().resolve()
    export_dir = (ws_root / "exports").resolve()
    export_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"export_{proj_id}_{src_path.name}"
    dest_path = (export_dir / dest_filename).resolve()

    # Verify destination containment
    try:
        dest_path.relative_to(ws_root)
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "error": "PATH_TRAVERSAL: Export path escapes workspace directory",
            "code": "PATH_TRAVERSAL",
        }

    # Idempotent copy / link
    if dest_path != src_path:
        import shutil
        shutil.copy2(src_path, dest_path)

    export_id = idempotency_key or f"export_{proj_id}_{src_path.stem}"
    final_url = f"file://{dest_path.resolve()}"
    return {
        "ok": True,
        "status": "completed",
        "export_id": export_id,
        "id": export_id,
        "final_video_url": final_url,
        "video_url": final_url,
        "output_url": final_url,
        "file_path": str(dest_path.resolve()),
        "file_size": dest_path.stat().st_size,
    }


# ---------------------------------------------------------------------------
# TOOL REGISTRATION
# ---------------------------------------------------------------------------

CANONICAL_PUBLIC_TOOLS = (
    video_project_create,
    video_project_get,
    resource_pack_save,
    resource_pack_get,
    resource_pack_lock,
    resource_pack_unlock,
    raw_idea_save,
    creative_brief_save,
    creative_brief_get,
    creative_brief_approve,
    scene_plan_save,
    scene_plan_get,
    scene_plan_approve,
    storyboard_generate,
    timeline_get,
    export_submit,
    video_factory_runtime_info,
)

HERMES_WIRE_COMPATIBILITY_TOOLS = (
    create_brief,
    create_scene_plan,
    create_storyboard,
    render,
    export,
    get_job_status,
)

ALL_VIDEO_FACTORY_TOOLS = CANONICAL_PUBLIC_TOOLS + HERMES_WIRE_COMPATIBILITY_TOOLS

for _tool in ALL_VIDEO_FACTORY_TOOLS:
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()