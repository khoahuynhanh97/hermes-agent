from __future__ import annotations

import pytest

from hermes.domain.web_document import WebDocument
from mcp_servers.research import server


def test_research_extract_is_deterministic_and_does_not_persist():
    result = server.research_extract(
        "<html><head><title>Facts</title></head><body><main><h1>Facts</h1><p>Known.</p><script>bad()</script></main></body></html>",
        "https://example.com/facts",
    )

    assert result["title"] == "Facts"
    assert "Known." in result["markdown"]
    assert "bad()" not in result["markdown"]
    assert result["content_hash"]


def test_research_fetch_persists_and_get_is_owner_scoped(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_RESEARCH_DB_PATH", str(tmp_path / "research.sqlite"))
    document = WebDocument(
        id="doc-research-1",
        owner_user_id="owner-1",
        run_id="session-1",
        product_id="research",
        requested_url="https://example.com/facts",
        final_url="https://example.com/facts",
        title="Facts",
        markdown="# Facts\n\nKnown.",
        metadata={"author": "Example"},
        acquisition_method="static_http",
        content_hash="hash-1",
        rights_status="reference_only",
        warnings=(),
        acquired_at="2026-08-06T00:00:00+00:00",
    )
    monkeypatch.setattr(server.WebAcquisitionService, "acquire", lambda self, request: document)

    fetched = server.research_fetch("owner-1", "session-1", "https://example.com/facts")
    assert fetched["source_id"] == "doc-research-1"
    assert fetched["rights_status"] == "reference_only"
    assert server.research_get_source("owner-1", "doc-research-1")["content"] == "# Facts\n\nKnown."
    with pytest.raises(ValueError, match="not found"):
        server.research_get_source("other-owner", "doc-research-1")


def test_research_fetch_maps_unsafe_url_without_bypassing_policy(tmp_path, monkeypatch):
    from hermes.domain.web_document import UnsafeWebUrl

    monkeypatch.setenv("HERMES_RESEARCH_DB_PATH", str(tmp_path / "research.sqlite"))
    with pytest.raises(UnsafeWebUrl) as exc_info:
        server.research_fetch("owner-1", "session-1", "http://127.0.0.1/admin")
    assert exc_info.value.code == "unsafe_url"
