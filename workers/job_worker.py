"""Deterministic worker for the canonical durable job plane."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Callable

from hermes.adapters.local.desktop_runtime import DesktopRuntime
from hermes.config import get_data_path
from hermes.db import Database
from hermes.jobs import JobRepository


Handler = Callable[[dict], dict]


class CanonicalJobWorker:
    def __init__(self, db_path: str, workspace: str, worker_id: str = "canonical-worker"):
        self.database = Database(db_path)
        self.database.initialize()
        self.repository = JobRepository(self.database)
        self.workspace = Path(workspace).expanduser().resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.worker_id = worker_id
        self.runtime = DesktopRuntime()
        configured_ffmpeg = os.environ.get("HERMES_FFMPEG_PATH", "").strip()
        if configured_ffmpeg:
            self.runtime.ffmpeg.ffmpeg_path = configured_ffmpeg
        self.handlers: dict[str, Handler] = {
            "video.cut": self._execute_video,
            "video.render": self._execute_video,
            "image_generate": self._execute_image,
            "video_generate": self._execute_video_generate,
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
            self.repository.complete(job_id, result)
        except Exception as error:
            retryable = isinstance(error, RuntimeError)
            self.repository.fail(job_id, str(error), retryable=retryable)
        return self.repository.get(job_id)

    def _execute_video(self, payload: dict, job_id: str) -> dict:
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
        from providers.image_provider_factory import get_image_provider

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
            raise ValueError(result.error_message or "image generation failed")

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
        from providers.video_provider_factory import get_video_provider

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
            provider_options=payload.get("provider_options") or None,
        )

        provider = get_video_provider(output_dir=str(video_dir))
        operation_id = payload.get("provider_operation_id")

        if not operation_id:
            submit = provider.generate(request)
            if not submit.success:
                raise ValueError(submit.error_message or "video generation failed")
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
            raise RuntimeError("video generation submitted; waiting for provider")

        status = provider.check_status(operation_id)
        if not status.success:
            raise ValueError(status.error_message or "video generation failed")
        if status.video_path:
            return self._video_result(status, request_id, scene_id)
        # still running: requeue for a later claim
        raise RuntimeError("video generation still running; will retry")

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

    def _contained_file(self, value: str | None, field: str) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"malformed payload: {field} is required")
        path = Path(value).expanduser().resolve()
        self._ensure_contained(path)
        if not path.is_file():
            raise ValueError(f"malformed payload: {field} does not exist")
        return path

    def _contained_output(self, value: str | None) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("malformed payload: output_path is required")
        path = Path(value).expanduser().resolve()
        self._ensure_contained(path)
        if path.suffix.lower() not in {".mp4", ".mov", ".webm"}:
            raise ValueError("malformed payload: unsupported output extension")
        return path

    def _ensure_contained(self, path: Path) -> None:
        try:
            path.relative_to(self.workspace)
        except ValueError as error:
            raise ValueError("payload path outside video workspace") from error


def build_worker() -> CanonicalJobWorker:
    db_path = os.environ.get("HERMES_VIDEO_DB_PATH", "").strip()
    if not db_path:
        db_path = str(get_data_path("db", "video.sqlite"))
    workspace = os.environ.get("HERMES_VIDEO_WORKSPACE", "").strip()
    if not workspace:
        workspace = str(get_data_path("workspaces", "video"))
    return CanonicalJobWorker(db_path, workspace, os.environ.get("HERMES_WORKER_ID", "canonical-worker"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one canonical Hermes durable job")
    parser.add_argument("--once", action="store_true", help="claim and execute at most one job")
    args = parser.parse_args()
    worker = build_worker()
    if args.once:
        worker.run_once()
        return 0
    while worker.run_once() is not None:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
