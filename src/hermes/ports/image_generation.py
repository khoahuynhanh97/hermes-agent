"""Port for specialized image generation capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass
class ImageGenerationRequest:
    """Normalized request for image generation."""
    request_id: str
    owner_user_id: str
    positive_prompt: str
    negative_prompt: str = ""
    reference_image_paths: tuple[str, ...] = ()
    width: int = 1024
    height: int = 1024
    aspect_ratio: str = ""
    num_images: int = 1
    provider_options: dict[str, Any] | None = None


@dataclass
class ImageGenerationResult:
    """Normalized result from image generation."""
    request_id: str
    success: bool
    image_paths: tuple[str, ...] = ()
    provider_operation_id: str | None = None
    error_message: str = ""
    metadata: dict[str, Any] | None = None


class ImageGenerationPort(Protocol):
    """Specialized image generation capability boundary."""

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Submit image generation request and return result or operation ID."""
        ...

    def check_status(self, operation_id: str) -> ImageGenerationResult:
        """Check status of async generation operation."""
        ...
