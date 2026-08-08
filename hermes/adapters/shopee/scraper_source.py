"""Integration adapter for experimental Shopee scraper.

Allows using ShopeeExperimentalScraper as a ProductSource in the
affiliate research pipeline.

Example:
    from hermes.adapters.shopee.scraper_source import ShopeeScraperSource
    
    source = ShopeeScraperSource(owner_user_id="user_123")
    candidates = source.load("user_123")
"""

from __future__ import annotations

from hermes.adapters.shopee.experimental_scraper import (
    ShopeeExperimentalScraper,
    ShopeeSearchConfig,
)
from hermes.domain.affiliate_research import ProductCandidate
from hermes.ports.affiliate_research import ProductSource


class ShopeeScraperSource(ProductSource):
    """ProductSource adapter wrapping ShopeeExperimentalScraper."""

    def __init__(
        self,
        owner_user_id: str,
        *,
        config: ShopeeSearchConfig | None = None,
    ):
        self._owner_user_id = owner_user_id
        self._scraper = ShopeeExperimentalScraper(config)

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        """Load products via scraper.

        Validates owner_user_id matches to prevent cross-owner pollution.
        """
        if owner_user_id != self._owner_user_id:
            raise ValueError(
                f"ShopeeScraperSource owner mismatch: "
                f"expected {self._owner_user_id}, got {owner_user_id}"
            )
        return self._scraper.load(owner_user_id)
