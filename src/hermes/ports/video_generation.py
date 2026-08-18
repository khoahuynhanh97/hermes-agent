"""Port for specialized video generation capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class VideoGenerationRequest:
    """Normalized request for video generation."""
    request_id: str
    owner_user_id: str
    scene_id: str
    prompt: str
    duration_seconds: int
    reference_image_paths: tuple[str, ...] = ()
    reference_video_path: str | None = None
    width: int = 1280
    height: int = 720
    fps: int = 24
    aspect_ratio: str = ""
    provider_options: dict[str, Any] | None = None


@dataclass
class VideoGenerationResult:
    """Normalized result from video generation."""
    request_id: str
    success: bool
    video_path: str | None = None
    provider_operation_id: str | None = None
    error_message: str = ""
    metadata: dict[str, Any] | None = None


class VideoGenerationPort(Protocol):
    """Specialized video generation capability boundary."""

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Submit video generation request and return result or operation ID."""
        ...

    def check_status(self, operation_id: str) -> VideoGenerationResult:
        """Check status of async generation operation."""
        ...
