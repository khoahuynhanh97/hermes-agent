"""Fake video generation provider for testing."""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from uuid import uuid4

from hermes.adapters.local.ffmpeg_capability import resolve_ffmpeg_exe
from hermes.ports.video_generation import (
    VideoGenerationPort,
    VideoGenerationRequest,
    VideoGenerationResult,
)


class FakeVideoGenerationProvider(VideoGenerationPort):
    """Deterministic fake video provider using FFmpeg for minimal test videos."""

    def __init__(self, output_dir: str | None = None):
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.gettempdir()) / "hermes-fake-videos"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Generate a minimal test video via FFmpeg, or a placeholder if absent."""
        try:
            filename = f"{request.request_id}.mp4"
            output_path = self.output_dir / filename
            
            # Create minimal color test video
            duration = min(request.duration_seconds, 8)
            ffmpeg = resolve_ffmpeg_exe()
            cmd = [
                ffmpeg, "-y",
                "-f", "lavfi",
                "-i", f"color=c=blue:s={request.width}x{request.height}:d={duration}",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-pix_fmt", "yuv420p",
                str(output_path)
            ]
            
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode != 0:
                if not output_path.exists() or output_path.stat().st_size == 0:
                    return VideoGenerationResult(
                        request_id=request.request_id,
                        success=False,
                        error_message=f"FFmpeg failed: {result.stderr.decode()[:300]}",
                    )
            
            return VideoGenerationResult(
                request_id=request.request_id,
                success=True,
                video_path=str(output_path),
                provider_operation_id=f"fake_vid_{uuid4().hex[:8]}",
                metadata={"provider": "fake", "mode": "test", "duration": duration},
            )
        except FileNotFoundError:
            # FFmpeg not installed: write a small placeholder file so tests
            # exercise the full job flow without a media binary.
            output_path = self.output_dir / f"{request.request_id}.mp4"
            output_path.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42placeholder")
            return VideoGenerationResult(
                request_id=request.request_id,
                success=True,
                video_path=str(output_path),
                provider_operation_id=f"fake_vid_{uuid4().hex[:8]}",
                metadata={"provider": "fake", "mode": "placeholder", "duration": min(request.duration_seconds, 8)},
            )
        except Exception as e:
            return VideoGenerationResult(
                request_id=request.request_id,
                success=False,
                error_message=str(e),
            )

    def check_status(self, operation_id: str) -> VideoGenerationResult:
        """Fake operations complete immediately."""
        return VideoGenerationResult(
            request_id=operation_id,
            success=True,
            metadata={"provider": "fake", "status": "completed"},
        )
