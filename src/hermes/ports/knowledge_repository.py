from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from hermes.domain.results import Result


class KnowledgeRepository(ABC):
    @abstractmethod
    def save(self, proposal: dict[str, Any]) -> Result[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get(self, proposal_id: str) -> Result[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str) -> Result[list[dict[str, Any]]]:
        raise NotImplementedError

    @abstractmethod
    def list_by_status(self, status: str) -> Result[list[dict[str, Any]]]:
        raise NotImplementedError