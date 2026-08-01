import pytest
from hermes.db import Database
from hermes.domain.affiliate_research import AffiliateProduct
from hermes.domain.web_document import WebDocument, WebFetchRequest
from hermes.adapters.sqlite.web_document_repository import SQLiteWebDocumentRepository
from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
from hermes.application.affiliate_web_reference_service import AffiliateWebReferenceService
from hermes.application.web_acquisition_service import WebAcquisitionService
from hermes.application.web_url_policy import PublicWebUrlPolicy


class CountingAcquisitionService:
    def __init__(self, document_map=None):
        self.document_map = document_map or {}
        self.calls = {}

    def acquire(self, request: WebFetchRequest) -> WebDocument:
        url = request.url
        self.calls[url] = self.calls.get(url, 0) + 1
        if url in self.document_map:
            return self.document_map[url]
        return WebDocument(
            id=f"doc-{hash(url)}",
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=url,
            final_url=url,
            title=f"Doc for {url}",
            markdown=f"# Title\n\nText for {url}",
            metadata={},
            acquisition_method="static_http",
            content_hash=f"hash-{hash(url)}",
            rights_status="reference_only",
            warnings=(),
            acquired_at="2026-08-01T00:00:00Z",
        )


@pytest.fixture
def db(tmp_path):
    database = Database(path=tmp_path / "recovery.db")
    database.initialize()
    with database.transaction() as conn:
        conn.execute(
            """
            INSERT INTO affiliate_products (
                id, owner_user_id, platform, external_product_id, name, category,
                price_vnd, source_type, authorization_scope, rights_status, content_hash,
                created_at, updated_at
            ) VALUES ('prod-1', '42', 'shopee', 'SKU-1', 'Item 1', 'category',
                      100000, 'csv', 'scope', 'status', 'hash', '2026-08-01', '2026-08-01')
            """
        )
        conn.execute(
            """
            INSERT INTO affiliate_research_runs (
                id, owner_user_id, idempotency_key, status, created_at, updated_at
            ) VALUES ('run-1', '42', 'key-1', 'running', '2026-08-01', '2026-08-01')
            """
        )
    return database


def sample_products():
    return [
        AffiliateProduct(
            id="prod-1",
            owner_user_id="42",
            platform="shopee",
            external_product_id="SKU-1",
            name="Item 1",
            category="category",
            price_vnd=100000,
            sold_count=10,
            rating=4.8,
            review_count=5,
            commission_rate=0.1,
            shop_name="Shop",
            product_url="https://example.com/item1",
            image_urls=(),
            visual_signals=(),
            source_type="csv",
            source_url="https://example.com/feed.csv",
            authorization_scope="scope",
            rights_status="status",
            content_hash="hash",
            created_at="2026-08-01",
            updated_at="2026-08-01",
        )
    ]


def policy():
    return PublicWebUrlPolicy(
        resolver=lambda host: {"example.com": ["93.184.216.34"]}.get(host, ["93.184.216.34"])
    )


def test_crash_after_first_document_saved_resumes_without_refetching(db):
    acquisition = CountingAcquisitionService()
    doc_repo = SQLiteWebDocumentRepository(db)
    res_repo = SQLiteAffiliateResearchRepository(db)
    service = AffiliateWebReferenceService(acquisition, doc_repo, res_repo, policy())

    inputs = [
        {"external_product_id": "SKU-1", "url": "https://example.com/p1", "source_kind": "manufacturer"},
        {"external_product_id": "SKU-1", "url": "https://example.com/p2", "source_kind": "editorial_review"},
        {"external_product_id": "SKU-1", "url": "https://example.com/p3", "source_kind": "documentation"},
    ]

    # Partial run: process first URL manually then simulate crash
    doc1 = acquisition.acquire(WebFetchRequest("42", "run-1", "prod-1", "https://example.com/p1"))
    doc_repo.save(doc1)
    doc_repo.attach("run-1", "prod-1", doc1.id, "manufacturer")
    assert acquisition.calls["https://example.com/p1"] == 1

    # Resume full collection
    refs = service.collect("42", "run-1", sample_products(), inputs)
    assert len(refs) == 3
    # p1 was reused from DB, so acquisition call count for p1 remains 1!
    assert acquisition.calls["https://example.com/p1"] == 1
    assert acquisition.calls["https://example.com/p2"] == 1
    assert acquisition.calls["https://example.com/p3"] == 1


def test_crash_before_content_generation_reuses_all_documents(db):
    acquisition = CountingAcquisitionService()
    doc_repo = SQLiteWebDocumentRepository(db)
    res_repo = SQLiteAffiliateResearchRepository(db)
    service = AffiliateWebReferenceService(acquisition, doc_repo, res_repo, policy())

    inputs = [
        {"external_product_id": "SKU-1", "url": "https://example.com/p1", "source_kind": "manufacturer"},
    ]

    refs1 = service.collect("42", "run-1", sample_products(), inputs)
    assert len(refs1) == 1
    assert acquisition.calls["https://example.com/p1"] == 1

    # Retry job after crash before content generation
    refs2 = service.collect("42", "run-1", sample_products(), inputs)
    assert len(refs2) == 1
    assert acquisition.calls["https://example.com/p1"] == 1
