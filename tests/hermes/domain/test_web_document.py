import pytest
from hermes.domain.web_document import (
    WebFetchRequest,
    WebDocument,
    WebFetchFailure,
    UnsafeWebUrl,
)


def test_web_document_requires_bounded_public_source():
    request = WebFetchRequest(
        owner_user_id="42",
        run_id="run-1",
        product_id="product-1",
        url="https://example.com/review",
    )
    assert request.url == "https://example.com/review"
    assert request.timeout_seconds == 30
    assert request.max_html_bytes == 2 * 1024 * 1024
    assert request.max_markdown_chars == 200_000


def test_web_document_immutable_fields():
    doc = WebDocument(
        id="doc-1",
        owner_user_id="42",
        run_id="run-1",
        product_id="prod-1",
        requested_url="https://example.com/review",
        final_url="https://example.com/review",
        title="Review Title",
        markdown="# Review",
        metadata={"author": "Tester"},
        acquisition_method="static_http",
        content_hash="abc123hash",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-01T00:00:00Z",
    )
    assert doc.rights_status == "reference_only"
    assert doc.acquisition_method == "static_http"


def test_web_fetch_failure_properties():
    err = UnsafeWebUrl("URL is blocked")
    assert err.code == "unsafe_url"
    assert err.retryable is False
    assert "URL is blocked" in str(err)
