from __future__ import annotations

from dataclasses import replace

from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource
from hermes.application.affiliate_catalog_service import AffiliateCatalogService
from hermes.domain.affiliate_research import ProductCandidate, ProductSnapshot


class MemoryAffiliateRepository:
    def __init__(self):
        self.products = {}
        self.snapshots = {}
        self.scores = {}
        self.runs = []

    def upsert_product(self, product):
        for existing in self.products.values():
            if (existing.owner_user_id, existing.platform, existing.external_product_id) == (
                product.owner_user_id,
                product.platform,
                product.external_product_id,
            ):
                product = replace(product, id=existing.id, created_at=existing.created_at)
                break
        self.products[product.id] = product
        return product

    def record_snapshot(self, product_id, snapshot_date, product):
        snapshots = self.snapshots.setdefault(product_id, [])
        existing = next((row for row in snapshots if row.snapshot_date == snapshot_date), None)
        if existing:
            return existing
        snapshot = ProductSnapshot(
            product_id=product_id,
            snapshot_date=snapshot_date,
            price_vnd=product.price_vnd,
            sold_count=product.sold_count,
            rating=product.rating,
            review_count=product.review_count,
            commission_rate=product.commission_rate,
            collected_at=snapshot_date,
        )
        snapshots.append(snapshot)
        return snapshot

    def list_products(self, owner_user_id, run_id=None):
        return [product for product in self.products.values() if product.owner_user_id == owner_user_id]

    def list_snapshots(self, product_id):
        return list(self.snapshots.get(product_id, []))

    def save_score(self, product_id, score, eligibility_status):
        self.scores[product_id] = (score, eligibility_status)

    def create_run(self, run_id, owner_user_id, idempotency_key):
        self.runs.append((run_id, owner_user_id, idempotency_key))
        return {"id": run_id}

    def finish_run(self, run_id, counters):
        return {"id": run_id, "counters": counters}


class StaticSource:
    def __init__(self, candidates):
        self.candidates = candidates

    def load(self, owner_user_id):
        return [replace(candidate, owner_user_id=owner_user_id) for candidate in self.candidates]


def candidate(product_id, *, category="mouse", price_vnd=349_000, sold_count=12_300):
    return ProductCandidate(
        owner_user_id="ignored",
        platform="shopee",
        external_product_id=product_id,
        name=f"Product {product_id}",
        category=category,
        price_vnd=price_vnd,
        sold_count=sold_count,
        rating=4.8,
        review_count=100,
        commission_rate=0.12,
        shop_name="Shop",
        product_url=f"https://shopee.vn/{product_id}",
        image_urls=("https://img.example/product.jpg",),
        visual_signals=("rgb",),
        source_type="manual",
        source_url="manual://import",
        authorization_scope="manual_user_input",
        rights_status="user_provided",
        content_hash=f"hash-{product_id}",
    )


def test_import_is_idempotent_for_a_200_row_csv_export(tmp_path):
    repository = MemoryAffiliateRepository()
    service = AffiliateCatalogService(repository)
    path = tmp_path / "export.csv"
    rows = ["item_id,product_name,category,price,sold,product_link"]
    rows.extend(
        f"{index},Mouse {index},mouse,349000,12300,https://shopee.vn/{index}"
        for index in range(200)
    )
    path.write_text("\n".join(rows), encoding="utf-8")
    source = ShopeeAffiliateCsvSource(path)

    first = service.import_candidates(source, owner_user_id="42", run_id="run-1", snapshot_date="2026-08-01")
    second = service.import_candidates(source, owner_user_id="42", run_id="run-2", snapshot_date="2026-08-01")

    assert first.imported == 200
    assert second.updated == 200
    assert len(repository.products) == 200
    assert all(len(snapshots) == 1 for snapshots in repository.snapshots.values())


def test_shortlist_excludes_ineligible_products_and_breaks_score_ties_by_product_id():
    repository = MemoryAffiliateRepository()
    service = AffiliateCatalogService(repository)
    source = StaticSource([
        candidate("200"),
        candidate("100"),
        candidate("999", category="phone", price_vnd=349_000),
    ])
    service.import_candidates(source, owner_user_id="42", run_id="run-1", snapshot_date="2026-08-01")

    shortlist = service.score_and_shortlist(owner_user_id="42", run_id="run-1", minimum=1, maximum=2)

    assert [row.product.id for row in shortlist] == sorted(row.product.id for row in shortlist)
    assert repository.scores[next(product_id for product_id, product in repository.products.items() if product.external_product_id == "999")][1] == "ineligible"
