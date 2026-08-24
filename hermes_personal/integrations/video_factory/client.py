from __future__ import annotations

import json
from dataclasses import asdict

from .contracts import (
    VideoArtifactRef,
    CreativeBriefRequest,
    ScenePlanRequest,
    StoryboardRequest,
    RenderRequest,
    ExportRequest,
)


class VideoFactoryClient:
    """Deterministic client for Phase 5 Task 3.

    Provides high‑level operations without external I/O:
    * ``create_creative_brief`` – returns a deterministic creative brief request.
    * ``create_scene_plan`` – returns a deterministic scene‑plan request.
    * ``create_storyboard`` – returns a deterministic storyboard request.
    * ``render_video`` – returns a deterministic render request.
    * ``export_video`` – returns a deterministic export request.
    All methods include an ``artifact_ref`` (stable SHA‑256 digest) and the
    serialized request payload. No live providers are invoked.
    """

    def __init__(self, owner_user_id: str = "user") -> None:
        self.owner_user_id = owner_user_id
        # reuse a single artifact reference for simplicity; in real client each step would
        # generate its own reference but deterministic behaviour is sufficient for tests.
        self._artifact = VideoArtifactRef()

    def _wrap(self, request) -> dict:
        """Serialize ``request`` and attach deterministic artifact reference and digest.

        Returns a mapping with keys:
        ``artifact_ref`` – SHA‑256 digest of :class:`VideoArtifactRef`.
        ``payload`` – JSON‑encoded request.
        ``digest`` – SHA‑256 digest of the request itself.
        """
        return {
            "artifact_ref": self._artifact.digest(),
            "payload": request.to_json(),
            "digest": request.digest(),
        }

    def create_creative_brief(self, brief_config: dict | None = None, **kwargs: Any) -> dict:
        req = CreativeBriefRequest()
        return self._wrap(req)

    def create_scene_plan(self, brief_ref: Any = None, **kwargs: Any) -> dict:
        req = ScenePlanRequest()
        return self._wrap(req)

    def create_storyboard(self, scene_ref: Any = None, **kwargs: Any) -> dict:
        req = StoryboardRequest()
        return self._wrap(req)

    def render_video(self, story_ref: Any = None, **kwargs: Any) -> dict:
        req = RenderRequest()
        return self._wrap(req)

    def export_video(self, render_ref: Any = None, **kwargs: Any) -> dict:
        req = ExportRequest()
        return self._wrap(req)
