"""Thin aiohttp API for the minimal Video Factory UI (UI1).

Calls VideoFactoryService + canonical durable jobs directly. No business
logic duplicated here; project/status remain source of truth in SQLite.

Owner: single default owner for UI1 (no auth system).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path

from aiohttp import web

from hermes.adapters.sqlite.canonical_job_repository import CanonicalJobRepository
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.config import get_data_path
from hermes.db import Database
from hermes.domain.job import Job
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, FramePrompt, GeneratedScene, RawIdea,
    ResourceIdentity, ResourcePack, Scene, ScenePlan, Storyboard,
    StoryboardFrame, Timeline, TimelineClip, VideoPrompt, new_id,
)

DEFAULT_OWNER = "web_owner"


def _db_path() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    return Path(configured).expanduser().resolve() if configured else get_data_path("db", "video_factory.sqlite")


def _workspace() -> Path:
    configured = os.environ.get("HERMES_VIDEO_FACTORY_WORKSPACE", "").strip()
    root = Path(configured).expanduser().resolve() if configured else get_data_path("workspaces", "video-factory")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _service() -> VideoFactoryService:
    return VideoFactoryService(SQLiteVideoFactoryRepository(Database(_db_path())))


def _jobs() -> CanonicalJobRepository:
    return CanonicalJobRepository(str(_db_path()))


def _project_json(project) -> dict:
    from dataclasses import asdict
    from enum import Enum

    def prim(v):
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, tuple):
            return [prim(x) for x in v]
        if isinstance(v, list):
            return [prim(x) for x in v]
        if isinstance(v, dict):
            return {k: prim(x) for k, x in v.items()}
        return v

    return prim(asdict(project))


async def _body(request) -> dict:
    try:
        return await request.json()
    except Exception:
        return {}


def _owner(request) -> str:
    q = request.query
    return q.get("owner_user_id", "").strip() or DEFAULT_OWNER


# ----------------------------------------------------------------------
# handlers
# ----------------------------------------------------------------------

async def list_projects(request):
    service = _service()
    owner = _owner(request)
    projects = service.repository.list_owned(owner) if hasattr(service.repository, "list_owned") else []
    return web.json_response({"status": "ok", "data": [_project_json(p) for p in projects]})


async def create_project(request):
    body = await _body(request)
    project = _service().create_project(_owner(request), body.get("project_id") or "")
    return web.json_response({"status": "ok", "data": _project_json(project)}, status=201)


async def get_project(request):
    project = _service().get_project(_owner(request), request.match_info["project_id"])
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def save_resources(request):
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    ws = _workspace()

    # optional product image upload (base64) -> workspace/products/
    product_asset_id = body.get("primary_asset_id") or "asset_prod_1"
    product_uri = f"asset://products/{product_asset_id}.png"
    if body.get("product_image_b64"):
        img_dir = ws / "products"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / f"{product_asset_id}.png").write_bytes(base64.b64decode(body["product_image_b64"]))

    pack = ResourcePack(
        id=body.get("pack_id") or "pack_web",
        owner_user_id=owner,
        product_references=(AssetReference(product_asset_id, product_uri, {"role": "primary"}),),
        primary_product_asset_id=product_asset_id,
        product_identity_description=body.get("product_identity_description") or "product",
        context=body.get("context") or "",
        visual_style=body.get("visual_style") or "",
    )
    service = _service()
    project = service.save_resource_pack(owner, pid, pack)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def lock_resources(request):
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]

    identity = ResourceIdentity(
        description=body.get("description") or body.get("identity_description") or body.get("product_identity_description") or "product",
        shape=body.get("shape") or "",
        color=body.get("color") or body.get("identity_color") or "",
        materials=tuple(body.get("materials") or []),
        logo_placement=body.get("logo_placement") or "",
        distinctive_features=tuple(body.get("distinctive_features") or []),
    )
    project = _service().lock_resource_pack(owner, pid, identity)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def save_idea(request):
    body = await _body(request)
    idea = RawIdea(
        text=body.get("text") or "",
        required_elements=tuple(body.get("required_elements") or []),
        required_cta=body.get("cta") or "",
        target_duration_seconds=body.get("duration_seconds"),
        platform=body.get("platform") or "tiktok",
        aspect_ratio=body.get("aspect_ratio") or "9:16",
    )
    project = _service().save_raw_idea(_owner(request), request.match_info["project_id"], idea)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def save_brief(request):
    body = await _body(request)
    brief = CreativeBrief(
        objective=body.get("objective") or "",
        target_audience=body.get("target_audience") or "",
        core_message=body.get("core_message") or "",
        tone=body.get("tone") or "neutral",
        pace=body.get("pace") or "normal",
        cta=body.get("cta") or "",
        content_blocks=tuple(body.get("content_blocks") or []),
        restrictions=tuple(body.get("restrictions") or []),
        required_content=tuple(body.get("required_content") or []),
        platform=body.get("platform") or "tiktok",
        aspect_ratio=body.get("aspect_ratio") or "9:16",
        target_duration_seconds=body.get("duration_seconds"),
    )
    project = _service().save_creative_brief(_owner(request), request.match_info["project_id"], brief)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def approve_brief(request):
    project = _service().approve_creative_brief(_owner(request), request.match_info["project_id"])
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def save_scenes(request):
    body = await _body(request)
    scenes = []
    for i, item in enumerate(body.get("scenes") or [], start=1):
        scenes.append(Scene(
            scene_id=item.get("scene_id") or f"scene_{i}",
            order=int(item.get("order") or i),
            title=item.get("title") or f"Scene {i}",
            objective=item.get("objective") or "",
            content=item.get("content") or "",
            main_action=item.get("main_action") or "",
            duration_seconds=int(item.get("duration_seconds") or 4),
            context=item.get("context") or "",
            camera_intention=item.get("camera_intention") or "",
            start_state=item.get("start_state") or "",
            end_state=item.get("end_state") or "",
            required_resources=tuple(item.get("required_resources") or ["asset_prod_1"]),
        ))
    project = _service().save_scene_plan(_owner(request), request.match_info["project_id"], ScenePlan(tuple(scenes)))
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def approve_scenes(request):
    project = _service().approve_scene_plan(_owner(request), request.match_info["project_id"])
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def save_storyboard(request):
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    frames = []
    for item in body.get("frames") or []:
        p = item.get("prompt") or {}
        frames.append(StoryboardFrame(
            frame_id=item.get("frame_id") or new_id("frame"),
            scene_id=item.get("scene_id") or "scene_1",
            order=int(item.get("order") or 1),
            label=item.get("label") or "frame",
            purpose=item.get("purpose") or "",
            visual_state=item.get("visual_state") or "",
            subject_action=item.get("subject_action") or "",
            product_state=item.get("product_state") or "",
            character_state=item.get("character_state") or "",
            context=item.get("context") or "",
            camera_intention=item.get("camera_intention") or "",
            required_resource_ids=tuple(item.get("required_resource_ids") or ["asset_prod_1"]),
            prompt=FramePrompt(
                positive_prompt=p.get("positive_prompt") or "",
                negative_constraints=p.get("negative_constraints") or "",
                product_identity_constraints=p.get("product_identity_constraints") or "",
                composition=p.get("composition") or "",
                camera=p.get("camera") or "",
                lighting=p.get("lighting") or "",
                environment=p.get("environment") or "",
                action=p.get("action") or "",
                reference_asset_ids=tuple(p.get("reference_asset_ids") or ["asset_prod_1"]),
                aspect_ratio=p.get("aspect_ratio") or "9:16",
                provider_options=p.get("provider_options") or {},
            ),
        ))
    storyboard = Storyboard(
        storyboard_id=body.get("storyboard_id") or "storyboard_web",
        project_id=pid,
        frames=tuple(frames),
    )
    project = _service().save_storyboard(owner, pid, storyboard)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def approve_storyboard(request):
    project = _service().approve_storyboard(_owner(request), request.match_info["project_id"], "approved via UI1")
    return web.json_response({"status": "ok", "data": _project_json(project)})


def _frame_image_path(ws: Path, project) -> Path | None:
    """Return the real generated storyboard frame image inside the workspace.

    Generated frame assets live under <workspace>/images/<request_id>_<i>.png
    (worker image_generate handler writes request_id-named files). We reuse the
    request_id convention: image jobs were enqueued with request_id
    "{project_id}_{frame_id}".
    """
    if not project.storyboard:
        return None
    img_dir = ws / "images"
    if not img_dir.is_dir():
        return None
    candidates = sorted(img_dir.glob("*.png"))
    if not candidates:
        return None
    # prefer files matching the frame request-id pattern, else the newest image
    frame_ids = {f.frame_id for f in project.storyboard.frames}
    for cand in candidates:
        if any(fid in cand.stem for fid in frame_ids):
            return cand
    return candidates[-1]


async def generate_image(request):
    """Save storyboard frame then enqueue one image_generate job (explicit user action)."""
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    service = _service()
    project = service.get_project(owner, pid)
    ws = _workspace()

    if project.storyboard is None:
        await save_storyboard(request)

    # enqueue job for each planned frame
    project = service.get_project(owner, pid)
    ref_paths = _resolve_resource_image_paths(project, ws)
    jobs = []
    for frame in project.storyboard.frames:
        if frame.generated_asset_id and frame.generation_status.value == "completed":
            continue
        job = Job.new("image_generate", {
            "owner_user_id": owner,
            "request_id": f"{pid}_{frame.frame_id}",
            "prompt": frame.prompt.positive_prompt,
            "negative_prompt": frame.prompt.negative_constraints,
            "aspect_ratio": frame.prompt.aspect_ratio or "9:16",
            "reference_image_paths": ref_paths,
            "max_attempts": 3,
        })
        _jobs().submit(job)
        jobs.append({"frame_id": frame.frame_id, "job_id": job.id})
    return web.json_response({"status": "ok", "data": {"jobs": jobs}})


def _resolve_resource_image_paths(project, ws: Path) -> list[str]:
    """Map Resource Pack product references to real image paths in the workspace.

    Resource URIs use the asset:// scheme (e.g. asset://products/foo.png).
    The referenced file must exist inside the workspace; anything else is
    ignored (source images stay source/reference material only).
    """
    paths: list[str] = []
    if not project.resource_pack:
        return paths
    for ref in project.resource_pack.product_references:
        uri = (ref.uri or "").removeprefix("asset://")
        candidate = (ws / uri).resolve()
        try:
            candidate.relative_to(ws.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            paths.append(str(candidate))
    return paths


async def generate_video_jobs(request):
    """Enqueue durable video_generate jobs for approved storyboard scenes."""
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    service = _service()
    project = service.get_project(owner, pid)

    if project.storyboard and project.storyboard.approval_status.value != "approved":
        return web.json_response({"status": "error", "message": "STORYBOARD_APPROVAL_REQUIRED"}, status=400)

    ref_paths = []
    frame_img = _frame_image_path(_workspace(), project)
    if frame_img:
        ref_paths.append(str(frame_img))

    jobs_enqueued = []
    scenes = project.scene_plan.scenes if (project.scene_plan and project.scene_plan.scenes) else []
    if not scenes:
        scenes = [Scene(scene_id="scene_1", order=1, title="Scene 1")]

    for sc in scenes:
        scene_id = getattr(sc, "scene_id", "scene_1")
        prompt = body.get("prompt") or f"video for scene {scene_id}"
        vp = VideoPrompt(
            scene_id=scene_id,
            duration_seconds=4,
            start_visual_state=body.get("start_visual_state") or "",
            end_visual_state=body.get("end_visual_state") or "",
            subject_action=body.get("subject_action") or "",
            product_action=body.get("product_action") or "",
            camera_movement=body.get("camera_movement") or "",
            camera_framing=body.get("camera_framing") or "",
            environment_motion=body.get("environment_motion") or "",
            motion_constraints=body.get("motion_constraints") or "",
            identity_constraints=body.get("identity_constraints") or "",
            reference_frame_ids=tuple(body.get("reference_frame_ids") or []),
            provider_options=body.get("provider_options") or {},
        )
        service.save_generated_scene(owner, pid, GeneratedScene(scene_id=scene_id, video_prompt=vp))

        job = Job.new("video_generate", {
            "owner_user_id": owner,
            "request_id": f"{pid}_{scene_id}",
            "scene_id": scene_id,
            "prompt": prompt,
            "duration_seconds": 4,
            "aspect_ratio": body.get("aspect_ratio") or "9:16",
            "reference_image_paths": ref_paths,
            "provider_options": body.get("provider_options") or {"resolution": "720p", "sampleCount": 1},
            "max_attempts": 200,
        })
        _jobs().submit(job)
        jobs_enqueued.append({"job_id": job.id, "scene_id": scene_id})

    return web.json_response({"status": "ok", "data": {"jobs": jobs_enqueued}})


async def save_video(request):
    """Save video prompt and enqueue one video_generate job."""
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    service = _service()
    project = service.get_project(owner, pid)

    if project.storyboard and project.storyboard.approval_status.value != "approved":
        return web.json_response({"status": "error", "message": "STORYBOARD_APPROVAL_REQUIRED"}, status=400)

    scene_id = body.get("scene_id") or "scene_1"
    prompt = body.get("prompt") or ""
    vp = VideoPrompt(
        scene_id=scene_id,
        duration_seconds=4,
        start_visual_state=body.get("start_visual_state") or "",
        end_visual_state=body.get("end_visual_state") or "",
        subject_action=body.get("subject_action") or "",
        product_action=body.get("product_action") or "",
        camera_movement=body.get("camera_movement") or "",
        camera_framing=body.get("camera_framing") or "",
        environment_motion=body.get("environment_motion") or "",
        motion_constraints=body.get("motion_constraints") or "",
        identity_constraints=body.get("identity_constraints") or "",
        reference_frame_ids=tuple(body.get("reference_frame_ids") or []),
        provider_options=body.get("provider_options") or {},
    )
    service.save_generated_scene(owner, pid, GeneratedScene(scene_id=scene_id, video_prompt=vp))

    # reference frame image path (must be inside workspace)
    ref_paths = []
    frame_img = _frame_image_path(_workspace(), service.get_project(owner, pid))
    if frame_img:
        ref_paths.append(str(frame_img))

    job = Job.new("video_generate", {
        "owner_user_id": owner,
        "request_id": f"{pid}_{scene_id}",
        "scene_id": scene_id,
        "prompt": prompt,
        "duration_seconds": 4,
        "aspect_ratio": body.get("aspect_ratio") or "9:16",
        "reference_image_paths": ref_paths,
        "provider_options": body.get("provider_options") or {"resolution": "720p", "sampleCount": 1},
        "max_attempts": 200,
    })
    _jobs().submit(job)
    return web.json_response({"status": "ok", "data": {"job_id": job.id}})


async def save_timeline(request):
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    clips = []
    for i, item in enumerate(body.get("clips") or [], start=1):
        clips.append(TimelineClip(
            clip_id=item.get("clip_id") or f"clip_{i}",
            order=int(item.get("order") or i),
            source_asset_id=item.get("source_asset_id") or "scene_asset_scene_1",
            duration_seconds=float(item.get("duration_seconds") or 4.0),
        ))
    timeline = Timeline(timeline_id=body.get("timeline_id") or "timeline_web", project_id=pid, clips=tuple(clips))
    project = _service().save_timeline(owner, pid, timeline)
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def generate_voiceover(request):
    """Enqueue a durable tts_generate job (explicit user action).

    The actual synthesis runs in the canonical worker via the configured
    TTS provider. The caller must POST /jobs/{id}/apply to persist the
    resulting WAV asset identity into the project timeline.
    """
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    text = body.get("text") or ""
    if not text.strip():
        return web.json_response({"status": "error", "message": "text required"}, status=400)
    style_prompt = body.get("style_prompt") or (
        "Speak Vietnamese with a bright, clear, youthful and energetic short-video narration style. "
        "Use lively pitch variation and expressive intonation. Keep articulation crisp and natural. "
        "Use a brisk pace without sounding rushed. Avoid excessive breathiness, heaviness, or overly theatrical delivery."
    )
    voice = body.get("voice") or "Zephyr"

    job = Job.new("tts_generate", {
        "owner_user_id": owner,
        "request_id": f"{pid}_voiceover",
        "text": text,
        "voice": voice,
        "language": body.get("language") or "vi-VN",
        "style_prompt": style_prompt,
        "max_attempts": 3,
    })
    _jobs().submit(job)

    return web.json_response({"status": "accepted", "data": {"job_id": job.id, "voice": voice}}, status=202)


async def mix_voiceover(request):
    """Mix one voiceover WAV into the draft video (deterministic FFmpeg)."""
    owner = _owner(request)
    pid = request.match_info["project_id"]
    project = _service().get_project(owner, pid)
    ws = _workspace()
    wavs = sorted((ws / "audio").glob("*.wav"))
    if not wavs:
        return web.json_response({"status": "error", "message": "no voiceover wav found"}, status=400)
    videos = sorted((ws / "videos").glob("*.mp4"))
    draft = next((v for v in videos if "draft" in v.name), None)
    src = draft or next((v for v in videos if "final" not in v.name), None)
    if src is None:
        return web.json_response({"status": "error", "message": "no source video found"}, status=400)

    from hermes.adapters.local.desktop_runtime import DesktopRuntime
    out = ws / "videos" / "final_video_with_voiceover.mp4"
    result = DesktopRuntime().ffmpeg.render_with_audio(str(src), str(wavs[0]), str(out))
    if not result.ok:
        return web.json_response({"status": "error", "message": result.message or "ffmpeg failed"}, status=500)
    return web.json_response({"status": "ok", "data": {"output_path": str(out)}})


async def publish_to_tiktok(request):
    """Explicit Publish action. Requires a valid TIKTOK_ACCESS_TOKEN (user OAuth)."""
    body = await _body(request)
    owner = _owner(request)
    pid = request.match_info["project_id"]
    project = _service().get_project(owner, pid)
    if project.status != "ready_to_publish" or not project.final_video_asset_id:
        return web.json_response({"status": "error", "message": "NOT_READY_TO_PUBLISH"}, status=400)

    caption = body.get("caption") or ""
    visibility = body.get("visibility") or "public"

    from hermes.adapters.sqlite.publisher_repository import SQLitePublicationStore
    from hermes.domain.publisher import Publication, PublicationStatus
    from hermes.ports.publisher import PublishRequest
    from providers.tiktok_publisher import TikTokPublisher

    ws = _workspace()
    final_video = ws / "videos" / "final_video.mp4"
    if not final_video.is_file():
        return web.json_response({"status": "error", "message": "final video missing"}, status=400)

    publisher = TikTokPublisher()
    result = publisher.publish(PublishRequest(
        project_id=pid, owner_user_id=owner, video_path=str(final_video),
        caption=caption, visibility=visibility,
    ))
    if not result.ok:
        return web.json_response({"status": "error", "message": result.error_message}, status=502)

    store = SQLitePublicationStore(Database(_db_path()))
    pub = store.get(owner, pid, "tiktok")
    if pub is None:
        pub = Publication(
            publication_id=f"pub_{pid}", project_id=pid, owner_user_id=owner, platform="tiktok",
            status=PublicationStatus.PROCESSING, caption=caption, post_id=result.post_id,
        )
    store.update_status(owner, pid, "tiktok", PublicationStatus.PROCESSING, post_id=result.post_id)
    return web.json_response({"status": "ok", "data": {"post_id": result.post_id, "status": result.status}})


async def get_publication(request):
    owner = _owner(request)
    pid = request.match_info["project_id"]
    from hermes.adapters.sqlite.publisher_repository import SQLitePublicationStore
    from hermes.domain.publisher import PublicationStatus
    store = SQLitePublicationStore(Database(_db_path()))
    pub = store.get(owner, pid, "tiktok")
    if pub is None:
        return web.json_response({"status": "ok", "data": {"status": PublicationStatus.NOT_PUBLISHED.value}})
    return web.json_response({"status": "ok", "data": {
        "status": pub.status.value, "post_id": pub.post_id,
        "caption": pub.caption, "published_at": pub.published_at, "last_error": pub.last_error,
    }})


async def tiktok_authorize(request):
    """Return the TikTok OAuth authorize URL (no external call)."""
    from providers.tiktok_publisher import authorize_url
    redirect_uri = os.environ.get("TIKTOK_REDIRECT_URI", "").strip()
    if not redirect_uri:
        return web.json_response({"status": "error", "message": "TIKTOK_REDIRECT_URI_REQUIRED"}, status=400)
    return web.json_response({"status": "ok", "data": {"authorize_url": authorize_url(redirect_uri)}})


async def apply_job(request):
    """Apply a completed durable job result into the Video Factory domain state.

    image_generate   → updates storyboard frame status/asset
    video_generate   → updates scene status/asset/operation id
    tts_generate     → updates timeline.audio_track_asset_id
    video.render     → draft/final asset (rendered file already in workspace)

    Idempotent: re-applying a completed job is safe.
    """
    owner = _owner(request)
    pid = request.match_info["project_id"]
    job_id = request.match_info["job_id"]
    job = _jobs().get_job(job_id)
    if job is None:
        return web.json_response({"status": "error", "message": "JOB_NOT_FOUND"}, status=404)
    if job.status.name.lower() != "succeeded":
        return web.json_response({"status": "error", "message": "JOB_NOT_COMPLETED"}, status=409)

    service = _service()
    project = service.get_project(owner, pid)
    payload = job.payload or {}
    result = job.result or {}

    if job.task_name == "image_generate":
        frame_id = (payload.get("request_id") or "").replace(f"{pid}_", "", 1)
        if not frame_id or not any(f.frame_id == frame_id for f in (project.storyboard.frames if project.storyboard else [])):
            return web.json_response({"status": "error", "message": "FRAME_NOT_FOUND"}, status=404)
        project = service.update_frame_generation_status(
            owner, pid, frame_id, "completed",
            asset_id=f"frame_asset_{frame_id}", job_id=job_id,
        )
    elif job.task_name == "video_generate":
        scene_id = payload.get("scene_id") or "scene_1"
        project = service.update_scene_generation_status(
            owner, pid, scene_id, "completed",
            asset_id=f"scene_asset_{scene_id}", job_id=job_id,
            provider_operation_id=(result or {}).get("provider_operation_id"),
        )
    elif job.task_name == "tts_generate":
        # Store the final wav_path in project.draft_video_asset_id and set audio track
        if result and result.get("wav_path"):
            # Update timeline audio_track_asset_id with the WAV asset
            project = service.update_timeline_status(owner, pid, "completed")
            # Persist the audio track identity - using real domain model pattern
            from hermes.domain.video_factory import Timeline, TimelineClip
            # Find or create audio track clip entry
            audio_clip = project.timeline.clips[-1] if project.timeline and project.timeline.clips else TimelineClip(clip_id="audio_track", order=1, source_asset_id="audio_track", duration_seconds=4.0)
            if not project.timeline:
                timeline = Timeline(timeline_id="timeline_web", project_id=pid, clips=[],
                                  audio_track_asset_id=f"audio_track_{job_id}")
            else:
                timeline = project.timeline
                timeline.audio_track_asset_id = f"audio_track_{job_id}"
                timeline.status = TimelineStatus.COMPLETED
                timeline.status = TimelineStatus.COMPLETED
                timeline.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
            # Save the updated timeline
            updated_timeline = service.save_timeline(owner, pid, timeline)
    else:
        # video.render / other: no domain mapping needed, file is in workspace
        pass

    return web.json_response({"status": "ok", "data": _project_json(project)})


async def render_draft(request):
    """Enqueue deterministic draft render of the generated scene video."""
    owner = _owner(request)
    pid = request.match_info["project_id"]
    service = _service()
    project = service.get_project(owner, pid)
    ws = _workspace()
    videos = sorted((ws / "videos").glob("*.mp4"))
    scene_mp4 = next((v for v in videos if "draft" not in v.name and "final" not in v.name), None)
    if scene_mp4 is None:
        return web.json_response({"status": "error", "message": "no generated scene video found"}, status=400)

    service.update_timeline_status(owner, pid, "rendering")
    job = Job.new("video.render", {
        "owner_user_id": owner,
        "asset_id": str(scene_mp4),
        "output_path": str(ws / "videos" / "draft_video.mp4"),
        "output_format": "mp4",
        "max_attempts": 3,
    })
    _jobs().submit(job)
    return web.json_response({"status": "ok", "data": {"job_id": job.id}})


async def approve_final(request):
    project = _service().approve_final_video(_owner(request), request.match_info["project_id"], "approved via UI1")
    return web.json_response({"status": "ok", "data": _project_json(project)})


async def export_final(request):
    """Enqueue deterministic final export (copy of draft), then save_final_export."""
    owner = _owner(request)
    pid = request.match_info["project_id"]
    service = _service()
    project = service.get_project(owner, pid)
    if project.final_approval.value != "approved":
        return web.json_response({"status": "error", "message": "FINAL_APPROVAL_REQUIRED"}, status=400)
    ws = _workspace()
    draft = ws / "videos" / "draft_video.mp4"
    if not draft.is_file():
        return web.json_response({"status": "error", "message": "draft video missing"}, status=400)
    job = Job.new("video.render", {
        "owner_user_id": owner,
        "asset_id": str(draft),
        "output_path": str(ws / "videos" / "final_video.mp4"),
        "output_format": "mp4",
        "max_attempts": 3,
    })
    _jobs().submit(job)
    return web.json_response({"status": "ok", "data": {"job_id": job.id}})


async def get_job(request):
    job = _jobs().get_job(request.match_info["job_id"])
    if job is None:
        return web.json_response({"status": "error", "message": "JOB_NOT_FOUND"}, status=404)
    return web.json_response({
        "status": "ok",
        "data": {
            "id": job.id,
            "task_name": job.task_name,
            "state": job.status.name.lower(),
            "payload": job.payload,
            "result": job.result,
            "error": job.error,
        },
    })


async def media(request):
    """Serve generated media from the workspace with containment checks."""
    ws = _workspace().resolve()
    rel = request.match_info["path"]
    target = (ws / rel).resolve()
    try:
        target.relative_to(ws)
    except ValueError:
        return web.Response(status=403, text="forbidden")
    if not target.is_file():
        return web.Response(status=404, text="not found")
    return web.FileResponse(target)


def build_routes() -> list:
    return [
        web.get("/api/vf/projects", list_projects),
        web.post("/api/vf/projects", create_project),
        web.get("/api/vf/projects/{project_id}", get_project),
        web.post("/api/vf/projects/{project_id}/resources", save_resources),
        web.post("/api/vf/projects/{project_id}/resources/lock", lock_resources),
        web.post("/api/vf/projects/{project_id}/idea", save_idea),
        web.post("/api/vf/projects/{project_id}/brief", save_brief),
        web.post("/api/vf/projects/{project_id}/brief/approve", approve_brief),
        web.post("/api/vf/projects/{project_id}/scenes", save_scenes),
        web.post("/api/vf/projects/{project_id}/scenes/approve", approve_scenes),
        web.post("/api/vf/projects/{project_id}/storyboard", save_storyboard),
        web.post("/api/vf/projects/{project_id}/storyboard/generate", generate_image),
        web.post("/api/vf/projects/{project_id}/storyboard/approve", approve_storyboard),
        web.post("/api/vf/projects/{project_id}/video", save_video),
        web.post("/api/vf/projects/{project_id}/video/generate", generate_video_jobs),
        web.post("/api/vf/projects/{project_id}/timeline", save_timeline),
        web.post("/api/vf/projects/{project_id}/timeline/render", render_draft),
        web.post("/api/vf/projects/{project_id}/final/approve", approve_final),
        web.post("/api/vf/projects/{project_id}/final/export", export_final),
        web.post("/api/vf/projects/{project_id}/tts", generate_voiceover),
        web.post("/api/vf/projects/{project_id}/tts/mix", mix_voiceover),
        web.post("/api/vf/projects/{project_id}/publish", publish_to_tiktok),
        web.get("/api/vf/projects/{project_id}/publication", get_publication),
        web.get("/api/vf/auth/tiktok", tiktok_authorize),
        web.get("/api/vf/jobs/{job_id}", get_job),
        web.post("/api/vf/projects/{project_id}/jobs/{job_id}/apply", apply_job),
        web.get("/media/{path:.*}", media),
    ]
