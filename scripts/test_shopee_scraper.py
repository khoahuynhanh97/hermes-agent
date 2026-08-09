"""Test script for experimental Shopee scraper.

Usage:
    python scripts/test_shopee_scraper.py --owner user_123 --limit 20

WARNING: This is experimental and violates Shopee ToS.
Use only for local testing/research. Do NOT run at scale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from hermes.adapters.shopee.experimental_scraper import (  # noqa: E402
    ShopeeExperimentalScraper,
    ShopeeSearchConfig,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Test experimental Shopee scraper (RESEARCH ONLY)"
    )
    parser.add_argument("--owner", required=True, help="owner_user_id")
    parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="max products per category (default: 20)",
    )
    parser.add_argument(
        "--min-price", type=int, default=200_000, help="min price VND"
    )
    parser.add_argument(
        "--max-price", type=int, default=500_000, help="max price VND"
    )
    parser.add_argument(
        "--output", default=None, help="output JSON file path (optional)"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="seconds between requests (default: 5.0)",
    )

    args = parser.parse_args(argv)

    config = ShopeeSearchConfig(
        min_price=args.min_price,
        max_price=args.max_price,
        limit_per_category=args.limit,
        request_delay_seconds=args.delay,
    )

    print(f"[ShopeeScraperTest] Starting scraper (limit={args.limit}/category)...")
    print(f"[ShopeeScraperTest] Price range: {args.min_price:,} - {args.max_price:,} VND")
    print(f"[ShopeeScraperTest] Rate limit: {args.delay}s between requests")
    print()

    scraper = ShopeeExperimentalScraper(config)
    
    try:
        candidates = scraper.load(args.owner)
    except KeyboardInterrupt:
        print("\n[ShopeeScraperTest] Interrupted by user")
        return 1

    print(f"\n[ShopeeScraperTest] Scraped {len(candidates)} products")
    
    if not candidates:
        print("[ShopeeScraperTest] No products found. Possible reasons:")
        print("  - Anti-bot detection blocked requests")
        print("  - No products match filters")
        print("  - Network/API error")
        return 1

    # Display summary
    print("\n[ShopeeScraperTest] Sample products:")
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
                "review_count": c.review_count,
                "shop_name": c.shop_name,
                "product_url": c.product_url,
                "image_urls": list(c.image_urls),
                "visual_signals": list(c.visual_signals),
            }
            for c in candidates
        ]

        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"[ShopeeScraperTest] Saved to {output_path}")

    print(f"\n[ShopeeScraperTest] Total: {len(candidates)} products")
    print("[ShopeeScraperTest] Categories:")
    categories = {}
    for c in candidates:
        categories[c.category] = categories.get(c.category, 0) + 1
    for cat, count in sorted(categories.items()):
        print(f"  - {cat}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
