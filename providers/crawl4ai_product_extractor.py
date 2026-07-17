from __future__ import annotations

from typing import Any

from core.video_mvp_contracts import normalize_product_brief


def _load_crawler():
    from crawl4ai import WebCrawler

    return WebCrawler


def _brief_from_markdown(markdown: str, url: str) -> dict[str, Any]:
    lines = [line.strip(" #\t") for line in markdown.splitlines() if line.strip()]
    title = lines[0] if lines else "Untitled product"
    description = "\n".join(lines[1:20])
    return normalize_product_brief(
        {"title": title, "description": description},
        source_url=url,
        warnings=[],
    )


def extract_product_brief(url: str, manual_data: dict[str, Any] | None = None) -> dict[str, Any]:
    if not url:
        return normalize_product_brief(manual_data or {}, warnings=["manual product data used"])
    try:
        crawler_cls = _load_crawler()
        with crawler_cls() as crawler:
            result = crawler.run(url)
        markdown = getattr(result, "markdown", "") or str(result)
        return _brief_from_markdown(markdown, url)
    except Exception as exc:
        warnings = [f"crawl4ai unavailable: {exc}"]
        if manual_data:
            return normalize_product_brief(manual_data, source_url=url, warnings=warnings)
        return normalize_product_brief({"title": url, "description": ""}, source_url=url, warnings=warnings)
