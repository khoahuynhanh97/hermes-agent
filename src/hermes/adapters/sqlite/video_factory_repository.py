from __future__ import annotations

import json
from dataclasses import asdict
from enum import Enum

from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, Claim, ClaimStatus, CreativeBrief, FinalApprovalStatus,
    FrameGenerationStatus, FramePrompt, GeneratedScene, ProjectStatus, RawIdea,
    ResourceIdentity, ResourcePack, Scene, ScenePlan, Storyboard,
    StoryboardApprovalStatus, StoryboardFrame, Timeline, TimelineClip,
    TimelineStatus, VideoFactoryProject, VideoGenerationStatus, VideoPrompt,
    HookVariant, ABVariantSet,
)
from hermes.ports.video_factory_repository import VideoFactoryRepository


def _json(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json(item) for item in value]
    if isinstance(value, list):
        return [_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    return value


def _dump(value) -> str:
    return json.dumps(_json(asdict(value) if hasattr(value, "__dataclass_fields__") else value), ensure_ascii=True)


def _asset(value: dict) -> AssetReference:
    return AssetReference(value["asset_id"], value["uri"], value.get("metadata", {}))


def _identity(value: dict | None) -> ResourceIdentity | None:
    if not value:
        return None
    value = dict(value)
    value["distinctive_features"] = tuple(value.get("distinctive_features", []))
    return ResourceIdentity(**value)


def _resource(value: dict | None, owner: str) -> ResourcePack | None:
    if not value:
        return None
    value = dict(value)
    value["owner_user_id"] = owner
    value["product_references"] = tuple(_asset(item) for item in value["product_references"])
    value["character_references"] = tuple(_asset(item) for item in value.get("character_references", []))
    value["locked_product_identity"] = _identity(value.get("locked_product_identity"))
    value["locked_character_identity"] = _identity(value.get("locked_character_identity"))
    return ResourcePack(**value)


def _idea(value: dict | None) -> RawIdea | None:
    if not value:
        return None
    value = dict(value)
    value["required_elements"] = tuple(value.get("required_elements", []))
    return RawIdea(**value)


def _brief(value: dict | None) -> CreativeBrief | None:
    if not value:
        return None
    value = dict(value)
    value["content_blocks"] = tuple(value.get("content_blocks", []))
    value["restrictions"] = tuple(value.get("restrictions", []))
    value["required_content"] = tuple(value.get("required_content", []))
    vsp = []
    for item in value.get("verified_selling_points", []):
        if isinstance(item, str):
            vsp.append(Claim(claim=item, status=ClaimStatus.VERIFIED))
        elif isinstance(item, dict):
            item_dict = dict(item)
            c_text = item_dict.get("claim") or item_dict.get("statement") or ""
            status_val = item_dict.get("status", "verified")
            ev_refs = tuple(item_dict.get("evidence_refs", []))
            restr = item_dict.get("restriction_reason")
            vsp.append(Claim(claim=c_text, status=ClaimStatus(status_val), evidence_refs=ev_refs, restriction_reason=restr))
    value["verified_selling_points"] = tuple(vsp)
    return CreativeBrief(**value)




def _scene_plan(value: dict | None) -> ScenePlan | None:
    if not value:
        return None
    scenes = []
    for item in value.get("scenes", []):
        item = dict(item)
        item["required_resources"] = tuple(item.get("required_resources", []))
        scenes.append(Scene(**item))
    return ScenePlan(tuple(scenes))


def _frame_prompt(value: dict | None) -> FramePrompt | None:
    if not value:
        return None
    value = dict(value)
    value["reference_asset_ids"] = tuple(value.get("reference_asset_ids", []))
    value["provider_options"] = value.get("provider_options", {})
    return FramePrompt(**value)


def _storyboard_frame(value: dict) -> StoryboardFrame:
    value = dict(value)
    value["required_resource_ids"] = tuple(value.get("required_resource_ids", []))
    value["prompt"] = _frame_prompt(value.get("prompt"))
    value["generation_status"] = FrameGenerationStatus(value.get("generation_status", "planned"))
    return StoryboardFrame(**value)


def _storyboard(value: dict | None) -> Storyboard | None:
    if not value or not value.get("storyboard_id"):
        return None
    value = dict(value)
    value["frames"] = tuple(_storyboard_frame(item) for item in value.get("frames", []))
    value["approval_status"] = StoryboardApprovalStatus(value.get("approval_status", "pending"))
    return Storyboard(**value)


def _video_prompt(value: dict | str | None | VideoPrompt) -> VideoPrompt:
    if isinstance(value, VideoPrompt):
        return value
    if isinstance(value, str):
        return VideoPrompt(
            scene_id="scene_default",
            duration_seconds=5.0,
            start_visual_state="",
            end_visual_state="",
            subject_action=value,
            product_action="",
            camera_movement="",
            camera_framing="",
            environment_motion="",
        )
    if not value:
        return VideoPrompt(
            scene_id="scene_default",
            duration_seconds=5.0,
            start_visual_state="",
            end_visual_state="",
            subject_action="",
            product_action="",
            camera_movement="",
            camera_framing="",
            environment_motion="",
        )
    val_dict = dict(value)
    if not val_dict.get("scene_id"):
        val_dict["scene_id"] = "scene_default"
    val_dict["reference_frame_ids"] = tuple(val_dict.get("reference_frame_ids", []))
    val_dict["provider_options"] = val_dict.get("provider_options", {})
    return VideoPrompt(**val_dict)





def _generated_scene(value: dict) -> GeneratedScene:
    value = dict(value)
    value["video_prompt"] = _video_prompt(value["video_prompt"])
    value["generation_status"] = VideoGenerationStatus(value.get("generation_status", "pending"))
    return GeneratedScene(**value)


def _timeline_clip(value: dict) -> TimelineClip:
    value = dict(value)
    value["audio_metadata"] = value.get("audio_metadata", {})
    return TimelineClip(**value)


def _timeline(value: dict | None) -> Timeline | None:
    if not value or not value.get("timeline_id"):
        return None
    value = dict(value)
    value["clips"] = tuple(_timeline_clip(item) for item in value.get("clips", []))
    value["status"] = TimelineStatus(value.get("status", "draft"))
    return Timeline(**value)


def _hook_variant(value: dict) -> HookVariant:
    value = dict(value)
    value["creative_brief"] = _brief(value.get("creative_brief"))
    value["scene_plan"] = _scene_plan(value.get("scene_plan"))
    value["storyboard"] = _storyboard(value.get("storyboard"))
    value["generated_scenes"] = tuple(
        _generated_scene(item) for item in value.get("generated_scenes", [])
    )
    value["timeline"] = _timeline(value.get("timeline"))
    return HookVariant(**value)


def _ab_variant_set(value: dict | None) -> ABVariantSet | None:
    if not value:
        return None
    value = dict(value)
    value["variants"] = tuple(
        _hook_variant(item) for item in value.get("variants", [])
    )
    return ABVariantSet(**value)


class SQLiteVideoFactoryRepository(VideoFactoryRepository):
    def __init__(self, database: Database):
        self._database = database
        self._database.initialize()

    def create(self, project: VideoFactoryProject) -> VideoFactoryProject:
        with self._database.transaction(immediate=True) as connection:
            connection.execute(
                "INSERT INTO video_factory_projects(id, owner_user_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (project.id, project.owner_user_id, project.created_at, project.updated_at),
            )
        return project

    def get_owned(self, project_id: str, owner_user_id: str) -> VideoFactoryProject | None:
        with self._database.transaction() as connection:
            row = connection.execute(
                "SELECT * FROM video_factory_projects WHERE id = ? AND owner_user_id = ?",
                (project_id, owner_user_id),
            ).fetchone()
        return self._from_row(row) if row else None

    def list_owned(self, owner_user_id: str) -> list[VideoFactoryProject]:
        with self._database.transaction() as connection:
            rows = connection.execute(
                "SELECT * FROM video_factory_projects WHERE owner_user_id = ? ORDER BY updated_at DESC",
                (owner_user_id,),
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def save(self, project: VideoFactoryProject) -> VideoFactoryProject:
        with self._database.transaction(immediate=True) as connection:
            scenes_data = [_json(asdict(scene)) for scene in project.generated_scenes]
            ab_variants_json = _dump(project.ab_variants) if project.ab_variants else "{}"
            
            connection.execute(
                """UPDATE video_factory_projects SET 
                   status=?, resource_pack_json=?, raw_idea_json=?,
                   creative_brief_json=?, scene_plan_json=?, 
                   storyboard_json=?, generated_scenes_json=?, timeline_json=?,
                   draft_video_asset_id=?, final_video_asset_id=?,
                   brief_approval=?, scene_plan_approval=?, final_approval=?, final_approval_notes=?,
                   ab_variants_json=?,
                   resource_version=?, idea_version=?, brief_version=?, scene_version=?,
                   storyboard_version=?, video_generation_version=?, timeline_version=?,
                   updated_at=? 
                   WHERE id=? AND owner_user_id=?""",
                (
                    project.status.value,
                    _dump(project.resource_pack) if project.resource_pack else "{}",
                    _dump(project.raw_idea) if project.raw_idea else "{}",
                    _dump(project.creative_brief) if project.creative_brief else "{}",
                    _dump(project.scene_plan) if project.scene_plan else "{}",
                    _dump(project.storyboard) if project.storyboard else "{}",
                    json.dumps(scenes_data, ensure_ascii=True),
                    _dump(project.timeline) if project.timeline else "{}",
                    project.draft_video_asset_id,
                    project.final_video_asset_id,
                    project.brief_approval,
                    project.scene_plan_approval,
                    project.final_approval.value,
                    project.final_approval_notes,
                    ab_variants_json,
                    project.resource_version,
                    project.idea_version,
                    project.brief_version,
                    project.scene_version,
                    project.storyboard_version,
                    project.video_generation_version,
                    project.timeline_version,
                    project.updated_at,
                    project.id,
                    project.owner_user_id,
                ),
            )
        return project

    def _from_row(self, row) -> VideoFactoryProject:
        try:
            generated_scenes_json = row["generated_scenes_json"] if "generated_scenes_json" in row.keys() else "[]"
            storyboard_json = row["storyboard_json"] if "storyboard_json" in row.keys() else "{}"
            timeline_json = row["timeline_json"] if "timeline_json" in row.keys() else "{}"
            draft_video_asset_id = row["draft_video_asset_id"] if "draft_video_asset_id" in row.keys() else None
            final_video_asset_id = row["final_video_asset_id"] if "final_video_asset_id" in row.keys() else None
            final_approval = row["final_approval"] if "final_approval" in row.keys() else "pending"
            final_approval_notes = row["final_approval_notes"] if "final_approval_notes" in row.keys() else ""
            storyboard_version = row["storyboard_version"] if "storyboard_version" in row.keys() else 0
            video_generation_version = row["video_generation_version"] if "video_generation_version" in row.keys() else 0
            timeline_version = row["timeline_version"] if "timeline_version" in row.keys() else 0
            ab_variants_json = row["ab_variants_json"] if "ab_variants_json" in row.keys() else "{}"
        except (KeyError, IndexError):
            generated_scenes_json = "[]"
            storyboard_json = "{}"
            timeline_json = "{}"
            draft_video_asset_id = None
            final_video_asset_id = None
            final_approval = "pending"
            final_approval_notes = ""
            storyboard_version = 0
            video_generation_version = 0
            timeline_version = 0
            ab_variants_json = "{}"
        
        generated_scenes_data = json.loads(generated_scenes_json)
        return VideoFactoryProject(
            id=row["id"],
            owner_user_id=row["owner_user_id"],
            status=ProjectStatus(row["status"]),
            resource_pack=_resource(json.loads(row["resource_pack_json"]), row["owner_user_id"]),
            raw_idea=_idea(json.loads(row["raw_idea_json"])),
            creative_brief=_brief(json.loads(row["creative_brief_json"])),
            brief_approval=row["brief_approval"],
            scene_plan=_scene_plan(json.loads(row["scene_plan_json"])),
            scene_plan_approval=row["scene_plan_approval"],
            storyboard=_storyboard(json.loads(storyboard_json)),
            generated_scenes=tuple(_generated_scene(item) for item in generated_scenes_data),
            timeline=_timeline(json.loads(timeline_json)),
            draft_video_asset_id=draft_video_asset_id,
            final_video_asset_id=final_video_asset_id,
            final_approval=FinalApprovalStatus(final_approval),
            final_approval_notes=final_approval_notes,
            ab_variants=_ab_variant_set(json.loads(ab_variants_json)),
            resource_version=row["resource_version"],
            idea_version=row["idea_version"],
            brief_version=row["brief_version"],
            scene_version=row["scene_version"],
            storyboard_version=storyboard_version,
            video_generation_version=video_generation_version,
            timeline_version=timeline_version,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
