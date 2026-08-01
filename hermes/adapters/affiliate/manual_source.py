from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from hermes.domain.affiliate_research import ProductCandidate


class ManualProductSource:
    """Supplies candidates explicitly entered or selected by the user."""

    def __init__(self, candidates: Sequence[ProductCandidate]):
        self._candidates = tuple(candidates)

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        return [replace(candidate, owner_user_id=owner_user_id) for candidate in self._candidates]
