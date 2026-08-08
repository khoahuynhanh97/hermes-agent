from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from hermes.domain.results import Result


class FFmpegCapability:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    def cut(self, input_path: str, output_path: str, start_seconds: int, end_seconds: int) -> Result[dict[str, Any]]:
        duration = end_seconds - start_seconds
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-ss", str(start_seconds),
            "-t", str(duration),
            "-c", "copy",
            output_path,
            "-y"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                return Result.success({
                    "output_path": output_path,
                    "start_seconds": start_seconds,
                    "end_seconds": end_seconds,
                })
            return Result.failure("ffmpeg_error", result.stderr)
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def render(self, input_path: str, output_path: str, output_format: str = "mp4") -> Result[dict[str, Any]]:
        cmd = [
            self.ffmpeg_path,
            "-i", input_path,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            output_path,
            "-y"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                return Result.success({"output_path": output_path, "format": output_format})
            return Result.failure("ffmpeg_error", result.stderr)
        except Exception as e:
            return Result.failure("unavailable", str(e))

    def render_with_audio(self, video_path: str, audio_path: str, output_path: str) -> Result[dict[str, Any]]:
        """Mux one video + one WAV into an MP4 (video length wins)."""
        cmd = [
            self.ffmpeg_path,
            "-i", video_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "128k",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            output_path,
            "-y"
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
            if result.returncode == 0:
                return Result.success({"output_path": output_path, "format": "mp4"})
            return Result.failure("ffmpeg_error", result.stderr)
        except Exception as e:
            return Result.failure("unavailable", str(e))
