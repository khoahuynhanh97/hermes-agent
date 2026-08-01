from hermes.domain.affiliate_research import AffiliateProduct, ProductPolicy, ProductScorer


def product(**overrides):
    values = {
        "id": "shopee:101",
        "owner_user_id": "42",
        "platform": "shopee",
        "external_product_id": "101",
        "name": "RGB mouse",
        "category": "mouse",
        "price_vnd": 350_000,
        "sold_count": 12_000,
        "rating": 4.8,
        "review_count": 1_200,
        "commission_rate": 0.12,
        "shop_name": "Example",
        "product_url": "https://shopee.vn/product/101",
        "image_urls": ("https://example.com/mouse.jpg",),
        "visual_signals": ("light", "visible_problem_solution", "multiple_scenes"),
        "source_type": "affiliate_csv",
        "source_url": "",
        "authorization_scope": "user_export",
        "rights_status": "affiliate_reference",
        "content_hash": "abc",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    }
    values.update(overrides)
    return AffiliateProduct(**values)


def test_price_policy_has_keyboard_exception():
    policy = ProductPolicy()

    assert policy.evaluate(product(price_vnd=600_000, category="mouse")).eligible is False
    assert policy.evaluate(product(price_vnd=1_400_000, category="keyboard")).eligible is True
    assert policy.evaluate(product(price_vnd=1_600_000, category="keyboard")).eligible is False


def test_keyboard_price_score_normalizes_category_at_price_boundaries():
    policy = ProductPolicy()
    scorer = ProductScorer()
    eligible_product = product(category=" Keyboard ", price_vnd=1_500_000)

    assert policy.evaluate(eligible_product).eligible is True
    assert scorer.score(
        eligible_product,
        category_sales=(100, 12_000),
        previous_sold_count=11_500,
        seen_before=False,
    ).components["price"] > 0
    assert policy.evaluate(product(category=" KEYBOARD ", price_vnd=1_500_001)).eligible is False


def test_score_is_explainable_and_totals_one_hundred():
    result = ProductScorer().score(
        product(),
        category_sales=(100, 12_000),
        previous_sold_count=11_500,
        seen_before=False,
    )

    assert result.total == sum(result.components.values())
    assert set(result.components) == {
        "sales",
        "visual",
        "price",
        "trust",
        "commission",
        "novelty",
    }
    assert result.total <= 100
    assert result.reason
    assert result.confidence == "high"


def test_missing_history_lowers_confidence_without_inventing_growth():
    result = ProductScorer().score(
        product(),
        category_sales=(100, 12_000),
        previous_sold_count=None,
        seen_before=True,
    )

    assert result.growth_rate is None
    assert result.confidence == "medium"
