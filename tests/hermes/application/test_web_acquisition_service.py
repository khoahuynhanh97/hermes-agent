import pytest
from hermes.domain.web_document import WebFetchRequest, WebDocument, WebFetchFailure
from hermes.web_research_config import WebResearchSettings, load_web_research_settings_from_env, validate_web_reference_batch, WebBatchRejected
from hermes.application.web_acquisition_service import WebAcquisitionService


class FakeFetcher:
    def __init__(self, document: WebDocument = None, failure: Exception = None):
        self.document = document
        self.failure = failure
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        if self.failure:
            raise self.failure
        return self.document


class FailingIfCalledFetcher:
    def __init__(self):
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        raise AssertionError("Fetcher should not have been called!")


def sample_request(url="https://example.com/app"):
    return WebFetchRequest(
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        url=url,
    )


def dynamic_shell_document():
    return WebDocument(
        id="doc-shell",
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        requested_url="https://example.com/app",
        final_url="https://example.com/app",
        title="App Shell",
        markdown="Loading...",
        metadata={},
        acquisition_method="static_http",
        content_hash="hash123",
        rights_status="reference_only",
        warnings=("dynamic_content_not_rendered",),
        acquired_at="2026-08-01T00:00:00Z",
    )


def rendered_document():
    return WebDocument(
        id="doc-rendered",
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        requested_url="https://example.com/app",
        final_url="https://example.com/app",
        title="Rendered App",
        markdown="# Rendered\n\nFull interactive content here.",
        metadata={},
        acquisition_method="crawl4ai",
        content_hash="hash456",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-01T00:00:00Z",
    )


def complete_document():
    return WebDocument(
        id="doc-complete",
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        requested_url="https://example.com/article",
        final_url="https://example.com/article",
        title="Complete Article",
        markdown="# Complete Article\n\nAll static text present.",
        metadata={},
        acquisition_method="static_http",
        content_hash="hash789",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-01T00:00:00Z",
    )


def test_dynamic_shell_falls_back_to_crawl4ai_once():
    static = FakeFetcher(document=dynamic_shell_document())
    browser = FakeFetcher(document=rendered_document())
    service = WebAcquisitionService(static, browser, enabled=True)
    result = service.acquire(sample_request("https://example.com/app"))
    assert result.acquisition_method == "crawl4ai"
    assert static.calls == 1
    assert browser.calls == 1


def test_successful_static_document_does_not_start_browser():
    browser = FailingIfCalledFetcher()
    result = WebAcquisitionService(
        FakeFetcher(document=complete_document()),
        browser,
        enabled=True,
    ).acquire(sample_request("https://example.com/article"))
    assert result.acquisition_method == "static_http"


def test_batch_rejects_more_than_20_urls_or_more_than_5_per_host():
    twenty_one_urls = [f"https://example{i}.com/page" for i in range(21)]
    with pytest.raises(WebBatchRejected):
        validate_web_reference_batch(twenty_one_urls)

    six_host_urls = [f"https://samehost.com/page{i}" for i in range(6)]
    with pytest.raises(WebBatchRejected):
        validate_web_reference_batch(six_host_urls)
