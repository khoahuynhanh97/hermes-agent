"""End-to-end pipeline: Scrape Shopee → Affiliate Research Run.

WARNING: Uses experimental scraper that violates Shopee ToS.
For research/testing only.

Usage:
    python scripts/run_scraper_pipeline.py --owner user_123 --key test_run_001

This script:
1. Scrapes products from Shopee (experimental, rate-limited)
2. Saves to temporary CSV
3. Runs full affiliate research pipeline
4. Generates packages + analyses
"""

from __future__ import annotations

import argparse
import csv
import sys
import tempfile
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
        description="Scrape Shopee + run affiliate pipeline (EXPERIMENTAL)"
    )
    parser.add_argument("--owner", required=True, help="owner_user_id")
    parser.add_argument("--key", required=True, help="idempotency_key for run")
    parser.add_argument(
        "--limit", type=int, default=30, help="products per category"
    )
    parser.add_argument(
        "--packages", type=int, default=5, help="content packages to generate"
    )
    parser.add_argument(
        "--delay", type=float, default=5.0, help="seconds between scrape requests"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scrape only, skip affiliate pipeline",
    )

    args = parser.parse_args(argv)

    print("[ScraperPipeline] Step 1: Scraping Shopee...")
    print(f"[ScraperPipeline] Owner: {args.owner}")
    print(f"[ScraperPipeline] Limit: {args.limit}/category")
    print(f"[ScraperPipeline] Rate limit: {args.delay}s")
    print()

    config = ShopeeSearchConfig(
        limit_per_category=args.limit,
        request_delay_seconds=args.delay,
    )
    scraper = ShopeeExperimentalScraper(config)

    try:
        candidates = scraper.load(args.owner)
    except Exception as e:
        print(f"[ScraperPipeline] Scraper failed: {e}")
        return 1

    if not candidates:
        print("[ScraperPipeline] No products found")
        return 1

    print(f"[ScraperPipeline] Scraped {len(candidates)} products")

    # Write to temporary CSV
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".csv",
        delete=False,
        newline="",
    ) as f:
        csv_path = Path(f.name)
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "item_id",
                "product_name",
                "category",
                "price",
                "sold_count",
                "rating",
                "review_count",
                "shop_name",
                "product_link",
                "image_url",
            ],
        )
        writer.writeheader()
        for c in candidates:
            writer.writerow(
                {
                    "item_id": c.external_product_id,
                    "product_name": c.name,
                    "category": c.category,
                    "price": c.price_vnd,
                    "sold_count": c.sold_count or 0,
                    "rating": c.rating or 0,
                    "review_count": c.review_count or 0,
                    "shop_name": c.shop_name,
                    "product_link": c.product_url,
                    "image_url": c.image_urls[0] if c.image_urls else "",
                }
            )

    print(f"[ScraperPipeline] Saved to temporary CSV: {csv_path}")

    if args.dry_run:
        print("[ScraperPipeline] Dry-run mode, stopping here")
        print(f"[ScraperPipeline] CSV retained at: {csv_path}")
        return 0

    print()
    print("[ScraperPipeline] Step 2: Running affiliate research pipeline...")

    from core.affiliate_research_jobs import (  # noqa: E402
        build_affiliate_research_job_handler,
    )

    handler = build_affiliate_research_job_handler()

    job_payload = {
        "id": f"scraper_job_{args.key}",
        "owner_user_id": args.owner,
        "payload": {
            "csv_path": str(csv_path),
            "idempotency_key": args.key,
            "package_limit": args.packages,
        },
    }

    try:
        result = handler(job_payload)
    except Exception as e:
        print(f"[ScraperPipeline] Affiliate pipeline failed: {e}")
        csv_path.unlink(missing_ok=True)
        return 1

    csv_path.unlink(missing_ok=True)

    print()
    print("[ScraperPipeline] ✓ Pipeline completed")
    print(f"  Run ID: {result.get('run_id')}")
    print(f"  Imported: {result.get('imported')}")
    print(f"  Shortlisted: {result.get('shortlisted')}")
    print(f"  Packages: {len(result.get('package_ids', []))}")

    if result.get("failed_projections"):
        print(f"  Failed projections: {result.get('failed_projections')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
