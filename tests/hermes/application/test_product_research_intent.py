from __future__ import annotations

from pathlib import Path


def test_vietnamese_product_research_request_parses_category_price_and_defaults():
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message(
        "42",
        "crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản",
    )

    assert intent.owner_user_id == "42"
    assert intent.category == "bàn phím"
    assert intent.keyword == "bàn phím"
    assert intent.min_price_vnd == 200_000
    assert intent.max_price_vnd == 500_000
    assert intent.source_preference == "crawler_first"
    assert intent.script_limit == 5
    assert intent.idempotency_key.startswith("product-research-script-")
    assert intent.to_payload()["category"] == "bàn phím"


def test_product_research_request_uses_conservative_defaults():
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message("42", "tìm sản phẩm hub rồi xuất sheet")

    assert intent.category == "hub"
    assert intent.min_price_vnd == 200_000
    assert intent.max_price_vnd == 500_000
    assert intent.script_limit == 5


def test_assistant_runtime_routes_product_research_script_request():
    from core.assistant_runtime import HermesAssistantRuntime

    runtime = HermesAssistantRuntime(Path.cwd())

    assert (
        runtime.classify("crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản")
        == "product_research_script"
    )


def test_affiliate_settings_include_product_research_gates(tmp_path):
    from hermes.affiliate_config import load_affiliate_research_settings

    settings = load_affiliate_research_settings(
        {
            "AFFILIATE_IMPORT_DIR": str(tmp_path / "imports"),
            "GOOGLE_SHEETS_ENABLED": "0",
            "HERMES_ENABLE_MARKETPLACE_CRAWLER": "1",
            "HERMES_ENABLE_PLAYWRIGHT_CRAWLER": "0",
            "PRODUCT_RESEARCH_OUTPUT_DIR": str(tmp_path / "exports"),
            "PRODUCT_RESEARCH_AUTO_GENERATE_SCRIPTS": "1",
        }
    )

    assert settings.marketplace_crawler_enabled is True
    assert settings.playwright_crawler_enabled is False
    assert settings.local_sheet_output_dir == (tmp_path / "exports").resolve()
    assert settings.auto_generate_scripts is True
    assert "GOOGLE" not in repr(settings)