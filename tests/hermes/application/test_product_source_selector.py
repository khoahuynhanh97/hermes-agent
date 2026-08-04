from __future__ import annotations

from pathlib import Path

from hermes.domain.affiliate_research import ProductCandidate


def candidate(number: int) -> ProductCandidate:
    return ProductCandidate(
        owner_user_id="42",
        platform="shopee",
        external_product_id=str(number),
        name=f"Keyboard {number}",
        category="keyboard",
        price_vnd=350000,
        sold_count=100 + number,
        rating=4.8,
        review_count=20,
        commission_rate=None,
        shop_name="Shop",
        product_url=f"https://example.test/{number}",
        image_urls=(),
        visual_signals=("tactile_interaction",),
        source_type="fake_crawler",
        source_url=f"https://example.test/{number}",
        authorization_scope="public_scrape",
        rights_status="reference_only",
        content_hash=f"hash-{number}",
    )


class FakeCrawler:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.called = False

    def load(self, owner_user_id: str):
        self.called = True
        if self.error:
            raise self.error
        return self.rows


def settings(tmp_path, enabled: bool):
    from hermes.affiliate_config import AffiliateResearchSettings

    return AffiliateResearchSettings(
        import_directory=tmp_path,
        google_sheets_enabled=False,
        google_sheets_credentials_file="",
        google_sheets_spreadsheet_id="",
        marketplace_crawler_enabled=enabled,
        playwright_crawler_enabled=False,
        local_sheet_output_dir=tmp_path / "exports",
        auto_generate_scripts=False,
    )


def intent():
    from hermes.application.product_research_intent import ProductResearchIntent

    return ProductResearchIntent.from_message("42", "crawl ngành bàn phím, giá 200k-500k")


def test_selector_uses_crawler_when_enabled(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler([candidate(1)])
    selected = ProductSourceSelector(settings(tmp_path, True), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "crawler"
    assert selected.load("42") == [candidate(1)]
    assert crawler.called is True


def test_selector_does_not_call_crawler_when_disabled(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler([candidate(1)])
    selected = ProductSourceSelector(settings(tmp_path, False), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "needs_csv_feed"
    assert selected.load("42") == []
    assert selected.warnings == ("Marketplace crawler is disabled; provide CSV/feed fallback.",)
    assert crawler.called is False


def test_selector_converts_crawler_block_to_csv_fallback(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler(error=RuntimeError("403 Forbidden"))
    selected = ProductSourceSelector(settings(tmp_path, True), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "crawler"
    assert selected.load("42") == []
    assert "CSV/feed fallback" in selected.warnings[0]