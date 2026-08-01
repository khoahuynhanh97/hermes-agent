import logging
from typing import Optional
from hermes.domain.web_document import (
    WebFetchRequest,
    WebDocument,
    WebFetchFailure,
    UnsafeWebUrl,
)
from hermes.ports.web_document_fetcher import WebDocumentFetcher
from hermes.web_research_config import WebResearchSettings, load_web_research_settings_from_env

logger = logging.getLogger(__name__)


class WebAcquisitionService:
    def __init__(
        self,
        static_fetcher: WebDocumentFetcher,
        crawl4ai_fetcher: Optional[WebDocumentFetcher] = None,
        settings: Optional[WebResearchSettings] = None,
        enabled: bool = False,
    ):
        self.static_fetcher = static_fetcher
        self.crawl4ai_fetcher = crawl4ai_fetcher
        self.settings = settings or load_web_research_settings_from_env()
        self.enabled = enabled or self.settings.crawl4ai_enabled

    def acquire(self, request: WebFetchRequest) -> WebDocument:
        static_doc: Optional[WebDocument] = None
        static_failure: Optional[WebFetchFailure] = None

        try:
            static_doc = self.static_fetcher.fetch(request)
        except WebFetchFailure as e:
            static_failure = e
            # Non-retryable structural policy failures should fail immediately
            if e.code in ("unsafe_url", "robots_denied", "unsupported_content", "too_large"):
                raise

        # Check if static acquisition succeeded and is complete
        if static_doc is not None:
            is_dynamic_shell = "dynamic_content_not_rendered" in static_doc.warnings
            if not is_dynamic_shell:
                # Static fetch was sufficient, no browser fallback needed
                return static_doc

            # Dynamic shell detected
            if self.enabled and self.crawl4ai_fetcher is not None:
                try:
                    c4a_doc = self.crawl4ai_fetcher.fetch(request)
                    return c4a_doc
                except WebFetchFailure as c4a_err:
                    logger.warning("Crawl4AI fallback failed for %s: %s", request.url, c4a_err)
                    if c4a_err.code in ("unsafe_url", "robots_denied"):
                        raise
                    # Otherwise return static doc with fallback warning preserved
                    return static_doc
            else:
                # Crawl4AI disabled or missing, return static doc with warning
                return static_doc

        # Static fetch failed with transport/timeout
        if self.enabled and self.crawl4ai_fetcher is not None:
            try:
                return self.crawl4ai_fetcher.fetch(request)
            except WebFetchFailure:
                pass

        if static_failure is not None:
            raise static_failure

        raise WebFetchFailure("Acquisition failed", code="transport_error", retryable=True)
