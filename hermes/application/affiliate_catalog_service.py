from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
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
                warnings = (
                    ()
                    if snapshot_date == datetime.now(timezone.utc).date().isoformat()
                    else (f"metrics snapshot is stale: {snapshot_date}",)
                )
                record_observation = getattr(
                    self._repository, "record_run_product", None
                )
                if record_observation is not None:
                    record_observation(run_id, saved.id, warnings=warnings)
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
        products = self._repository.list_products(owner_user_id, run_id=run_id)
        category_sales = self._category_sales(products)
        ranked: list[RankedProduct] = []
        for product in products:
            snapshots = self._repository.list_snapshots(product.id)
            evidence_ids, snapshot_timestamps = self._score_evidence(
                product, owner_user_id, snapshots
            )
            decision = self._policy.evaluate(product)
            if not decision.eligible:
                self._save_score(
                    run_id,
                    product.id,
                    self._ineligible_score(
                        decision.reason,
                        evidence_ids,
                        snapshot_timestamps,
                    ),
                    "ineligible",
                )
                continue
            previous_sales = snapshots[-2].sold_count if len(snapshots) > 1 else None
            score = replace(
                self._scorer.score(
                    product,
                    category_sales=category_sales[
                        self._category_key(product.category)
                    ],
                    previous_sold_count=previous_sales,
                    seen_before=len(snapshots) > 1,
                ),
                evidence_ids=evidence_ids,
                snapshot_timestamps=snapshot_timestamps,
            )
            ranked.append(RankedProduct(product, score))
        ranked.sort(key=lambda item: (-item.score.total, item.product.id))
        shortlist = ranked[:maximum]
        for rank, item in enumerate(ranked, start=1):
            shortlisted = rank <= maximum
            self._save_score(
                run_id,
                item.product.id,
                item.score,
                "shortlisted" if shortlisted else "eligible",
                rank=rank,
                shortlisted=shortlisted,
            )
        return shortlist

    def _save_score(
        self,
        run_id: str,
        product_id: str,
        score: ScoreBreakdown,
        eligibility_status: str,
        *,
        rank: int | None = None,
        shortlisted: bool = False,
    ) -> None:
        save_run_score = getattr(self._repository, "save_run_score", None)
        if save_run_score is not None:
            save_run_score(
                run_id,
                product_id,
                score,
                eligibility_status,
                rank=rank,
                shortlisted=shortlisted,
            )
            return
        self._repository.save_score(product_id, score, eligibility_status)

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
    def _score_evidence(
        product: AffiliateProduct,
        owner_user_id: str,
        snapshots: list,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        source_fingerprint = product.content_hash or hashlib.sha256(
            product.source_url.encode("utf-8")
        ).hexdigest()
        evidence_ids = [
            f"source:{owner_user_id}:{product.id}:{source_fingerprint}"
        ]
        evidence_ids.extend(
            f"snapshot:{owner_user_id}:{product.id}:{snapshot.snapshot_date}"
            for snapshot in snapshots
        )
        return (
            tuple(evidence_ids),
            tuple(snapshot.collected_at for snapshot in snapshots),
        )

    @staticmethod
    def _ineligible_score(
        reason: str,
        evidence_ids: tuple[str, ...] = (),
        snapshot_timestamps: tuple[str, ...] = (),
    ) -> ScoreBreakdown:
        return ScoreBreakdown(
            0.0,
            {},
            reason,
            "low",
            None,
            evidence_ids=evidence_ids,
            snapshot_timestamps=snapshot_timestamps,
        )
