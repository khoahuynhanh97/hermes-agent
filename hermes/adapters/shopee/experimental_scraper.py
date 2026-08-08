"""EXPERIMENTAL: Shopee public search scraper.

WARNING: For research/testing only. Not production-ready.
- Violates Shopee ToS
- Will be rate-limited/blocked at scale
- Use official Affiliate API for production

This adapter targets Shopee's public search JSON endpoint
which is less protected than the main HTML pages but still
subject to anti-bot detection.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterator, Sequence
from urllib.parse import urlencode

import requests

from hermes.domain.affiliate_research import ProductCandidate


@dataclass(frozen=True)
class ShopeeSearchConfig:
    """Configuration for experimental Shopee scraper."""

    category_ids: tuple[int, ...] = (
        11044826,  # Computer Accessories
        11044823,  # Keyboard & Mouse
        11044827,  # Audio
    )
    min_price: int = 200_000
    max_price: int = 500_000
    min_sold: int = 10
    sort_by: str = "sales"  # sales, price, relevancy
    limit_per_category: int = 50
    request_delay_seconds: float = 5.0
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


class ShopeeExperimentalScraper:
    """Experimental scraper targeting Shopee search API."""

    BASE_URL = "https://shopee.vn/api/v4/search/search_items"

    def __init__(self, config: ShopeeSearchConfig | None = None):
        self._config = config or ShopeeSearchConfig()
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": self._config.user_agent,
                "Referer": "https://shopee.vn/",
                "Accept": "application/json",
                "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            }
        )
        self._last_request_time = 0.0

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        """Scrape products matching configured filters.

        Returns at most limit_per_category * len(category_ids) candidates.
        Automatically rate-limits requests.
        """
        results: list[ProductCandidate] = []
        for category_id in self._config.category_ids:
            try:
                items = self._fetch_category(category_id)
                for item_data in items:
                    candidate = self._parse_item(item_data, owner_user_id, category_id)
                    if candidate and self._matches_filters(candidate):
                        results.append(candidate)
            except Exception as e:
                # Graceful degradation: log but continue with other categories
                print(f"ShopeeExperimentalScraper: category {category_id} failed: {e}")
                continue

        return results

    def _fetch_category(self, category_id: int) -> list[dict]:
        """Fetch products for one category."""
        items = []
        offset = 0
        limit = min(50, self._config.limit_per_category)

        while len(items) < self._config.limit_per_category:
            self._rate_limit()

            params = {
                "by": self._config.sort_by,
                "category": str(category_id),
                "limit": limit,
                "newest": offset,
                "order": "desc",
                "price_min": self._config.min_price,
                "price_max": self._config.max_price,
            }

            try:
                resp = self._session.get(
                    self.BASE_URL,
                    params=params,
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()

                batch = data.get("items", [])
                if not batch:
                    break

                items.extend(batch)
                offset += limit

                if len(batch) < limit:
                    break

            except (requests.RequestException, ValueError) as e:
                print(f"ShopeeExperimentalScraper: fetch failed at offset {offset}: {e}")
                break

        return items[: self._config.limit_per_category]

    def _parse_item(
        self, item_data: dict, owner_user_id: str, category_id: int
    ) -> ProductCandidate | None:
        """Parse Shopee API item structure into ProductCandidate."""
        try:
            item = item_data.get("item_basic", {})
            item_id = str(item.get("itemid", ""))
            shop_id = str(item.get("shopid", ""))
            if not item_id or not shop_id:
                return None

            name = item.get("name", "").strip()
            price = int(item.get("price", 0)) // 100  # cents -> VND
            sold_count = int(item.get("sold", 0))
            rating = float(item.get("item_rating", {}).get("rating_star", 0))
            review_count = int(item.get("item_rating", {}).get("rating_count", [0])[0])

            image_url = ""
            if item.get("images"):
                image_url = f"https://cf.shopee.vn/file/{item['images'][0]}"

            product_url = f"https://shopee.vn/-i.{shop_id}.{item_id}"

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            content_hash = hashlib.sha256(
                f"{item_id}:{name}:{price}:{sold_count}".encode("utf-8")
            ).hexdigest()

            return ProductCandidate(
                owner_user_id=owner_user_id,
                platform="shopee",
                external_product_id=item_id,
                name=name,
                category=self._category_name(category_id),
                price_vnd=price,
                sold_count=sold_count,
                rating=rating,
                review_count=review_count,
                commission_rate=None,  # Not available in public API
                shop_name=item.get("shop_name", "").strip(),
                product_url=product_url,
                image_urls=(image_url,) if image_url else (),
                visual_signals=self._infer_visual_signals(name, item),
                source_type="shopee_experimental_scraper",
                source_url=product_url,
                authorization_scope="public_scrape",
                rights_status="reference_only",
                content_hash=content_hash,
            )
        except (KeyError, ValueError, TypeError) as e:
            print(f"ShopeeExperimentalScraper: parse error: {e}")
            return None

    def _matches_filters(self, candidate: ProductCandidate) -> bool:
        """Apply post-fetch filters."""
        if not (self._config.min_price <= candidate.price_vnd <= self._config.max_price):
            return False
        if candidate.sold_count is not None and candidate.sold_count < self._config.min_sold:
            return False
        return True

    def _rate_limit(self) -> None:
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._config.request_delay_seconds:
            time.sleep(self._config.request_delay_seconds - elapsed)
        self._last_request_time = time.time()

    @staticmethod
    def _category_name(category_id: int) -> str:
        """Map category ID to human-readable name."""
        mapping = {
            11044826: "computer_accessories",
            11044823: "keyboard_mouse",
            11044827: "audio",
        }
        return mapping.get(category_id, f"category_{category_id}")

    @staticmethod
    def _infer_visual_signals(name: str, item: dict) -> tuple[str, ...]:
        """Heuristic visual signal detection from product name."""
        signals = []
        name_lower = name.lower()

        if any(kw in name_lower for kw in ["rgb", "led", "ánh sáng", "đèn"]):
            signals.append("light")
            signals.append("rgb")

        if any(kw in name_lower for kw in ["cơ", "mechanical", "switch"]):
            signals.append("tactile_interaction")
            signals.append("audible_interaction")

        if any(kw in name_lower for kw in ["wireless", "không dây"]):
            signals.append("movement")

        return tuple(signals)
