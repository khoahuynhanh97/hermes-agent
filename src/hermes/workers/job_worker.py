"""Deterministic worker for the canonical durable job plane."""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from typing import Callable

from hermes.adapters.local.desktop_runtime import DesktopRuntime
from hermes.config import get_data_path
from hermes.db import Database
from hermes.jobs import JobRepository


Handler = Callable[[dict], dict]


class JobPending(RuntimeError):
    """Provider operation is healthy but not terminal yet."""


class CanonicalJobWorker:
    def __init__(self, db_path: str, workspace: str, worker_id: str = "canonical-worker"):
        self.database = Database(db_path)
        self.database.initialize()
        self.repository = JobRepository(self.database)
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id
        self.runtime = DesktopRuntime()
        configured_ffmpeg = (
            os.environ.get("HERMES_FFMPEG_PATH", "").strip()
            or os.environ.get("FFMPEG_PATH", "").strip()
        )
        if configured_ffmpeg:
            self.runtime.ffmpeg.ffmpeg_path = configured_ffmpeg
        self.handlers: dict[str, Handler] = {
            # Legacy job types
            "video.cut": self._execute_video,
            "video.render": self._execute_video,
            "image_generate": self._execute_image,
            "video_generate": self._execute_video_generate,
            "tts_generate": self._execute_tts,
            "export": self._execute_export,
            "product_to_video": self._execute_product_to_video_workflow,
            "product_to_video_workflow": self._execute_product_to_video_workflow,

            # New Video Factory Pipeline job types
            "video_factory.generate_scene_plan": self._handle_generate_scene_plan,
            "video_factory.generate_storyboard": self._handle_generate_storyboard,
            "video_factory.generate_scene_video": self._handle_generate_scene_video,
            "video_factory.generate_voiceover": self._handle_generate_voiceover,
            "video_factory.generate_captions": self._handle_generate_captions,
            "video_factory.compose_final_video": self._handle_compose_final_video,
        }

    def _handle_generate_scene_plan(self, payload: dict, job_id: str) -> dict:
        """Generate a 4-beat scene plan from payload brief/prompt."""
        from hermes.domain.video_factory import Scene, ScenePlan

        product_name = payload.get("product_name", "product")
        scenes = []
        beats = [
            ("Beat 1: Visual Hook & Reveal", "Unboxing & visual reveal", "Push in slow zoom", 6),
            ("Beat 2: Core Features & Sound", "Demonstrate key features", "Cinematic slow zoom", 8),
            ("Beat 3: Comfort & Battery", "Showcase fit and battery", "Side panning shot", 8),
            ("Beat 4: Call to Action", "Direct viewers to buy", "Static hero shot", 8),
        ]
        for i, (title, objective, camera, dur) in enumerate(beats, 1):
            scenes.append(Scene(
                scene_id=f"scene_{i}",
                order=i,
                title=title,
                objective=objective,
                content=f"{objective} of {product_name}",
                main_action=f"Scene {i} action",
                duration_seconds=dur,
                camera_intention=camera,
            ))
        plan = ScenePlan(scenes=tuple(scenes))

        plan_path = str(self.workspace / f"scene_plan_{job_id}.json")
        from pathlib import Path as _P
        _P(plan_path).write_text(
            __import__("json").dumps(
                {"scenes": [{"scene_id": s.scene_id, "title": s.title, "duration_seconds": s.duration_seconds} for s in plan.scenes]},
                indent=2,
            ),
            encoding="utf-8",
        )
        return {"status": "completed", "plan_path": plan_path, "scenes": [s.scene_id for s in plan.scenes]}

    def _handle_generate_storyboard(self, payload: dict, job_id: str) -> dict:
        """Generate keyframe images for each scene using render_beat_keyframe."""
        from hermes.adapters.local.ffmpeg_capability import render_beat_keyframe

        project_id = payload.get("project_id", job_id)
        scenes = payload.get("scenes", [])
        product_name = payload.get("product_name", "product")
        ref_image_path = payload.get("ref_image_path")
        storyboard_dir = self.workspace / f"storyboard_{project_id}"
        storyboard_dir.mkdir(parents=True, exist_ok=True)

        frame_paths = []
        for i, scene in enumerate(scenes):
            beat_idx = scene.get("order", i + 1) if isinstance(scene, dict) else i + 1
            kf_path = str(storyboard_dir / f"keyframe_beat_{beat_idx}.png")
            render_beat_keyframe(
                output_path=kf_path,
                beat_index=beat_idx,
                title=scene.get("title", f"Beat {beat_idx}") if isinstance(scene, dict) else f"Beat {beat_idx}",
                subtitle=scene.get("objective", "") if isinstance(scene, dict) else "",
                product_name=product_name,
                product_ref_image_path=ref_image_path,
            )
            frame_paths.append(kf_path)

        return {
            "status": "completed",
            "storyboard_path": str(storyboard_dir),
            "frame_paths": frame_paths,
        }

    def _handle_generate_scene_video(self, payload: dict, job_id: str) -> dict:
        """Generate scene video: Ken Burns from image or delegate to AI provider."""
        video_type = payload.get("scene_video_type", "ken_burns")
        image_path = payload.get("image_path")
        output_path = payload.get("output_path", str(self.workspace / f"scene_{job_id}.mp4"))
        duration = float(payload.get("duration_seconds", 5))

        if not image_path or not Path(image_path).is_file():
            raise ValueError("image_path is required and must exist for scene video generation")

        if video_type == "ken_burns":
            result = self.runtime.ffmpeg.create_ken_burns_clip(
                image_path=image_path,
                output_path=output_path,
                duration_seconds=duration,
            )
            return {
                "status": "completed",
                "scene_video_path": result.value["output_path"],
                "scene_video_type": "ken_burns",
            }

        if video_type == "ai_generated":
            # Submit to video generation provider
            vgen_payload = {
                "request_id": f"vgen_{job_id}",
                "prompt": payload.get("prompt", f"Product video scene {job_id}"),
                "reference_image_paths": [image_path] if image_path else [],
                "duration_seconds": int(duration),
                "output_path": output_path,
                "scene_id": payload.get("scene_id", ""),
                "width": int(payload.get("width", 720)),
                "height": int(payload.get("height", 1280)),
            }
            return self._execute_video_generate(vgen_payload, job_id)

        raise ValueError(f"Unknown scene_video_type: {video_type}")

    def _handle_generate_voiceover(self, payload: dict, job_id: str) -> dict:
        """Generate voiceover via EdgeTTS for Vietnamese text."""
        from hermes.integrations.providers.tts_provider_factory import get_tts_provider
        from hermes.ports.text_to_speech import TTSRequest

        text = payload.get("text", "")
        if not text.strip():
            raise ValueError("text is required for voiceover generation")

        voice = payload.get("voice", "vi-VN-HoaiMyNeural")
        language = payload.get("language", "vi-VN")
        output_path = payload.get("output_path", str(self.workspace / f"voiceover_{job_id}.mp3"))
        audio_dir = str(Path(output_path).parent)
        Path(audio_dir).mkdir(parents=True, exist_ok=True)

        provider = get_tts_provider(output_dir=audio_dir)
        result = provider.synthesize(TTSRequest(
            request_id=f"tts_{job_id}",
            text=text,
            voice=voice,
            language=language,
        ))
        if not result.success:
            raise RuntimeError(f"TTS synthesis failed: {result.error_message}")

        # Copy to requested output path if different
        wav_path = result.wav_path
        if Path(wav_path).resolve() != Path(output_path).resolve():
            import shutil
            shutil.copy2(wav_path, output_path)

        return {
            "status": "completed",
            "voiceover_path": output_path,
            "wav_path": wav_path,
            "voice": voice,
            "duration_seconds": payload.get("duration_seconds"),
        }

    def _handle_generate_captions(self, payload: dict, job_id: str) -> dict:
        """Generate .ass subtitle file from voiceover text and timing."""
        from hermes.video.ass_generator import generate_ass_from_text

        text = payload.get("text", "")
        audio_duration = float(payload.get("audio_duration", 30.0))
        output_path = payload.get("output_path", str(self.workspace / f"captions_{job_id}.ass"))

        ass_path = generate_ass_from_text(
            text=text,
            audio_duration=audio_duration,
            output_path=output_path,
        )
        return {
            "status": "completed",
            "captions_path": ass_path,
        }

    def _handle_compose_final_video(self, payload: dict, job_id: str) -> dict:
        """Compose final video using MasterVideoCompositor."""
        from hermes.video.composition import MasterVideoCompositor
        from hermes.video.models import VideoComposition

        scene_videos = payload.get("scene_videos", [])
        voiceover_track = payload.get("voiceover_track", "")
        bgm_track = payload.get("bgm_track")
        captions_ass_path = payload.get("captions_ass_path")
        output_path = payload.get("output_path", str(self.workspace / f"final_{job_id}.mp4"))

        if not scene_videos:
            raise ValueError("scene_videos list is required for composition")
        if not voiceover_track or not Path(voiceover_track).is_file():
            raise ValueError("voiceover_track is required and must exist")

        comp = VideoComposition(
            project_id=payload.get("project_id", job_id),
            scene_videos=scene_videos,
            voiceover_track=voiceover_track,
            bgm_track=bgm_track,
            captions_ass_path=captions_ass_path,
            output_path=output_path,
        )

        compositor = MasterVideoCompositor()
        compositor.compose(comp)

        if not Path(output_path).is_file():
            raise RuntimeError(f"Final composition failed: {output_path} not created")

        return {
            "status": "completed",
            "final_video_path": output_path,
        }


    def run_once(self) -> dict | None:
        job = self.repository.claim_next()
        if not job:
            return None
        job_id = job["id"]
        try:
            if self.repository.is_cancel_requested(job_id):
                self.repository.acknowledge_cancel(job_id)
                return self.repository.get(job_id)
            handler = self.handlers.get(job["job_type"])
            if handler is None:
                raise ValueError(f"unsupported task type: {job['job_type']}")
            result = handler(job["payload"], job["id"])
            if self.repository.is_cancel_requested(job_id):
                self.repository.acknowledge_cancel(job_id)
                return self.repository.get(job_id)
            from hermes.adapters.sqlite.generated_asset_repository import SQLiteGeneratedAssetRepository
            from hermes.application.job_result_projector import JobResultProjector
            projector = JobResultProjector(SQLiteGeneratedAssetRepository(self.database))
            projected_result = projector.project_terminal_result(job_id, job["job_type"], result, job["payload"])
            self.repository.complete(job_id, projected_result)
        except JobPending:
            self.repository.defer(job_id, delay_seconds=10)
        except Exception as error:
            retryable = isinstance(error, RuntimeError)
            self.repository.fail(job_id, str(error), retryable=retryable)
        return self.repository.get(job_id)

    def _execute_video(self, payload: dict, job_id: str) -> dict:
        if payload.get("clip_paths"):
            return self._execute_timeline_render(payload)
        input_path = self._contained_file(payload.get("asset_id"), "asset_id")
        output_path = self._contained_output(payload.get("output_path"))
        operation = payload.get("operation")
        if operation is None:
            operation = "cut" if payload.get("start_seconds") is not None else "render"
        execution_payload = dict(payload)
        execution_payload["asset_id"] = str(input_path)
        execution_payload["output_path"] = str(output_path)
        result = self.runtime.execute(f"video.{operation}", execution_payload)
        if not result.ok:
            if result.error_code == "unavailable":
                raise RuntimeError(result.message or result.error_code)
            raise ValueError(result.message or result.error_code or "video execution failed")
        if not output_path.is_file():
            raise ValueError("video execution did not produce output")
        return {
            "task_type": f"video.{operation}",
            "output_path": str(output_path),
            **(result.value or {}),
        }

    def _execute_image(self, payload: dict, job_id: str) -> dict:
        from hermes.ports.image_generation import ImageGenerationRequest
        from hermes.integrations.providers.image_provider_factory import get_image_provider

        request_id = payload.get("request_id")
        prompt = payload.get("prompt")
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("malformed payload: request_id is required")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("malformed payload: prompt is required")

        reference_paths = tuple(
            str(self._contained_file(ref, "reference_image_paths"))
            for ref in (payload.get("reference_image_paths") or [])
            if isinstance(ref, str) and ref.strip()
        )

        image_dir = self.workspace / "images"
        image_dir.mkdir(parents=True, exist_ok=True)

        request = ImageGenerationRequest(
            request_id=request_id,
            owner_user_id=str(payload.get("owner_user_id") or "system"),
            positive_prompt=prompt,
            negative_prompt=payload.get("negative_prompt") or "",
            reference_image_paths=reference_paths,
            width=int(payload.get("width") or 1024),
            height=int(payload.get("height") or 1024),
            aspect_ratio=payload.get("aspect_ratio") or "",
            num_images=int(payload.get("num_images") or 1),
            provider_options=payload.get("provider_options") or None,
        )

        provider = get_image_provider(output_dir=str(image_dir))
        result = provider.generate(request)
        if not result.success:
            raise self._provider_error(result.error_message or "image generation failed")

        return {
            "task_type": "image_generate",
            "request_id": request_id,
            "output_paths": list(result.image_paths),
            "provider": (result.metadata or {}).get("provider"),
            "provider_operation_id": result.provider_operation_id,
        }

    def _execute_video_generate(self, payload: dict, job_id: str) -> dict:
        """Single-shot async video generation step via VideoGenerationPort.

        One claim does one step, then requeues for the next claim:
        1. no operation_id yet -> submit predictLongRunning, persist operation id, requeue
        2. operation_id present -> fetchPredictOperation once
           - running  -> retryable requeue (later worker claim resumes)
           - done     -> return video result (job completes)
        No tight polling loop inside one execution.
        """
        from hermes.ports.video_generation import VideoGenerationRequest
        from hermes.integrations.providers.video_provider_factory import get_video_provider

        request_id = payload.get("request_id")
        prompt = payload.get("prompt")
        scene_id = payload.get("scene_id") or ""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("malformed payload: request_id is required")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("malformed payload: prompt is required")

        reference_paths = tuple(
            str(self._contained_file(ref, "reference_image_paths"))
            for ref in (payload.get("reference_image_paths") or [])
            if isinstance(ref, str) and ref.strip()
        )

        video_dir = self.workspace / "videos"
        video_dir.mkdir(parents=True, exist_ok=True)

        request = VideoGenerationRequest(
            request_id=request_id,
            owner_user_id=str(payload.get("owner_user_id") or "system"),
            scene_id=scene_id,
            prompt=prompt,
            duration_seconds=int(payload.get("duration_seconds") or 5),
            reference_image_paths=reference_paths,
            reference_video_path=payload.get("reference_video_path"),
            width=int(payload.get("width") or 1280),
            height=int(payload.get("height") or 720),
            fps=int(payload.get("fps") or 24),
            aspect_ratio=str(payload.get("aspect_ratio") or ""),
            provider_options=payload.get("provider_options") or None,
        )

        provider = get_video_provider(output_dir=str(video_dir))
        operation_id = payload.get("provider_operation_id")

        if not operation_id:
            submit = provider.generate(request)
            if not submit.success:
                raise self._provider_error(submit.error_message or "video generation failed")
            if submit.video_path:
                # synchronous provider (e.g. fake) finished immediately
                return self._video_result(submit, request_id, scene_id)
            operation_id = submit.provider_operation_id
            if not operation_id:
                raise ValueError("provider returned no operation id")
            new_payload = dict(payload)
            new_payload["provider_operation_id"] = operation_id
            self.repository.update_payload(job_id, new_payload, stage="provider_running")
            # requeue: next worker claim resumes by polling the operation
            raise JobPending("video generation submitted; waiting for provider")

        status = provider.check_status(operation_id)
        if not status.success:
            raise self._provider_error(status.error_message or "video generation failed")
        if status.video_path:
            return self._video_result(status, request_id, scene_id)
        # still running: requeue for a later claim
        raise JobPending("video generation still running")

    @staticmethod
    def _video_result(result, request_id: str, scene_id: str) -> dict:
        return {
            "task_type": "video_generate",
            "request_id": request_id,
            "scene_id": scene_id,
            "output_path": result.video_path,
            "provider_operation_id": result.provider_operation_id,
            "provider": (result.metadata or {}).get("provider"),
        }

    def _execute_tts(self, payload: dict, job_id: str) -> dict:
        """Execute a TTS generation job via the configured TTS provider."""
        from hermes.ports.text_to_speech import TTSRequest
        from hermes.integrations.providers.tts_provider_factory import get_tts_provider

        request_id = payload.get("request_id")
        text = payload.get("text")
        voice = payload.get("voice") or "Zephyr"
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("malformed payload: request_id is required")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("malformed payload: text is required")

        audio_dir = self.workspace / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        provider = get_tts_provider(output_dir=str(audio_dir))
        result = provider.synthesize(TTSRequest(
            request_id=request_id,
            text=text,
            voice=voice,
            language=payload.get("language") or "vi-VN",
            style_prompt=payload.get("style_prompt") or "",
        ))
        if not result.success:
            raise self._provider_error(result.error_message or "tts generation failed")

        return {
            "task_type": "tts_generate",
            "request_id": request_id,
            "wav_path": result.wav_path,
            "provider": result.provider,
            "voice": result.voice,
        }

    def _execute_export(self, payload: dict, job_id: str) -> dict:
        """Publish the validated timeline render as the final MP4."""
        import shutil
        input_path = self._contained_file(payload.get("input_path"), "input_path")
        output_path_str = payload.get("output_path")
        if not output_path_str:
            raise ValueError("malformed payload: output_path is required")
        output_path = self._contained_output(output_path_str)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_path, output_path)
        return {
            "task_type": "export",
            "output_path": str(output_path),
            "provider": "local",
        }

    def _execute_product_to_video_workflow(self, payload: dict, job_id: str) -> dict:
        """Execute full product-to-video workflow via WorkflowOrchestrator."""
        from hermes.application.workflow import WorkflowOrchestrator
        orchestrator = WorkflowOrchestrator(Path(self.database.path))
        result = orchestrator.run_product_to_video_workflow(
            owner_user_id=str(payload.get("owner_user_id") or "user"),
            prompt=str(payload.get("prompt") or "Tạo video TikTok review sản phẩm dài 30 giây"),
            product_query=payload.get("product_query"),
            duration_seconds=int(payload.get("duration_seconds") or 30),
            platform=str(payload.get("platform") or "TikTok"),
            language=str(payload.get("language") or "Vietnamese"),
            project_id=payload.get("project_id"),
            run_id=payload.get("run_id"),
        )
        return {
            "task_type": "product_to_video_workflow",
            "project_id": result["project_id"],
            "output_path": result["final_mp4_path"],
            "final_mp4_path": result["final_mp4_path"],
            "final_asset_id": result["final_asset_id"],
            "video_specs": result.get("video_specs", {}),
            "status": "completed",
        }

    def _execute_timeline_render(self, payload: dict) -> dict:
        import subprocess
        clip_paths = [self._contained_file(value, "clip_paths") for value in payload.get("clip_paths", [])]
        if not clip_paths:
            raise ValueError("malformed payload: clip_paths are required")
        output_path = self._contained_output(payload.get("output_path"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = int(payload.get("duration_seconds") or 30)
        cmd = [self.runtime.ffmpeg.ffmpeg_path, "-y"]
        for path in clip_paths:
            cmd.extend(["-i", str(path)])
        audio_path_value = payload.get("audio_path")
        audio_path = self._contained_file(audio_path_value, "audio_path") if audio_path_value else None
        if audio_path:
            cmd.extend(["-i", str(audio_path)])
        video_inputs = "".join(f"[{index}:v]setpts=PTS-STARTPTS[v{index}];" for index in range(len(clip_paths)))
        concat_inputs = "".join(f"[v{index}]" for index in range(len(clip_paths)))
        filter_graph = f"{video_inputs}{concat_inputs}concat=n={len(clip_paths)}:v=1:a=0,trim=duration={duration},setpts=PTS-STARTPTS[v]"
        if audio_path:
            audio_index = len(clip_paths)
            filter_graph += f";[{audio_index}:a]apad,atrim=duration={duration}[a]"
        cmd.extend(["-filter_complex", filter_graph, "-map", "[v]"])
        if audio_path:
            cmd.extend(["-map", "[a]", "-c:a", "aac", "-b:a", "128k"])
        cmd.extend(["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20", "-pix_fmt", "yuv420p", "-t", str(duration), str(output_path)])
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0 or not output_path.is_file() or output_path.stat().st_size == 0:
            raise ValueError(f"timeline ffmpeg failed: {result.stderr[-800:]}")
        return {"task_type": "video.render", "output_path": str(output_path), "provider": "local", "duration_seconds": duration}

    @staticmethod
    def _provider_error(message: str) -> Exception:
        lowered = message.lower()
        transient = ("429", "500", "502", "503", "504", "timeout", "timed out", "connection", "temporar")
        return RuntimeError(message) if any(token in lowered for token in transient) else ValueError(message)

    def _contained_file(self, value: str | None, field: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"malformed payload: {field} is required")
        path = Path(value).expanduser().resolve()
        self._ensure_input_allowed(path)
        if not path.is_file():
            raise ValueError(f"malformed payload: {field} does not exist")
        return path

    def _ensure_input_allowed(self, path: Path) -> None:
        from hermes.runtime_layout import get_product_intelligence_data_root, get_workspaces_dir
        roots = [self.workspace, get_workspaces_dir()]
        pi_root = get_product_intelligence_data_root()
        if pi_root is not None:
            roots.append(pi_root)
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError("payload input path outside approved media roots")

    def _contained_output(self, value: str | None) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("malformed payload: output_path is required")
        path = Path(value).expanduser().resolve()
        self._ensure_output_allowed(path)
        if path.suffix.lower() not in {".mp4", ".mov", ".webm"}:
            raise ValueError("malformed payload: unsupported output extension")
        return path

    def _ensure_output_allowed(self, path: Path) -> None:
        from hermes.runtime_layout import get_workspaces_dir
        roots = (self.workspace, get_workspaces_dir())
        if not any(path == root or root in path.parents for root in roots):
            raise ValueError("payload output path outside approved media workspaces")


def build_worker(
    db_path: str | None = None,
    workspace: str | None = None,
    worker_id: str | None = None,
) -> CanonicalJobWorker:
    resolved_db_path = (db_path or "").strip() or os.environ.get("HERMES_VIDEO_DB_PATH", "").strip()
    if not resolved_db_path:
        resolved_db_path = str(get_data_path("db", "video.sqlite"))
    resolved_workspace = (workspace or "").strip() or os.environ.get("HERMES_VIDEO_WORKSPACE", "").strip()
    if not resolved_workspace:
        resolved_workspace = str(get_data_path("workspaces", "video"))
    resolved_worker_id = (worker_id or "").strip() or os.environ.get("HERMES_WORKER_ID", "canonical-worker")
    return CanonicalJobWorker(resolved_db_path, resolved_workspace, resolved_worker_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one canonical Hermes durable job")
    parser.add_argument("--once", action="store_true", help="claim and execute at most one job")
    parser.add_argument("--daemon", action="store_true", help="poll continuously for durable jobs")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--db-path", type=str, default="", help="path to sqlite database")
    parser.add_argument("--workspace", type=str, default="", help="path to worker workspace")
    args = parser.parse_args()
    worker = build_worker(db_path=args.db_path, workspace=args.workspace)
    if args.once:
        worker.run_once()
        return 0
    if args.daemon:
        while True:
            if worker.run_once() is None:
                time.sleep(max(0.1, args.poll_seconds))
    while worker.run_once() is not None:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
