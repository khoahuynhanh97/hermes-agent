from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_legacy_runtime_is_not_a_semantic_router():
    source = (ROOT / "core" / "assistant_runtime.py").read_text(encoding="utf-8")

    assert "INTENT_RULES" not in source
    assert "return \"assistant_core\"" in source
    assert "affiliate-product-research" in source


def test_telegram_does_not_contain_product_intent_detector():
    source = (ROOT / "telegram_bot.py").read_text(encoding="utf-8")

    assert "is_product_research_script_request" not in source
