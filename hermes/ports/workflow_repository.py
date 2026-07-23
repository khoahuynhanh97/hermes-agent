from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol, TypeVar

from hermes.domain.prompt_studio import PromptStudioWorkflow
from hermes.domain.results import Result

T = TypeVar("T")


class WorkflowRepository(ABC):
    @abstractmethod
    def get(self, project_id: str) -> Result[PromptStudioWorkflow]:
        raise NotImplementedError

    @abstractmethod
    def save(self, workflow: PromptStudioWorkflow) -> Result[PromptStudioWorkflow]:
        raise NotImplementedError
