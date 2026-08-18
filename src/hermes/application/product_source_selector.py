from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hermes.application.product_research_intent import ProductResearchIntent
from hermes.domain.affiliate_research import ProductCandidate


@dataclass(frozen=True)
class ProductSourceSelection:
    status: str
    source: Any | None = None
    warnings: tuple[str, ...] = ()

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        if self.source is None:
            return []
        try:
            return list(self.source.load(owner_user_id))
        except Exception as error:
            object.__setattr__(
                self,
                "warnings",
                (f"Marketplace crawler failed; use CSV/feed fallback: {str(error)[:200]}",),
            )
            return []


class ProductSourceSelector:
    def __init__(
        self,
        settings: Any,
        *,
        crawler_factory: Callable[[ProductResearchIntent], Any] | None = None,
    ):
        self._settings = settings
        self._crawler_factory = crawler_factory or self._default_crawler

    def select(self, intent: ProductResearchIntent) -> ProductSourceSelection:
        if not getattr(self._settings, "marketplace_crawler_enabled", False):
            return ProductSourceSelection(
                status="needs_csv_feed",
                warnings=("Marketplace crawler is disabled; provide CSV/feed fallback.",),
            )
        return ProductSourceSelection(status="crawler", source=self._crawler_factory(intent))

    @staticmethod
    def _default_crawler(intent: ProductResearchIntent) -> Any:
        from hermes.adapters.shopee.experimental_scraper import (
            ShopeeExperimentalScraper,
            ShopeeSearchConfig,
        )

        return ShopeeExperimentalScraper(
            ShopeeSearchConfig(
                min_price=int(intent.min_price_vnd),
                max_price=int(intent.max_price_vnd),
                limit_per_category=50,
            )
        )