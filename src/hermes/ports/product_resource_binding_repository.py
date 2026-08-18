"""Port interface for ProjectResourceBinding repository."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from hermes.domain.product_resource import ProjectResourceBinding


class ProjectResourceBindingRepository(ABC):
    @abstractmethod
    def save(self, binding: ProjectResourceBinding, owner_user_id: str, resource_lock_id: str) -> None:
        """Persist a ProjectResourceBinding."""
        pass

    @abstractmethod
    def get_by_project_id(self, project_id: str) -> Optional[ProjectResourceBinding]:
        """Retrieve active ProjectResourceBinding for project_id."""
        pass
