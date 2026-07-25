from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class IngestionRequest:
    id: str
    source: str
    source_type: str
    requested_action: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: str = "pending"