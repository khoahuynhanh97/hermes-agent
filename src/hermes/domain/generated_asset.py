from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GeneratedAsset:
    asset_id: str
    owner_user_id: str
    project_id: str
    job_id: str
    artifact_type: Literal["frame_image", "scene_video", "draft_video", "final_video"]
    artifact_id: str
    artifact_version: int
    storage_key: str
    mime_type: str
    checksum_sha256: str
