import json
import pytest
from pathlib import Path
from hermes.db import Database, SCHEMA_V1, SCHEMA_V3
from hermes.adapters.sqlite.schema_v2 import apply_schema_v2
from hermes.adapters.sqlite.schema_v4 import apply_schema_v4
from hermes.adapters.sqlite.schema_v5 import apply_schema_v5
from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
from hermes.adapters.sqlite.web_document_repository import SQLiteWebDocumentRepository
from hermes.adapters.web.static_fetcher import StaticWebDocumentFetcher
from hermes.adapters.web.crawl4ai_fetcher import Crawl4AIWebDocumentFetcher
from hermes.application.web_acquisition_service import WebAcquisitionService
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.application.affiliate_web_reference_service import AffiliateWebReferenceService
from hermes.application.affiliate_run_service import AffiliateRunService, AffiliateRunRequest
from hermes.application.affiliate_catalog_service import AffiliateCatalogService
from hermes.application.affiliate_content_service import AffiliateContentService
from hermes.adapters.google.sheets_projection import GoogleSheetsProjection
from tests.hermes.adapters.test_google_sheets_projection import FakeSheetsClient
from hermes.domain.web_document import WebDocument, WebFetchRequest
from hermes.domain.affiliate_research import ContentPackage, PackageStatus


class FakeStaticFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        if "static-good" in request.url:
            return WebDocument(
                id="doc-static",
                owner_user_id=request.owner_user_id,
                run_id=request.run_id,
                product_id=request.product_id,
                requested_url=request.url,
                final_url=request.url,
                title="Static Good Spec",
                markdown="# Static Good Spec\n\nFull static product specifications present here.",
                metadata={"author": "ReviewSite"},
                acquisition_method="static_http",
                content_hash="hash-static",
                rights_status="reference_only",
                warnings=(),
                acquired_at="2026-08-01T00:00:00Z",
            )
        else:
            # Returns dynamic shell needing Crawl4AI fallback
            return WebDocument(
                id="doc-shell",
                owner_user_id=request.owner_user_id,
                run_id=request.run_id,
                product_id=request.product_id,
                requested_url=request.url,
                final_url=request.url,
                title="App Shell",
                markdown="Loading...",
                metadata={},
                acquisition_method="static_http",
                content_hash="hash-shell",
                rights_status="reference_only",
                warnings=("dynamic_content_not_rendered",),
                acquired_at="2026-08-01T00:00:00Z",
            )


class FakeCrawl4AIFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        return WebDocument(
            id="doc-c4a",
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=request.url,
            final_url=request.url,
            title="Rendered Dynamic Spec",
            markdown="# Rendered Spec\n\nRendered dynamic product specs.",
            metadata={"author": "Crawl4AI"},
            acquisition_method="crawl4ai",
            content_hash="hash-c4a",
            rights_status="reference_only",
            warnings=(),
            acquired_at="2026-08-01T00:00:00Z",
        )


class FakeGateway:
    def generate(self, product, references, **kwargs):
        evidence_url = product.product_url
        if references:
            evidence_url = references[0].source_url
        return {
            "audience": "office_worker",
            "angle": f"Angle for {product.name}",
            "angle_reason": "Reasoning for angle",
            "hook": f"Unique hook for {product.id}",
            "script": f"Detailed script for {product.name}",
            "duration_seconds": 45,
            "storyboard": [{"visual": "Show product", "start": 0, "end": 45}],
            "ai_prompts": ["Prompt text"],
            "voiceover_plan": "Neutral voice",
            "text_overlays": ["Overlay text"],
            "claims": [
                {
                    "text": f"Claim for {product.name}",
                    "evidence_url": evidence_url,
                }
            ],
            "warnings": [],
        }


class FakeCsvSource:
    def __init__(self, path):
        pass

    def load_batch(self, owner_user_id: str):
        from hermes.domain.affiliate_research import ProductCandidate
        candidates = []
        for i in range(1, 101):
            candidates.append(
                ProductCandidate(
                    owner_user_id=owner_user_id,
                    platform="shopee",
                    external_product_id=f"SKU-{i}",
                    name=f"Product {i}",
                    category="lamp",
                    price_vnd=250000 + i * 1000,
                    sold_count=500 + i if i <= 5 else 50 + i,
                    rating=4.5 + (i % 5) * 0.1,
                    review_count=10 + i,
                    commission_rate=0.1,
                    shop_name="OfficialShop",
                    product_url=f"https://example.com/item/{i}",
                    image_urls=(),
                    visual_signals=("LED display",),
                    source_type="affiliate_csv",
                    source_url="https://example.com/feed.csv",
                    authorization_scope="user_export",
                    rights_status="affiliate_reference",
                    content_hash=f"hash-{i}",
                )
            )
        class Batch:
            def __init__(self, c):
                self.candidates = c
                self.errors = []
                self.imported = len(c)
                self.updated = 0
                self.rejected = 0
        return Batch(candidates)


def test_offline_crawl4ai_affiliate_acceptance_flow(tmp_path):
    db_path = tmp_path / "acceptance.db"

    # 1. Create a V5 database manually then initialize to run V6 migration
    import sqlite3
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_V1)
    apply_schema_v2(conn)
    conn.executescript(SCHEMA_V3)
    apply_schema_v4(conn)
    apply_schema_v5(conn)
    conn.execute("PRAGMA user_version = 5")
    conn.commit()
    conn.close()

    database = Database(db_path)
    database.initialize()  # Migrates to V6

    with database.connect() as check_conn:
        version = check_conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == 6

    # 2. Build composition with fake fetchers & fake gateway
    policy = PublicWebUrlPolicy(
        resolver=lambda host: {"example.com": ["93.184.216.34"]}.get(host, ["93.184.216.34"])
    )
    static_fetcher = FakeStaticFetcher()
    c4a_fetcher = FakeCrawl4AIFetcher()
    acquisition_service = WebAcquisitionService(
        static_fetcher=static_fetcher,
        crawl4ai_fetcher=c4a_fetcher,
        enabled=True,
    )
    doc_repo = SQLiteWebDocumentRepository(database)
    res_repo = SQLiteAffiliateResearchRepository(database)
    web_ref_service = AffiliateWebReferenceService(
        web_acquisition_service=acquisition_service,
        web_document_repository=doc_repo,
        research_repository=res_repo,
        url_policy=policy,
    )

    catalog_service = AffiliateCatalogService(res_repo)
    content_service = AffiliateContentService(res_repo, FakeGateway())
    sheets_client = FakeSheetsClient()
    sheets_projection = GoogleSheetsProjection(res_repo, sheets_client, "sheet-acceptance")

    run_service = AffiliateRunService(
        repository=res_repo,
        catalog_service=catalog_service,
        content_service=content_service,
        source_factory=FakeCsvSource,
        sheets_projection=sheets_projection,
        web_reference_collector=web_ref_service,
    )

    # 3. First execution
    web_inputs = [
        {"external_product_id": "SKU-1", "url": "https://example.com/static-good", "source_kind": "manufacturer"},
        {"external_product_id": "SKU-2", "url": "https://example.com/dynamic-page", "source_kind": "editorial_review"},
    ]
    request = AffiliateRunRequest(
        owner_user_id="42",
        idempotency_key="idemp-acceptance-1",
        csv_path=str(tmp_path / "feed.csv"),
        package_limit=5,
        web_references=tuple(web_inputs),
    )

    res1 = run_service.run(request)
    assert res1.run_id is not None
    assert res1.imported >= 100
    assert len(res1.package_ids) == 5
    assert res1.reused is False
    assert static_fetcher.calls == 2
    assert c4a_fetcher.calls == 1  # Called for SKU-2 dynamic page only

    # 4. Assert 7 Google Sheets tabs exist
    assert set(sheets_client.tabs) == {
        "Products", "Shortlist", "Ideas", "Scripts", "Approval Queue", "Runs & Errors", "Web Evidence"
    }

    # 5. Idempotent rerun with same idempotency key
    res2 = run_service.run(request)
    assert res2.reused is True
    assert set(res2.package_ids) == set(res1.package_ids)
    # Assert no extra fetch calls on rerun!
    assert static_fetcher.calls == 2
    assert c4a_fetcher.calls == 1
