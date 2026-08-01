from __future__ import annotations

from dataclasses import replace

import pytest

from hermes.domain.affiliate_research import (
    AffiliateProduct,
    ContentPackage,
    PackageStatus,
    ReferenceMetadata,
)


class MemoryRepository:
    def __init__(self):
        self.ideas = []
        self.packages = []
        self.products = []

    def save_ideas(self, product_id, run_id, ideas):
        assert all(idea.product_id == product_id and idea.run_id == run_id for idea in ideas)
        self.ideas.extend(ideas)
        return list(ideas)

    def save_package(self, package):
        self.packages.append(package)
        return package

    def get_package(self, package_id, owner_user_id):
        return next(
            (
                package
                for package in self.packages
                if package.id == package_id and package.owner_user_id == owner_user_id
            ),
            None,
        )

    def list_packages(self, owner_user_id, run_id=None):
        packages = [package for package in self.packages if package.owner_user_id == owner_user_id]
        if run_id is not None:
            packages = [package for package in packages if package.run_id == run_id]
        return list(packages)

    def list_products(self, owner_user_id, run_id=None):
        return [product for product in self.products if product.owner_user_id == owner_user_id]


class FakeContentGateway:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def generate(self, product, references, *, previous_package=None, feedback=""):
        self.calls.append((product, tuple(references), previous_package, feedback))
        return self.payload


@pytest.fixture
def repository():
    return MemoryRepository()


@pytest.fixture
def product():
    return AffiliateProduct(
        id="product-1",
        owner_user_id="42",
        platform="shopee",
        external_product_id="101",
        name="Ergonomic mouse",
        category="mouse",
        price_vnd=300_000,
        sold_count=120,
        rating=4.8,
        review_count=40,
        commission_rate=0.1,
        shop_name="Example shop",
        product_url="https://example.test/products/101",
        image_urls=("https://example.test/mouse.jpg",),
        visual_signals=("light", "visible_problem_solution"),
        source_type="affiliate_csv",
        source_url="https://example.test/feed.csv",
        authorization_scope="user_export",
        rights_status="affiliate_reference",
        content_hash="hash-101",
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


@pytest.fixture
def reference():
    return ReferenceMetadata(
        id="reference-1",
        owner_user_id="42",
        product_id="product-1",
        platform="tiktok",
        source_url="https://example.test/reference/1",
        title="Reference title",
        author_name="Creator",
        author_url="https://example.test/creator",
        thumbnail_url="https://example.test/thumb.jpg",
        caption="Reference caption",
        embed_html="<blockquote></blockquote>",
        authorization_scope="public_metadata",
        rights_status="reference_only",
        media_local_path="",
        collected_at="2026-08-01T00:00:00+00:00",
    )


def valid_payload(**overrides):
    value = {
        "audience": "office_worker",
        "angle": "Desk comfort",
        "angle_reason": "Visible setup improvement",
        "hook": "Bàn làm việc gọn hơn trong vài giây.",
        "script": "Chuột đặt vừa tay và phù hợp cho góc bàn nhỏ.",
        "duration_seconds": 45,
        "storyboard": [{"start": 0, "end": 5, "visual": "Mouse on desk"}],
        "ai_prompts": ["Modern office desk with space reserved for supplied product image"],
        "voiceover_plan": "Vietnamese neutral voice",
        "text_overlays": ["Gon ban lam viec"],
        "claims": [{"text": "Thông tin sản phẩm", "evidence_url": "https://example.test/products/101"}],
        "warnings": [],
    }
    value.update(overrides)
    return value


def test_content_service_rejects_unsourced_claims(repository, product):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    gateway = FakeContentGateway(
        valid_payload(
            script="Chuột này có độ trễ 1 ms chưa được xác thực.",
            claims=[{"text": "1 ms latency", "evidence_url": ""}],
        )
    )

    with pytest.raises(ContentValidationError, match="evidence"):
        AffiliateContentService(repository, gateway).create_packages("42", "run-1", [product], per_run=1)


def test_package_is_valid_keeps_reference_rights_and_persists_ideas(repository, product, reference):
    from hermes.application.affiliate_content_service import AffiliateContentService

    packages = AffiliateContentService(repository, FakeContentGateway(valid_payload())).create_packages(
        "42", "run-1", [product], [reference], per_run=1
    )

    assert 30 <= packages[0].duration_seconds <= 90
    assert packages[0].status is PackageStatus.PENDING_REVIEW
    assert packages[0].asset_rights[reference.id] == "reference_only"
    assert packages[0].claims[0]["evidence_url"]
    assert len(repository.ideas) == 3


def test_content_service_rejects_references_without_reference_only_rights(repository, product, reference):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    with pytest.raises(ContentValidationError, match="reference_only"):
        AffiliateContentService(repository, FakeContentGateway(valid_payload())).create_packages(
            "42", "run-1", [product], [replace(reference, rights_status="licensed")], per_run=1
        )


@pytest.mark.parametrize(
    "payload",
    [
        valid_payload(duration_seconds=25),
        valid_payload(storyboard=[{"start": 5, "end": 3, "visual": "Mouse on desk"}]),
    ],
)
def test_content_service_rejects_invalid_duration_or_storyboard(repository, product, payload):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    with pytest.raises(ContentValidationError):
        AffiliateContentService(repository, FakeContentGateway(payload)).create_packages(
            "42", "run-1", [product], per_run=1
        )


def test_content_service_rejects_duplicate_or_high_overlap_content(repository, product):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    existing = ContentPackage(
        id="existing",
        owner_user_id="42",
        product_id=product.id,
        run_id="old-run",
        revision=1,
        status=PackageStatus.PENDING_REVIEW,
        audience="office_worker",
        angle="Desk comfort",
        angle_reason="Visible setup improvement",
        hook="Bàn làm việc gọn hơn trong vài giây.",
        script="Chuột đặt vừa tay và phù hợp cho góc bàn nhỏ.",
        duration_seconds=45,
        storyboard=({"start": 0, "end": 5, "visual": "Mouse on desk"},),
        ai_prompts=("Modern office desk",),
        voiceover_plan="Vietnamese neutral voice",
        text_overlays=("Gon ban lam viec",),
        claims=({"text": "Thông tin sản phẩm", "evidence_url": product.product_url},),
        warnings=(),
        asset_rights={},
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    repository.packages.append(existing)
    payload = valid_payload(
        hook="Một góc nhìn mới cho bàn nhỏ.",
        script="Chuột đặt vừa tay phù hợp cho góc bàn nhỏ.",
    )

    with pytest.raises(ContentValidationError, match="duplicate"):
        AffiliateContentService(repository, FakeContentGateway(payload)).create_packages(
            "42", "run-1", [product], per_run=1
        )


def test_revise_package_preserves_old_revision_and_uses_feedback(repository, product):
    from hermes.application.affiliate_content_service import AffiliateContentService

    gateway = FakeContentGateway(valid_payload(hook="Phiên bản mới cho góc bàn gọn gàng."))
    service = AffiliateContentService(repository, gateway)
    repository.products.append(product)
    original = service.create_packages("42", "run-1", [product], per_run=1)[0]
    revised = service.revise_package(original.id, "42", "Làm hook ngắn hơn")

    assert revised.id != original.id
    assert revised.revision == 2
    assert repository.get_package(original.id, "42") == original
    assert gateway.calls[-1][2] == original
    assert gateway.calls[-1][3] == "Làm hook ngắn hơn"
