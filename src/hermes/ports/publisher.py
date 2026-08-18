"""Publication capability ports."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

from hermes.domain.publisher import Publication, PublicationStatus


@dataclass(frozen=True)
class PublishRequest:
    project_id: str
    owner_user_id: str
    video_path: str
    caption: str
    visibility: str = "public"  # tiktok: public / private / self_only


@dataclass(frozen=True)
class PublishResult:
    ok: bool
    post_id: str | None = None
    status: str = ""
    error_message: str = ""


class PublisherPort(Protocol):
    def publish(self, request: PublishRequest) -> PublishResult:
        ...


class PublicationStore(ABC):
    @abstractmethod
    def upsert(self, publication: Publication) -> Publication:
        raise NotImplementedError

    @abstractmethod
    def get(self, owner_user_id: str, project_id: str, platform: str) -> Publication | None:
        raise NotImplementedError

    @abstractmethod
    def update_status(self, owner_user_id: str, project_id: str, platform: str,
                      status: PublicationStatus, post_id: str | None = None,
                      last_error: str = "") -> Publication | None:
        raise NotImplementedError

    @abstractmethod
    def list_by_owner(self, owner_user_id: str) -> list[Publication]:
        raise NotImplementedError
