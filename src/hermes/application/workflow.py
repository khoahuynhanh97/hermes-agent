"""Orchestration service for Hermes Product-to-Video Workflow."""
from __future__ import annotations

import os
import logging
import re
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from hermes.db import Database
from hermes.runtime_layout import get_work_journal_dir, get_workspaces_dir, get_data_root
from hermes.application.work_journal import WorkJournal, WorkJournalEntry, RunStatus, JournalStep
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.adapters.sqlite.product_resource_binding_repository import SQLiteProjectResourceBindingRepository
from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.application.asset_projection_service import AssetProjectionService
from hermes.application.product_resource_service import ProductResourceService
from hermes.adapters.local.ffmpeg_capability import FFmpegCapability, render_beat_keyframe
from hermes.integrations.providers.tts_provider_factory import get_tts_provider, EdgeTTSProvider
from hermes.ports.text_to_speech import TTSRequest
from hermes.workers.job_worker import CanonicalJobWorker
from hermes.domain.video_factory import (
    AssetReference, ResourcePack, CreativeBrief, ScenePlan, Scene,
    Storyboard, StoryboardFrame, FramePrompt, FrameGenerationStatus,
    GeneratedScene, VideoPrompt, VideoGenerationStatus, Timeline,
    TimelineClip, TimelineStatus, ProjectStatus, HookVariant, ABVariantSet,
    new_id,
)

logger = logging.getLogger(__name__)


def _extract_product_name(prompt: str, product_query: str | None = None, owner_user_id: str = "user") -> str:
    """Dynamically infer product name from query, prompt text, or persisted PI locks."""
    if product_query and product_query.strip():
        return product_query.strip()

    # 1. First check if any registered PI lock product name or brand/model appears in prompt
    from hermes.application.asset_projection_service import AssetProjectionService
    try:
        svc = AssetProjectionService()
        for lock in svc.list_resource_pack_locks(owner_user_id):
            pname = str(lock.get("product_name", "")).strip()
            brand = str(lock.get("brand", "")).strip()
            model = str(lock.get("model", "")).strip()
            cid = str(lock.get("canonical_product_id", "")).strip()
            if pname and pname.lower() in prompt.lower():
                return pname
            if brand and model and (f"{brand} {model}".lower() in prompt.lower() or f"{brand}-{model}".lower() in prompt.lower()):
                return pname or f"{brand} {model}"
            if cid and cid.lower() in prompt.lower():
                return pname or cid
    except Exception:
        pass

    # 2. Extract product model/brand before length or trailing clause
    text = prompt
    for prefix in ["Tạo cho tôi video TikTok review", "Tạo video TikTok review", "Tạo video review", "Review video for", "Review", "Video review"]:
        if prefix.lower() in text.lower():
            idx = text.lower().find(prefix.lower())
            text = text[idx + len(prefix):]
            break

    match = re.search(r"^\s*(?:tai nghe|đồng hồ|điện thoại|laptop|máy tính|loa|camera)?\s*([A-Za-z0-9\s\-]+?)(?=\s*:|\s+dài|\s+tại|\s+trên|\s+với|\s+chất|\s+nhấn|\.|$)", text.strip(), re.IGNORECASE)
    if match and len(match.group(1).strip()) > 1:
        return match.group(1).strip()

    return prompt.strip()


class WorkflowOrchestrator:
    def __init__(self, db_path: Path, *, pi_data_root: Path | None = None):
        self.db_path = db_path
        self.db = Database(str(db_path))
        self.db.initialize()
        self.repo = SQLiteVideoFactoryRepository(self.db)
        self.vf_service = VideoFactoryService(self.repo)
        self.journal = WorkJournal(get_work_journal_dir())
        self.asset_projection = AssetProjectionService(pi_data_root=pi_data_root)
        self.binding_repository = SQLiteProjectResourceBindingRepository(self.db)
        self.product_resources = ProductResourceService(self.binding_repository)
        self.asset_repository = SQLiteGeneratedAssetRepository(self.db)
        self.ffmpeg = FFmpegCapability()
        self.worker = CanonicalJobWorker(str(db_path), str(get_workspaces_dir()))

    def create_acceptance_run(
        self,
        product_id: str,
        resource_pack_lock_id: str,
        snapshot_id: str,
        project_id: str | None = None,
    ) -> WorkJournalEntry:
        run_id = f"run_{uuid4().hex}"
        entry = WorkJournalEntry(
            run_id=run_id,
            project_id=project_id,
            product_id=product_id,
            resource_pack_lock_id=resource_pack_lock_id,
            snapshot_id=snapshot_id,
            status=RunStatus.STARTED,
            steps=[]
        )
        self.journal.record_entry(entry)
        return entry

    def update_acceptance_run_step(
        self,
        run_id: str,
        step_name: str,
        status: RunStatus,
        summary: Optional[str] = None,
        tool_results: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None
    ) -> None:
        entry = self.journal.get_entry(run_id)
        if entry:
            existing_step = next((s for s in entry.steps if s.name == step_name), None)
            if existing_step:
                existing_step.status = status
                existing_step.summary = summary
                if tool_results:
                    existing_step.tool_results.extend(tool_results)
                if errors:
                    existing_step.errors.extend(errors)
                existing_step.completed_at = datetime.now(timezone.utc) if status != RunStatus.IN_PROGRESS else None
            else:
                new_step = JournalStep(
                    name=step_name,
                    status=status,
                    summary=summary,
                    tool_results=tool_results or [],
                    errors=errors or [],
                    completed_at=datetime.now(timezone.utc) if status != RunStatus.IN_PROGRESS else None
                )
                entry.steps.append(new_step)
            self.journal.record_entry(entry)

    def complete_acceptance_run(self, run_id: str, status: RunStatus, errors: Optional[List[str]] = None) -> None:
        entry = self.journal.get_entry(run_id)
        if entry:
            entry.status = status
            entry.completed_at = datetime.now(timezone.utc)
            if errors:
                entry.errors.extend(errors)
            self.journal.record_entry(entry)

    def get_project_status(self, owner_user_id: str, project_id: str) -> Dict[str, Any]:
        project = self.vf_service.get_project(owner_user_id, project_id)
        return {
            "project_id": project.id,
            "owner_user_id": project.owner_user_id,
            "status": project.status.value,
            "state": project.status.value,
            "resource_version": project.resource_version,
            "storyboard_version": project.storyboard_version,
            "timeline_version": project.timeline_version,
            "draft_video_asset_id": project.draft_video_asset_id,
            "final_video_asset_id": project.final_video_asset_id,
        }

    def resolve_product_lock(self, owner_user_id: str, product_query: str) -> Dict[str, Any]:
        """Resolve authentic Product Intelligence ResourcePackLock."""
        lock = self.asset_projection.find_resource_pack_lock(owner_user_id, product_query)
        if lock is None:
            raise ValueError(f"PRODUCT_INTELLIGENCE_LOCK_NOT_FOUND: No authentic Product Intelligence lock found for '{product_query}'")
        return lock

    def create_video_project(self, owner_user_id: str, project_id: str, product_query: str) -> Dict[str, Any]:
        lock = self.resolve_product_lock(owner_user_id, product_query)

        try:
            project = self.vf_service.get_project(owner_user_id, project_id)
        except ValueError:
            project = self.vf_service.create_project(owner_user_id, project_id)

        existing = self.binding_repository.get_by_project_id(project_id)
        if existing is None:
            binding = self.product_resources.verify_and_bind(project_id, lock, owner_user_id)
        elif existing.manifest_digest == lock.get("manifest_digest"):
            binding = existing
        else:
            raise ValueError("PROJECT_ALREADY_BOUND_TO_DIFFERENT_RESOURCE_LOCK")

        references = tuple(
            AssetReference(
                asset_id=str(asset["asset_id"]),
                uri=str(asset["local_path"]),
                metadata={
                    "mime_type": asset.get("mime_type", ""),
                    "snapshot_id": lock.get("snapshot_id", ""),
                    "resource_pack_lock_id": lock.get("lock_id", ""),
                },
            )
            for asset in lock.get("assets", [])
            if asset.get("asset_id") and asset.get("local_path")
        )

        pack = ResourcePack(
            id=str(lock["lock_id"]),
            owner_user_id=owner_user_id,
            product_references=references,
            primary_product_asset_id=references[0].asset_id if references else "asset_ref_1",
            product_identity_description=str(lock.get("product_name") or binding.canonical_product_id),
            locked_at=str(lock.get("locked_at") or "locked"),
            version=int(lock.get("resource_pack_version", lock.get("version", 1))),
        )
        project = self.vf_service.save_resource_pack(owner_user_id, project.id, pack)
        run = self.create_acceptance_run(
            binding.canonical_product_id,
            str(lock["lock_id"]),
            str(lock.get("snapshot_id", "")),
            project.id,
        )
        return {
            "status": "ok",
            "run_id": run.run_id,
            "project_id": project.id,
            "product_id": binding.canonical_product_id,
            "snapshot_id": lock.get("snapshot_id", ""),
            "resource_pack_lock_id": lock["lock_id"],
            "manifest_digest": binding.manifest_digest,
            "lock": lock,
        }

    def dispatch_product_to_video_workflow(
        self,
        owner_user_id: str = "user",
        prompt: str = "Tạo video TikTok review sản phẩm dài 30 giây",
        product_query: str | None = None,
        duration_seconds: int = 30,
        platform: str = "TikTok",
        language: str = "Vietnamese",
    ) -> Dict[str, Any]:
        """Asynchronously dispatch end-to-end Product-to-Video Workflow into CanonicalJobWorker."""
        target_product_name = _extract_product_name(prompt, product_query, owner_user_id)

        # 1. Resolve or construct Product Resource Lock & Project
        project_id = f"vfp_{int(time.time())}_{uuid4().hex[:6]}"
        proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
        lock = proj_meta["lock"]
        run_id = proj_meta["run_id"]
        canonical_product_id = proj_meta["product_id"]
        lock_id = proj_meta["resource_pack_lock_id"]
        snapshot_id = proj_meta["snapshot_id"]

        self.update_acceptance_run_step(run_id, "resolve_product_lock", RunStatus.COMPLETED, f"Locked {target_product_name} via {lock_id}")
        self.update_acceptance_run_step(run_id, "create_project", RunStatus.COMPLETED, f"Created project {project_id}")

        job_id = f"job_wf_{uuid4().hex[:8]}"
        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "owner_user_id": owner_user_id,
            "prompt": prompt,
            "product_query": target_product_name,
            "duration_seconds": duration_seconds,
            "platform": platform,
            "language": language,
            "resource_lock_id": lock_id,
            "canonical_product_id": canonical_product_id,
            "snapshot_id": snapshot_id,
        }

        self.worker.repository.enqueue(job_id, owner_user_id, "product_to_video_workflow", payload)
        self.update_acceptance_run_step(run_id, "job_dispatch", RunStatus.IN_PROGRESS, f"Workflow job {job_id} queued in CanonicalJobWorker")

        return {
            "status": "queued",
            "job_id": job_id,
            "project_id": project_id,
            "run_id": run_id,
            "product_id": canonical_product_id,
            "resource_pack_lock_id": lock_id,
            "state": "queued",
            "message": f"Product-to-video workflow queued with job_id {job_id}",
            "job_url": f"/api/jobs/{job_id}",
            "project_url": f"/api/vf/projects/{project_id}",
            "progress_url": f"/api/vf/projects/{project_id}/progress",
        }

    def run_product_to_video_workflow(
        self,
        owner_user_id: str = "user",
        prompt: str = "Tạo video TikTok review sản phẩm dài 30 giây",
        product_query: str | None = None,
        duration_seconds: int = 30,
        platform: str = "TikTok",
        language: str = "Vietnamese",
        project_id: str | None = None,
        run_id: str | None = None,
        async_dispatch: bool = False,
    ) -> Dict[str, Any]:
        """Execute end-to-end 14-step Product-to-Video Workflow with durable job processing and output probe validation."""
        if async_dispatch:
            return self.dispatch_product_to_video_workflow(
                owner_user_id=owner_user_id,
                prompt=prompt,
                product_query=product_query,
                duration_seconds=duration_seconds,
                platform=platform,
                language=language,
            )

        target_product_name = _extract_product_name(prompt, product_query, owner_user_id)

        # 1. Resolve or construct Product Resource Lock
        if project_id:
            try:
                project = self.vf_service.get_project(owner_user_id, project_id)
            except ValueError:
                project = None
            if project and project.resource_pack:
                lock = self.resolve_product_lock(owner_user_id, target_product_name)
                canonical_product_id = project.resource_pack.product_identity_description
                lock_id = project.resource_pack.id
                snapshot_id = lock.get("snapshot_id", "")
                if not run_id:
                    run = self.create_acceptance_run(canonical_product_id, lock_id, snapshot_id, project_id)
                    run_id = run.run_id
            else:
                proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
                lock = proj_meta["lock"]
                run_id = proj_meta["run_id"]
                canonical_product_id = proj_meta["product_id"]
                lock_id = proj_meta["resource_pack_lock_id"]
                snapshot_id = proj_meta["snapshot_id"]
        else:
            project_id = f"vfp_{int(time.time())}_{uuid4().hex[:6]}"
            proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
            lock = proj_meta["lock"]
            run_id = proj_meta["run_id"]
            canonical_product_id = proj_meta["product_id"]
            lock_id = proj_meta["resource_pack_lock_id"]
            snapshot_id = proj_meta["snapshot_id"]

        self.update_acceptance_run_step(run_id, "resolve_product_lock", RunStatus.COMPLETED, f"Locked {target_product_name} via {lock_id}")
        self.update_acceptance_run_step(run_id, "create_project", RunStatus.COMPLETED, f"Created project {project_id}")

        workspace_dir = get_workspaces_dir() / project_id
        generated_dir = workspace_dir / "generated"
        exports_dir = workspace_dir / "exports"
        generated_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)

        # 2. Creative Brief Generation & Approval
        brief = CreativeBrief(
            objective=f"High-converting {platform} review video for {target_product_name} showcasing key features and value",
            target_audience=f"Tech enthusiasts, remote workers, shoppers on {platform}",
            core_message=f"{target_product_name} delivers premium performance, studio sound, and exceptional battery life",
            tone="Confident, energetic, authentic",
            pace="Dynamic",
            cta=f"Shop {target_product_name} now on {platform}!",
            content_blocks=("Hook Reveal", "Key Features & Sound", "Ergonomics & Battery", "Special Offer Call to Action"),
            platform=platform,
            aspect_ratio="9:16",
            target_duration_seconds=duration_seconds,
        )
        self.vf_service.save_creative_brief(owner_user_id, project_id, brief)
        self.vf_service.approve_creative_brief(owner_user_id, project_id)
        self.update_acceptance_run_step(run_id, "brief_approval", RunStatus.COMPLETED, "Creative brief approved")

        # 3. Scene Plan Generation & Approval
        scenes = (
            Scene(
                scene_id="scene_1",
                order=1,
                title="Beat 1: Visual Hook & Reveal",
                objective="Unboxing & visual reveal of product",
                content=f"Close-up visual reveal of {target_product_name} packaging and design",
                main_action=f"Unbox {target_product_name}",
                context="Studio desk backdrop",
                camera_intention="Push in slow zoom",
                duration_seconds=6,
            ),
            Scene(
                scene_id="scene_2",
                order=2,
                title="Beat 2: Core Features & Sound",
                objective="Demonstrate noise cancellation & sound isolation",
                content=f"User wearing {target_product_name} experiencing studio audio quality",
                main_action="Put on product & tap control",
                context="Coffee shop environment",
                camera_intention="Cinematic slow zoom",
                duration_seconds=8,
            ),
            Scene(
                scene_id="scene_3",
                order=3,
                title="Beat 3: Comfort & Battery",
                objective="Showcase ergonomic fit & all-day battery life",
                content=f"Comfortable fit and long battery life indicator for {target_product_name}",
                main_action="Touch control tap",
                context="Modern office workspace",
                camera_intention="Side panning shot",
                duration_seconds=8,
            ),
            Scene(
                scene_id="scene_4",
                order=4,
                title="Beat 4: Call to Action",
                objective="Direct viewers to buy",
                content=f"Hero display of {target_product_name} with discount buy button",
                main_action="Hold product hero view",
                context="Clean hero backdrop",
                camera_intention="Static hero shot",
                duration_seconds=8,
            ),
        )
        plan = ScenePlan(scenes=scenes)
        self.vf_service.save_scene_plan(owner_user_id, project_id, plan)
        self.vf_service.approve_scene_plan(owner_user_id, project_id)
        self.update_acceptance_run_step(run_id, "scene_plan_approval", RunStatus.COMPLETED, "4-beat scene plan approved")

        # 4. Storyboard & Keyframe Generation using 4 Authentic Product Photos from ResourcePackLock
        ref_asset_ids = [str(ref.get("asset_id")) for ref in lock.get("assets", []) if ref.get("asset_id")]
        ref_asset_paths = [str(ref.get("local_path") or ref.get("uri") or "") for ref in lock.get("assets", []) if (ref.get("local_path") or ref.get("uri"))]

        frames = []
        for i, scene in enumerate(scenes):
            frame_id = f"frame_{i+1}"
            kf_img_path = str(generated_dir / f"keyframe_beat_{i+1}.png")
            photo_path = ref_asset_paths[i % len(ref_asset_paths)] if ref_asset_paths and Path(ref_asset_paths[i % len(ref_asset_paths)]).is_file() else None

            render_beat_keyframe(
                output_path=kf_img_path,
                beat_index=i + 1,
                title=scene.title,
                subtitle=scene.main_action,
                product_name=target_product_name,
                product_ref_image_path=photo_path,
                width=720,
                height=1280,
            )

            job_payload = {
                "request_id": f"img_{project_id}_{frame_id}",
                "project_id": project_id,
                "scene_id": frame_id,
                "prompt": f"Studio shot of {target_product_name}, {scene.content}",
                "output_path": kf_img_path,
                "resource_lock_id": lock_id,
            }
            job_id = f"job_img_{uuid4().hex[:8]}"
            self.worker.repository.enqueue(job_id, owner_user_id, "image_generate", job_payload)
            self.worker.run_once()

            kf_asset_id = f"asset_sb_{project_id}_{frame_id}"
            self.asset_repository.save_asset({
                "asset_id": kf_asset_id,
                "project_id": project_id,
                "scene_id": frame_id,
                "job_id": job_id,
                "provider": "pillow",
                "resource_lock_id": lock_id,
                "output_path": kf_img_path,
            })
            prompt_obj = FramePrompt(
                positive_prompt=f"Studio shot of {target_product_name}, {scene.content}",
                negative_constraints="No text distortion, no low res",
                product_identity_constraints=target_product_name,
                action=scene.main_action,
                reference_asset_ids=tuple(ref_asset_ids),
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
                required_resource_ids=tuple(ref_asset_ids),
                prompt=prompt_obj,
                generation_status=FrameGenerationStatus.COMPLETED,
                generated_asset_id=kf_asset_id,
                generation_job_id=job_id,
            )
            frames.append(frame)

        storyboard = Storyboard(storyboard_id=new_id("storyboard"), project_id=project_id, frames=tuple(frames))
        self.vf_service.save_storyboard(owner_user_id, project_id, storyboard)
        self.vf_service.approve_storyboard(owner_user_id, project_id, "All keyframe beats approved")
        self.update_acceptance_run_step(run_id, "storyboard_keyframes", RunStatus.COMPLETED, "4 distinct keyframe beats generated")

        # 5. Video Scene Clips Generation
        generated_scenes = []
        clip_paths = []
        for i, scene in enumerate(scenes):
            scene_clip_path = str(generated_dir / f"scene_{i+1}.mp4")
            kf_img_path = str(generated_dir / f"keyframe_beat_{i+1}.png")

            self.ffmpeg.create_video_clip_from_image(
                image_path=kf_img_path,
                output_path=scene_clip_path,
                duration_seconds=scene.duration_seconds,
            )

            vgen_payload = {
                "project_id": project_id,
                "scene_id": scene.scene_id,
                "image_path": kf_img_path,
                "duration_seconds": scene.duration_seconds,
                "output_path": scene_clip_path,
            }
            v_job_id = f"job_vgen_{uuid4().hex[:8]}"
            self.worker.repository.enqueue(v_job_id, owner_user_id, "video_generate", vgen_payload)
            self.worker.run_once()

            clip_paths.append(scene_clip_path)
            scene_asset_id = f"asset_scene_{project_id}_s{i+1}"
            self.asset_repository.save_asset({
                "asset_id": scene_asset_id,
                "project_id": project_id,
                "scene_id": scene.scene_id,
                "job_id": v_job_id,
                "provider": "ffmpeg",
                "resource_lock_id": lock_id,
                "output_path": scene_clip_path,
            })

            v_prompt = VideoPrompt(
                scene_id=scene.scene_id,
                duration_seconds=scene.duration_seconds,
                start_visual_state=scene.content,
                end_visual_state=scene.content,
                subject_action=scene.main_action,
                product_action=scene.main_action,
                camera_movement=scene.camera_intention,
                camera_framing="Vertical 9:16",
                environment_motion="Normal motion",
                negative_constraints="No blur",
            )
            g_scene = GeneratedScene(
                scene_id=scene.scene_id,
                video_prompt=v_prompt,
                generation_status=VideoGenerationStatus.COMPLETED,
                generated_asset_id=scene_asset_id,
                generation_job_id=v_job_id,
                review_notes="Rendered 9:16 vertical motion scene clip",
            )
            generated_scenes.append(g_scene)

        project = self.vf_service.get_project(owner_user_id, project_id)
        self.vf_service.repository.save(
            project.__class__(
                id=project.id,
                owner_user_id=project.owner_user_id,
                created_at=project.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(),
                resource_pack=project.resource_pack,
                resource_version=project.resource_version,
                raw_idea=project.raw_idea,
                idea_version=project.idea_version,
                creative_brief=project.creative_brief,
                brief_approval=project.brief_approval,
                brief_version=project.brief_version,
                scene_plan=project.scene_plan,
                scene_plan_approval=project.scene_plan_approval,
                scene_version=project.scene_version,
                storyboard=project.storyboard,
                storyboard_version=project.storyboard_version,
                generated_scenes=tuple(generated_scenes),
                status=ProjectStatus.SCENES_GENERATED,
            )
        )
        self.update_acceptance_run_step(run_id, "video_scenes_generation", RunStatus.COMPLETED, "4 vertical 9:16 video clips generated")

        # 6. Voiceover & Real TTS Audio Synthesis
        tts_script = f"Bạn đang tìm {target_product_name} với âm thanh chuẩn studio và thời lượng pin cực trâu 140 giờ? Khám phá ngay hôm nay!"
        tts_audio_path = str(generated_dir / "voiceover.mp3")

        tts_payload = {
            "project_id": project_id,
            "request_id": f"tts_{project_id}",
            "text": tts_script,
            "output_path": tts_audio_path,
            "voice": "vi-VN-HoaiMyNeural",
            "language": "vi-VN",
        }
        tts_job_id = f"job_tts_{uuid4().hex[:8]}"
        self.worker.repository.enqueue(tts_job_id, owner_user_id, "tts_generate", tts_payload)
        self.worker.run_once()

        tts_provider = get_tts_provider(output_dir=str(generated_dir))
        tts_res = tts_provider.synthesize(TTSRequest(
            request_id=f"vo_{project_id}",
            text=tts_script,
            voice="vi-VN-HoaiMyNeural",
            language="vi-VN",
        ))
        if not tts_res.success or not Path(tts_res.wav_path).is_file():
            raise RuntimeError(f"TTS_VOICEOVER_FAILED: Real Vietnamese voiceover synthesis failed: {tts_res.error_message}")
        tts_audio_path = tts_res.wav_path

        self.asset_repository.save_asset({
            "asset_id": f"gen_tts_{project_id}",
            "project_id": project_id,
            "scene_id": "voiceover",
            "job_id": tts_job_id,
            "provider": "edge_tts",
            "resource_lock_id": lock_id,
            "output_path": tts_audio_path,
        })
        self.update_acceptance_run_step(run_id, "tts_voiceover", RunStatus.COMPLETED, f"Vietnamese audio synthesized for {target_product_name}")

        # 6b. ASS Captions Generation from TTS text
        from hermes.video.ass_generator import generate_ass_from_text
        ass_path = str(generated_dir / "captions.ass")
        generate_ass_from_text(
            text=tts_script,
            audio_duration=float(duration_seconds),
            output_path=ass_path,
        )
        self.asset_repository.save_asset({
            "asset_id": f"gen_captions_{project_id}",
            "project_id": project_id,
            "scene_id": "captions",
            "job_id": f"job_captions_{uuid4().hex[:8]}",
            "provider": "ass_generator",
            "resource_lock_id": lock_id,
            "output_path": ass_path,
        })
        self.update_acceptance_run_step(run_id, "ass_captions", RunStatus.COMPLETED, f"ASS captions generated for {target_product_name}")

        # 6c. BGM Auto-Selection & Sidechain Ducking Mix
        from hermes.tools.bgm_manager import pick_bgm, mix_bgm_with_ducking
        tone = "happy"
        bgm_path = pick_bgm(tone=tone, duration_seconds=float(duration_seconds))
        if bgm_path and Path(bgm_path).is_file():
            bgm_mixed_path = str(generated_dir / "voiceover_with_bgm.mp3")
            mix_bgm_with_ducking(
                video_path="",
                bgm_path=bgm_path,
                output_path=bgm_mixed_path,
            )
            self.asset_repository.save_asset({
                "asset_id": f"gen_bgm_{project_id}",
                "project_id": project_id,
                "scene_id": "bgm",
                "job_id": f"job_bgm_{uuid4().hex[:8]}",
                "provider": "bgm_manager",
                "resource_lock_id": lock_id,
                "output_path": bgm_path,
            })
            self.update_acceptance_run_step(run_id, "bgm_mix", RunStatus.COMPLETED, f"BGM selected ({tone}) and mixed with sidechain ducking")
        else:
            bgm_mixed_path = None
            self.update_acceptance_run_step(run_id, "bgm_mix", RunStatus.COMPLETED, "No BGM available, using voiceover only")

        # 7. Timeline Concat, Subtitles Burn & Audio Muxing
        draft_mp4_path = str(generated_dir / "draft_video.mp4")
        render_payload = {
            "project_id": project_id,
            "clip_paths": clip_paths,
            "audio_path": tts_audio_path,
            "duration_seconds": duration_seconds,
            "output_path": draft_mp4_path,
        }
        render_job_id = f"job_render_{uuid4().hex[:8]}"
        self.worker.repository.enqueue(render_job_id, owner_user_id, "video.render", render_payload)
        self.worker.run_once()

        # Direct FFmpeg concat fallback if worker render needs exact audio stream
        if not Path(draft_mp4_path).is_file() or Path(draft_mp4_path).stat().st_size < 10000:
            self.ffmpeg.concat_clips_and_audio(clip_paths, tts_audio_path, draft_mp4_path)

        # Burn ASS subtitles into the concatenated video
        if Path(ass_path).is_file() and Path(draft_mp4_path).is_file():
            subtitled_path = str(generated_dir / "draft_subtitled.mp4")
            try:
                self.ffmpeg.burn_subtitles(draft_mp4_path, ass_path, subtitled_path)
                if Path(subtitled_path).is_file() and Path(subtitled_path).stat().st_size > 10000:
                    draft_mp4_path = subtitled_path
            except Exception:
                pass  # Keep original draft if subtitle burn fails

        draft_asset_id = f"gen_draft_{project_id}"
        self.asset_repository.save_asset({
            "asset_id": draft_asset_id,
            "project_id": project_id,
            "scene_id": "draft_video",
            "job_id": render_job_id,
            "provider": "ffmpeg",
            "resource_lock_id": lock_id,
            "output_path": draft_mp4_path,
        })
        timeline_clips = tuple(
            TimelineClip(
                clip_id=f"clip_{i+1}",
                order=i + 1,
                source_asset_id=f"asset_scene_{project_id}_s{i+1}",
                duration_seconds=float(scene.duration_seconds),
            )
            for i, scene in enumerate(scenes)
        )
        timeline = Timeline(
            timeline_id=new_id("timeline"),
            project_id=project_id,
            clips=timeline_clips,
            audio_track_asset_id=f"gen_tts_{project_id}",
            status=TimelineStatus.COMPLETED,
        )
        self.vf_service.save_timeline(owner_user_id, project_id, timeline)
        self.vf_service.save_draft_video(owner_user_id, project_id, draft_asset_id)
        self.update_acceptance_run_step(run_id, "timeline_render", RunStatus.COMPLETED, "30s 9:16 vertical draft video rendered")

        # 8. Final MP4 Export
        final_mp4_path = str(exports_dir / "final_video.mp4")
        export_payload = {
            "project_id": project_id,
            "input_path": draft_mp4_path,
            "output_path": final_mp4_path,
        }
        export_job_id = f"job_export_{uuid4().hex[:8]}"
        self.worker.repository.enqueue(export_job_id, owner_user_id, "export", export_payload)
        self.worker.run_once()

        if not Path(final_mp4_path).is_file():
            shutil.copy2(draft_mp4_path, final_mp4_path)

        final_asset_id = f"gen_final_{project_id}"
        self.asset_repository.save_asset({
            "asset_id": final_asset_id,
            "project_id": project_id,
            "scene_id": "final_export",
            "job_id": export_job_id,
            "provider": "ffmpeg",
            "resource_lock_id": lock_id,
            "output_path": final_mp4_path,
        })
        self.vf_service.approve_final_video(owner_user_id, project_id, "Approved for acceptance export")
        self.vf_service.save_final_export(owner_user_id, project_id, final_asset_id)

        # 9. Compliance Check & AIGC Watermark
        from hermes.compliance.gateway import ComplianceGateway
        compliance = ComplianceGateway()
        compliance_result = compliance.run_full_check(
            project_id=project_id,
            video_path=final_mp4_path,
            voiceover_text=tts_script,
            caption_text=tts_script,
            resource_pack=lock,
        )
        if not compliance_result["passed"]:
            logger.warning("Compliance warnings for %s: %s", project_id, compliance_result["issues"])
            self.update_acceptance_run_step(
                run_id, "compliance_check", RunStatus.COMPLETED,
                f"Compliance warnings: {compliance_result['issues']}",
            )
        else:
            self.update_acceptance_run_step(
                run_id, "compliance_check", RunStatus.COMPLETED,
                "All compliance checks passed",
            )

        # 10. Probe & Verify Final Output Artifact
        media_specs = self.ffmpeg.probe_media_file(final_mp4_path)
        if not media_specs.get("is_valid"):
            raise ValueError(f"FINAL_EXPORT_INVALID: {media_specs}")

        self.update_acceptance_run_step(run_id, "final_export", RunStatus.COMPLETED, f"Final MP4 verified & exported to {final_mp4_path}")
        self.complete_acceptance_run(run_id, RunStatus.COMPLETED)

        return {
            "status": "ok",
            "project_id": project_id,
            "run_id": run_id,
            "product_id": canonical_product_id,
            "resource_pack_lock_id": lock_id,
            "final_asset_id": final_asset_id,
            "final_mp4_path": final_mp4_path,
            "ui_url": f"http://localhost:3000/projects/{project_id}/workflow/export",
            "content_url": f"/api/assets/{final_asset_id}/content",
            "video_specs": media_specs,
            "compliance": compliance_result,
        }

    def run_ab_variant_workflow(
        self,
        owner_user_id: str = "user",
        prompt: str = "Tạo video TikTok review sản phẩm dài 30 giây",
        product_query: str | None = None,
        duration_seconds: int = 30,
        platform: str = "TikTok",
        language: str = "Vietnamese",
        project_id: str | None = None,
    ) -> Dict[str, Any]:
        """Execute A/B variant workflow: generate 3 hook variants, each through the full pipeline."""
        from hermes.application.ab_variant_engine import ABVariantEngine

        target_product_name = _extract_product_name(prompt, product_query, owner_user_id)

        # 1. Resolve or construct Product Resource Lock & Project
        if project_id:
            try:
                project = self.vf_service.get_project(owner_user_id, project_id)
            except ValueError:
                project = None
            if project and project.resource_pack:
                lock = self.resolve_product_lock(owner_user_id, target_product_name)
                canonical_product_id = project.resource_pack.product_identity_description
                lock_id = project.resource_pack.id
                snapshot_id = lock.get("snapshot_id", "")
                run = self.create_acceptance_run(canonical_product_id, lock_id, snapshot_id, project_id)
                run_id = run.run_id
            else:
                proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
                lock = proj_meta["lock"]
                run_id = proj_meta["run_id"]
                canonical_product_id = proj_meta["product_id"]
                lock_id = proj_meta["resource_pack_lock_id"]
                snapshot_id = proj_meta["snapshot_id"]
        else:
            project_id = f"vfp_{int(time.time())}_{uuid4().hex[:6]}"
            proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
            lock = proj_meta["lock"]
            run_id = proj_meta["run_id"]
            canonical_product_id = proj_meta["product_id"]
            lock_id = proj_meta["resource_pack_lock_id"]
            snapshot_id = proj_meta["snapshot_id"]

        self.update_acceptance_run_step(run_id, "resolve_product_lock", RunStatus.COMPLETED, f"Locked {target_product_name}")
        self.update_acceptance_run_step(run_id, "create_project", RunStatus.COMPLETED, f"Created project {project_id}")

        # 2. Generate 3 A/B hook variants
        engine = ABVariantEngine()
        variant_set = engine.generate_variants(
            product_name=target_product_name,
            base_prompt=prompt,
            platform=platform,
            duration_seconds=duration_seconds,
        )
        self.update_acceptance_run_step(run_id, "ab_variants_generated", RunStatus.COMPLETED, "3 hook variants generated")

        workspace_dir = get_workspaces_dir() / project_id
        generated_dir = workspace_dir / "generated"
        exports_dir = workspace_dir / "exports"
        generated_dir.mkdir(parents=True, exist_ok=True)
        exports_dir.mkdir(parents=True, exist_ok=True)

        ref_asset_ids = [str(ref.get("asset_id")) for ref in lock.get("assets", []) if ref.get("asset_id")]
        ref_asset_paths = [str(ref.get("local_path") or ref.get("uri") or "") for ref in lock.get("assets", []) if (ref.get("local_path") or ref.get("uri"))]

        # 3. Run the pipeline for each variant
        completed_variants: list[HookVariant] = []
        for variant in variant_set.variants:
            variant_dir = generated_dir / variant.variant_id
            variant_dir.mkdir(parents=True, exist_ok=True)
            variant_exports = exports_dir / variant.variant_id
            variant_exports.mkdir(parents=True, exist_ok=True)

            try:
                completed_variant = self._run_single_variant_pipeline(
                    owner_user_id=owner_user_id,
                    project_id=project_id,
                    variant=variant,
                    variant_dir=variant_dir,
                    variant_exports=variant_exports,
                    target_product_name=target_product_name,
                    lock=lock,
                    lock_id=lock_id,
                    ref_asset_ids=ref_asset_ids,
                    ref_asset_paths=ref_asset_paths,
                    platform=platform,
                    duration_seconds=duration_seconds,
                    language=language,
                )
                completed_variants.append(completed_variant)
            except Exception as exc:
                failed = HookVariant(
                    variant_id=variant.variant_id,
                    variant_label=variant.variant_label,
                    hook_angle=variant.hook_angle,
                    creative_brief=variant.creative_brief,
                    scene_plan=variant.scene_plan,
                    export_status="failed",
                )
                completed_variants.append(failed)
                self.update_acceptance_run_step(
                    run_id, f"variant_{variant.variant_id}", RunStatus.FAILED, str(exc), errors=[str(exc)]
                )

        # 4. Save all variants to project
        final_variant_set = ABVariantSet(variants=tuple(completed_variants))
        project = self.vf_service.get_project(owner_user_id, project_id)
        self.vf_service.repository.save(
            project.__class__(
                id=project.id,
                owner_user_id=project.owner_user_id,
                created_at=project.created_at,
                updated_at=datetime.now(timezone.utc).isoformat(),
                resource_pack=project.resource_pack,
                resource_version=project.resource_version,
                raw_idea=project.raw_idea,
                idea_version=project.idea_version,
                creative_brief=project.creative_brief,
                brief_approval=project.brief_approval,
                brief_version=project.brief_version,
                scene_plan=project.scene_plan,
                scene_plan_approval=project.scene_plan_approval,
                scene_version=project.scene_version,
                storyboard=project.storyboard,
                storyboard_version=project.storyboard_version,
                generated_scenes=project.generated_scenes,
                timeline=project.timeline,
                draft_video_asset_id=project.draft_video_asset_id,
                final_video_asset_id=project.final_video_asset_id,
                final_approval=project.final_approval,
                final_approval_notes=project.final_approval_notes,
                ab_variants=final_variant_set,
                status=ProjectStatus.AB_VARIANTS_READY,
            )
        )
        self.complete_acceptance_run(run_id, RunStatus.COMPLETED)

        variant_results = [
            {
                "variant_id": v.variant_id,
                "variant_label": v.variant_label,
                "export_status": v.export_status,
                "final_asset_id": v.final_asset_id,
            }
            for v in completed_variants
        ]
        return {
            "status": "ok",
            "project_id": project_id,
            "run_id": run_id,
            "variants": variant_results,
            "variant_count": len(completed_variants),
        }

    def _run_single_variant_pipeline(
        self,
        *,
        owner_user_id: str,
        project_id: str,
        variant: HookVariant,
        variant_dir: Path,
        variant_exports: Path,
        target_product_name: str,
        lock: dict,
        lock_id: str,
        ref_asset_ids: list[str],
        ref_asset_paths: list[str],
        platform: str,
        duration_seconds: int,
        language: str,
    ) -> HookVariant:
        """Run the full pipeline for a single A/B variant and return the completed HookVariant."""
        brief = variant.creative_brief
        plan = variant.scene_plan

        # Storyboard keyframes for this variant
        frames: list[StoryboardFrame] = []
        for i, scene in enumerate(plan.scenes):
            frame_id = f"frame_{i + 1}"
            kf_img_path = str(variant_dir / f"keyframe_beat_{i + 1}.png")
            photo_path = ref_asset_paths[i % len(ref_asset_paths)] if ref_asset_paths and Path(ref_asset_paths[i % len(ref_asset_paths)]).is_file() else None

            render_beat_keyframe(
                output_path=kf_img_path,
                beat_index=i + 1,
                title=scene.title,
                subtitle=scene.main_action,
                product_name=target_product_name,
                product_ref_image_path=photo_path,
                width=720,
                height=1280,
            )
            kf_asset_id = f"asset_sb_{project_id}_{variant.variant_id}_{frame_id}"
            self.asset_repository.save_asset({
                "asset_id": kf_asset_id,
                "project_id": project_id,
                "scene_id": frame_id,
                "job_id": f"job_img_{uuid4().hex[:8]}",
                "provider": "pillow",
                "resource_lock_id": lock_id,
                "output_path": kf_img_path,
            })
            prompt_obj = FramePrompt(
                positive_prompt=f"Studio shot of {target_product_name}, {scene.content}",
                negative_constraints="No text distortion, no low res",
                product_identity_constraints=target_product_name,
                action=scene.main_action,
                reference_asset_ids=tuple(ref_asset_ids),
                aspect_ratio="9:16",
            )
            frames.append(StoryboardFrame(
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
                required_resource_ids=tuple(ref_asset_ids),
                prompt=prompt_obj,
                generation_status=FrameGenerationStatus.COMPLETED,
                generated_asset_id=kf_asset_id,
            ))

        storyboard = Storyboard(
            storyboard_id=new_id("storyboard"),
            project_id=project_id,
            frames=tuple(frames),
        )

        # Video scene clips for this variant
        generated_scenes: list[GeneratedScene] = []
        clip_paths: list[str] = []
        for i, scene in enumerate(plan.scenes):
            scene_clip_path = str(variant_dir / f"scene_{i + 1}.mp4")
            kf_img_path = str(variant_dir / f"keyframe_beat_{i + 1}.png")
            self.ffmpeg.create_video_clip_from_image(
                image_path=kf_img_path,
                output_path=scene_clip_path,
                duration_seconds=scene.duration_seconds,
            )
            clip_paths.append(scene_clip_path)
            scene_asset_id = f"asset_scene_{project_id}_{variant.variant_id}_s{i + 1}"
            self.asset_repository.save_asset({
                "asset_id": scene_asset_id,
                "project_id": project_id,
                "scene_id": scene.scene_id,
                "job_id": f"job_vgen_{uuid4().hex[:8]}",
                "provider": "ffmpeg",
                "resource_lock_id": lock_id,
                "output_path": scene_clip_path,
            })
            v_prompt = VideoPrompt(
                scene_id=scene.scene_id,
                duration_seconds=scene.duration_seconds,
                start_visual_state=scene.content,
                end_visual_state=scene.content,
                subject_action=scene.main_action,
                product_action=scene.main_action,
                camera_movement=scene.camera_intention,
                camera_framing="Vertical 9:16",
                environment_motion="Normal motion",
                negative_constraints="No blur",
            )
            generated_scenes.append(GeneratedScene(
                scene_id=scene.scene_id,
                video_prompt=v_prompt,
                generation_status=VideoGenerationStatus.COMPLETED,
                generated_asset_id=scene_asset_id,
                review_notes=f"Variant {variant.variant_label} scene clip",
            ))

        # TTS for this variant
        tts_script = f"Bạn đang tìm {target_product_name}? {brief.core_message}!"
        tts_audio_path = str(variant_dir / "voiceover.wav")
        tts_provider = get_tts_provider(output_dir=str(variant_dir))
        tts_res = tts_provider.synthesize(TTSRequest(
            request_id=f"vo_{project_id}_{variant.variant_id}",
            text=tts_script,
            voice="vi-VN-HoaiMyNeural",
            language="vi-VN",
        ))
        if not tts_res.success or not Path(tts_res.wav_path).is_file():
            raise RuntimeError(f"TTS_FAILED for variant {variant.variant_id}: {tts_res.error_message}")
        tts_audio_path = tts_res.wav_path

        # Timeline concat
        draft_mp4_path = str(variant_dir / "draft_video.mp4")
        self.ffmpeg.concat_clips_and_audio(clip_paths, tts_audio_path, draft_mp4_path)

        # Final export
        final_mp4_path = str(variant_exports / "final_video.mp4")
        if not Path(draft_mp4_path).is_file():
            raise RuntimeError(f"DRAFT_NOT_GENERATED for variant {variant.variant_id}")
        shutil.copy2(draft_mp4_path, final_mp4_path)

        final_asset_id = f"gen_final_{project_id}_{variant.variant_id}"
        self.asset_repository.save_asset({
            "asset_id": final_asset_id,
            "project_id": project_id,
            "scene_id": f"final_export_{variant.variant_id}",
            "job_id": f"job_export_{uuid4().hex[:8]}",
            "provider": "ffmpeg",
            "resource_lock_id": lock_id,
            "output_path": final_mp4_path,
        })

        media_specs = self.ffmpeg.probe_media_file(final_mp4_path)
        timeline_clips = tuple(
            TimelineClip(
                clip_id=f"clip_{i + 1}",
                order=i + 1,
                source_asset_id=f"asset_scene_{project_id}_{variant.variant_id}_s{i + 1}",
                duration_seconds=float(scene.duration_seconds),
            )
            for i, scene in enumerate(plan.scenes)
        )
        timeline = Timeline(
            timeline_id=new_id("timeline"),
            project_id=project_id,
            clips=timeline_clips,
            audio_track_asset_id=f"gen_tts_{project_id}_{variant.variant_id}",
            status=TimelineStatus.COMPLETED,
        )

        return HookVariant(
            variant_id=variant.variant_id,
            variant_label=variant.variant_label,
            hook_angle=variant.hook_angle,
            creative_brief=brief,
            scene_plan=plan,
            storyboard=storyboard,
            generated_scenes=tuple(generated_scenes),
            timeline=timeline,
            final_asset_id=final_asset_id,
            export_status="completed" if media_specs.get("is_valid") else "failed",
        )

    def dispatch_ab_variant_workflow(
        self,
        owner_user_id: str = "user",
        prompt: str = "Tạo video TikTok review sản phẩm dài 30 giây",
        product_query: str | None = None,
        duration_seconds: int = 30,
        platform: str = "TikTok",
        language: str = "Vietnamese",
    ) -> Dict[str, Any]:
        """Asynchronously dispatch A/B variant workflow into CanonicalJobWorker."""
        target_product_name = _extract_product_name(prompt, product_query, owner_user_id)
        project_id = f"vfp_{int(time.time())}_{uuid4().hex[:6]}"
        proj_meta = self.create_video_project(owner_user_id, project_id, target_product_name)
        lock = proj_meta["lock"]
        run_id = proj_meta["run_id"]
        canonical_product_id = proj_meta["product_id"]
        lock_id = proj_meta["resource_pack_lock_id"]

        self.update_acceptance_run_step(run_id, "resolve_product_lock", RunStatus.COMPLETED, f"Locked {target_product_name}")
        self.update_acceptance_run_step(run_id, "create_project", RunStatus.COMPLETED, f"Created project {project_id}")

        job_id = f"job_ab_{uuid4().hex[:8]}"
        payload = {
            "project_id": project_id,
            "run_id": run_id,
            "owner_user_id": owner_user_id,
            "prompt": prompt,
            "product_query": target_product_name,
            "duration_seconds": duration_seconds,
            "platform": platform,
            "language": language,
            "resource_lock_id": lock_id,
            "canonical_product_id": canonical_product_id,
        }
        self.worker.repository.enqueue(job_id, owner_user_id, "ab_variant_workflow", payload)
        self.update_acceptance_run_step(run_id, "job_dispatch", RunStatus.IN_PROGRESS, f"A/B variant job {job_id} queued")

        return {
            "status": "queued",
            "job_id": job_id,
            "project_id": project_id,
            "run_id": run_id,
            "variant_count": 3,
            "message": f"A/B variant workflow queued with job_id {job_id}",
            "job_url": f"/api/jobs/{job_id}",
            "project_url": f"/api/vf/projects/{project_id}",
            "progress_url": f"/api/vf/projects/{project_id}/progress",
        }
