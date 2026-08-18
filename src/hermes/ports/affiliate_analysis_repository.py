"""Persistence port for ``AffiliateAnalysis``."""

from __future__ import annotations

from typing import Protocol

from hermes.domain.affiliate_analysis import AffiliateAnalysis


class AffiliateAnalysisRepository(Protocol):
    def save(self, analysis: AffiliateAnalysis) -> AffiliateAnalysis: ...

    def find_for_product(
        self, owner_user_id: str, product_id: str
    ) -> list[AffiliateAnalysis]: ...
