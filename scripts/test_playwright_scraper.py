"""Test Playwright-based Shopee scraper.

Usage:
    pip install playwright
    playwright install chromium
    python scripts/test_playwright_scraper.py --owner user_123 --keyword "bàn phím cơ"

WARNING: Opens real browser. Slower but bypasses API blocks.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from hermes.adapters.shopee.playwright_scraper import (  # noqa: E402
    ShopeePlaywrightScraper,
    ShopeePlaywrightConfig,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Test Playwright Shopee scraper (RESEARCH ONLY)"
    )
    parser.add_argument("--owner", required=True, help="owner_user_id")
    parser.add_argument(
        "--keyword",
        default="bàn phím cơ",
        help="search keyword (default: 'bàn phím cơ')",
    )
    parser.add_argument("--pages", type=int, default=2, help="max pages to scrape")
    parser.add_argument(
        "--min-price", type=int, default=200_000, help="min price VND"
    )
    parser.add_argument(
        "--max-price", type=int, default=500_000, help="max price VND"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run browser in headless mode (faster but harder to debug)",
    )
    parser.add_argument(
        "--output", default=None, help="output JSON file path (optional)"
    )

    args = parser.parse_args(argv)

    config = ShopeePlaywrightConfig(
        search_keyword=args.keyword,
        min_price=args.min_price,
        max_price=args.max_price,
        max_pages=args.pages,
        headless=args.headless,
    )

    print(f"[PlaywrightTest] Keyword: '{args.keyword}'")
    print(f"[PlaywrightTest] Price: {args.min_price:,} - {args.max_price:,} VND")
    print(f"[PlaywrightTest] Pages: {args.pages}")
    print(f"[PlaywrightTest] Headless: {args.headless}")
    print()

    scraper = ShopeePlaywrightScraper(config)

    try:
        candidates = scraper.load(args.owner)
    except Exception as e:
        print(f"[PlaywrightTest] Scraper failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print(f"\n[PlaywrightTest] Scraped {len(candidates)} products")

    if not candidates:
        print("[PlaywrightTest] No products found")
        return 1

    # Display summary
    print("\n[PlaywrightTest] Sample products:")
    for i, candidate in enumerate(candidates[:5], 1):
        print(f"  {i}. {candidate.name}")
        print(f"     Price: {candidate.price_vnd:,} VND | Sold: {candidate.sold_count}")
        print(f"     URL: {candidate.product_url}")
        print()

    # Save to file if requested
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        data = [
            {
                "external_product_id": c.external_product_id,
                "name": c.name,
                "category": c.category,
                "price_vnd": c.price_vnd,
                "sold_count": c.sold_count,
                "rating": c.rating,
                "shop_name": c.shop_name,
                "product_url": c.product_url,
                "image_urls": list(c.image_urls),
            }
            for c in candidates
        ]

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[PlaywrightTest] Saved to {output_path}")

    print(f"\n[PlaywrightTest] Total: {len(candidates)} products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
