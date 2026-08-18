"""FastAPI routes for Video Factory API."""
from __future__ import annotations

import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from enum import Enum
from dataclasses import asdict, replace

from fastapi import APIRouter, HTTPException, BackgroundTasks, status, Depends
from pydantic import BaseModel

from hermes.db import Database
from hermes.config import get_data_path
from hermes.runtime_layout import get_project_workspace, get_data_root
from hermes.channels.api.dependencies import get_video_factory_job_service, get_authenticated_principal_context, verify_owner_match
from hermes.security.principal import PrincipalContext
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.adapters.sqlite.product_resource_binding_repository import SQLiteProjectResourceBindingRepository
from hermes.application.asset_projection_service import AssetProjectionService
from hermes.application.product_resource_service import ProductResourceService
from hermes.application.video_factory_service import VideoFactoryService
from hermes.domain.video_factory import (
    ResourcePack, AssetReference, CreativeBrief, ScenePlan, Storyboard,
    StoryboardFrame, Timeline, TimelineClip, TimelineStatus, RawIdea,
    ProjectStatus, ResourceIdentity, FrameGenerationStatus, VideoGenerationStatus,
    FinalApprovalStatus, StoryboardApprovalStatus, GeneratedScene, Scene,
    FramePrompt, VideoPrompt, VideoFactoryProject, HookVariant, ABVariantSet,
    new_id,
)

router = APIRouter(prefix="/vf")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _database_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else get_data_path("db", "video_factory.sqlite")


def _vf_service() -> VideoFactoryService:
    db_path = _database_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = Database(str(db_path))
    db.initialize()
    return VideoFactoryService(SQLiteVideoFactoryRepository(db))


def _resolve_resource_pack(product_query: str, owner_user_id: str) -> tuple[ResourcePack, Dict[str, Any]]:
    """Resolve a persisted Product Intelligence lock through the projection adapter."""
    lock = AssetProjectionService.from_runtime().find_resource_pack_lock(owner_user_id, product_query)
    if not lock or lock.get("status") != "locked":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Could not resolve a locked resource pack for query: '{product_query}'"
        )

    expected_digest = str(lock.get("manifest_digest") or "")
    actual_digest = ProductResourceService.compute_manifest_digest(lock)
    if not expected_digest or expected_digest != actual_digest:
        raise HTTPException(status_code=409, detail="PRODUCT_RESOURCE_LOCK_DIGEST_MISMATCH")
    
    product_refs = []
    for asset in lock.get("assets", []):
        product_refs.append(AssetReference(
            asset_id=asset["asset_id"],
            uri=asset["local_path"],
            metadata={
                "physical_hash_filename": asset.get("physical_hash_filename", ""),
                "mime_type": asset.get("mime_type", ""),
                "snapshot_id": lock.get("snapshot_id", ""),
                "resource_pack_lock_id": lock.get("lock_id", ""),
            }
        ))

    if not product_refs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource pack lock '{lock.get('lock_id')}' contains no assets."
        )

    identity_data = lock.get("identity_constraints") or {}
    locked_identity = ResourceIdentity(
        description=" ".join(filter(None, (
            str(identity_data.get("brand") or lock.get("brand") or ""),
            str(identity_data.get("model") or lock.get("model") or lock.get("product_name") or ""),
            str(identity_data.get("product_type") or ""),
        ))),
        color=str(identity_data.get("variant") or lock.get("variant") or ""),
        distinctive_features=tuple(str(value) for value in identity_data.get("distinctive_features", ()) if value),
    )
    pack = ResourcePack(
        id=lock["lock_id"],
        owner_user_id=owner_user_id,
        product_references=tuple(product_refs),
        primary_product_asset_id=product_refs[0].asset_id,
        product_identity_description=lock.get("product_name", "Unknown Product"),
        locked_product_identity=locked_identity,
        locked_at=lock.get("locked_at") or lock.get("created_at") or "persisted-lock",
        version=int(lock.get("resource_pack_version", lock.get("version", 1))),
    )
    return pack, lock



def _default_scene_plan(product_description: str) -> ScenePlan:
    product = product_description.strip() or "the product"
    return ScenePlan(scenes=(
        Scene("scene_1", 1, "Hook", "Capture attention", f"Vertical product reveal of {product}, clean studio lighting, accurate product identity", "Slow product reveal", 6, "Minimal technology studio", "Slow push-in"),
        Scene("scene_2", 2, "Use case", "Show practical value", f"Show {product} being used naturally, preserve exact shape, colors, logo and materials", "Lifestyle demonstration", 8, "Modern everyday setting", "Stable medium close-up"),
        Scene("scene_3", 3, "Highlights", "Present key details", f"Detailed feature montage of {product}, macro details and realistic materials", "Feature montage", 8, "Premium tabletop setup", "Controlled macro orbit"),
        Scene("scene_4", 4, "Call to action", "Close the review", f"Hero shot of {product} with a clean closing composition and space for call to action", "Product outro", 8, "Clean brand-neutral studio", "Slow pull-back"),
    ))


def _identity_preserving_prompt(project: VideoFactoryProject, scene: Scene) -> str:
    identity = project.resource_pack.locked_product_identity if project.resource_pack else None
    identity_text = identity.description if identity else (
        project.resource_pack.product_identity_description if project.resource_pack else "the referenced product"
    )
    if identity and identity.color:
        identity_text += f", color/variant: {identity.color}"
    return (
        f"Create one polished vertical 9:16 storyboard photograph for: {scene.content}. "
        f"The attached reference images are the sole source of truth for {identity_text}. "
        "Preserve exact product geometry, case proportions, earbud silhouette, materials, colors, and logo placement. "
        "Never add or remove stems, buttons, displays, lights, ports, logos, or accessories. "
        "Do not copy source-image typography. No captions, labels, banners, watermarks, UI, feature claims, or readable text. "
        f"Action: {scene.main_action}. Context: {scene.context}. Camera: {scene.camera_intention}."
    )


def _default_timeline(project: VideoFactoryProject, audio_track_asset_id: str | None = None) -> Timeline:
    clips = []
    for i, scene in enumerate(project.generated_scenes):
        clips.append(TimelineClip(
            clip_id=f"clip_{i+1}",
            order=i + 1,
            source_asset_id=scene.generated_asset_id,
            duration_seconds=scene.video_prompt.duration_seconds,
        ))

    return Timeline(
        timeline_id=new_id("timeline"),
        project_id=project.id,
        clips=tuple(clips),
        status=TimelineStatus.DRAFT,
        audio_track_asset_id=audio_track_asset_id,
    )


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


def _serialize_project(project) -> dict[str, Any]:
    payload = _primitive(asdict(project))
    pack = payload.get("resource_pack")
    if pack:
        for ref in (*pack.get("product_references", []), *pack.get("character_references", [])):
            ref["uri"] = f"/api/assets/{ref['asset_id']}/content"
    return payload


def _sync_project_generation_status(project, service) -> VideoFactoryProject:
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
    db_path = _database_path()
    db = Database(str(db_path))
    db.initialize()
    asset_repo = SQLiteGeneratedAssetRepository(db)
    
    # 1. Sync storyboard frames
    if project.storyboard:
        changed = False
        for frame in project.storyboard.frames:
            if frame.generation_status != FrameGenerationStatus.COMPLETED and frame.generation_job_id:
                asset = asset_repo.get_by_job_id(frame.generation_job_id)
                if asset:
                    project = service.update_frame_generation_status(
                        project.owner_user_id, project.id, frame.frame_id,
                        FrameGenerationStatus.COMPLETED, asset["asset_id"],
                        frame.generation_job_id
                    )
                    changed = True
                    
        # If all frames are completed, let's auto-approve the storyboard!
        if changed and project.storyboard and all(f.generation_status == FrameGenerationStatus.COMPLETED for f in project.storyboard.frames):
            project = service.approve_storyboard(project.owner_user_id, project.id, "Auto approved")
            
            # Submit video_generate jobs for all scenes in the scene plan automatically when storyboard is approved!
            if project.scene_plan and not project.generated_scenes:
                job_service = get_video_factory_job_service()
                frame_by_scene = {
                    frame.scene_id: frame for frame in project.storyboard.frames
                    if frame.generated_asset_id
                }

                for i, scene in enumerate(project.scene_plan.scenes):
                    frame = frame_by_scene.get(scene.scene_id)
                    frame_asset = asset_repo.get_by_asset_id(frame.generated_asset_id) if frame else None
                    reference_images = [frame_asset["output_path"]] if frame_asset else []
                    if not reference_images and project.resource_pack:
                        reference_images = [project.resource_pack.product_references[0].uri]
                    identity_constraints = (
                        project.resource_pack.locked_product_identity.description
                        if project.resource_pack and project.resource_pack.locked_product_identity
                        else project.resource_pack.product_identity_description if project.resource_pack else ""
                    )
                    video_prompt = VideoPrompt(
                        scene_id=scene.scene_id,
                        duration_seconds=scene.duration_seconds,
                        start_visual_state=scene.start_state or scene.content,
                        end_visual_state=scene.end_state or scene.content,
                        subject_action=scene.main_action,
                        product_action=scene.main_action,
                        camera_movement=scene.camera_intention,
                        camera_framing="Vertical 9:16 product-focused composition",
                        environment_motion="Subtle realistic environmental motion",
                        identity_constraints=identity_constraints,
                        reference_frame_ids=(frame.frame_id,) if frame else (),
                        negative_constraints="No geometry changes; never add or remove earbud stems, controls, lights, ports, logos or accessories; no text, captions, banners, claims or watermarks",
                        provider_options={"resolution": "720p", "generateAudio": False},
                    )
                    payload = {
                        "project_id": project.id,
                        "scene_id": scene.scene_id,
                        "prompt": (
                            video_prompt.start_visual_state + ". " + video_prompt.subject_action + ". "
                            "Animate the supplied storyboard frame conservatively. Preserve the exact product silhouette, "
                            "case proportions, earbud geometry, colors, materials and logo placement in every frame. "
                            + video_prompt.negative_constraints
                        ),
                        "owner_user_id": project.owner_user_id,
                        "request_id": f"req_vid_{project.id}_{scene.scene_id}_{(frame.generated_asset_id if frame else 'source')[-8:]}",
                        "duration_seconds": scene.duration_seconds,
                        "reference_image_paths": reference_images,
                        "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
                        "width": 720,
                        "height": 1280,
                        "aspect_ratio": "9:16",
                        "provider_options": video_prompt.provider_options,
                        "max_attempts": 3,
                    }
                    job_id = job_service.submit_job("video_generate", payload)

                    gen_scene = GeneratedScene(
                        scene_id=scene.scene_id,
                        video_prompt=video_prompt,
                        generation_status=VideoGenerationStatus.GENERATING,
                        generation_job_id=job_id
                    )
                    project = service.save_generated_scene(project.owner_user_id, project.id, gen_scene)
            
    # 2. Sync generated scenes
    if project.generated_scenes:
        for scene in project.generated_scenes:
            if scene.generation_status != VideoGenerationStatus.COMPLETED and scene.generation_job_id:
                asset = asset_repo.get_by_job_id(scene.generation_job_id)
                if asset:
                    project = service.update_scene_generation_status(
                        project.owner_user_id, project.id, scene.scene_id,
                        VideoGenerationStatus.COMPLETED, asset["asset_id"],
                        scene.generation_job_id
                    )
                    
    # 3. Sync draft video from timeline render job
    if project.timeline:
        timeline_cutoff = project.timeline.updated_at or project.timeline.created_at or ""
        latest_timeline_asset = next((
            asset for asset in asset_repo.list_assets()
            if (
                asset.get("project_id") == project.id
                and asset.get("scene_id") == "timeline"
                and str(asset.get("created_at") or "") >= timeline_cutoff
            )
        ), None)
        if latest_timeline_asset and latest_timeline_asset.get("asset_id") != project.draft_video_asset_id:
            project = service.save_draft_video(project.owner_user_id, project.id, latest_timeline_asset["asset_id"])
            project = service.approve_final_video(project.owner_user_id, project.id, "Auto approved")
                
    # 4. Sync final export
    if project.draft_video_asset_id and project.final_approval == FinalApprovalStatus.APPROVED:
        draft_asset = asset_repo.get_by_asset_id(project.draft_video_asset_id)
        export_cutoff = str(draft_asset.get("created_at") or "") if draft_asset else ""
        latest_export_asset = next((
            asset for asset in asset_repo.list_assets()
            if (
                asset.get("project_id") == project.id
                and asset.get("scene_id") == "export"
                and str(asset.get("created_at") or "") >= export_cutoff
            )
        ), None)
        if latest_export_asset and latest_export_asset.get("asset_id") != project.final_video_asset_id:
            project = service.save_final_export(project.owner_user_id, project.id, latest_export_asset["asset_id"])
                
    return project


class CreateProjectRequest(BaseModel):
    project_id: str








class SaveBriefRequest(BaseModel):
    objective: str
    target_audience: str
    core_message: str
    content_blocks: List[str]


class SaveTTSRequest(BaseModel):
    text: str
    style_prompt: str
    voice: str


@router.get("/projects")
def list_video_projects(
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    projects = service.repository.list_owned(owner)
            
    synced_projects = []
    for p in projects:
        try:
            synced_projects.append(_sync_project_generation_status(p, service))
        except Exception:
            synced_projects.append(p)
            
    return {
        "status": "ok",
        "data": [_serialize_project(p) for p in synced_projects],
    }


@router.post("/projects")
def create_video_project(
    body: CreateProjectRequest,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.create_project(owner, body.project_id)
        return {"status": "ok", "data": _serialize_project(project)}
    except Exception as e:
        print(f"Error creating project: {e}", flush=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}")
def get_video_project(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        project = _sync_project_generation_status(project, service)
        return {"status": "ok", "data": _serialize_project(project)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


class BindResourceRequest(BaseModel):
    product_query: str

@router.post("/projects/{project_id}/resources/bind")
def bind_project_resources(
    project_id: str,
    body: BindResourceRequest,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        pack, lock = _resolve_resource_pack(body.product_query, owner)
        binding_repository = SQLiteProjectResourceBindingRepository(Database(str(_database_path())))
        resource_service = ProductResourceService(binding_repository)
        existing = binding_repository.get_by_project_id(project_id)
        if existing is None:
            resource_service.verify_and_bind(project_id, lock, owner)
        elif existing.manifest_digest != lock.get("manifest_digest"):
            raise HTTPException(status_code=409, detail="PROJECT_ALREADY_BOUND_TO_DIFFERENT_RESOURCE_LOCK")
        project = service.save_resource_pack(owner, project_id, pack)
        return {"status": "ok", "data": _serialize_project(project)}
    except HTTPException as e:
        raise e  # Re-raise user-facing HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/brief")
def save_project_brief(
    project_id: str,
    body: SaveBriefRequest,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        brief = CreativeBrief(
            objective=body.objective,
            target_audience=body.target_audience,
            core_message=body.core_message,
            content_blocks=tuple(body.content_blocks),
            tone="Sôi động, trẻ trung",
            pace="Nhanh",
            cta="Mua ngay!"
        )
        project = service.save_creative_brief(owner, project_id, brief)
        return {"status": "ok", "data": _serialize_project(project)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/brief/approve")
def approve_project_brief(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.approve_creative_brief(owner, project_id)
        return {"status": "ok", "data": _serialize_project(project)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/scenes/approve")
def approve_project_scenes(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        if not project.scene_plan:
            description = project.resource_pack.product_identity_description if project.resource_pack else "the product"
            plan = _default_scene_plan(description)
            project = service.save_scene_plan(owner, project_id, plan)
        project = service.approve_scene_plan(owner, project_id)
        return {"status": "ok", "data": _serialize_project(project)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/storyboard/generate")
def generate_project_storyboard(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
    job_service = Depends(get_video_factory_job_service)
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        
        # Ensure scene plan is approved first
        if not project.scene_plan:
            description = project.resource_pack.product_identity_description if project.resource_pack else "the product"
            plan = _default_scene_plan(description)
            project = service.save_scene_plan(owner, project_id, plan)
            project = service.approve_scene_plan(owner, project_id)
            
        reference_images = []
        if project.resource_pack:
            reference_images = [ref.uri for ref in project.resource_pack.product_references]
            
        frames = []
        submitted_jobs = []
        storyboard_revision = project.storyboard_version + 1
        
        for i, scene in enumerate(project.scene_plan.scenes):
            frame_id = f"frame_{i+1}"
            generation_prompt = _identity_preserving_prompt(project, scene)
            payload = {
                "project_id": project_id,
                "scene_id": frame_id,
                "prompt": generation_prompt,
                "owner_user_id": owner,
                "request_id": f"req_{project_id}_sb{storyboard_revision}_{frame_id}",
                "reference_image_paths": reference_images,
                "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
                "width": 720,
                "height": 1280,
                "aspect_ratio": "9:16",
                "max_attempts": 3,
            }
            job_id = job_service.submit_job("image_generate", payload)
            
            prompt = FramePrompt(
                positive_prompt=generation_prompt,
                negative_constraints="No text, captions, banners, watermarks, invented claims, or product geometry changes",
                product_identity_constraints=project.resource_pack.product_identity_description if project.resource_pack else "",
                action=scene.main_action,
                reference_asset_ids=tuple(ref.asset_id for ref in project.resource_pack.product_references) if project.resource_pack else (),
                aspect_ratio="9:16",
            )
            frame = StoryboardFrame(
                frame_id=frame_id,
                scene_id=scene.scene_id,
                order=i + 1,
                label=scene.title,
                purpose=scene.objective,
                visual_state=scene.content,
                subject_action=scene.main_action,
                product_state=scene.content,
                character_state="",
                context=scene.context,
                camera_intention=scene.camera_intention,
                required_resource_ids=prompt.reference_asset_ids,
                prompt=prompt,
                generation_status=FrameGenerationStatus.GENERATING,
                generation_job_id=job_id
            )
            frames.append(frame)
            submitted_jobs.append({"job_id": job_id, "frame_id": frame_id})
            
        storyboard = Storyboard(
            storyboard_id=new_id("storyboard"),
            project_id=project_id,
            frames=tuple(frames),
        )
        project = service.save_storyboard(owner, project_id, storyboard)
        
        return {
            "status": "ok",
            "data": _serialize_project(project),
            "jobs": submitted_jobs
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/tts", status_code=202)
def save_project_tts(
    project_id: str,
    body: SaveTTSRequest,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
    job_service = Depends(get_video_factory_job_service)
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        job_id = job_service.submit_job("tts_generate", {
            "project_id": project_id,
            "scene_id": "tts",
            "owner_user_id": owner,
            "request_id": f"tts_{project_id}",
            "text": body.text,
            "voice": body.voice,
            "style_prompt": body.style_prompt,
            "language": "vi-VN",
            "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
            "max_attempts": 3,
        })
        return {"status": "accepted", "job_id": job_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/tts/mix")
def mix_project_tts(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context)
) -> Dict[str, Any]:
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
    owner = verify_owner_match(owner_user_id, principal)
    try:
        project = _vf_service().get_project(owner, project_id)
        mixed_path = get_project_workspace(project_id) / "generated" / "mixed_audio.wav"
        mixed_path.parent.mkdir(parents=True, exist_ok=True)
        
        import wave
        with wave.open(str(mixed_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(b"\x00\x00" * 24000)
            
        asset_repo = SQLiteGeneratedAssetRepository(Database(str(_database_path())))
        asset_record = {
            "asset_id": f"gen_mix_{project_id}",
            "project_id": project_id,
            "scene_id": "mix",
            "job_id": f"job_mix_{project_id}",
            "provider": "fake",
            "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
            "reference_asset_ids": [],
            "prompt_version": 1,
            "physical_hash_filename": f"sha256_mix_{project_id}.media",
            "output_path": str(mixed_path),
            "status": "completed",
        }
        asset_repo.save_asset(asset_record)
        
        return {
            "status": "ok",
            "data": {
                "output_path": f"/api/assets/gen_mix_{project_id}/content"
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/timeline/render")
def render_project_timeline(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
    job_service = Depends(get_video_factory_job_service)
) -> Dict[str, Any]:
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
    owner = verify_owner_match(owner_user_id, principal)

    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        
        if not project.generated_scenes:
            raise HTTPException(status_code=400, detail="Generated scenes are required before timeline rendering.")
            
        asset_repo = SQLiteGeneratedAssetRepository(Database(str(_database_path())))
        scene_assets = []
        for scene in project.generated_scenes:
            if scene.generation_status != VideoGenerationStatus.COMPLETED or not scene.generated_asset_id:
                raise HTTPException(status_code=409, detail=f"Scene {scene.scene_id} is not complete.")
            asset = asset_repo.get_by_asset_id(scene.generated_asset_id)
            if not asset:
                raise HTTPException(status_code=409, detail=f"Generated asset missing for scene {scene.scene_id}.")
            scene_assets.append(asset)

        audio_asset = next((asset for asset in asset_repo.list_assets() if asset.get("project_id") == project_id and asset.get("scene_id") == "mix"), None)
        if audio_asset is None:
            audio_asset = next((asset for asset in asset_repo.list_assets() if asset.get("project_id") == project_id and asset.get("scene_id") == "tts"), None)

        timeline = _default_timeline(project, audio_asset["asset_id"] if audio_asset else None)
        project = service.save_timeline(owner, project_id, timeline)
        
        payload = {
            "project_id": project_id,
            "scene_id": "timeline",
            "clip_paths": [asset["output_path"] for asset in scene_assets],
            "audio_path": audio_asset["output_path"] if audio_asset else None,
            "duration_seconds": sum(scene.video_prompt.duration_seconds for scene in project.generated_scenes),
            "output_path": str(get_project_workspace(project_id) / "generated" / "draft_video.mp4"),
            "owner_user_id": owner,
            "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
            "max_attempts": 3,
        }
        job_id = job_service.submit_job("video.render", payload)
        
        return {
            "status": "ok",
            "job_id": job_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/projects/{project_id}/final/export")
def export_project_final(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
    job_service = Depends(get_video_factory_job_service)
) -> Dict[str, Any]:
    from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
    owner = verify_owner_match(owner_user_id, principal)

    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        if not project.draft_video_asset_id:
            raise HTTPException(status_code=400, detail="Timeline draft video must be completed first.")
            
        project = service.approve_final_video(owner, project_id, "Approved for export")
        asset_repo = SQLiteGeneratedAssetRepository(Database(str(_database_path())))
        draft_asset = asset_repo.get_by_asset_id(project.draft_video_asset_id)
        if not draft_asset:
            raise HTTPException(status_code=409, detail="Draft video asset is missing.")
        
        payload = {
            "project_id": project_id,
            "scene_id": "export",
            "input_path": draft_asset["output_path"],
            "output_path": str(get_project_workspace(project_id) / "exports" / "final_video.mp4"),
            "owner_user_id": owner,
            "resource_lock_id": project.resource_pack.id if project.resource_pack else "",
            "max_attempts": 3,
        }
        job_id = job_service.submit_job("export", payload)
        
        return {
            "status": "ok",
            "job_id": job_id
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class WorkflowDispatchRequest(BaseModel):
    prompt: str
    product_query: Optional[str] = None
    duration_seconds: int = 30
    platform: str = "TikTok"
    language: str = "Vietnamese"


@router.post("/workflow/dispatch")
def dispatch_workflow(
    body: WorkflowDispatchRequest,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    from hermes.application.workflow import WorkflowOrchestrator
    orchestrator = WorkflowOrchestrator(_database_path())
    try:
        return orchestrator.dispatch_product_to_video_workflow(
            owner_user_id=owner,
            prompt=body.prompt,
            product_query=body.product_query,
            duration_seconds=body.duration_seconds,
            platform=body.platform,
            language=body.language,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/progress")
def get_project_progress(
    project_id: str,
    owner_user_id: Optional[str] = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        project = _sync_project_generation_status(project, service)
        
        return {
            "status": "ok",
            "project_id": project.id,
            "project_status": project.status.value,
            "stages": {
                "resource_pack": {
                    "status": "completed" if project.resource_pack else "pending",
                    "pack_id": project.resource_pack.id if project.resource_pack else None,
                    "version": project.resource_version,
                },
                "brief": {
                    "status": "completed" if project.brief_approval else "pending",
                    "version": project.brief_version,
                },
                "scene_plan": {
                    "status": "completed" if project.scene_plan_approval else "pending",
                    "version": project.scene_version,
                },
                "storyboard": {
                    "status": project.storyboard.approval_status.value if project.storyboard else "pending",
                    "frame_count": len(project.storyboard.frames) if project.storyboard else 0,
                    "version": project.storyboard_version,
                },
                "tts_voiceover": {
                    "status": "completed" if (project.timeline and project.timeline.audio_track_asset_id) else "pending",
                    "audio_asset_id": project.timeline.audio_track_asset_id if project.timeline else None,
                },
                "video_scenes": {
                    "status": "completed" if (project.generated_scenes and all(s.generation_status.value == "completed" for s in project.generated_scenes)) else "pending",
                    "scene_count": len(project.generated_scenes),
                    "completed_scenes": sum(1 for s in project.generated_scenes if s.generation_status.value == "completed"),
                },
                "timeline_render": {
                    "status": "completed" if project.draft_video_asset_id else "pending",
                    "draft_video_asset_id": project.draft_video_asset_id,
                    "version": project.timeline_version,
                },
                "final_export": {
                    "status": "completed" if project.final_video_asset_id else ("ready_for_export" if project.draft_video_asset_id else "pending"),
                    "final_video_asset_id": project.final_video_asset_id,
                },
            },
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── A/B Variant Endpoints ──────────────────────────────────────────────────


class GenerateABVariantsRequest(BaseModel):
    prompt: str = "Tạo video TikTok review sản phẩm dài 30 giây"
    product_query: str | None = None
    duration_seconds: int = 30
    platform: str = "TikTok"
    language: str = "Vietnamese"


class SelectVariantRequest(BaseModel):
    variant_id: str


@router.post("/projects/{project_id}/ab-variants/generate")
def generate_ab_variants(
    project_id: str,
    body: GenerateABVariantsRequest,
    owner_user_id: str | None = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    from hermes.application.workflow import WorkflowOrchestrator
    orchestrator = WorkflowOrchestrator(_database_path())
    try:
        return orchestrator.run_ab_variant_workflow(
            owner_user_id=owner,
            prompt=body.prompt,
            product_query=body.product_query,
            duration_seconds=body.duration_seconds,
            platform=body.platform,
            language=body.language,
            project_id=project_id,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/ab-variants")
def get_ab_variants(
    project_id: str,
    owner_user_id: str | None = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        project = _sync_project_generation_status(project, service)
        if not project.ab_variants:
            return {"status": "ok", "data": {"variants": [], "selected_variant_id": ""}}
        variant_list = []
        for v in project.ab_variants.variants:
            variant_list.append({
                "variant_id": v.variant_id,
                "variant_label": v.variant_label,
                "hook_angle": v.hook_angle,
                "creative_brief": _primitive(asdict(v.creative_brief)),
                "scene_plan": _primitive(asdict(v.scene_plan)),
                "final_asset_id": v.final_asset_id,
                "export_status": v.export_status,
                "timeline": _primitive(asdict(v.timeline)) if v.timeline else None,
            })
        return {
            "status": "ok",
            "data": {
                "variants": variant_list,
                "selected_variant_id": project.ab_variants.selected_variant_id,
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/projects/{project_id}/ab-variants/{variant_id}")
def get_single_ab_variant(
    project_id: str,
    variant_id: str,
    owner_user_id: str | None = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        if not project.ab_variants:
            raise HTTPException(status_code=404, detail="No A/B variants found for this project")
        variant = next((v for v in project.ab_variants.variants if v.variant_id == variant_id), None)
        if variant is None:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")
        return {
            "status": "ok",
            "data": {
                "variant_id": variant.variant_id,
                "variant_label": variant.variant_label,
                "hook_angle": variant.hook_angle,
                "creative_brief": _primitive(asdict(variant.creative_brief)),
                "scene_plan": _primitive(asdict(variant.scene_plan)),
                "final_asset_id": variant.final_asset_id,
                "export_status": variant.export_status,
                "timeline": _primitive(asdict(variant.timeline)) if variant.timeline else None,
            },
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/projects/{project_id}/ab-variants/{variant_id}/select")
def select_ab_variant(
    project_id: str,
    variant_id: str,
    owner_user_id: str | None = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        if not project.ab_variants:
            raise HTTPException(status_code=404, detail="No A/B variants found for this project")
        ids = {v.variant_id for v in project.ab_variants.variants}
        if variant_id not in ids:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")
        updated_set = ABVariantSet(
            variants=project.ab_variants.variants,
            selected_variant_id=variant_id,
        )
        updated_project = replace(project, ab_variants=updated_set, updated_at=_now())
        service.repository.save(updated_project)
        return {"status": "ok", "selected_variant_id": variant_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/projects/{project_id}/ab-variants/{variant_id}/download")
def download_ab_variant(
    project_id: str,
    variant_id: str,
    owner_user_id: str | None = None,
    principal: PrincipalContext = Depends(get_authenticated_principal_context),
) -> Dict[str, Any]:
    owner = verify_owner_match(owner_user_id, principal)
    service = _vf_service()
    try:
        project = service.get_project(owner, project_id)
        if not project.ab_variants:
            raise HTTPException(status_code=404, detail="No A/B variants found for this project")
        variant = next((v for v in project.ab_variants.variants if v.variant_id == variant_id), None)
        if variant is None:
            raise HTTPException(status_code=404, detail=f"Variant {variant_id} not found")
        if not variant.final_asset_id:
            raise HTTPException(status_code=400, detail="Variant has not been exported yet")
        return {
            "status": "ok",
            "download_url": f"/api/assets/{variant.final_asset_id}/content",
            "asset_id": variant.final_asset_id,
            "variant_label": variant.variant_label,
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

