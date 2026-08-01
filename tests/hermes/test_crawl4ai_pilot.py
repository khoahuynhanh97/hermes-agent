import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.crawl4ai_pilot import (  # noqa: E402
    ALLOWED_SOURCE_KINDS,
    MAX_URLS,
    MAX_URLS_PER_HOST,
    MIN_URLS,
    PilotInputError,
    PilotRuntimeError,
    _safe_detail,
    load_entries,
    redact_url,
    run_pilot,
    validate_batch,
)
from hermes.application.web_url_policy import PublicWebUrlPolicy  # noqa: E402
from hermes.domain.web_document import (  # noqa: E402
    WebDocument,
    WebFetchFailure,
    WebFetchRequest,
)


def fake_public_resolver(host: str) -> list[str]:
    mapping = {
        "example.com": ["93.184.216.34"],
        "example.org": ["93.184.216.34"],
        "public.example": ["93.184.216.34"],
    }
    return mapping.get(host, ["93.184.216.34"])


def make_policy():
    return PublicWebUrlPolicy(resolver=fake_public_resolver)


def make_entry(url="https://example.com/article", kind="public_article", external_id="SKU-001"):
    return {"url": url, "external_product_id": external_id, "source_kind": kind}


def _batch_hosts():
    return ("example.com", "example.org")


def make_batch(n=MIN_URLS):
    hosts = _batch_hosts()
    return [
        make_entry(
            f"https://{hosts[i % len(hosts)]}/article-{i}",
            external_id=f"SKU-{i:03d}",
        )
        for i in range(n)
    ]


class FakeStaticFetcher:
    def __init__(self, markdown="# Static\n\nShort static content.", failure=None):
        self.markdown = markdown
        self.failure = failure
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        if self.failure:
            raise self.failure
        return WebDocument(
            id="doc-static",
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=request.url,
            final_url=request.url,
            title="Static Title",
            markdown=self.markdown,
            metadata={},
            acquisition_method="static_http",
            content_hash="hash-static",
            rights_status="reference_only",
            warnings=(),
            acquired_at="2026-08-01T00:00:00Z",
        )


class FakeCrawl4AIFetcher:
    def __init__(self, markdown="# Rendered\n\nMuch longer rendered content that is clearly richer than the static version.", failure=None):
        self.markdown = markdown
        self.failure = failure
        self.calls = 0

    def fetch(self, request: WebFetchRequest) -> WebDocument:
        self.calls += 1
        if self.failure:
            raise self.failure
        return WebDocument(
            id="doc-c4a",
            owner_user_id=request.owner_user_id,
            run_id=request.run_id,
            product_id=request.product_id,
            requested_url=request.url,
            final_url=request.url,
            title="Rendered Title",
            markdown=self.markdown,
            metadata={},
            acquisition_method="crawl4ai",
            content_hash="hash-c4a",
            rights_status="reference_only",
            warnings=(),
            acquired_at="2026-08-01T00:00:00Z",
        )


def write_input(tmp_path, entries):
    path = tmp_path / "pilot-input.json"
    path.write_text(json.dumps(entries), encoding="utf-8")
    return path


# --- load_entries ---


def test_load_entries_accepts_object_list():
    entries = load_entries([make_entry(), make_entry("https://example.org/other")])
    assert len(entries) == 2
    assert entries[0]["source_kind"] == "public_article"


def test_load_entries_accepts_urls_wrapper():
    entries = load_entries({"urls": [make_entry()]})
    assert len(entries) == 1


def test_load_entries_rejects_non_list_object():
    with pytest.raises(PilotInputError):
        load_entries({"url": "https://example.com/a"})


def test_load_entries_rejects_missing_fields():
    with pytest.raises(PilotInputError, match="external_product_id"):
        load_entries([{"url": "https://example.com/a", "source_kind": "manufacturer"}])


def test_load_entries_rejects_non_object_entry():
    with pytest.raises(PilotInputError):
        load_entries(["https://example.com/a"])


# --- validate_batch ---


def test_validate_batch_accepts_valid_batch():
    batch = validate_batch(make_batch(), make_policy())
    assert len(batch) == MIN_URLS
    assert all(e["source_kind"] in ALLOWED_SOURCE_KINDS for e in batch)


def test_validate_batch_rejects_too_few_urls():
    with pytest.raises(PilotInputError, match=f"{MIN_URLS}-{MAX_URLS}"):
        validate_batch([make_entry()], make_policy())


def test_validate_batch_rejects_too_many_urls():
    with pytest.raises(PilotInputError, match=f"{MIN_URLS}-{MAX_URLS}"):
        validate_batch(make_batch(MAX_URLS + 1), make_policy())


def test_validate_batch_rejects_duplicate_url():
    entries = make_batch(MIN_URLS - 1)
    entries.append(entries[0])
    with pytest.raises(PilotInputError, match="Duplicate"):
        validate_batch(entries, make_policy())


def test_validate_batch_rejects_host_limit():
    urls = [f"https://example.com/p-{i}" for i in range(MAX_URLS_PER_HOST + 1)]
    urls += [f"https://example.org/p-{i}" for i in range(MIN_URLS - len(urls))]
    batch = [make_entry(u) for u in urls]
    with pytest.raises(PilotInputError, match="per host"):
        validate_batch(batch, make_policy())


@pytest.mark.parametrize("kind", ["manufacturer", "editorial_review", "documentation", "public_article"])
def test_validate_batch_accepts_all_source_kinds(kind):
    hosts = _batch_hosts()
    batch = [
        make_entry(f"https://{hosts[i % len(hosts)]}/{kind}-{i}", kind=kind)
        for i in range(MIN_URLS)
    ]
    assert len(validate_batch(batch, make_policy())) == MIN_URLS


def test_validate_batch_rejects_invalid_source_kind():
    batch = [make_entry(f"https://example.com/x-{i}", kind="scraped_page") for i in range(MIN_URLS)]
    with pytest.raises(PilotInputError, match="Invalid source_kind"):
        validate_batch(batch, make_policy())


def test_validate_batch_rejects_blocked_host():
    batch = [make_entry(f"https://tiktok.com/@x/video/{i}") for i in range(MIN_URLS)]
    with pytest.raises(PilotInputError):
        validate_batch(batch, make_policy())


def test_validate_batch_rejects_credentials_in_url():
    batch = [make_entry(f"https://user:pass@example.com/{i}") for i in range(MIN_URLS)]
    with pytest.raises(PilotInputError):
        validate_batch(batch, make_policy())


# --- redaction ---


def test_redact_url_strips_query_fragment_and_credentials():
    raw = "https://user:secret@example.com/path/page?token=abc123&x=1#section"
    redacted = redact_url(raw)
    assert redacted == "https://example.com/path/page"
    assert "secret" not in redacted
    assert "token" not in redacted


def test_redact_url_keeps_host_and_port():
    assert redact_url("https://example.com:443/a") == "https://example.com:443/a"


def test_redact_url_keeps_path():
    assert redact_url("https://example.com/a/b/c") == "https://example.com/a/b/c"


def test_validate_batch_normalizes_fragment_and_query():
    hosts = _batch_hosts()
    batch = [
        make_entry(f"https://{hosts[i % len(hosts)]}/article-{i}?token=abc#frag")
        for i in range(MIN_URLS)
    ]
    validated = validate_batch(batch, make_policy())
    assert all("#" not in e["url"] for e in validated)


# --- runtime failure (fail-fast) ---


def test_runtime_unavailable_fails_fast(tmp_path):
    from scripts.crawl4ai_pilot import Crawl4AIUnavailable

    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher()
    c4a = FakeCrawl4AIFetcher(failure=Crawl4AIUnavailable("browser binary missing"))

    with pytest.raises(PilotRuntimeError, match="runtime unavailable"):
        run_pilot(
            input_path,
            output_path,
            policy=make_policy(),
            static_fetcher=static,
            crawl4ai_fetcher=c4a,
        )
    assert not output_path.exists()
    assert not _safe_detail("unexpected_error").startswith("Exception")


def test_render_failure_fails_fast(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher()
    c4a = FakeCrawl4AIFetcher(failure=WebFetchFailure("render boom", code="render_failed", retryable=True))

    with pytest.raises(PilotRuntimeError, match="rendering failed"):
        run_pilot(
            input_path,
            output_path,
            policy=make_policy(),
            static_fetcher=static,
            crawl4ai_fetcher=c4a,
        )
    assert not output_path.exists()


def test_per_url_non_retryable_failure_is_recorded_not_aborted(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher()
    c4a = FakeCrawl4AIFetcher(failure=WebFetchFailure("robots", code="robots_denied", retryable=False))

    summary = run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=static,
        crawl4ai_fetcher=c4a,
    )
    assert summary["crawl4ai_success_count"] == 0
    assert output_path.exists()


# --- metrics & comparison ---


def test_metrics_are_accurate_and_do_not_fabricate_html_bytes(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher(markdown="# Short")
    c4a = FakeCrawl4AIFetcher(markdown="# Long\n\n" + ("x" * 500))

    summary = run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=static,
        crawl4ai_fetcher=c4a,
    )

    assert summary["total_urls"] == MIN_URLS
    assert summary["static_success_count"] == MIN_URLS
    assert summary["crawl4ai_success_count"] == MIN_URLS
    assert summary["median_elapsed_ms"] >= 0
    assert summary["max_elapsed_ms"] >= summary["median_elapsed_ms"]

    report = json.loads(output_path.read_text(encoding="utf-8"))
    first = report["results"][0]
    assert first["crawl4ai"]["html_bytes"] is None
    assert first["static"]["html_bytes"] is None
    assert first["crawl4ai"]["markdown_bytes"] >= 0
    assert first["crawl4ai"]["markdown_chars"] == len(c4a.markdown)
    assert first["crawl4ai_improved"] is True


def test_comparison_marks_improvement_when_rendered_is_richer(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher(markdown="# Static\n\nTiny shell page.")
    c4a = FakeCrawl4AIFetcher(markdown="# Rendered\n\n" + ("Detailed rendered article. " * 40))

    summary = run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=static,
        crawl4ai_fetcher=c4a,
    )
    assert summary["crawl4ai_improved_count"] == MIN_URLS
    assert summary["crawl4ai_not_improved_count"] == 0


def test_comparison_marks_no_improvement_when_rendered_is_shorter(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher(markdown="# Static\n\nFull rich static article. " * 50)
    c4a = FakeCrawl4AIFetcher(markdown="# Rendered")

    summary = run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=static,
        crawl4ai_fetcher=c4a,
    )
    assert summary["crawl4ai_improved_count"] == 0
    assert summary["crawl4ai_not_improved_count"] == MIN_URLS


def test_report_contains_no_raw_html_or_markdown(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"
    static = FakeStaticFetcher(markdown="# Static SecretContent")
    c4a = FakeCrawl4AIFetcher(markdown="# Rendered SecretContent")

    run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=static,
        crawl4ai_fetcher=c4a,
    )
    raw = output_path.read_text(encoding="utf-8")
    assert "SecretContent" not in raw
    assert "<html" not in raw
    assert "<script" not in raw


def test_report_urls_are_redacted(tmp_path):
    hosts = _batch_hosts()
    entries = [
        make_entry(f"https://{hosts[i % len(hosts)]}/article-{i}?secret=1#frag")
        for i in range(MIN_URLS)
    ]
    input_path = write_input(tmp_path, entries)
    output_path = tmp_path / "report.json"

    run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=FakeStaticFetcher(),
        crawl4ai_fetcher=FakeCrawl4AIFetcher(),
    )
    raw = output_path.read_text(encoding="utf-8")
    assert "secret=1" not in raw
    assert "#frag" not in raw


def test_report_has_peak_memory_key(tmp_path):
    input_path = write_input(tmp_path, make_batch())
    output_path = tmp_path / "report.json"

    summary = run_pilot(
        input_path,
        output_path,
        policy=make_policy(),
        static_fetcher=FakeStaticFetcher(),
        crawl4ai_fetcher=FakeCrawl4AIFetcher(),
    )
    assert "peak_memory_mb" in summary
