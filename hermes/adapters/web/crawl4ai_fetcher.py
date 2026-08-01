import asyncio
import datetime
import hashlib
import uuid
from dataclasses import dataclass
from typing import Callable, Optional, Any

from hermes.domain.web_document import (
    WebFetchRequest,
    WebDocument,
    WebFetchFailure,
    UnsafeWebUrl,
)
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.application.web_document_normalizer import WebDocumentNormalizer, NormalizationResult


class Crawl4AIUnavailable(WebFetchFailure):
    def __init__(self, detail: str = "Crawl4AI dynamic fetcher is unavailable"):
        super().__init__(detail=detail, code="render_failed", retryable=False)


@dataclass
class SafeBrowserConfig:
    headless: bool = True
    browser_type: str = "chromium"
    use_persistent_context: bool = False
    verbose: bool = False


@dataclass
class SafeCrawlerRunConfig:
    cache_mode: Any = None
    check_robots_txt: bool = True
    page_timeout: int = 30000
    js_code: Any = None
    extraction_strategy: Any = None
    screenshot: bool = False
    pdf: bool = False
    process_iframes: bool = False
    remove_overlay_elements: bool = True


class Crawl4AIWebDocumentFetcher:
    def __init__(
        self,
        crawler_factory: Optional[Callable[[Any], Any]] = None,
        policy: Optional[PublicWebUrlPolicy] = None,
        normalizer: Optional[WebDocumentNormalizer] = None,
    ):
        self.crawler_factory = crawler_factory
        self.policy = policy or PublicWebUrlPolicy()
        self.normalizer = normalizer or WebDocumentNormalizer()

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        validated_url = self.policy.validate(request.url)

        # Import crawl4ai or use factory
        c4a_browser_config = None
        c4a_run_config = None

        if self.crawler_factory is not None:
            try:
                b_config = SafeBrowserConfig(headless=True, browser_type="chromium")
                crawler = self.crawler_factory(b_config)
                run_config = SafeCrawlerRunConfig(
                    check_robots_txt=True,
                    page_timeout=request.timeout_seconds * 1000,
                    js_code=None,
                    extraction_strategy=None,
                )
            except ImportError as e:
                raise Crawl4AIUnavailable("crawl4ai==0.9.2 is not installed.") from e
            except Exception as e:
                if isinstance(e, Crawl4AIUnavailable):
                    raise
                raise Crawl4AIUnavailable(f"Failed to instantiate crawler: {e}") from e
        else:
            try:
                from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
                b_config = BrowserConfig(
                    headless=True,
                    browser_type="chromium",
                    use_persistent_context=False,
                    verbose=False,
                )
                crawler = AsyncWebCrawler(config=b_config)
                run_config = CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS,
                    check_robots_txt=True,
                    page_timeout=request.timeout_seconds * 1000,
                    js_code=None,
                    extraction_strategy=None,
                    screenshot=False,
                    pdf=False,
                    process_iframes=False,
                    remove_overlay_elements=True,
                )
            except ImportError as e:
                raise Crawl4AIUnavailable("crawl4ai==0.9.2 is not installed. Install requirements-crawl4ai.txt and run setup_crawl4ai.ps1.") from e

        # Execute crawler run
        async def _execute():
            if hasattr(crawler, "__aenter__"):
                async with crawler as c:
                    return await c.arun(url=validated_url, config=run_config)
            else:
                return await crawler.arun(url=validated_url, config=run_config)

        try:
            result = asyncio.run(_execute())
        except WebFetchFailure:
            raise
        except Exception as e:
            raise WebFetchFailure(f"Crawl4AI execution error: {e}", code="render_failed", retryable=True) from e

        if not result or not getattr(result, "success", False):
            err_msg = getattr(result, "error_message", "") or "Render failed"
            if "robots" in err_msg.lower() or "denied" in err_msg.lower():
                raise WebFetchFailure(f"Access denied by robots.txt: {err_msg}", code="robots_denied", retryable=False)
            raise WebFetchFailure(f"Crawl4AI failed: {err_msg}", code="render_failed", retryable=True)

        final_url = getattr(result, "url", None) or validated_url
        try:
            final_url = self.policy.validate(final_url)
        except UnsafeWebUrl as e:
            raise WebFetchFailure(f"Final URL unsafe: {e}", code="unsafe_url", retryable=False) from e

        html = getattr(result, "cleaned_html", None) or getattr(result, "html", None) or ""
        if html:
            norm_res = self.normalizer.normalize(
                html,
                base_url=final_url,
                max_markdown_chars=request.max_markdown_chars,
            )
        else:
            markdown = getattr(result, "markdown", "") or ""
            if not markdown:
                raise WebFetchFailure("Crawl4AI returned empty content", code="empty_content", retryable=False)
            content_hash = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            title = (getattr(result, "metadata", {}) or {}).get("title", "")
            norm_res = NormalizationResult(
                title=title,
                markdown=markdown,
                metadata={},
                content_hash=content_hash,
                warnings=(),
                dynamic_fallback_recommended=False,
            )

        doc_id = f"doc_{uuid.uuid4().hex[:16]}"
        acquired_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

        return WebDocument(
            id=doc_id,
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=request.url,
            final_url=final_url,
            title=norm_res.title,
            markdown=norm_res.markdown,
            metadata=norm_res.metadata,
            acquisition_method="crawl4ai",
            content_hash=norm_res.content_hash,
            rights_status="reference_only",
            warnings=norm_res.warnings,
            acquired_at=acquired_at,
        )
