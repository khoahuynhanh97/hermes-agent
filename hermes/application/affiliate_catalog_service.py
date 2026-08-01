from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ProductCandidate,
    ProductPolicy,
    ProductScorer,
    ScoreBreakdown,
)
from hermes.ports.affiliate_research import AffiliateResearchRepository, ProductSource


@dataclass(frozen=True)
class ImportSummary:
    imported: int
    updated: int
    rejected: int
    errors: int


@dataclass(frozen=True)
class RankedProduct:
    product: AffiliateProduct
    score: ScoreBreakdown


class AffiliateCatalogService:
    def __init__(
        self,
        repository: AffiliateResearchRepository,
        policy: ProductPolicy | None = None,
        scorer: ProductScorer | None = None,
    ):
        self._repository = repository
        self._policy = policy or ProductPolicy()
        self._scorer = scorer or ProductScorer()

    def import_candidates(
        self,
        source: ProductSource,
        *,
        owner_user_id: str,
        run_id: str,
        snapshot_date: str,
    ) -> ImportSummary:
        batch = source.load_batch(owner_user_id) if hasattr(source, "load_batch") else None
        candidates = batch.candidates if batch else source.load(owner_user_id)
        rejected = len(batch.errors) if batch else 0
        existing = {
            (product.platform, product.external_product_id)
            for product in self._repository.list_products(owner_user_id)
        }
        imported = updated = errors = 0
        for candidate in candidates:
            try:
                product = self._product_from_candidate(candidate, owner_user_id)
                saved = self._repository.upsert_product(product)
                self._repository.record_snapshot(saved.id, snapshot_date, saved)
                if (saved.platform, saved.external_product_id) in existing:
                    updated += 1
                else:
                    imported += 1
                    existing.add((saved.platform, saved.external_product_id))
            except (TypeError, ValueError, LookupError):
                errors += 1
        return ImportSummary(imported, updated, rejected, errors)

    def score_and_shortlist(
        self,
        *,
        owner_user_id: str,
        run_id: str,
        minimum: int = 15,
        maximum: int = 25,
    ) -> list[RankedProduct]:
        if not 15 <= minimum <= maximum <= 25:
            raise ValueError("shortlist bounds must satisfy 15 <= minimum <= maximum <= 25")
        products = self._repository.list_products(owner_user_id)
        category_sales = self._category_sales(products)
        ranked: list[RankedProduct] = []
        for product in products:
            decision = self._policy.evaluate(product)
            if not decision.eligible:
                self._repository.save_score(product.id, self._ineligible_score(decision.reason), "ineligible")
                continue
            snapshots = self._repository.list_snapshots(product.id)
            previous_sales = snapshots[-2].sold_count if len(snapshots) > 1 else None
            score = self._scorer.score(
                product,
                category_sales=category_sales[self._category_key(product.category)],
                previous_sold_count=previous_sales,
                seen_before=len(snapshots) > 1,
            )
            self._repository.save_score(product.id, score, "eligible")
            ranked.append(RankedProduct(product, score))
        ranked.sort(key=lambda item: (-item.score.total, item.product.id))
        shortlist = ranked[:maximum]
        for item in shortlist:
            self._repository.save_score(item.product.id, item.score, "shortlisted")
        return shortlist

    @staticmethod
    def _product_from_candidate(candidate: ProductCandidate, owner_user_id: str) -> AffiliateProduct:
        now = datetime.now(timezone.utc).isoformat()
        product_id = hashlib.sha256(
            f"{owner_user_id}\0{candidate.platform}\0{candidate.external_product_id}".encode("utf-8")
        ).hexdigest()
        return AffiliateProduct(
            id=product_id,
            owner_user_id=owner_user_id,
            platform=candidate.platform,
            external_product_id=candidate.external_product_id,
            name=candidate.name,
            category=candidate.category,
            price_vnd=candidate.price_vnd,
            sold_count=candidate.sold_count,
            rating=candidate.rating,
            review_count=candidate.review_count,
            commission_rate=candidate.commission_rate,
            shop_name=candidate.shop_name,
            product_url=candidate.product_url,
            image_urls=candidate.image_urls,
            visual_signals=candidate.visual_signals,
            source_type=candidate.source_type,
            source_url=candidate.source_url,
            authorization_scope=candidate.authorization_scope,
            rights_status=candidate.rights_status,
            content_hash=candidate.content_hash,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _category_key(category: str) -> str:
        return category.strip().lower().replace(" ", "_").replace("-", "_")

    def _category_sales(self, products: list[AffiliateProduct]) -> dict[str, tuple[int, int]]:
        grouped: dict[str, list[int]] = {}
        for product in products:
            if product.sold_count is not None:
                grouped.setdefault(self._category_key(product.category), []).append(product.sold_count)
        return {
            self._category_key(product.category): (
                min(grouped.get(self._category_key(product.category), [0])),
                max(grouped.get(self._category_key(product.category), [0])),
            )
            for product in products
        }

    @staticmethod
    def _ineligible_score(reason: str) -> ScoreBreakdown:
        return ScoreBreakdown(0.0, {}, reason, "low", None)
