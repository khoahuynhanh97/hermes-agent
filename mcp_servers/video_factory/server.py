from __future__ import annotations

import os
import sys
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from mcp.server.fastmcp import FastMCP

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.config import get_data_path
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, Claim, ClaimStatus, CreativeBrief, FinalApprovalStatus,
    FrameGenerationStatus, FramePrompt, GeneratedScene, RawIdea, ResourceIdentity,
    ResourcePack, Scene, ScenePlan, Storyboard, StoryboardApprovalStatus,
    StoryboardFrame, Timeline, TimelineClip, TimelineStatus,
    VideoGenerationStatus, VideoPrompt,
)


mcp = FastMCP("hermes-video-factory")


class AssetReferenceInput(TypedDict):
    asset_id: str
    uri: str
    metadata: NotRequired[dict[str, Any]]


class ResourcePackInput(TypedDict):
    product_references: list[AssetReferenceInput]
    primary_product_asset_id: str
    product_identity_description: str
    id: NotRequired[str]
    character_references: NotRequired[list[AssetReferenceInput]]
    primary_character_asset_id: NotRequired[str]
    character_identity_description: NotRequired[str]
    default_outfit: NotRequired[str]
    context: NotRequired[str]
    visual_style: NotRequired[str]


class CreativeBriefClaimInput(TypedDict):
    claim: str
    status: str
    evidence_refs: NotRequired[list[str]]
    restriction_reason: NotRequired[str]


class CreativeBriefInput(TypedDict):
    objective: str
    target_audience: str
    core_message: str
    tone: str
    pace: str
    cta: str
    content_blocks: list[str]
    verified_selling_points: NotRequired[list[CreativeBriefClaimInput]]
    restrictions: NotRequired[list[str]]
    required_content: NotRequired[list[str]]
    platform: NotRequired[str]
    aspect_ratio: NotRequired[str]
    target_duration_seconds: NotRequired[int]


# F1 tools (existing)

def video_project_create(owner_user_id: str, project_id: str = "") -> dict[str, Any]:
    return _result(_service().create_project(owner_user_id, project_id))


def video_project_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().get_project(owner_user_id, project_id))


def resource_pack_save(owner_user_id: str, project_id: str, resource_pack: ResourcePackInput) -> dict[str, Any]:
    """Save product references using product_references entries containing
    asset_id, uri, and optional metadata. Also provide
    primary_product_asset_id and product_identity_description.
    """
    return _result(_service().save_resource_pack(owner_user_id, project_id, _resource_pack(resource_pack, owner_user_id)))


def resource_pack_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    project = _service().get_project(owner_user_id, project_id)
    if project.resource_pack is None:
        raise ValueError("RESOURCE_PACK_NOT_FOUND")
    return _result(project)


def resource_pack_lock(owner_user_id: str, project_id: str, product_identity: dict[str, Any], character_identity: dict[str, Any] | None = None) -> dict[str, Any]:
    return _result(_service().lock_resource_pack(owner_user_id, project_id, _identity(product_identity), _identity(character_identity) if character_identity else None))


def resource_pack_unlock(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().unlock_resource_pack(owner_user_id, project_id))


def raw_idea_save(owner_user_id: str, project_id: str, raw_idea: dict[str, Any]) -> dict[str, Any]:
    return _result(_service().save_raw_idea(owner_user_id, project_id, _idea(raw_idea)))


def creative_brief_save(owner_user_id: str, project_id: str, creative_brief: CreativeBriefInput) -> dict[str, Any]:
    """Save a Creative Brief using objective, target_audience, core_message,
    tone, pace, cta, and content_blocks. Optional fields are
    verified_selling_points, restrictions, required_content, platform,
    aspect_ratio, and target_duration_seconds.
    """
    return _result(_service().save_creative_brief(owner_user_id, project_id, _brief(creative_brief)))


def creative_brief_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    project = _service().get_project(owner_user_id, project_id)
    if project.creative_brief is None:
        raise ValueError("CREATIVE_BRIEF_NOT_FOUND")
    return _result(project)


def creative_brief_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().approve_creative_brief(owner_user_id, project_id))


def scene_plan_save(owner_user_id: str, project_id: str, scene_plan: dict[str, Any]) -> dict[str, Any]:
    return _result(_service().save_scene_plan(owner_user_id, project_id, _scene_plan(scene_plan)))


def scene_plan_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    project = _service().get_project(owner_user_id, project_id)
    if project.scene_plan is None:
        raise ValueError("SCENE_PLAN_NOT_FOUND")
    return _result(project)


def scene_plan_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().approve_scene_plan(owner_user_id, project_id))


# F2 tools: Storyboard

def storyboard_save(owner_user_id: str, project_id: str, storyboard: dict[str, Any]) -> dict[str, Any]:
    """Save storyboard with frame plan."""
    return _result(_service().save_storyboard(owner_user_id, project_id, _storyboard(storyboard)))


def storyboard_update_frame_status(
    owner_user_id: str, project_id: str, frame_id: str,
    status: str, asset_id: str = "", job_id: str = ""
) -> dict[str, Any]:
    """Update frame generation status."""
    return _result(_service().update_frame_generation_status(
        owner_user_id, project_id, frame_id,
        FrameGenerationStatus(status),
        asset_id or None,
        job_id or None
    ))


def storyboard_approve(owner_user_id: str, project_id: str, notes: str = "") -> dict[str, Any]:
    """Approve complete storyboard."""
    return _result(_service().approve_storyboard(owner_user_id, project_id, notes))


def storyboard_reject_frame(owner_user_id: str, project_id: str, frame_id: str, notes: str) -> dict[str, Any]:
    """Reject a frame and request regeneration."""
    return _result(_service().reject_storyboard_frame(owner_user_id, project_id, frame_id, notes))


# F3 tools: Video Generation

def video_scene_save(owner_user_id: str, project_id: str, generated_scene: dict[str, Any]) -> dict[str, Any]:
    """Save generated scene video."""
    return _result(_service().save_generated_scene(owner_user_id, project_id, _generated_scene(generated_scene)))


def video_scene_update_status(
    owner_user_id: str, project_id: str, scene_id: str,
    status: str, asset_id: str = "", job_id: str = "", provider_operation_id: str = ""
) -> dict[str, Any]:
    """Update scene video generation status."""
    return _result(_service().update_scene_generation_status(
        owner_user_id, project_id, scene_id,
        VideoGenerationStatus(status),
        asset_id or None,
        job_id or None,
        provider_operation_id or None
    ))


# F4 tools: Timeline

def timeline_save(owner_user_id: str, project_id: str, timeline: dict[str, Any]) -> dict[str, Any]:
    """Save timeline composition."""
    return _result(_service().save_timeline(owner_user_id, project_id, _timeline(timeline)))


def timeline_update_status(owner_user_id: str, project_id: str, status: str) -> dict[str, Any]:
    """Update timeline render status."""
    return _result(_service().update_timeline_status(owner_user_id, project_id, TimelineStatus(status)))


def timeline_save_draft_video(owner_user_id: str, project_id: str, asset_id: str) -> dict[str, Any]:
    """Save draft video asset."""
    return _result(_service().save_draft_video(owner_user_id, project_id, asset_id))


# F5 tools: Final Review and Export

def final_approve(owner_user_id: str, project_id: str, notes: str = "") -> dict[str, Any]:
    """Approve final video for export."""
    return _result(_service().approve_final_video(owner_user_id, project_id, notes))


def final_request_revision(owner_user_id: str, project_id: str, notes: str) -> dict[str, Any]:
    """Request revision to final video."""
    return _result(_service().request_final_revision(owner_user_id, project_id, notes))




def creative_brief_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    project = _service().get_project(owner_user_id, project_id)
    if project.creative_brief is None:
        raise ValueError("CREATIVE_BRIEF_NOT_FOUND")
    return _result(project)


def creative_brief_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().approve_creative_brief(owner_user_id, project_id))


def scene_plan_save(owner_user_id: str, project_id: str, scene_plan: dict[str, Any]) -> dict[str, Any]:
    return _result(_service().save_scene_plan(owner_user_id, project_id, _scene_plan(scene_plan)))


def scene_plan_get(owner_user_id: str, project_id: str) -> dict[str, Any]:
    project = _service().get_project(owner_user_id, project_id)
    if project.scene_plan is None:
        raise ValueError("SCENE_PLAN_NOT_FOUND")
    return _result(project)


def scene_plan_approve(owner_user_id: str, project_id: str) -> dict[str, Any]:
    return _result(_service().approve_scene_plan(owner_user_id, project_id))


# F2 tools: Storyboard

def storyboard_save(owner_user_id: str, project_id: str, storyboard: dict[str, Any]) -> dict[str, Any]:
    """Save storyboard with frame plan."""
    return _result(_service().save_storyboard(owner_user_id, project_id, _storyboard(storyboard)))


def storyboard_update_frame_status(
    owner_user_id: str, project_id: str, frame_id: str,
    status: str, asset_id: str = "", job_id: str = ""
) -> dict[str, Any]:
    """Update frame generation status."""
    return _result(_service().update_frame_generation_status(
        owner_user_id, project_id, frame_id,
        FrameGenerationStatus(status),
        asset_id or None,
        job_id or None
    ))


def storyboard_approve(owner_user_id: str, project_id: str, notes: str = "") -> dict[str, Any]:
    """Approve complete storyboard."""
    return _result(_service().approve_storyboard(owner_user_id, project_id, notes))


def storyboard_reject_frame(owner_user_id: str, project_id: str, frame_id: str, notes: str) -> dict[str, Any]:
    """Reject a frame and request regeneration."""
    return _result(_service().reject_storyboard_frame(owner_user_id, project_id, frame_id, notes))


# F3 tools: Video Generation

def video_scene_save(owner_user_id: str, project_id: str, generated_scene: dict[str, Any]) -> dict[str, Any]:
    """Save generated scene video."""
    return _result(_service().save_generated_scene(owner_user_id, project_id, _generated_scene(generated_scene)))


def video_scene_update_status(
    owner_user_id: str, project_id: str, scene_id: str,
    status: str, asset_id: str = "", job_id: str = "", provider_operation_id: str = ""
) -> dict[str, Any]:
    """Update scene video generation status."""
    return _result(_service().update_scene_generation_status(
        owner_user_id, project_id, scene_id,
        VideoGenerationStatus(status),
        asset_id or None,
        job_id or None,
        provider_operation_id or None
    ))


# F4 tools: Timeline

def timeline_save(owner_user_id: str, project_id: str, timeline: dict[str, Any]) -> dict[str, Any]:
    """Save timeline composition."""
    return _result(_service().save_timeline(owner_user_id, project_id, _timeline(timeline)))


def timeline_update_status(owner_user_id: str, project_id: str, status: str) -> dict[str, Any]:
    """Update timeline render status."""
    return _result(_service().update_timeline_status(owner_user_id, project_id, TimelineStatus(status)))


def timeline_save_draft_video(owner_user_id: str, project_id: str, asset_id: str) -> dict[str, Any]:
    """Save draft video asset."""
    return _result(_service().save_draft_video(owner_user_id, project_id, asset_id))


# F5 tools: Final Review and Export

def final_approve(owner_user_id: str, project_id: str, notes: str = "") -> dict[str, Any]:
    """Approve final video for export."""
    return _result(_service().approve_final_video(owner_user_id, project_id, notes))


def final_request_revision(owner_user_id: str, project_id: str, notes: str) -> dict[str, Any]:
    """Request revision to final video."""
    return _result(_service().request_final_revision(owner_user_id, project_id, notes))


def final_save_export(owner_user_id: str, project_id: str, asset_id: str) -> dict[str, Any]:
    """Save final exported video, reaching ready_to_publish."""
    return _result(_service().save_final_export(owner_user_id, project_id, asset_id))


# Internal helpers

def _database_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else get_data_path("db", "video_factory.sqlite")


def _workspace_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "").strip()
    return Path(configured).expanduser().resolve() if configured else get_data_path("workspaces", "video-factory")


def video_factory_runtime_info() -> dict[str, Any]:
    """Return observable runtime identity information for the Video Factory MCP server."""
    return {
        "python_executable": str(Path(sys.executable).resolve()),
        "module_file": str(Path(__file__).resolve()),
        "database_path": str(_database_path()),
        "workspace_path": str(_workspace_path()),
    }


def _service() -> VideoFactoryService:
    return VideoFactoryService(SQLiteVideoFactoryRepository(Database(_database_path())))


def _resource_pack(value: ResourcePackInput, owner: str) -> ResourcePack:
    data = dict(value)
    data["id"] = data.get("id", "resource_pack")
    data["owner_user_id"] = owner
    data["product_references"] = tuple(_asset(item) for item in data.get("product_references", []))
    data["character_references"] = tuple(_asset(item) for item in data.get("character_references", []))
    if data.get("locked_product_identity"):
        data["locked_product_identity"] = _identity(data["locked_product_identity"])
    if data.get("locked_character_identity"):
        data["locked_character_identity"] = _identity(data["locked_character_identity"])
    return ResourcePack(**data)


def _asset(value: dict[str, Any]) -> AssetReference:
    return AssetReference(str(value["asset_id"]), str(value["uri"]), dict(value.get("metadata", {})))


def _identity(value: dict[str, Any]) -> ResourceIdentity:
    data = dict(value)
    data["distinctive_features"] = tuple(data.get("distinctive_features", []))
    return ResourceIdentity(**data)


def _idea(value: dict[str, Any]) -> RawIdea:
    data = dict(value)
    data["required_elements"] = tuple(data.get("required_elements", []))
    return RawIdea(**data)


def _brief(value: CreativeBriefInput) -> CreativeBrief:
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
        raise ValueError(
            "creative_brief missing required fields: " + ", ".join(missing)
        )

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
            raise ValueError(
                "creative_brief verified_selling_points entries require claim and canonical status"
            )
        try:
            status = ClaimStatus(item["status"])
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "creative_brief verified_selling_points contains an invalid status"
            ) from exc
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


def _frame_prompt(value: dict[str, Any]) -> FramePrompt:
    data = dict(value)
    data["reference_asset_ids"] = tuple(data.get("reference_asset_ids", []))
    data["provider_options"] = data.get("provider_options", {})
    return FramePrompt(**data)


def _storyboard_frame(value: dict[str, Any]) -> StoryboardFrame:
    data = dict(value)
    data["required_resource_ids"] = tuple(data.get("required_resource_ids", []))
    if data.get("prompt"):
        data["prompt"] = _frame_prompt(data["prompt"])
    else:
        data["prompt"] = None
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


def _timeline(value: dict[str, Any]) -> Timeline:
    data = dict(value)
    data["clips"] = tuple(_timeline_clip(item) for item in data.get("clips", []))
    data["status"] = TimelineStatus(data.get("status", "draft"))
    return Timeline(**data)


def _result(project) -> dict[str, Any]:
    return {"ok": True, "project": _primitive(asdict(project))}


def _primitive(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, list):
        return [_primitive(item) for item in value]



def _scene_plan(value: dict[str, Any]) -> ScenePlan:
    scenes = []
    for item in value.get("scenes", []):
        data = dict(item)
        data["required_resources"] = tuple(data.get("required_resources", []))
        scenes.append(Scene(**data))
    return ScenePlan(tuple(scenes))


def _frame_prompt(value: dict[str, Any]) -> FramePrompt:
    data = dict(value)
    data["reference_asset_ids"] = tuple(data.get("reference_asset_ids", []))
    data["provider_options"] = data.get("provider_options", {})
    return FramePrompt(**data)


def _storyboard_frame(value: dict[str, Any]) -> StoryboardFrame:
    data = dict(value)
    data["required_resource_ids"] = tuple(data.get("required_resource_ids", []))
    if data.get("prompt"):
        data["prompt"] = _frame_prompt(data["prompt"])
    else:
        data["prompt"] = None
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


def _timeline(value: dict[str, Any]) -> Timeline:
    data = dict(value)
    data["clips"] = tuple(_timeline_clip(item) for item in data.get("clips", []))
    data["status"] = TimelineStatus(data.get("status", "draft"))
    return Timeline(**data)


def _result(project) -> dict[str, Any]:
    return {"ok": True, "project": _primitive(asdict(project))}


def _primitive(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_primitive(item) for item in value]
    if isinstance(value, list):
        return [_primitive(item) for item in value]
    if isinstance(value, dict):
        return {key: _primitive(item) for key, item in value.items()}
    return value


# Register all tools
for _tool in (
    video_factory_runtime_info,
    video_project_create, video_project_get, resource_pack_save, resource_pack_get,
    resource_pack_lock, resource_pack_unlock, raw_idea_save, creative_brief_save,
    creative_brief_get, creative_brief_approve, scene_plan_save, scene_plan_get,
    scene_plan_approve, storyboard_save, storyboard_update_frame_status,
    storyboard_approve, storyboard_reject_frame, video_scene_save,
    video_scene_update_status, timeline_save, timeline_update_status,
    timeline_save_draft_video, final_approve, final_request_revision, final_save_export
):
    mcp.tool()(_tool)


if __name__ == "__main__":
    mcp.run()
