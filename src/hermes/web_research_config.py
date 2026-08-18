import os
import urllib.parse
from dataclasses import dataclass
from typing import Sequence


class WebBatchRejected(Exception):
    """Raised when a batch of web reference URLs violates limits."""
    pass


HARD_MAX_URLS_PER_RUN = 20
HARD_MAX_URLS_PER_HOST = 5
HARD_MAX_TIMEOUT_SECONDS = 30
HARD_MAX_HTML_BYTES = 2 * 1024 * 1024
HARD_MAX_MARKDOWN_CHARS = 200_000


@dataclass(frozen=True)
class WebResearchSettings:
    crawl4ai_enabled: bool = False
    max_urls_per_run: int = 20
    max_urls_per_host: int = 5
    timeout_seconds: int = 30
    max_html_bytes: int = 2 * 1024 * 1024
    max_markdown_chars: int = 200_000


def load_web_research_settings_from_env() -> WebResearchSettings:
    enabled_val = os.getenv("CRAWL4AI_ENABLED", "0").strip().lower()
    crawl4ai_enabled = enabled_val in ("1", "true", "yes", "on")

    run_limit = int(os.getenv("WEB_RESEARCH_MAX_URLS_PER_RUN", str(HARD_MAX_URLS_PER_RUN)))
    run_limit = min(run_limit, HARD_MAX_URLS_PER_RUN)

    host_limit = int(os.getenv("WEB_RESEARCH_MAX_URLS_PER_HOST", str(HARD_MAX_URLS_PER_HOST)))
    host_limit = min(host_limit, HARD_MAX_URLS_PER_HOST)

    timeout = int(os.getenv("WEB_RESEARCH_TIMEOUT_SECONDS", str(HARD_MAX_TIMEOUT_SECONDS)))
    timeout = min(timeout, HARD_MAX_TIMEOUT_SECONDS)

    html_bytes = int(os.getenv("WEB_RESEARCH_MAX_HTML_BYTES", str(HARD_MAX_HTML_BYTES)))
    html_bytes = min(html_bytes, HARD_MAX_HTML_BYTES)

    markdown_chars = int(os.getenv("WEB_RESEARCH_MAX_MARKDOWN_CHARS", str(HARD_MAX_MARKDOWN_CHARS)))
    markdown_chars = min(markdown_chars, HARD_MAX_MARKDOWN_CHARS)

    return WebResearchSettings(
        crawl4ai_enabled=crawl4ai_enabled,
        max_urls_per_run=run_limit,
        max_urls_per_host=host_limit,
        timeout_seconds=timeout,
        max_html_bytes=html_bytes,
        max_markdown_chars=markdown_chars,
    )


def validate_web_reference_batch(
    urls: Sequence[str],
    settings: WebResearchSettings = WebResearchSettings(),
) -> None:
    if len(urls) > settings.max_urls_per_run:
        raise WebBatchRejected(f"Batch contains {len(urls)} URLs, exceeding limit of {settings.max_urls_per_run} per run.")

    host_counts = {}
    for url in urls:
        parsed = urllib.parse.urlparse(url)
        host = (parsed.hostname or "").lower()
        host_counts[host] = host_counts.get(host, 0) + 1
        if host_counts[host] > settings.max_urls_per_host:
            raise WebBatchRejected(f"Host '{host}' has {host_counts[host]} URLs in batch, exceeding limit of {settings.max_urls_per_host} per host.")
