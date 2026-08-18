from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, TypeVar

from hermes.domain.results import Result

T = TypeVar("T")


from dataclasses import dataclass

@dataclass
class Project:
    id: str
    name: str
    filesystem_root: str = ""
    created_at: str = ""
    updated_at: str = ""
    is_active: bool = True


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

