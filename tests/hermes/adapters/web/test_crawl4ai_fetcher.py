import pytest
from hermes.domain.web_document import WebFetchRequest, WebFetchFailure, UnsafeWebUrl
from hermes.application.web_url_policy import PublicWebUrlPolicy
from hermes.adapters.web.crawl4ai_fetcher import Crawl4AIWebDocumentFetcher, Crawl4AIUnavailable


class FakeResult:
    def __init__(
        self,
        success: bool = True,
        url: str = "https://example.com/rendered",
        markdown: str = "# Rendered\n\nUseful text",
        html: str = "<html><body><main><h1>Rendered</h1><p>Useful text here that is long enough to avoid dynamic fallback trigger.</p></main></body></html>",
        metadata: dict = None,
        error_message: str = None,
    ):
        self.success = success
        self.url = url
        self.markdown = markdown
        self.html = html
        self.cleaned_html = html
        self.metadata = metadata or {"title": "Rendered"}
        self.error_message = error_message


class FakeAsyncCrawler:
    def __init__(self, result: FakeResult = None):
        self.result = result or FakeResult()
        self.browser_config = None
        self.run_config = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def arun(self, url: str, config=None):
        self.run_config = config
        return self.result


def public_policy():
    return PublicWebUrlPolicy(
        resolver=lambda host: {
            "example.com": ["93.184.216.34"],
            "public.example": ["93.184.216.34"],
            "internal.example": ["10.0.0.8"],
        }.get(host, ["93.184.216.34"])
    )


def public_request(url="https://example.com/rendered"):
    return WebFetchRequest(
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        url=url,
    )


def test_crawl4ai_adapter_uses_safe_non_llm_configuration():
    crawler = FakeAsyncCrawler()

    def factory(b_config):
        crawler.browser_config = b_config
        return crawler

    fetcher = Crawl4AIWebDocumentFetcher(
        crawler_factory=factory,
        policy=public_policy(),
    )
    document = fetcher.fetch(public_request("https://example.com/rendered"))

    assert document.acquisition_method == "crawl4ai"
    assert crawler.browser_config.headless is True
    assert crawler.run_config.check_robots_txt is True
    assert crawler.run_config.js_code is None
    assert crawler.run_config.extraction_strategy is None


def test_crawl4ai_adapter_handles_robots_denial():
    crawler = FakeAsyncCrawler(
        result=FakeResult(
            success=False,
            error_message="Access denied by robots.txt policy",
        )
    )

    def factory(b_config):
        crawler.browser_config = b_config
        return crawler

    fetcher = Crawl4AIWebDocumentFetcher(
        crawler_factory=factory,
        policy=public_policy(),
    )
    with pytest.raises(WebFetchFailure) as exc_info:
        fetcher.fetch(public_request())
    assert exc_info.value.code == "robots_denied"
    assert exc_info.value.retryable is False


def test_crawl4ai_adapter_revalidates_final_redirect():
    crawler = FakeAsyncCrawler(
        result=FakeResult(
            success=True,
            url="http://10.0.0.8/internal-secret",
        )
    )

    def factory(b_config):
        return crawler

    fetcher = Crawl4AIWebDocumentFetcher(
        crawler_factory=factory,
        policy=public_policy(),
    )
    with pytest.raises(WebFetchFailure) as exc_info:
        fetcher.fetch(public_request())
    assert exc_info.value.code == "unsafe_url"


def test_crawl4ai_missing_dependency_raises_unavailable():
    def failing_factory(b_config):
        raise ImportError("No module named 'crawl4ai'")

    fetcher = Crawl4AIWebDocumentFetcher(
        crawler_factory=failing_factory,
        policy=public_policy(),
    )
    with pytest.raises(Crawl4AIUnavailable):
        fetcher.fetch(public_request())
