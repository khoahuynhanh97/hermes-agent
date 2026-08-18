"""Publication domain (Publishing1)."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PublicationStatus(str, Enum):
    NOT_PUBLISHED = "not_published"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(frozen=True)
class Publication:
    publication_id: str
    project_id: str
    owner_user_id: str
    platform: str
    status: PublicationStatus = PublicationStatus.NOT_PUBLISHED
    post_id: str | None = None
    caption: str = ""
    published_at: str | None = None
    last_error: str = ""
    created_at: str = ""
    updated_at: str = ""
