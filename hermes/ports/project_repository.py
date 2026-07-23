from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, TypeVar

from hermes.domain.results import Result

T = TypeVar("T")


class Project(Protocol):
    id: str
    name: str
    filesystem_root: str
    created_at: str
    updated_at: str
    is_active: bool


class ProjectRepository(ABC):
    @abstractmethod
    def create(self, name: str, filesystem_root: str) -> Result[Project]:
        raise NotImplementedError

    @abstractmethod
    def get(self, project_id: str) -> Result[Project]:
        raise NotImplementedError

    @abstractmethod
    def list_active(self) -> Result[list[Project]]:
        raise NotImplementedError

    @abstractmethod
    def archive(self, project_id: str) -> Result[None]:
        raise NotImplementedError

