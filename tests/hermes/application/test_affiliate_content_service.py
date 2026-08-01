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
        existing = next((item for item in self.packages if item.id == package.id), None)
        if existing is not None:
            if existing != package:
                raise ValueError(f"conflicting package payload for id: {package.id}")
            return existing
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
        AffiliateContentService(repository, gateway).create_packages("42", "run-1", [product], per_run=5)


def test_package_is_valid_keeps_reference_rights_and_persists_ideas(repository, product, reference):
    from hermes.application.affiliate_content_service import AffiliateContentService

    packages = AffiliateContentService(repository, FakeContentGateway(valid_payload())).create_packages(
        "42", "run-1", [product], [reference], per_run=5
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
            "42", "run-1", [product], [replace(reference, rights_status="licensed")], per_run=5
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
            "42", "run-1", [product], per_run=5
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
            "42", "run-1", [product], per_run=5
        )


def test_revise_package_preserves_old_revision_and_uses_feedback(repository, product):
    from hermes.application.affiliate_content_service import AffiliateContentService

    gateway = FakeContentGateway(valid_payload(hook="Phiên bản mới cho góc bàn gọn gàng."))
    service = AffiliateContentService(repository, gateway)
    repository.products.append(product)
    original = service.create_packages("42", "run-1", [product], per_run=5)[0]
    gateway.payload = valid_payload(
        hook="Thu gon goc lam viec trong mot buoc.",
        script="Su dung goc quay tren cao de thay doi bo cuc ban lam viec.",
    )
    revised = service.revise_package(original.id, "42", "Làm hook ngắn hơn")

    assert revised.id != original.id
    assert revised.revision == 2
    assert repository.get_package(original.id, "42") == original
    assert gateway.calls[-1][2] == original
    assert gateway.calls[-1][3] == "Làm hook ngắn hơn"


def test_production_per_run_must_be_between_five_and_ten(repository, product):
    from hermes.application.affiliate_content_service import AffiliateContentService

    with pytest.raises(ValueError, match="between 5 and 10"):
        AffiliateContentService(repository, FakeContentGateway(valid_payload())).create_packages(
            "42", "run-1", [product], per_run=4
        )


def test_revisions_have_deterministic_lineage_and_idempotent_retries(repository, product):
    from hermes.application.affiliate_content_service import AffiliateContentService

    gateway = FakeContentGateway(
        valid_payload(
            hook="Goc lam viec gon gang hon.",
            script="Dat chuot dung vi tri de thao tac de dang.",
        )
    )
    service = AffiliateContentService(repository, gateway)
    repository.products.append(product)
    original = service.create_packages("42", "run-1", [product], per_run=5)[0]
    gateway.payload = valid_payload(
        hook="Thu gon goc lam viec trong mot buoc.",
        script="Su dung goc quay tren cao de thay doi bo cuc ban lam viec.",
    )
    revised = service.revise_package(original.id, "42", "Lam hook ngan hon")
    repeated = service.revise_package(original.id, "42", "Lam hook ngan hon")

    assert revised.id == f"{original.id}:r2"
    assert revised.revision == 2
    assert repeated == revised
    assert len(repository.packages) == 2

    gateway.payload = valid_payload(
        hook="Huong dan moi cho goc ban nho.",
        script="Canh quay moi trinh bay bo cuc va vi tri dat chuot.",
    )
    with pytest.raises(ValueError, match="conflicting package payload"):
        service.revise_package(original.id, "42", "Lam hook ngan hon")

    gateway.payload = valid_payload(
        hook="Mot thao tac de ban lam viec sach hon.",
        script="Quay can canh vi tri chuot va khoang trong tren mat ban.",
    )
    third = service.revise_package(revised.id, "42", "Them goc quay can canh")

    assert third.id == f"{original.id}:r3"
    assert third.revision == 3


def test_revision_checks_parent_for_high_overlap_content(repository, product):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    gateway = FakeContentGateway(
        valid_payload(
            hook="Goc lam viec gon gang hon.",
            script="Dat chuot dung vi tri de thao tac de dang.",
        )
    )
    service = AffiliateContentService(repository, gateway)
    repository.products.append(product)
    original = service.create_packages("42", "run-1", [product], per_run=5)[0]
    gateway.payload = valid_payload(
        hook="Goc quay moi cho ban lam viec.",
        script="Mo dau moi. Dat chuot dung vi tri de thao tac de dang. Ket thuc moi.",
    )

    with pytest.raises(ContentValidationError, match="duplicate"):
        service.revise_package(original.id, "42", "Doi cach dien dat")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("hook", "T\u00d4I   tr\u1ea3i   nghi\u1ec7m con chuot nay."),
        ("script", "T\u00f4i \u0111\u00e3 d\u00f9ng san pham nay."),
        ("claims", [{"text": "M\u00ecnh d\u00f9ng chuot nay", "evidence_url": "https://example.test/products/101"}]),
        ("text_overlays", ["Sau khi d\u00f9ng"]),
        ("voiceover_plan", "T\u00f4i tr\u1ea3i nghi\u1ec7m goc ban nay"),
        ("storyboard", [{"start": 0, "end": 5, "visual": "Sau khi d\u00f9ng chuot"}]),
        ("ai_prompts", ["T\u00f4i \u0111\u00e3 d\u00f9ng chuot tren ban lam viec"]),
    ],
)
def test_first_hand_detection_scans_all_package_text_fields(repository, product, field, value):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    with pytest.raises(ContentValidationError, match="first-hand"):
        AffiliateContentService(repository, FakeContentGateway(valid_payload(**{field: value}))).create_packages(
            "42", "run-1", [product], per_run=5
        )


def test_overlap_detects_padded_copied_passages_but_ignores_short_generic_hooks():
    from hermes.application.affiliate_content_service import AffiliateContentService

    assert AffiliateContentService._is_high_overlap("Gon hon", "  gon   HON ")
    assert not AffiliateContentService._is_high_overlap("Gon hon", "Ban sach")
    assert AffiliateContentService._is_high_overlap(
        "Mo dau moi. Dat chuot dung vi tri de thao tac de dang. Ket thuc moi.",
        "Dat chuot dung vi tri de thao tac de dang.",
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("voiceover_plan", "I   tried the product."),
        ("ai_prompts", ["I used the supplied product image on a desk."]),
        ("claims", [{"text": "My experience with this setup", "evidence_url": "https://example.test/products/101"}]),
        ("text_overlays", ["T\u00f4i review con chuot nay"]),
        ("storyboard", [{"start": 0, "end": 5, "visual": "M\u00ecnh review chuot tren ban"}]),
    ],
)
def test_first_hand_detection_rejects_clear_english_and_vietnamese_variants(
    repository, product, field, value
):
    from hermes.application.affiliate_content_service import (
        AffiliateContentService,
        ContentValidationError,
    )

    with pytest.raises(ContentValidationError, match="first-hand"):
        AffiliateContentService(repository, FakeContentGateway(valid_payload(**{field: value}))).create_packages(
            "42", "run-1", [product], per_run=5
        )
