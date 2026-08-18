from __future__ import annotations

from abc import ABC, abstractmethod

from hermes.domain.video_factory import VideoFactoryProject


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
