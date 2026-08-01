from __future__ import annotations

from typing import Protocol, Sequence

from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentIdea,
    ContentPackage,
    ProductCandidate,
    ProductSnapshot,
    ProjectionResult,
    ReferenceMetadata,
    ScoreBreakdown,
)


class AffiliateResearchRepository(Protocol):
    def upsert_product(self, product: AffiliateProduct) -> AffiliateProduct: ...

    def record_snapshot(
        self, product_id: str, snapshot_date: str, product: AffiliateProduct
    ) -> ProductSnapshot: ...

    def list_products(self, owner_user_id: str, run_id: str | None = None) -> list[AffiliateProduct]: ...

    def list_snapshots(self, product_id: str) -> list[ProductSnapshot]: ...

    def save_score(self, product_id: str, score: ScoreBreakdown, eligibility_status: str) -> None: ...

    def save_reference(self, reference: ReferenceMetadata) -> ReferenceMetadata: ...

    def save_ideas(self, product_id: str, run_id: str, ideas: Sequence[ContentIdea]) -> list[ContentIdea]: ...

    def save_package(self, package: ContentPackage) -> ContentPackage: ...

    def get_package(self, package_id: str, owner_user_id: str) -> ContentPackage | None: ...

    def list_packages(
        self, owner_user_id: str, run_id: str | None = None
    ) -> list[ContentPackage]: ...

    def transition_package(
        self, package_id: str, owner_user_id: str, action: str, reason: str
    ) -> ContentPackage: ...

    def create_run(self, run_id: str, owner_user_id: str, idempotency_key: str) -> dict: ...

    def finish_run(self, run_id: str, counters: dict[str, int]) -> dict: ...

    def projection_rows(self, owner_user_id: str, run_id: str) -> dict[str, list[dict]]: ...


class ProductSource(Protocol):
    def load(self, owner_user_id: str) -> list[ProductCandidate]: ...


class ContentPackageGateway(Protocol):
    def generate(
        self, product: AffiliateProduct, references: Sequence[ReferenceMetadata]
    ) -> ContentPackage: ...


class SheetsProjection(Protocol):
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult: ...


class ReviewDelivery(Protocol):
    def send_pending(self, owner_user_id: str, package_ids: Sequence[str]) -> ProjectionResult: ...
