from __future__ import annotations

from abc import ABC, abstractmethod
from hermes.domain.model_request import ModelRequest, ModelResponse
from hermes.domain.results import Result


class ModelGateway(ABC):
    @abstractmethod
    def complete(self, request: ModelRequest) -> Result[ModelResponse]:
        raise NotImplementedError
