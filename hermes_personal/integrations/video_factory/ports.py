"""Video Factory domain ports and abstract interfaces."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from hermes_personal.integrations.video_factory.domain import VideoFactoryProject


class VideoFactoryRepository(ABC):
    @abstractmethod
    def create(self, project: VideoFactoryProject) -> VideoFactoryProject:
        raise NotImplementedError

    @abstractmethod
    def get_owned(self, project_id: str, owner_user_id: str) -> VideoFactoryProject | None:
        raise NotImplementedError

    @abstractmethod
    def list_owned(self, owner_user_id: str) -> list[VideoFactoryProject]:
        raise NotImplementedError

    @abstractmethod
    def save(self, project: VideoFactoryProject) -> VideoFactoryProject:
        raise NotImplementedError


@dataclass(frozen=True)
class VideoGenerationRequest:
    """Normalized request for video generation."""

    request_id: str
    owner_user_id: str
    project_id: str
    scene_id: str
    prompt: str
    duration_seconds: int
    reference_image_paths: tuple[str, ...] = ()
    aspect_ratio: str = "9:16"
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VideoGenerationResult:
    """Normalized result from video generation."""

    request_id: str
    status: Literal["submitted", "running", "completed", "failed"] = "failed"
    provider_operation_id: str | None = None
    video_path: str | None = None
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        return self.status in ("submitted", "running", "completed")


class VideoGenerationPort(Protocol):
    """Specialized video generation capability boundary."""

    def submit(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        """Submit video generation request and return result or operation ID."""
        ...

    def get_status(self, operation_id: str) -> VideoGenerationResult:
        """Check status of async generation operation."""
        ...

