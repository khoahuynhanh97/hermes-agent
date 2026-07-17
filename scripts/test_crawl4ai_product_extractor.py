"""Tests for optional crawl4ai product extraction."""

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parent.parent))

from providers.crawl4ai_product_extractor import extract_product_brief


class FakeCrawler:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def run(self, url):
        return type("Result", (), {"markdown": "# Travel Mug\nKeeps coffee hot."})()


def run_tests():
    manual = extract_product_brief("", manual_data={"title": "Manual Lamp", "description": "Desk lamp"})
    assert manual["title"] == "Manual Lamp"
    assert manual["warnings"] == ["manual product data used"]

    with patch("providers.crawl4ai_product_extractor._load_crawler", return_value=FakeCrawler):
        brief = extract_product_brief("https://example.com/mug")
    assert brief["title"] == "Travel Mug"
    assert "Keeps coffee hot" in brief["description"]
    assert brief["source_url"] == "https://example.com/mug"

    with patch("providers.crawl4ai_product_extractor._load_crawler", side_effect=ImportError("missing")):
        fallback = extract_product_brief("https://example.com/fallback", manual_data={"title": "Fallback"})
    assert fallback["title"] == "Fallback"
    assert "crawl4ai unavailable: missing" in fallback["warnings"][0]
    print("crawl4ai product extractor tests: PASS")


if __name__ == "__main__":
    run_tests()
