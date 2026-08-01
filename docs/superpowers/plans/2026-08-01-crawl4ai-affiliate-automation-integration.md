# Crawl4AI Affiliate Automation Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure, optional Crawl4AI acquisition capability that converts explicit public web references into canonical evidence for the existing affiliate research, Google Sheets, and Telegram review flow.

**Architecture:** Hermes owns URL policy, jobs, retries, persistence, evidence, LLM routing, and projections. A static HTTP adapter handles ordinary pages first; Crawl4AI 0.9.2 is a bounded JavaScript-rendering fallback behind a Hermes-owned `WebDocumentFetcher` port. Each normalized document is persisted in SQLite V6 and reused by idempotency key before content generation.

**Tech Stack:** Python 3.10+, SQLite V6, requests, BeautifulSoup, Crawl4AI 0.9.2, Playwright Chromium, pytest, existing Hermes job/repository/application ports.

## Global Constraints

- Pin optional dependency to `crawl4ai==0.9.2`; do not add it to the base `requirements.txt`.
- Create `requirements-crawl4ai.txt`; install browser runtime explicitly with `crawl4ai-setup` and verify with `crawl4ai-doctor`.
- Support public `http` and `https` URLs only; reject credentials in URLs, localhost, private/reserved/link-local/multicast IPs, nonstandard ports, and unsafe redirects.
- Re-resolve and validate the destination before the first request and after every redirect.
- Block Shopee, TikTok, Douyin, YouTube, Facebook, Instagram, and other configured social/marketplace hosts from Crawl4AI acquisition.
- Do not accept login state, cookies, browser profiles, proxies, stealth mode, raw JavaScript, hooks, or raw Crawl4AI configuration from jobs/users.
- Do not run the Crawl4AI Docker API or expose a crawler service to LAN/Internet.
- Disable Crawl4AI LLM extraction; all model calls remain behind `HermesLLMGateway`.
- Respect `robots.txt` in Crawl4AI mode.
- Static fetch runs first; Crawl4AI runs only for a validated dynamic-page fallback.
- Limit one affiliate run to 20 web references, one host to 5 references, timeout to 30 seconds per URL, redirect count to 5, downloaded HTML to 2 MiB, and normalized Markdown to 200,000 characters.
- Persist acquisition results after each URL; a retry must reuse successful canonical documents and must not crawl them again.
- Never download third-party video, audio, screenshots, PDFs, or arbitrary files through this capability.
- No unit or acceptance test contacts the public Internet, a live browser profile, a paid LLM, Google Sheets, or Telegram.
- Existing V4 and V5 migrations are immutable; all new persistence is SQLite V6.

---

### Task 1: Web Document Domain, Port, And URL Security Policy

**Files:**
- Create: `hermes/domain/web_document.py`
- Create: `hermes/ports/web_document_fetcher.py`
- Create: `hermes/application/web_url_policy.py`
- Create: `tests/hermes/domain/test_web_document.py`
- Create: `tests/hermes/application/test_web_url_policy.py`

**Interfaces:**
- Consumes: standard-library `ipaddress`, `socket`, `urllib.parse`.
- Produces: `WebFetchRequest`, `WebDocument`, `WebFetchFailure`, `WebDocumentFetcher`, and `PublicWebUrlPolicy`.

- [ ] **Step 1: Write failing domain and SSRF-policy tests**

```python
def test_web_document_requires_bounded_public_source():
    request = WebFetchRequest(
        owner_user_id="42",
        run_id="run-1",
        product_id="product-1",
        url="https://example.com/review",
    )
    assert request.url == "https://example.com/review"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://user:pass@example.com/",
        "https://example.com:8443/",
        "https://www.shopee.vn/product/1",
        "https://www.tiktok.com/@x/video/1",
    ],
)
def test_policy_rejects_unsafe_or_disallowed_urls(url):
    policy = PublicWebUrlPolicy(resolver=fake_public_resolver)
    with pytest.raises(UnsafeWebUrl):
        policy.validate(url)


def test_policy_revalidates_redirect_destination():
    policy = PublicWebUrlPolicy(
        resolver=lambda host: {
            "public.example": ["93.184.216.34"],
            "internal.example": ["10.0.0.8"],
        }[host]
    )
    first = policy.validate("https://public.example/article")
    with pytest.raises(UnsafeWebUrl):
        policy.validate_redirect(first, "http://internal.example/admin")
```

- [ ] **Step 2: Run tests and verify missing modules**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\domain\test_web_document.py tests\hermes\application\test_web_url_policy.py -q --basetemp .pytest-crawl4ai-task1
```

Expected: collection fails because the domain and policy modules do not exist.

- [ ] **Step 3: Implement immutable contracts**

```python
@dataclass(frozen=True)
class WebFetchRequest:
    owner_user_id: str
    run_id: str
    product_id: str
    url: str
    timeout_seconds: int = 30
    max_html_bytes: int = 2 * 1024 * 1024
    max_markdown_chars: int = 200_000


@dataclass(frozen=True)
class WebDocument:
    id: str
    owner_user_id: str
    run_id: str
    product_id: str
    requested_url: str
    final_url: str
    title: str
    markdown: str
    metadata: Mapping[str, str]
    acquisition_method: Literal["static_http", "crawl4ai"]
    content_hash: str
    rights_status: Literal["reference_only"]
    warnings: tuple[str, ...]
    acquired_at: str


class WebDocumentFetcher(Protocol):
    def fetch(self, request: WebFetchRequest) -> WebDocument: ...
```

`WebFetchFailure` must carry `code`, `detail`, and `retryable`. Codes are
`unsafe_url`, `robots_denied`, `unsupported_content`, `too_large`, `timeout`,
`transport_error`, `render_failed`, and `empty_content`.

- [ ] **Step 4: Implement `PublicWebUrlPolicy`**

Validate:

- normalized `http`/`https`;
- no username/password;
- ports 80/443 only;
- hostname is not in the configured blocked suffix set;
- every resolved IPv4/IPv6 address is globally routable;
- redirect target repeats all checks;
- final normalized URL drops fragments.

The default blocked suffixes must include:

```python
(
    "shopee.vn", "shopee.com", "tiktok.com", "douyin.com",
    "youtube.com", "youtu.be", "facebook.com", "instagram.com",
)
```

- [ ] **Step 5: Run tests**

Expected: all Task 1 tests pass without DNS/network because the resolver is injected.

- [ ] **Step 6: Commit**

```powershell
git add -- hermes/domain/web_document.py hermes/ports/web_document_fetcher.py hermes/application/web_url_policy.py tests/hermes/domain/test_web_document.py tests/hermes/application/test_web_url_policy.py
git commit -m "feat: define secure web document acquisition"
```

---

### Task 2: Static HTTP Fetcher And Deterministic Normalization

**Files:**
- Create: `hermes/adapters/web/__init__.py`
- Create: `hermes/adapters/web/static_fetcher.py`
- Create: `hermes/application/web_document_normalizer.py`
- Create: `tests/hermes/adapters/web/test_static_fetcher.py`
- Create: `tests/hermes/application/test_web_document_normalizer.py`

**Interfaces:**
- Consumes: `WebFetchRequest`, `WebDocument`, `PublicWebUrlPolicy`.
- Produces: `StaticWebDocumentFetcher` and `WebDocumentNormalizer`.

- [ ] **Step 1: Write failing normalization and transport tests**

```python
def test_static_fetcher_returns_clean_bounded_markdown():
    session = FakeSession(
        html="<html><head><title>Desk lamp review</title></head>"
             "<body><nav>Menu</nav><main><h1>Desk lamp</h1><p>Three modes.</p></main>"
             "<script>alert(1)</script></body></html>"
    )
    document = StaticWebDocumentFetcher(
        session=session,
        policy=public_policy(),
    ).fetch(public_request("https://example.com/lamp"))
    assert document.acquisition_method == "static_http"
    assert document.title == "Desk lamp review"
    assert "Three modes." in document.markdown
    assert "Menu" not in document.markdown
    assert "alert(1)" not in document.markdown


def test_static_fetcher_revalidates_every_redirect():
    session = FakeRedirectSession(
        "https://public.example/start",
        location="http://127.0.0.1/admin",
    )
    with pytest.raises(WebFetchFailure, match="unsafe_url"):
        StaticWebDocumentFetcher(session=session, policy=public_policy()).fetch(
            public_request("https://public.example/start")
        )
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\adapters\web\test_static_fetcher.py tests\hermes\application\test_web_document_normalizer.py -q --basetemp .pytest-crawl4ai-task2
```

- [ ] **Step 3: Implement the fetcher**

Use an injected requests-compatible session with:

- `allow_redirects=False`;
- streamed response and explicit byte count;
- at most 5 redirects;
- `Content-Type` allowlist: `text/html`, `application/xhtml+xml`;
- timeout from request;
- no cookie jar persistence;
- a fixed Hermes user agent;
- no automatic authentication.

- [ ] **Step 4: Implement deterministic normalization**

Remove `script`, `style`, `nav`, `footer`, `form`, hidden elements, data URLs,
tracking query parameters, duplicate whitespace, and repeated navigation text.
Prefer `main`, then `article`, then `body`. Return Markdown plus allowlisted
metadata: `description`, `author`, `published_time`, `site_name`, and
`canonical_url`.

Set `dynamic_fallback_recommended=True` when:

- body text is under 300 characters;
- a root node exists but contains only loading placeholders;
- script count is high and main/article content is absent.

- [ ] **Step 5: Run focused tests and commit**

```powershell
git add -- hermes/adapters/web hermes/application/web_document_normalizer.py tests/hermes/adapters/web tests/hermes/application/test_web_document_normalizer.py
git commit -m "feat: fetch and normalize public web pages"
```

---

### Task 3: Optional Crawl4AI 0.9.2 Adapter

**Files:**
- Create: `requirements-crawl4ai.txt`
- Create: `hermes/adapters/web/crawl4ai_fetcher.py`
- Create: `scripts/setup_crawl4ai.ps1`
- Create: `tests/hermes/adapters/web/test_crawl4ai_fetcher.py`

**Interfaces:**
- Consumes: `WebDocumentFetcher`, `PublicWebUrlPolicy`, `WebDocumentNormalizer`.
- Produces: `Crawl4AIWebDocumentFetcher` and `Crawl4AIUnavailable`.

- [ ] **Step 1: Pin the optional dependency**

`requirements-crawl4ai.txt`:

```text
# Optional dynamic-page acquisition. Keep out of the base runtime.
crawl4ai==0.9.2
```

The version is pinned to the current PyPI release and Python floor verified on
2026-08-01: [Crawl4AI PyPI](https://pypi.org/project/Crawl4AI/).

- [ ] **Step 2: Write adapter tests against an injected fake crawler**

```python
def test_crawl4ai_adapter_uses_safe_non_llm_configuration():
    crawler = FakeAsyncCrawler(
        result=FakeResult(
            success=True,
            url="https://example.com/rendered",
            markdown="# Rendered\n\nUseful text",
            html="<main>Useful text</main>",
            metadata={"title": "Rendered"},
        )
    )
    document = Crawl4AIWebDocumentFetcher(
        crawler_factory=lambda browser_config: crawler,
        policy=public_policy(),
    ).fetch(public_request("https://example.com/rendered"))
    assert document.acquisition_method == "crawl4ai"
    assert crawler.browser_config.headless is True
    assert crawler.run_config.check_robots_txt is True
    assert crawler.run_config.js_code is None
    assert crawler.run_config.extraction_strategy is None
```

Also test timeout, robots denial, unsuccessful results, unsafe final redirects,
oversized Markdown, and missing optional dependency.

- [ ] **Step 3: Implement a narrow adapter**

Production configuration must be equivalent to:

```python
browser = BrowserConfig(
    headless=True,
    browser_type="chromium",
    use_persistent_context=False,
    verbose=False,
)
run = CrawlerRunConfig(
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
```

Do not set proxy, user-data directory, cookies, hooks, stealth/undetected
browser, downloads, screenshots, PDF, deep crawl, or LLM strategy. Import
Crawl4AI lazily inside the factory.

- [ ] **Step 4: Add Windows setup script**

`scripts/setup_crawl4ai.ps1` must:

1. verify it is running from the Hermes workspace;
2. install `requirements-crawl4ai.txt`;
3. run `crawl4ai-setup`;
4. run `crawl4ai-doctor`;
5. print no environment secrets.

- [ ] **Step 5: Run fake-adapter tests and commit**

No test starts Chromium or accesses the Internet.

```powershell
git add -- requirements-crawl4ai.txt hermes/adapters/web/crawl4ai_fetcher.py scripts/setup_crawl4ai.ps1 tests/hermes/adapters/web/test_crawl4ai_fetcher.py
git commit -m "feat: add optional Crawl4AI web adapter"
```

---

### Task 4: Acquisition Fallback, Limits, And Failure Classification

**Files:**
- Create: `hermes/application/web_acquisition_service.py`
- Create: `hermes/web_research_config.py`
- Create: `tests/hermes/application/test_web_acquisition_service.py`
- Create: `tests/hermes/test_web_research_config.py`

**Interfaces:**
- Consumes: static and Crawl4AI `WebDocumentFetcher` implementations.
- Produces: `WebAcquisitionService.acquire()` and `WebResearchSettings`.

- [ ] **Step 1: Write fallback and bounded-batch tests**

```python
def test_dynamic_shell_falls_back_to_crawl4ai_once():
    static = FakeFetcher(document=dynamic_shell_document())
    browser = FakeFetcher(document=rendered_document())
    service = WebAcquisitionService(static, browser, enabled=True)
    result = service.acquire(public_request("https://example.com/app"))
    assert result.acquisition_method == "crawl4ai"
    assert static.calls == 1
    assert browser.calls == 1


def test_successful_static_document_does_not_start_browser():
    browser = FailingIfCalledFetcher()
    result = WebAcquisitionService(
        FakeFetcher(document=complete_document()),
        browser,
        enabled=True,
    ).acquire(public_request("https://example.com/article"))
    assert result.acquisition_method == "static_http"


def test_batch_rejects_more_than_20_urls_or_more_than_5_per_host():
    with pytest.raises(WebBatchRejected):
        validate_web_reference_batch(twenty_one_urls())
```

- [ ] **Step 2: Implement redacted configuration**

```python
@dataclass(frozen=True)
class WebResearchSettings:
    crawl4ai_enabled: bool = False
    max_urls_per_run: int = 20
    max_urls_per_host: int = 5
    timeout_seconds: int = 30
    max_html_bytes: int = 2 * 1024 * 1024
    max_markdown_chars: int = 200_000
```

Environment names:

```text
CRAWL4AI_ENABLED=0
WEB_RESEARCH_MAX_URLS_PER_RUN=20
WEB_RESEARCH_MAX_URLS_PER_HOST=5
WEB_RESEARCH_TIMEOUT_SECONDS=30
WEB_RESEARCH_MAX_HTML_BYTES=2097152
WEB_RESEARCH_MAX_MARKDOWN_CHARS=200000
```

Hard maximums equal the Global Constraints; environment values may lower but
not raise them.

- [ ] **Step 3: Implement failure policy**

- unsafe URL, robots denial, unsupported content, too large: non-retryable;
- timeout, transport error, browser crash: retryable;
- static dynamic shell plus Crawl4AI disabled: successful document with
  `dynamic_content_not_rendered` warning, not a worker crash;
- Crawl4AI missing while enabled: configuration error before claiming a job.

- [ ] **Step 4: Run focused tests and commit**

```powershell
git add -- hermes/application/web_acquisition_service.py hermes/web_research_config.py tests/hermes/application/test_web_acquisition_service.py tests/hermes/test_web_research_config.py
git commit -m "feat: orchestrate bounded web acquisition"
```

---

### Task 5: SQLite V6 Canonical Web Evidence

**Files:**
- Create: `hermes/adapters/sqlite/schema_v6.py`
- Create: `hermes/adapters/sqlite/web_document_repository.py`
- Modify: `hermes/db.py`
- Create: `hermes/ports/web_document_repository.py`
- Create: `tests/hermes/test_web_document_repository.py`
- Modify: `tests/hermes/test_database.py`

**Interfaces:**
- Consumes: normalized `WebDocument`.
- Produces: `WebDocumentRepository`, content-addressed reuse, and run/product evidence queries.

- [ ] **Step 1: Write V5-to-V6 migration and repository tests**

Required tables:

```sql
CREATE TABLE web_documents (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT NOT NULL,
    title TEXT NOT NULL,
    markdown TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    acquisition_method TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    rights_status TEXT NOT NULL CHECK(rights_status = 'reference_only'),
    warnings_json TEXT NOT NULL,
    acquired_at TEXT NOT NULL,
    UNIQUE(owner_user_id, final_url, content_hash)
);

CREATE TABLE affiliate_run_web_documents (
    run_id TEXT NOT NULL,
    product_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY(run_id, product_id, document_id),
    FOREIGN KEY(run_id) REFERENCES affiliate_runs(id) ON DELETE CASCADE,
    FOREIGN KEY(product_id) REFERENCES affiliate_products(id) ON DELETE CASCADE,
    FOREIGN KEY(document_id) REFERENCES web_documents(id) ON DELETE CASCADE
);
```

Add indexes by owner/final URL/content hash and by run/product.

- [ ] **Step 2: Implement repository contract**

```python
class WebDocumentRepository(Protocol):
    def find_reusable(
        self, owner_user_id: str, normalized_url: str
    ) -> WebDocument | None: ...

    def save(self, document: WebDocument) -> WebDocument: ...

    def attach(
        self, run_id: str, product_id: str, document_id: str, source_kind: str
    ) -> None: ...

    def list_for_product(
        self, owner_user_id: str, run_id: str, product_id: str
    ) -> list[WebDocument]: ...
```

All reads and writes are owner-scoped through the run/product relationship.
Saving the same final URL/content hash is idempotent.

- [ ] **Step 3: Add immutable V6 migration**

Set `SCHEMA_VERSION = 6`, run `SCHEMA_V6` only when `user_version < 6`, and
add a fixture test proving a real V5 database upgrades without changing
existing affiliate products, runs, packages, outbox, or projection items.

- [ ] **Step 4: Run repository/migration tests and commit**

```powershell
git add -- hermes/adapters/sqlite/schema_v6.py hermes/adapters/sqlite/web_document_repository.py hermes/ports/web_document_repository.py hermes/db.py tests/hermes/test_web_document_repository.py tests/hermes/test_database.py
git commit -m "feat: persist canonical web evidence"
```

---

### Task 6: Affiliate Flow Integration

**Files:**
- Create: `hermes/application/affiliate_web_reference_service.py`
- Modify: `hermes/application/affiliate_run_service.py`
- Modify: `core/affiliate_research_jobs.py`
- Modify: `hermes/application/affiliate_content_service.py`
- Modify: `hermes/adapters/sqlite/affiliate_research_repository.py`
- Modify: `hermes/ports/affiliate_research.py`
- Create: `tests/hermes/application/test_affiliate_web_reference_service.py`
- Modify: `tests/hermes/application/test_affiliate_run_service.py`
- Modify: `tests/hermes/test_affiliate_research_job.py`
- Modify: `tests/hermes/application/test_affiliate_content_service.py`

**Interfaces:**
- Consumes: shortlist products, explicit `web_references`, `WebAcquisitionService`, and V6 repository.
- Produces: canonical `ReferenceMetadata` and evidence-bound research briefs/packages.

- [ ] **Step 1: Define the job payload**

Add a separate field; do not overload TikTok `reference_urls`:

```json
{
  "web_references": [
    {
      "external_product_id": "SKU-123",
      "url": "https://manufacturer.example/product/specifications",
      "source_kind": "manufacturer"
    },
    {
      "external_product_id": "SKU-123",
      "url": "https://review.example/desk-lamp-review",
      "source_kind": "editorial_review"
    }
  ]
}
```

Allowed `source_kind` values are `manufacturer`, `editorial_review`,
`documentation`, and `public_article`. Reject unknown product IDs, duplicate
URLs in a run, and URLs for products outside the current shortlist.

- [ ] **Step 2: Write idempotency and owner-scope tests**

```python
def test_web_references_are_acquired_once_and_bound_to_product():
    service, repository, acquisition = build_service()
    first = service.collect("42", "run-1", shortlisted_products(), web_inputs())
    second = service.collect("42", "run-1", shortlisted_products(), web_inputs())
    assert len(first) == 2
    assert second == first
    assert acquisition.calls == 2
    assert all(item.rights_status == "reference_only" for item in first)


def test_reference_for_other_owner_or_non_shortlisted_product_is_rejected():
    with pytest.raises(WebReferenceRejected):
        service.collect("99", "run-1", shortlisted_products(), web_inputs())
```

- [ ] **Step 3: Implement collection and persistence**

For each accepted input:

1. validate product association and URL policy;
2. reuse an attached or owner-reusable document when present;
3. static fetch, then optional Crawl4AI fallback;
4. save and attach after each successful URL;
5. convert it to `ReferenceMetadata` with `source_type="public_web_document"`,
   canonical `source_url`, `content_hash`, and `rights_status="reference_only"`;
6. persist the reference through `AffiliateResearchRepository`.

A process crash after one URL must reuse that URL and continue at the next.

- [ ] **Step 4: Bind web evidence to content generation**

`AffiliateContentService` must:

- include normalized web evidence in `ResearchBrief.verified_specs`,
  strengths, limitations, and unverified claims;
- keep each factual claim bound to the canonical web document/reference ID;
- reject claim URLs that are not among product, TikTok metadata, or web
  documents attached to the same owner/run/product;
- keep source wording out of generated hook/script through the existing
  overlap gate.

- [ ] **Step 5: Wire production composition**

`build_affiliate_research_job_handler()` constructs web acquisition only after
validated settings load. With `CRAWL4AI_ENABLED=0`, static public web
references still work and dynamic pages receive a warning. With it enabled,
missing Crawl4AI/browser setup fails before a job is claimed.

- [ ] **Step 6: Run focused tests and commit**

```powershell
git add -- hermes/application/affiliate_web_reference_service.py hermes/application/affiliate_run_service.py core/affiliate_research_jobs.py hermes/application/affiliate_content_service.py hermes/adapters/sqlite/affiliate_research_repository.py hermes/ports/affiliate_research.py tests/hermes/application/test_affiliate_web_reference_service.py tests/hermes/application/test_affiliate_run_service.py tests/hermes/test_affiliate_research_job.py tests/hermes/application/test_affiliate_content_service.py
git commit -m "feat: add web evidence to affiliate research"
```

---

### Task 7: Google Sheets Projection, Monitoring, And Recovery

**Files:**
- Modify: `hermes/adapters/google/sheets_projection.py`
- Modify: `hermes/adapters/sqlite/affiliate_research_repository.py`
- Modify: `tests/hermes/adapters/test_google_sheets_projection.py`
- Create: `tests/hermes/test_crawl4ai_recovery.py`

**Interfaces:**
- Consumes: V6 web-document queries and existing run/projection state.
- Produces: `Web Evidence` tab and crash-safe per-document recovery.

- [ ] **Step 1: Write projection tests**

Add a seventh tab, `Web Evidence`, with:

```text
stable_id
run_id
product_id
source_kind
title
final_url
acquisition_method
content_hash
rights_status
warnings
acquired_at
operator_notes
```

`operator_notes` and `custom_*` columns remain editable and survive resync.
Markdown body is not projected to Sheets; SQLite remains canonical.

- [ ] **Step 2: Write crash/retry tests**

Simulate a crash:

- after first of three documents is saved;
- after static shell detection but before Crawl4AI;
- after all documents are saved but before content generation.

On retry, successful documents are not fetched again, pending documents
continue, and the same run/package IDs are reused.

- [ ] **Step 3: Add run counters and error visibility**

Persist and project:

```text
web_requested
web_static_succeeded
web_crawl4ai_succeeded
web_reused
web_failed_retryable
web_failed_permanent
web_robots_denied
```

Errors may contain URL host/path and failure code, but never query secrets,
cookies, browser state, raw HTML, or Markdown.

- [ ] **Step 4: Run tests and commit**

```powershell
git add -- hermes/adapters/google/sheets_projection.py hermes/adapters/sqlite/affiliate_research_repository.py tests/hermes/adapters/test_google_sheets_projection.py tests/hermes/test_crawl4ai_recovery.py
git commit -m "feat: project and recover web evidence"
```

---

### Task 8: Offline Acceptance, Pilot Tool, And Operations Documentation

**Files:**
- Create: `scripts/crawl4ai_pilot.py`
- Create: `tests/hermes/test_crawl4ai_affiliate_acceptance.py`
- Modify: `docs/affiliate-product-research-user-guide.md`
- Create: `docs/runbooks/crawl4ai-web-research.md`

**Interfaces:**
- Consumes: all Tasks 1-7.
- Produces: offline acceptance, controlled 10-20 URL pilot, and operator guide.

- [ ] **Step 1: Write offline acceptance**

The test must:

- create a temporary V5 database and migrate to V6;
- import 100 authorized CSV products;
- attach three public web-reference fixtures to shortlisted products;
- make one fixture succeed statically and one require fake Crawl4AI;
- run the same idempotency key twice;
- assert no fetch repeats on retry;
- assert evidence-bound briefs/packages;
- assert seven Google tabs and pending Telegram packages;
- patch public requests, real Crawl4AI, browser launch, LLM, Google, and
  Telegram constructors to raise if called.

- [ ] **Step 2: Create a controlled pilot command**

```powershell
.\.venv\Scripts\python.exe scripts\crawl4ai_pilot.py `
  --input .\scratch\crawl4ai-pilot-urls.json `
  --output .\scratch\crawl4ai-pilot-report.json
```

The input accepts 10-20 explicit public URLs. The command writes only metrics
and redacted metadata:

- success/failure code;
- static versus Crawl4AI method;
- elapsed milliseconds;
- HTML bytes and Markdown characters;
- warning count;
- peak process memory if available.

It must not write raw HTML/Markdown to the report.

- [ ] **Step 3: Document installation and operation**

The runbook must cover:

- optional installation and Chromium setup;
- environment variables and hard limits;
- accepted/rejected URL classes;
- job `web_references` format;
- static-first/Crawl4AI-fallback behavior;
- robots, SSRF and redirect controls;
- SQLite evidence ownership;
- Google `Web Evidence` tab;
- retry/recovery and cache invalidation;
- uninstall/disable procedure;
- security upgrade checklist for Crawl4AI.

- [ ] **Step 4: Run the final focused gate**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\hermes\domain\test_web_document.py `
  tests\hermes\application\test_web_url_policy.py `
  tests\hermes\adapters\web `
  tests\hermes\application\test_web_document_normalizer.py `
  tests\hermes\application\test_web_acquisition_service.py `
  tests\hermes\test_web_research_config.py `
  tests\hermes\test_web_document_repository.py `
  tests\hermes\application\test_affiliate_web_reference_service.py `
  tests\hermes\test_crawl4ai_recovery.py `
  tests\hermes\test_crawl4ai_affiliate_acceptance.py `
  tests\hermes\test_affiliate_research_acceptance.py `
  tests\hermes\test_affiliate_final_review.py `
  tests\hermes\test_database.py `
  -q --basetemp .pytest-crawl4ai-final
```

Expected: all tests pass with no public network/browser/paid calls.

- [ ] **Step 5: Run a manual pilot gate**

Only after the offline gate passes and the operator explicitly supplies
approved URLs:

1. install the optional dependency;
2. run `scripts/crawl4ai_pilot.py` on 10-20 public URLs;
3. compare static and rendered success rate, median latency, peak memory, and
   normalized output quality;
4. enable production only when browser crashes are zero, no security-policy
   bypass occurs, and rendered pages materially improve over static fetch.

- [ ] **Step 6: Commit**

```powershell
git add -- scripts/crawl4ai_pilot.py tests/hermes/test_crawl4ai_affiliate_acceptance.py docs/affiliate-product-research-user-guide.md docs/runbooks/crawl4ai-web-research.md
git commit -m "docs: complete Crawl4AI affiliate rollout"
```

---

## Final Verification Gate

- [ ] Confirm Crawl4AI is optional and Hermes starts with it uninstalled.
- [ ] Confirm no base dependency or protected user configuration file was overwritten.
- [ ] Confirm V5-to-V6 migration preserves all affiliate data and V4/V5 files are unchanged.
- [ ] Confirm every redirect is SSRF-validated and blocked hosts never reach either adapter.
- [ ] Confirm static fetch prevents unnecessary Chromium startup.
- [ ] Confirm Crawl4AI runs without LLM extraction, proxy, stealth, hooks, login state, downloads, screenshots, PDF, or deep crawl.
- [ ] Confirm a retry after each acquisition checkpoint does not fetch completed URLs again.
- [ ] Confirm every web claim points to owner/run/product-scoped canonical evidence.
- [ ] Confirm Google Sheets projects metadata only and preserves editable columns.
- [ ] Confirm disabled mode and all offline tests work without browser/network.
- [ ] Run task-scoped reviews after each task and one whole-branch review before merge.

## Rollout Decision

Start with `CRAWL4AI_ENABLED=0`. Static web acquisition and all persistence may
ship first. Enable Crawl4AI only after the 10-20 URL pilot demonstrates a
material improvement on approved JavaScript-heavy pages without browser
instability or policy bypass.

Do not use the adapter to crawl Shopee/TikTok, bypass anti-bot controls, reuse
authenticated browser state, or download media. Existing TikTok oEmbed,
video resolver, `yt-dlp`, Whisper, job queue, SQLite authority, and
`HermesLLMGateway` remain unchanged.
