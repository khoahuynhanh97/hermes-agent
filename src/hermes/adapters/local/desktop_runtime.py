from __future__ import annotations

from typing import Any

from hermes.domain.results import Result
from hermes.adapters.local.ffmpeg_capability import FFmpegCapability


class DesktopRuntime:
    def __init__(self):
        self.ffmpeg = FFmpegCapability()

    def execute(self, job_type: str, payload: dict[str, Any]) -> Result[dict[str, Any]]:
        if job_type == "video.cut":
            return self._execute_cut(payload)
        elif job_type == "video.render":
            return self._execute_render(payload)
        return Result.failure("unsupported_capability", f"Unknown job type: {job_type}")

    def _execute_cut(self, payload: dict[str, Any]) -> Result[dict[str, Any]]:
        input_path = payload.get("asset_id")
        start = payload.get("start_seconds", 0)
        end = payload.get("end_seconds", 60)
        output_path = payload.get("output_path", f"cut_{input_path}")
        return self.ffmpeg.cut(input_path, output_path, start, end)

    def _execute_render(self, payload: dict[str, Any]) -> Result[dict[str, Any]]:
        input_path = payload.get("asset_id")
        output_format = payload.get("output_format", "mp4")
        output_path = payload.get("output_path", f"render.{output_format}")
        return self.ffmpeg.render(input_path, output_path, output_format)
