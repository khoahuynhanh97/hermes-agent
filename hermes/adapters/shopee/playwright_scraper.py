"""Alternative: Browser-based Shopee scraper using Playwright.

This approach renders actual browser to bypass API detection.
Still violates ToS but has higher success rate than API scraping.

Requirements:
    pip install playwright
    playwright install chromium

WARNING: Slower, resource-heavy, still blockable. Research only.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from hermes.domain.affiliate_research import ProductCandidate


@dataclass(frozen=True)
class ShopeePlaywrightConfig:
    """Configuration for browser-based scraper."""

    search_keyword: str = "bàn phím cơ"
    min_price: int = 200_000
    max_price: int = 500_000
    min_sold: int = 10
    max_pages: int = 3  # Each page ~60 items
    headless: bool = True
    page_delay_seconds: float = 3.0


class ShopeePlaywrightScraper:
    """Browser-based scraper using Playwright."""

    def __init__(self, config: ShopeePlaywrightConfig | None = None):
        self._config = config or ShopeePlaywrightConfig()

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        """Scrape products by opening real browser."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )

        results: list[ProductCandidate] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self._config.headless)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            page = context.new_page()

            try:
                # Build search URL with filters
                search_url = self._build_search_url()
                print(f"[PlaywrightScraper] Opening: {search_url}")
                page.goto(search_url, wait_until="domcontentloaded", timeout=30000)
                time.sleep(5)  # Wait for JS to load items

                for page_num in range(self._config.max_pages):
                    print(f"[PlaywrightScraper] Scraping page {page_num + 1}...")

                    # Extract items from current page
                    items = self._extract_items(page, owner_user_id)
                    results.extend(items)

                    # Try to go to next page
                    if page_num < self._config.max_pages - 1:
                        next_button = page.query_selector('button[class*="next"]')
                        if next_button and not next_button.is_disabled():
                            next_button.click()
                            time.sleep(self._config.page_delay_seconds)
                        else:
                            break

            finally:
                browser.close()

        return results

    def _build_search_url(self) -> str:
        """Build Shopee search URL with filters."""
        keyword = self._config.search_keyword.replace(" ", "%20")
        return (
            f"https://shopee.vn/search?keyword={keyword}"
            f"&minPrice={self._config.min_price}"
            f"&maxPrice={self._config.max_price}"
            f"&sortBy=sales"
        )

    def _extract_items(self, page: Any, owner_user_id: str) -> list[ProductCandidate]:
        """Extract product cards from current page."""
        candidates = []

        # Shopee uses data-sqe attribute for product cards
        cards = page.query_selector_all('div[data-sqe="link"]')
        print(f"[PlaywrightScraper] Found {len(cards)} product cards")

        for card in cards:
            try:
                candidate = self._parse_card(card, owner_user_id)
                if candidate and self._matches_filters(candidate):
                    candidates.append(candidate)
            except Exception as e:
                # Skip malformed cards
                continue

        return candidates

    def _parse_card(self, card: Any, owner_user_id: str) -> ProductCandidate | None:
        """Parse a single product card element."""
        try:
            # Extract link
            link_elem = card.query_selector("a")
            if not link_elem:
                return None
            href = link_elem.get_attribute("href")
            if not href:
                return None

            product_url = f"https://shopee.vn{href}" if href.startswith("/") else href

            # Extract ID from URL: /product-name-i.123.456
            match = re.search(r"-i\.(\d+)\.(\d+)", href)
            if not match:
                return None
            shop_id, item_id = match.groups()

            # Extract name
            name_elem = card.query_selector('div[class*="title"]')
            name = name_elem.inner_text().strip() if name_elem else ""

            # Extract price
            price_elem = card.query_selector('span[class*="price"]')
            price_text = price_elem.inner_text().strip() if price_elem else "0"
            price = self._parse_price(price_text)

            # Extract sold count
            sold_elem = card.query_selector('div[class*="sold"]')
            sold_text = sold_elem.inner_text().strip() if sold_elem else "0"
            sold_count = self._parse_sold(sold_text)

            # Extract rating
            rating_elem = card.query_selector('div[class*="rating"]')
            rating = 0.0
            if rating_elem:
                rating_text = rating_elem.inner_text().strip()
                try:
                    rating = float(rating_text.replace(",", "."))
                except ValueError:
                    pass

            # Extract image
            img_elem = card.query_selector("img")
            image_url = img_elem.get_attribute("src") if img_elem else ""

            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            content_hash = hashlib.sha256(
                f"{item_id}:{name}:{price}:{sold_count}".encode("utf-8")
            ).hexdigest()

            return ProductCandidate(
                owner_user_id=owner_user_id,
                platform="shopee",
                external_product_id=item_id,
                name=name,
                category="tech_product",
                price_vnd=price,
                sold_count=sold_count,
                rating=rating,
                review_count=None,
                commission_rate=None,
                shop_name="",
                product_url=product_url,
                image_urls=(image_url,) if image_url else (),
                visual_signals=(),
                source_type="shopee_playwright_scraper",
                source_url=product_url,
                authorization_scope="public_scrape",
                rights_status="reference_only",
                content_hash=content_hash,
            )

        except Exception as e:
            return None

    def _matches_filters(self, candidate: ProductCandidate) -> bool:
        """Post-extraction filter."""
        if not (self._config.min_price <= candidate.price_vnd <= self._config.max_price):
            return False
        if candidate.sold_count is not None and candidate.sold_count < self._config.min_sold:
            return False
        return True

    @staticmethod
    def _parse_price(text: str) -> int:
        """Parse price string like '₫450.000' or '450k' to VND."""
        clean = re.sub(r"[^\d]", "", text)
        if not clean:
            return 0
        value = int(clean)
        # Handle 'k' notation: if value < 10000, multiply by 1000
        if value < 10000:
            value *= 1000
        return value

    @staticmethod
    def _parse_sold(text: str) -> int:
        """Parse sold text like 'Đã bán 1,2k' or 'Sold 500'."""
        match = re.search(r"([\d,]+)([kK])?", text)
        if not match:
            return 0
        num_str = match.group(1).replace(",", "")
        multiplier = 1000 if match.group(2) else 1
        try:
            return int(num_str) * multiplier
        except ValueError:
            return 0
