import pytest
from hermes.domain.affiliate_research import AffiliateProduct, ReferenceMetadata
from hermes.domain.web_document import WebDocument, WebFetchRequest
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.application.affiliate_web_reference_service import (
    AffiliateWebReferenceService,
    WebReferenceRejected,
)


class FakeWebAcquisitionService:
    def __init__(self):
        self.calls = 0

    def acquire(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        return WebDocument(
            id=f"doc-{self.calls}",
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=request.url,
            final_url=request.url,
            title="Spec Doc",
            markdown="# Spec Doc\n\nDetailed specifications.",
            metadata={"author": "TechReview"},
            acquisition_method="static_http",
            content_hash=f"hash-{self.calls}",
            rights_status="reference_only",
            warnings=(),
            acquired_at="2026-08-01T00:00:00Z",
        )


class FakeWebDocRepository:
    def __init__(self):
        self.docs = {}
        self.attachments = []

    def find_reusable(self, owner_user_id: str, normalized_url: str):
        return self.docs.get((owner_user_id, normalized_url))

    def save(self, document: WebDocument):
        key = (document.owner_user_id, document.final_url)
        if key in self.docs:
            return self.docs[key]
        self.docs[key] = document
        return document

    def attach(self, run_id: str, product_id: str, document_id: str, source_kind: str):
        self.attachments.append((run_id, product_id, document_id, source_kind))

    def list_for_product(self, owner_user_id: str, run_id: str, product_id: str):
        res = []
        for (r, p, d, s) in self.attachments:
            if r == run_id and p == product_id:
                for doc in self.docs.values():
                    if doc.id == d and doc.owner_user_id == owner_user_id:
                        res.append(doc)
        return res


class FakeResearchRepository:
    def __init__(self):
        self.references = []

    def save_reference(self, reference: ReferenceMetadata) -> ReferenceMetadata:
        self.references.append(reference)
        return reference


def sample_products():
    return [
        AffiliateProduct(
            id="prod-1",
            owner_user_id="42",
            platform="shopee",
            external_product_id="SKU-123",
            name="Desk Lamp",
            category="lamp",
            price_vnd=100000,
            sold_count=10,
            rating=4.8,
            review_count=5,
            commission_rate=0.1,
            shop_name="LampShop",
            product_url="https://example.com/item",
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
        resolver=lambda host: {"example.com": ["93.184.216.34"], "review.example": ["93.184.216.34"]}.get(host, ["93.184.216.34"])
    )


def test_web_references_are_acquired_once_and_bound_to_product():
    acquisition = FakeWebAcquisitionService()
    doc_repo = FakeWebDocRepository()
    res_repo = FakeResearchRepository()

    service = AffiliateWebReferenceService(
        web_acquisition_service=acquisition,
        web_document_repository=doc_repo,
        research_repository=res_repo,
        url_policy=policy(),
    )

    inputs = [
        {
            "external_product_id": "SKU-123",
            "url": "https://example.com/spec",
            "source_kind": "manufacturer",
        },
        {
            "external_product_id": "SKU-123",
            "url": "https://review.example/lamp",
            "source_kind": "editorial_review",
        },
    ]

    first = service.collect("42", "run-1", sample_products(), inputs)
    assert len(first) == 2
    assert acquisition.calls == 2
    assert all(item.rights_status == "reference_only" for item in first)

    # Second run reusing same documents
    second = service.collect("42", "run-1", sample_products(), inputs)
    assert len(second) == 2
    assert acquisition.calls == 2  # No new acquisition calls!


def test_reference_for_other_owner_or_non_shortlisted_product_is_rejected():
    acquisition = FakeWebAcquisitionService()
    doc_repo = FakeWebDocRepository()
    res_repo = FakeResearchRepository()

    service = AffiliateWebReferenceService(
        web_acquisition_service=acquisition,
        web_document_repository=doc_repo,
        research_repository=res_repo,
        url_policy=policy(),
    )

    inputs = [
        {
            "external_product_id": "UNKNOWN-SKU",
            "url": "https://example.com/spec",
            "source_kind": "manufacturer",
        }
    ]

    with pytest.raises(WebReferenceRejected):
        service.collect("42", "run-1", sample_products(), inputs)
