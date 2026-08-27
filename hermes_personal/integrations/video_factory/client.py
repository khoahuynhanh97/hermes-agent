from __future__ import annotations

from typing import Any

from .contracts import (
    VideoArtifactRef,
    CreativeBriefRequest,
    ScenePlanRequest,
    StoryboardRequest,
    RenderRequest,
    ExportRequest,
)


class VideoFactoryClient:
    """Deterministic client for Phase 5 Task 3.

    Provides high-level operations without external I/O:
    * ``create_creative_brief`` - returns a deterministic creative brief request.
    * ``create_scene_plan`` - returns a deterministic scene-plan request.
    * ``create_storyboard`` - returns a deterministic storyboard request.
    * ``render_video`` - returns a deterministic render request.
    * ``export_video`` - returns a deterministic export request.
    All methods include an ``artifact_ref`` (stable SHA-256 digest), the
    serialized request payload, and workflow/job/idempotency correlation metadata.
    """

    def __init__(self, owner_user_id: str = "user") -> None:
        self.owner_user_id = owner_user_id
        self._artifact = VideoArtifactRef()

    def _wrap(
        self,
        request: Any,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        """Serialize ``request`` and attach deterministic artifact reference, digest, and correlation."""
        wrapped = {
            "artifact_ref": self._artifact.digest(),
            "payload": request.to_json(),
            "digest": request.digest(),
        }
        if workflow_id:
            wrapped["workflow_id"] = workflow_id
        if job_id:
            wrapped["job_id"] = job_id
        if idempotency_key:
            wrapped["idempotency_key"] = idempotency_key
        return wrapped

    def create_creative_brief(
        self,
        product_id: str | None = None,
        brief_config: dict | None = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict:
        req = CreativeBriefRequest(
            product_id=product_id or "",
            brief_config=brief_config or {},
        )
        return self._wrap(req, workflow_id=workflow_id, job_id=job_id, idempotency_key=idempotency_key)

    def create_scene_plan(
        self,
        brief_ref: Any = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict:
        req = ScenePlanRequest()
        return self._wrap(req, workflow_id=workflow_id, job_id=job_id, idempotency_key=idempotency_key)

    def create_storyboard(
        self,
        scene_ref: Any = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict:
        req = StoryboardRequest()
        return self._wrap(req, workflow_id=workflow_id, job_id=job_id, idempotency_key=idempotency_key)

    def render_video(
        self,
        story_ref: Any = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict:
        req = RenderRequest()
        return self._wrap(req, workflow_id=workflow_id, job_id=job_id, idempotency_key=idempotency_key)

    def export_video(
        self,
        render_ref: Any = None,
        workflow_id: str | None = None,
        job_id: str | None = None,
        idempotency_key: str | None = None,
        **kwargs: Any,
    ) -> dict:
        req = ExportRequest()
        return self._wrap(req, workflow_id=workflow_id, job_id=job_id, idempotency_key=idempotency_key)
