# Affiliate Product Research Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an API-first Hermes pipeline that imports 100-200 authorized Shopee Affiliate candidates, ranks technology accessories, produces 5-10 original research/content packages, projects them to Google Sheets, and collects Telegram review decisions.

**Architecture:** Add a focused affiliate-research domain beside the existing knowledge domain. `hermes.db.Database` remains the canonical SQLite entry point, `hermes.jobs.JobRepository` remains the operational queue, and external systems are isolated behind source, model, projection, and notification ports. CSV/manual import is the first working source; authorized Product Feed/API implementations can use the same contract later without changing scoring or content planning.

**Tech Stack:** Python 3.10+, SQLite, standard-library CSV/JSON/dataclasses, `requests`, existing `HermesLLMGateway`, `google-api-python-client`, `google-auth`, `python-telegram-bot`, `pytest`/`unittest`.

## Global Constraints

- Research only: do not buy, render, publish, or schedule videos.
- Do not scrape Shopee or TikTok search/product/account pages.
- Do not download or reuse third-party video/audio without documented rights.
- General product price range is VND 200,000-500,000.
- Keyboard maximum price is VND 1,500,000.
- Process 100-200 candidates, shortlist 15-25, and produce 5-10 packages per run.
- Product scoring weights are sales 45, visual potential 30, price fit 10, rating/shop confidence 8, commission 5, and novelty 2.
- SQLite is canonical; Google Sheets and Telegram are retryable projections.
- Never store credentials, cookies, tokens, or service-account contents in SQLite, Sheets, logs, artifacts, or tests.
- Tests must not call paid models or live Shopee, TikTok, Google, or Telegram services.
- Preserve unrelated worktree changes and modify only files listed by the active task.

---

## File Map

### Domain And Ports

- `hermes/domain/affiliate_research.py`: immutable product, score, reference, package, lifecycle, and policy types.
- `hermes/ports/affiliate_research.py`: repository, source, content-model, sheet, and review-delivery protocols.

### Application Services

- `hermes/application/affiliate_catalog_service.py`: import, normalization, eligibility, snapshots, scoring, and shortlist orchestration.
- `hermes/application/affiliate_content_service.py`: reference-bound research, angle generation, package validation, and revision.
- `hermes/application/affiliate_review_service.py`: owner-scoped approve/revise/reject transitions.
- `hermes/application/affiliate_run_service.py`: one complete canonical research run and projection checkpoints.

### Adapters

- `hermes/adapters/sqlite/affiliate_research_repository.py`: canonical persistence and atomic lifecycle changes.
- `hermes/adapters/affiliate/shopee_csv.py`: authorized Product Feed/user-export CSV adapter.
- `hermes/adapters/affiliate/manual_source.py`: explicit manual candidates.
- `hermes/adapters/tiktok/public_reference.py`: allowlisted TikTok oEmbed metadata only.
- `hermes/adapters/model/affiliate_content_gateway.py`: structured prompts through `HermesLLMGateway`.
- `hermes/adapters/google/sheets_projection.py`: idempotent six-tab Google Sheets projection.
- `hermes/adapters/telegram/affiliate_review.py`: safe message rendering and review callback parsing.

### Runtime Integration

- `core/affiliate_research_jobs.py`: job payload construction and handler wiring.
- `core/job_watcher.py`: dispatch the new job type before the legacy media path.
- `telegram_bot.py`: authorized affiliate review callbacks and revision command.
- `config.py`, `.env.example`, `requirements.txt`: non-secret adapter configuration.
- `docs/runbooks/affiliate-product-research.md`: setup and operating procedure.

### Tests

- `tests/hermes/domain/test_affiliate_research.py`
- `tests/hermes/test_affiliate_research_repository.py`
- `tests/hermes/adapters/test_shopee_affiliate_csv.py`
- `tests/hermes/adapters/test_tiktok_public_reference.py`
- `tests/hermes/application/test_affiliate_catalog_service.py`
- `tests/hermes/application/test_affiliate_content_service.py`
- `tests/hermes/application/test_affiliate_run_service.py`
- `tests/hermes/adapters/test_google_sheets_projection.py`
- `tests/hermes/test_telegram_affiliate_review.py`
- `tests/hermes/test_affiliate_research_job.py`
- `tests/hermes/test_affiliate_research_acceptance.py`

---

### Task 1: Domain Model, Eligibility, And Explainable Scoring

**Files:**
- Create: `hermes/domain/affiliate_research.py`
- Create: `hermes/ports/affiliate_research.py`
- Create: `tests/hermes/domain/test_affiliate_research.py`

**Interfaces:**
- Produces: `ProductCandidate`, `AffiliateProduct`, `ProductSnapshot`, `ScoreBreakdown`, `EligibilityDecision`, `ReferenceMetadata`, `ContentPackage`, `PackageStatus`, `ProductPolicy`, `ProductScorer`.
- Produces: `AffiliateResearchRepository`, `ProductSource`, `ContentPackageGateway`, `SheetsProjection`, and `ReviewDelivery` protocols.

- [ ] **Step 1: Write failing policy and scoring tests**

```python
from hermes.domain.affiliate_research import AffiliateProduct, ProductPolicy, ProductScorer


def product(**overrides):
    values = {
        "id": "shopee:101",
        "owner_user_id": "42",
        "platform": "shopee",
        "external_product_id": "101",
        "name": "RGB mouse",
        "category": "mouse",
        "price_vnd": 350_000,
        "sold_count": 12_000,
        "rating": 4.8,
        "review_count": 1_200,
        "commission_rate": 0.12,
        "shop_name": "Example",
        "product_url": "https://shopee.vn/product/101",
        "image_urls": ("https://example.com/mouse.jpg",),
        "visual_signals": ("light", "visible_problem_solution", "multiple_scenes"),
        "source_type": "affiliate_csv",
        "source_url": "",
        "authorization_scope": "user_export",
        "rights_status": "affiliate_reference",
        "content_hash": "abc",
        "created_at": "2026-08-01T00:00:00+00:00",
        "updated_at": "2026-08-01T00:00:00+00:00",
    }
    values.update(overrides)
    return AffiliateProduct(**values)


def test_price_policy_has_keyboard_exception():
    policy = ProductPolicy()
    assert policy.evaluate(product(price_vnd=600_000, category="mouse")).eligible is False
    assert policy.evaluate(product(price_vnd=1_400_000, category="keyboard")).eligible is True
    assert policy.evaluate(product(price_vnd=1_600_000, category="keyboard")).eligible is False


def test_score_is_explainable_and_totals_one_hundred():
    result = ProductScorer().score(
        product(),
        category_sales=(100, 12_000),
        previous_sold_count=11_500,
        seen_before=False,
    )
    assert result.total == sum(result.components.values())
    assert set(result.components) == {
        "sales", "visual", "price", "trust", "commission", "novelty"
    }
    assert result.total <= 100
    assert result.reason
    assert result.confidence == "high"


def test_missing_history_lowers_confidence_without_inventing_growth():
    result = ProductScorer().score(
        product(),
        category_sales=(100, 12_000),
        previous_sold_count=None,
        seen_before=True,
    )
    assert result.growth_rate is None
    assert result.confidence == "medium"
```

- [ ] **Step 2: Run the tests and confirm the missing module failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/domain/test_affiliate_research.py -q
```

Expected: collection fails with `ModuleNotFoundError: hermes.domain.affiliate_research`.

- [ ] **Step 3: Implement immutable types and pure policies**

Implement these exact public shapes:

```python
@dataclass(frozen=True)
class AffiliateProduct:
    id: str
    owner_user_id: str
    platform: str
    external_product_id: str
    name: str
    category: str
    price_vnd: int
    sold_count: int | None
    rating: float | None
    review_count: int | None
    commission_rate: float | None
    shop_name: str
    product_url: str
    image_urls: tuple[str, ...]
    visual_signals: tuple[str, ...]
    source_type: str
    source_url: str
    authorization_scope: str
    rights_status: str
    content_hash: str
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    components: dict[str, float]
    reason: str
    confidence: str
    growth_rate: float | None


class PackageStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REVISION_REQUESTED = "revision_requested"
    REJECTED = "rejected"
```

Implement `ProductPolicy.evaluate(product) -> EligibilityDecision` with the
agreed niche and price rules. Implement `ProductScorer.score(...)` with
component caps `45/30/10/8/5/2`, log-scaled category sales, optional observed
growth, explicit visual-signal weights, and confidence reduction when sales
history or evidence is absent.

Define protocols with these signatures:

```python
class ProductSource(Protocol):
    def load(self, owner_user_id: str) -> list[ProductCandidate]: ...


class ContentPackageGateway(Protocol):
    def generate(self, product: AffiliateProduct, references: Sequence[ReferenceMetadata]) -> ContentPackage: ...


class SheetsProjection(Protocol):
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult: ...


class ReviewDelivery(Protocol):
    def send_pending(self, owner_user_id: str, package_ids: Sequence[str]) -> ProjectionResult: ...
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/domain/test_affiliate_research.py -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 1**

```powershell
git add hermes/domain/affiliate_research.py hermes/ports/affiliate_research.py tests/hermes/domain/test_affiliate_research.py
git commit -m "feat: define affiliate research domain"
```

---

### Task 2: SQLite Schema V3 And Canonical Repository

**Files:**
- Modify: `hermes/db.py`
- Create: `hermes/adapters/sqlite/affiliate_research_repository.py`
- Create: `tests/hermes/test_affiliate_research_repository.py`
- Modify: `tests/hermes/test_database.py`

**Interfaces:**
- Consumes: domain records from Task 1.
- Produces: `SQLiteAffiliateResearchRepository` implementing the repository protocol.
- Produces: schema version `3` with seven affiliate tables and stable uniqueness constraints.

- [ ] **Step 1: Write failing migration and repository tests**

```python
def test_initialize_creates_affiliate_schema(tmp_path):
    from hermes.db import Database

    database = Database(tmp_path / "hermes.db")
    database.initialize()
    with database.connect() as connection:
        names = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        version = connection.execute("PRAGMA user_version").fetchone()[0]
    assert version == 3
    assert {
        "affiliate_products",
        "affiliate_product_snapshots",
        "affiliate_references",
        "affiliate_content_ideas",
        "affiliate_content_packages",
        "affiliate_approval_events",
        "affiliate_research_runs",
    }.issubset(names)


def test_upsert_and_snapshot_are_idempotent(database, product):
    from hermes.adapters.sqlite.affiliate_research_repository import (
        SQLiteAffiliateResearchRepository,
    )

    repository = SQLiteAffiliateResearchRepository(database)
    first = repository.upsert_product(product)
    second = repository.upsert_product(product)
    repository.record_snapshot(first.id, "2026-08-01", product)
    repository.record_snapshot(first.id, "2026-08-01", product)

    assert first.id == second.id
    assert len(repository.list_products("42")) == 1
    assert len(repository.list_snapshots(first.id)) == 1
```

Add tests for append-only approval events, owner-scoped lookup, revision
preservation, valid lifecycle transitions, and rollback on an invalid
transition.

- [ ] **Step 2: Run tests and verify schema/repository failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_database.py tests/hermes/test_affiliate_research_repository.py -q
```

Expected: schema version remains `2` and repository import fails.

- [ ] **Step 3: Add schema V3**

Set `SCHEMA_VERSION = 3`, add `SCHEMA_V3`, and apply it only when
`current_version < 3`. Use:

```sql
CREATE TABLE IF NOT EXISTS affiliate_products (
    id TEXT PRIMARY KEY,
    owner_user_id TEXT NOT NULL,
    platform TEXT NOT NULL,
    external_product_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    price_vnd INTEGER NOT NULL CHECK(price_vnd >= 0),
    sold_count INTEGER,
    rating REAL,
    review_count INTEGER,
    commission_rate REAL,
    shop_name TEXT NOT NULL DEFAULT '',
    product_url TEXT NOT NULL DEFAULT '',
    image_urls_json TEXT NOT NULL DEFAULT '[]',
    visual_signals_json TEXT NOT NULL DEFAULT '[]',
    source_type TEXT NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    authorization_scope TEXT NOT NULL,
    rights_status TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    eligibility_status TEXT NOT NULL DEFAULT 'candidate',
    score REAL,
    score_json TEXT NOT NULL DEFAULT '{}',
    score_reason TEXT NOT NULL DEFAULT '',
    score_confidence TEXT NOT NULL DEFAULT 'low',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(owner_user_id, platform, external_product_id)
);
```

Add the other six tables with foreign keys, `UNIQUE(product_id, snapshot_date)`
for snapshots, `UNIQUE(owner_user_id, id)` for packages, and indexes for owner,
run, status, score, and product relationships. Approval events and snapshots
are append-only at repository level.

- [ ] **Step 4: Implement repository transactions and row mappers**

Use `Database.transaction(immediate=True)` for upsert, package revision, and
lifecycle operations. Expose:

```python
def upsert_product(self, product: AffiliateProduct) -> AffiliateProduct: ...
def record_snapshot(self, product_id: str, snapshot_date: str, product: AffiliateProduct) -> ProductSnapshot: ...
def list_products(self, owner_user_id: str, run_id: str | None = None) -> list[AffiliateProduct]: ...
def list_snapshots(self, product_id: str) -> list[ProductSnapshot]: ...
def save_score(self, product_id: str, score: ScoreBreakdown, eligibility_status: str) -> None: ...
def save_reference(self, reference: ReferenceMetadata) -> ReferenceMetadata: ...
def save_ideas(self, product_id: str, run_id: str, ideas: Sequence[ContentIdea]) -> list[ContentIdea]: ...
def save_package(self, package: ContentPackage) -> ContentPackage: ...
def get_package(self, package_id: str, owner_user_id: str) -> ContentPackage | None: ...
def transition_package(self, package_id: str, owner_user_id: str, action: str, reason: str) -> ContentPackage: ...
def create_run(self, run_id: str, owner_user_id: str, idempotency_key: str) -> dict: ...
def finish_run(self, run_id: str, counters: dict[str, int]) -> dict: ...
def projection_rows(self, owner_user_id: str, run_id: str) -> dict[str, list[dict]]: ...
```

- [ ] **Step 5: Run focused persistence tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_database.py tests/hermes/test_affiliate_research_repository.py -q
```

Expected: all tests pass and temporary databases report `user_version = 3`.

- [ ] **Step 6: Commit Task 2**

```powershell
git add hermes/db.py hermes/adapters/sqlite/affiliate_research_repository.py tests/hermes/test_database.py tests/hermes/test_affiliate_research_repository.py
git commit -m "feat: persist affiliate research state"
```

---

### Task 3: Authorized Shopee CSV And Manual Import

**Files:**
- Create: `hermes/adapters/affiliate/__init__.py`
- Create: `hermes/adapters/affiliate/shopee_csv.py`
- Create: `hermes/adapters/affiliate/manual_source.py`
- Create: `hermes/application/affiliate_catalog_service.py`
- Create: `tests/hermes/adapters/test_shopee_affiliate_csv.py`
- Create: `tests/hermes/application/test_affiliate_catalog_service.py`
- Create: `tests/fixtures/shopee_affiliate_products.csv`

**Interfaces:**
- Consumes: `ProductSource`, domain policy/scorer, and repository.
- Produces: `ShopeeAffiliateCsvSource`, `ManualProductSource`, `AffiliateCatalogService.import_candidates(...)`, and `AffiliateCatalogService.score_and_shortlist(...)`.

- [ ] **Step 1: Write failing CSV normalization tests**

```python
def test_csv_adapter_normalizes_vietnamese_money_and_aliases(tmp_path):
    from hermes.adapters.affiliate.shopee_csv import ShopeeAffiliateCsvSource

    path = tmp_path / "feed.csv"
    path.write_text(
        "item_id,product_name,category,price,sold,rating,commission,product_link,image\n"
        "101,RGB Mouse,mouse,\"349.000 đ\",\"12,3k\",4.8,12%,https://shopee.vn/a,https://img/a.jpg\n",
        encoding="utf-8",
    )
    rows = ShopeeAffiliateCsvSource(path).load("42")
    assert rows[0].external_product_id == "101"
    assert rows[0].price_vnd == 349_000
    assert rows[0].sold_count == 12_300
    assert rows[0].commission_rate == 0.12
    assert rows[0].authorization_scope == "user_export"


def test_invalid_rows_are_reported_without_dropping_valid_rows(tmp_path):
    source = make_source_with_one_valid_and_one_invalid_row(tmp_path)
    batch = source.load_batch("42")
    assert len(batch.candidates) == 1
    assert batch.errors[0].row_number == 3
```

- [ ] **Step 2: Run tests and verify missing adapter failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_shopee_affiliate_csv.py tests/hermes/application/test_affiliate_catalog_service.py -q
```

Expected: collection fails because adapter and service modules do not exist.

- [ ] **Step 3: Implement bounded parsing and provenance**

Use `csv.DictReader`, a fixed alias map, UTF-8/UTF-8-SIG decoding, a 10 MB file
limit, a 5,000-row limit, and deterministic SHA-256 hashes. Do not inspect
browser cookies or call Shopee. Required normalized fields are product ID,
name, category, price, and product URL. Missing sales data is allowed but
reduces score confidence.

Implement:

```python
class ShopeeAffiliateCsvSource:
    def __init__(self, path: str | Path, authorization_scope: str = "user_export"): ...
    def load(self, owner_user_id: str) -> list[ProductCandidate]: ...
    def load_batch(self, owner_user_id: str) -> ImportBatch: ...


class ManualProductSource:
    def __init__(self, candidates: Sequence[ProductCandidate]): ...
    def load(self, owner_user_id: str) -> list[ProductCandidate]: ...
```

- [ ] **Step 4: Implement catalog import, deduplication, snapshots, and shortlist**

```python
class AffiliateCatalogService:
    def import_candidates(
        self,
        source: ProductSource,
        *,
        owner_user_id: str,
        run_id: str,
        snapshot_date: str,
    ) -> ImportSummary: ...

    def score_and_shortlist(
        self,
        *,
        owner_user_id: str,
        run_id: str,
        minimum: int = 15,
        maximum: int = 25,
    ) -> list[RankedProduct]: ...
```

The import must continue after row-level validation failures, use repository
upsert/snapshot methods, and return imported/updated/rejected/error counters.
Shortlisting must never include ineligible products and must be deterministic
for equal scores using product ID as the final tie-breaker.

- [ ] **Step 5: Run focused import tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_shopee_affiliate_csv.py tests/hermes/application/test_affiliate_catalog_service.py -q
```

Expected: all tests pass, including a generated 200-row fixture import and
same-file re-import.

- [ ] **Step 6: Commit Task 3**

```powershell
git add hermes/adapters/affiliate hermes/application/affiliate_catalog_service.py tests/hermes/adapters/test_shopee_affiliate_csv.py tests/hermes/application/test_affiliate_catalog_service.py tests/fixtures/shopee_affiliate_products.csv
git commit -m "feat: import and rank Shopee affiliate products"
```

---

### Task 4: Safe TikTok Reference Metadata

**Files:**
- Create: `hermes/adapters/tiktok/__init__.py`
- Create: `hermes/adapters/tiktok/public_reference.py`
- Create: `tests/hermes/adapters/test_tiktok_public_reference.py`

**Interfaces:**
- Consumes: `ReferenceMetadata`.
- Produces: `TikTokPublicReferenceAdapter.fetch(url, owner_user_id, product_id)`.

- [ ] **Step 1: Write failing allowlist and no-download tests**

```python
def test_only_tiktok_public_video_urls_are_accepted():
    adapter = TikTokPublicReferenceAdapter(get_json=lambda *_args, **_kwargs: {})
    with pytest.raises(ValueError, match="TikTok"):
        adapter.fetch("https://example.com/video/1", "42", "shopee:101")


def test_oembed_metadata_is_reference_only():
    calls = []

    def get_json(url, **kwargs):
        calls.append((url, kwargs))
        return {
            "title": "Desk setup idea",
            "author_name": "creator",
            "author_url": "https://www.tiktok.com/@creator",
            "thumbnail_url": "https://example.com/thumb.jpg",
        }

    reference = TikTokPublicReferenceAdapter(get_json=get_json).fetch(
        "https://www.tiktok.com/@creator/video/123", "42", "shopee:101"
    )
    assert calls[0][0] == "https://www.tiktok.com/oembed"
    assert reference.rights_status == "reference_only"
    assert reference.media_local_path == ""
```

- [ ] **Step 2: Run tests and verify missing adapter failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_tiktok_public_reference.py -q
```

Expected: collection fails because `public_reference.py` does not exist.

- [ ] **Step 3: Implement oEmbed-only metadata retrieval**

Validate HTTPS URLs against `tiktok.com`, `www.tiktok.com`, and `vm.tiktok.com`.
Resolve at most one redirect with a five-second timeout, then call only
`https://www.tiktok.com/oembed`. Limit response size and accepted text lengths.
Do not invoke `yt-dlp`, the localhost crawler, video fetcher, or binary download.

Return:

```python
ReferenceMetadata(
    id=stable_reference_id(product_id, normalized_url),
    owner_user_id=owner_user_id,
    product_id=product_id,
    platform="tiktok",
    source_url=normalized_url,
    title=payload.get("title", ""),
    author_name=payload.get("author_name", ""),
    author_url=payload.get("author_url", ""),
    thumbnail_url=payload.get("thumbnail_url", ""),
    caption=payload.get("title", ""),
    embed_html=payload.get("html", ""),
    authorization_scope="public_oembed",
    rights_status="reference_only",
    media_local_path="",
    collected_at=utc_now(),
)
```

- [ ] **Step 4: Run focused tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_tiktok_public_reference.py -q
```

Expected: all tests pass and no test performs a network request.

- [ ] **Step 5: Commit Task 4**

```powershell
git add hermes/adapters/tiktok tests/hermes/adapters/test_tiktok_public_reference.py
git commit -m "feat: add safe TikTok reference metadata"
```

---

### Task 5: Structured Research Briefs And Content Packages

**Files:**
- Create: `hermes/adapters/model/__init__.py`
- Create: `hermes/adapters/model/affiliate_content_gateway.py`
- Create: `hermes/application/affiliate_content_service.py`
- Create: `tests/hermes/application/test_affiliate_content_service.py`

**Interfaces:**
- Consumes: `HermesLLMGateway`, products, references, repository.
- Produces: `AffiliateContentGateway.generate(...)` and `AffiliateContentService.create_packages(...)`.

- [ ] **Step 1: Write failing structured-package tests**

```python
def test_content_service_rejects_unsourced_claims(repository, product):
    gateway = FakeContentGateway(
        payload={
            "audience": "office_worker",
            "angle": "Desk comfort",
            "angle_reason": "Visible setup improvement",
            "hook": "A shorter original hook",
            "script": "This mouse has an unverified 1 ms latency.",
            "duration_seconds": 45,
            "storyboard": [{"start": 0, "end": 5, "visual": "Mouse on desk"}],
            "ai_prompts": ["Modern office desk with space reserved for supplied product image"],
            "voiceover_plan": "Vietnamese neutral voice",
            "text_overlays": ["Gọn bàn làm việc"],
            "claims": [{"text": "1 ms latency", "evidence_url": ""}],
            "warnings": [],
        }
    )
    service = AffiliateContentService(repository, gateway)
    with pytest.raises(ContentValidationError, match="evidence"):
        service.create_packages("42", "run-1", [product], per_run=1)


def test_package_is_original_and_keeps_reference_rights(repository, product, reference):
    service = AffiliateContentService(repository, valid_fake_gateway())
    packages = service.create_packages("42", "run-1", [product], [reference], per_run=1)
    assert 30 <= packages[0].duration_seconds <= 90
    assert packages[0].status.value == "pending_review"
    assert packages[0].asset_rights[reference.id] == "reference_only"
    assert packages[0].claims[0]["evidence_url"]
```

- [ ] **Step 2: Run tests and verify missing service/gateway failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/application/test_affiliate_content_service.py -q
```

Expected: collection fails because the modules do not exist.

- [ ] **Step 3: Implement the model adapter**

Use `HermesLLMGateway.structured` with top-level schema:

```python
PACKAGE_SCHEMA = {
    "audience": str,
    "angle": str,
    "angle_reason": str,
    "hook": str,
    "script": str,
    "duration_seconds": int,
    "storyboard": list,
    "ai_prompts": list,
    "voiceover_plan": str,
    "text_overlays": list,
    "claims": list,
    "warnings": list,
}
```

The system prompt must label product/reference input as untrusted data, require
Vietnamese output, forbid copied wording and first-hand-use claims, and require
an evidence URL for every factual claim. Use task type `script`. Do not call the
model when a fake gateway is injected.

- [ ] **Step 4: Implement deterministic validation and revision**

`AffiliateContentService` must:

- create and persist three to five `ContentIdea` records per shortlisted
  product before selecting package outputs;
- cap packages to `5..10`;
- validate audience, duration, storyboard ordering, claims, rights, and required
  fields;
- reject exact or high-overlap hooks/scripts already stored for the owner;
- persist immutable revisions;
- generate a revision from saved package plus human feedback without mutating
  the old revision.

Expose:

```python
def create_packages(
    self,
    owner_user_id: str,
    run_id: str,
    products: Sequence[AffiliateProduct],
    references: Sequence[ReferenceMetadata] = (),
    *,
    per_run: int = 10,
) -> list[ContentPackage]: ...

def revise_package(
    self,
    package_id: str,
    owner_user_id: str,
    feedback: str,
) -> ContentPackage: ...
```

- [ ] **Step 5: Run focused content tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/application/test_affiliate_content_service.py tests/hermes/test_llm_gateway.py -q
```

Expected: all tests pass with fake model responses only.

- [ ] **Step 6: Commit Task 5**

```powershell
git add hermes/adapters/model hermes/application/affiliate_content_service.py tests/hermes/application/test_affiliate_content_service.py
git commit -m "feat: generate evidence-bound affiliate content"
```

---

### Task 6: Canonical Run Service And Existing Job Queue Integration

**Files:**
- Create: `hermes/application/affiliate_run_service.py`
- Create: `core/affiliate_research_jobs.py`
- Modify: `core/job_watcher.py`
- Create: `tests/hermes/application/test_affiliate_run_service.py`
- Create: `tests/hermes/test_affiliate_research_job.py`

**Interfaces:**
- Consumes: catalog service, content service, repository, `AgentJobManager`, and `JobWorker`.
- Produces: `AffiliateRunService.run(request) -> RunResult`, job type `affiliate_product_research`, and `AffiliateResearchJobHandler`.

- [ ] **Step 1: Write failing run idempotency and dispatch tests**

```python
def test_same_idempotency_key_returns_existing_run(run_service):
    first = run_service.run(
        AffiliateRunRequest("42", "run-key-1", "products.csv", package_limit=5)
    )
    second = run_service.run(
        AffiliateRunRequest("42", "run-key-1", "products.csv", package_limit=5)
    )
    assert first.run_id == second.run_id
    assert second.reused is True


def test_job_worker_dispatches_affiliate_job_without_legacy_media_path(fake_manager):
    handler = Mock(return_value={"run_id": "run-1", "package_ids": ["pkg-1"]})
    worker = JobWorker(manager=fake_manager, affiliate_research_handler=handler)
    assert worker.process_next_job() is True
    handler.assert_called_once()
    assert fake_manager.completed[0]["summary"].startswith("Affiliate research")
```

- [ ] **Step 2: Run tests and verify missing integration failures**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/application/test_affiliate_run_service.py tests/hermes/test_affiliate_research_job.py -q
```

Expected: missing modules and unsupported constructor argument failures.

- [ ] **Step 3: Implement the run transaction checkpoints**

```python
@dataclass(frozen=True)
class AffiliateRunRequest:
    owner_user_id: str
    idempotency_key: str
    csv_path: str
    package_limit: int = 10
    reference_urls: tuple[str, ...] = ()


@dataclass(frozen=True)
class RunResult:
    run_id: str
    imported: int
    shortlisted: int
    package_ids: tuple[str, ...]
    reused: bool = False
```

`AffiliateRunService.run` must create/reuse the run, import, snapshot, score,
shortlist, create packages, commit canonical counters, then invoke Sheets and
Telegram projections. Projection failures are stored for retry and do not roll
back canonical packages.

- [ ] **Step 4: Add early job dispatch**

Add optional `affiliate_research_handler` injection to `JobWorker`. Immediately
after claiming a SQLite job and before dereferencing legacy `target` or
`source`, dispatch:

```python
if job.get("job_type") == "affiliate_product_research":
    result = self.affiliate_research_handler(job)
    summary = (
        f"Affiliate research run {result['run_id']} completed; "
        f"{len(result['package_ids'])} package(s) pending review."
    )
    self.manager.complete_job(job_id, summary=summary, files_created=[])
    return True
```

`core/affiliate_research_jobs.py` must validate that the CSV path resolves
inside an explicitly configured import directory and build the handler with
production repository/adapters. Invalid path, authorization, and CSV errors are
non-retryable; network, Sheets, Telegram, and model availability errors are
retryable under the existing bounded job policy.

- [ ] **Step 5: Run focused queue tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/application/test_affiliate_run_service.py tests/hermes/test_affiliate_research_job.py tests/hermes/test_job_repository.py -q
```

Expected: all tests pass without changing existing job behavior.

- [ ] **Step 6: Commit Task 6**

```powershell
git add hermes/application/affiliate_run_service.py core/affiliate_research_jobs.py core/job_watcher.py tests/hermes/application/test_affiliate_run_service.py tests/hermes/test_affiliate_research_job.py
git commit -m "feat: run affiliate research through job queue"
```

---

### Task 7: Idempotent Google Sheets Projection

**Files:**
- Create: `hermes/adapters/google/__init__.py`
- Create: `hermes/adapters/google/sheets_projection.py`
- Modify: `requirements.txt`
- Create: `tests/hermes/adapters/test_google_sheets_projection.py`

**Interfaces:**
- Consumes: repository projection queries and `SheetsProjection`.
- Produces: `GoogleSheetsProjection`, `DisabledSheetsProjection`, and `FakeSheetsProjection`.

- [ ] **Step 1: Write failing six-tab and retry tests**

```python
def test_projection_reconciles_six_tabs_by_stable_id(repository):
    client = FakeSheetsClient()
    projection = GoogleSheetsProjection(repository, client, "sheet-123")
    result = projection.sync("42", "run-1")
    assert result.ok is True
    assert set(client.tabs) == {
        "Products", "Shortlist", "Ideas", "Scripts", "Approval Queue", "Runs & Errors"
    }
    projection.sync("42", "run-1")
    assert client.row_count("Products") == 1


def test_sheet_outage_returns_retryable_result_without_changing_sqlite(repository):
    projection = GoogleSheetsProjection(repository, FailingSheetsClient(), "sheet-123")
    result = projection.sync("42", "run-1")
    assert result.ok is False
    assert result.retryable is True
    assert repository.get_package("pkg-1", "42") is not None
```

- [ ] **Step 2: Run tests and verify missing adapter failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_google_sheets_projection.py -q
```

Expected: collection fails because the Google adapter does not exist.

- [ ] **Step 3: Add official Google client dependencies**

Add:

```text
google-api-python-client>=2.0.0
google-auth>=2.0.0
```

Do not read credentials at import time.

- [ ] **Step 4: Implement projection with a narrow client wrapper**

`GoogleSheetsProjection.from_environment(repository)` reads
`GOOGLE_SHEETS_CREDENTIALS_FILE` and `GOOGLE_SHEETS_SPREADSHEET_ID`. The client
uses the read/write Sheets scope only. Build all six tab payloads from
repository queries and reconcile rows by the first `stable_id` column.

Provide:

```python
class DisabledSheetsProjection:
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        return ProjectionResult(ok=True, retryable=False, detail="disabled")


class FakeSheetsProjection:
    def __init__(self): self.calls = []
    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        self.calls.append((owner_user_id, run_id))
        return ProjectionResult(ok=True, retryable=False, detail="fake")
```

- [ ] **Step 5: Run focused adapter tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/adapters/test_google_sheets_projection.py -q
```

Expected: all tests pass with fake clients; no credential file or network is
required.

- [ ] **Step 6: Commit Task 7**

```powershell
git add hermes/adapters/google requirements.txt tests/hermes/adapters/test_google_sheets_projection.py
git commit -m "feat: project affiliate research to Google Sheets"
```

---

### Task 8: Telegram Package Review And Revision Feedback

**Files:**
- Create: `hermes/application/affiliate_review_service.py`
- Create: `hermes/adapters/telegram/affiliate_review.py`
- Modify: `telegram_bot.py`
- Create: `tests/hermes/test_telegram_affiliate_review.py`

**Interfaces:**
- Consumes: repository, owner allowlist, safe Telegram HTML helpers.
- Produces: `AffiliateReviewService`, renderer, callback parser, `/affiliate_revise`.
- Produces: `TelegramReviewDelivery` implementing `ReviewDelivery`.

- [ ] **Step 1: Write failing lifecycle, duplicate callback, and authorization tests**

```python
def test_approve_is_owner_scoped_and_idempotent(repository):
    service = AffiliateReviewService(repository)
    first = service.apply("pkg-1", "42", "approve")
    second = service.apply("pkg-1", "42", "approve")
    assert first.status.value == "approved"
    assert second.status.value == "approved"
    assert repository.count_approval_events("pkg-1", "approve") == 1
    with pytest.raises(PackageNotFound):
        service.apply("pkg-1", "99", "reject")


def test_callback_rejects_unauthorized_user(fake_query, repository):
    fake_query.data = "affiliate_approve:pkg-1"
    with patch("telegram_bot.is_authorized_user_id", return_value=False):
        asyncio.run(telegram_bot.handle_callback(make_update(fake_query), make_context()))
    assert repository.get_package("pkg-1", "42").status.value == "pending_review"


def test_revision_command_requires_feedback(repository):
    update = make_update(user_id=42)
    context = SimpleNamespace(args=["pkg-1"])
    asyncio.run(telegram_bot.affiliate_revise_command(update, context))
    assert "feedback" in update.message.replies[0].lower()
```

- [ ] **Step 2: Run tests and verify missing review paths**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_telegram_affiliate_review.py -q
```

Expected: missing service/adapter and unregistered command failures.

- [ ] **Step 3: Implement lifecycle service and Telegram renderer**

Use repository atomic transitions and keep business rules outside
`telegram_bot.py`:

```python
class AffiliateReviewService:
    def apply(
        self,
        package_id: str,
        owner_user_id: str,
        action: Literal["approve", "revise", "reject"],
        reason: str = "",
    ) -> ContentPackage: ...
```

Render escaped HTML with product name, score reason, audience, hook, script
summary, storyboard summary, warnings, and package ID. Buttons use:

```text
affiliate_approve:<package_id>
affiliate_revise:<package_id>
affiliate_reject:<package_id>
```

Keep Telegram callback data below 64 bytes by using compact package IDs.
`TelegramReviewDelivery.send_pending(...)` loads owner-scoped packages, sends
the rendered messages through the injected bot, and returns a retryable
`ProjectionResult` on transport failure. Tests inject a fake bot.

- [ ] **Step 4: Wire authorized callbacks and revision command**

Add affiliate prefixes near the start of `handle_callback`, after the existing
authorization check. Duplicate callbacks return current status without adding a
second event. `/affiliate_revise <package_id> <feedback>` records a revision
request and invokes `AffiliateContentService.revise_package`; blank feedback is
rejected. Register the command in `main()`.

- [ ] **Step 5: Run focused Telegram tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_telegram_affiliate_review.py tests/hermes/test_telegram_authorization.py tests/hermes/test_telegram_memory.py -q
```

Expected: all tests pass and existing Telegram approvals remain unchanged.

- [ ] **Step 6: Commit Task 8**

```powershell
git add hermes/application/affiliate_review_service.py hermes/adapters/telegram/affiliate_review.py telegram_bot.py tests/hermes/test_telegram_affiliate_review.py
git commit -m "feat: review affiliate packages in Telegram"
```

---

### Task 9: Configuration, Offline Acceptance Test, And Runbook

**Files:**
- Modify: `config.py`
- Modify: `.env.example`
- Create: `tests/hermes/test_affiliate_research_acceptance.py`
- Create: `docs/runbooks/affiliate-product-research.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: documented configuration and one offline 200-row acceptance path.

- [ ] **Step 1: Write the failing end-to-end offline acceptance test**

```python
def test_200_product_run_is_idempotent_and_produces_review_packages(tmp_path):
    fixture = write_200_authorized_products(tmp_path / "products.csv")
    harness = build_offline_harness(
        database_path=tmp_path / "hermes.db",
        content_gateway=DeterministicContentGateway(),
        sheets=FakeSheetsProjection(),
        review_delivery=FakeReviewDelivery(),
    )
    first = harness.run("42", "daily-2026-08-01", fixture, package_limit=10)
    second = harness.run("42", "daily-2026-08-01", fixture, package_limit=10)

    assert first.imported == 200
    assert 15 <= first.shortlisted <= 25
    assert 5 <= len(first.package_ids) <= 10
    assert second.reused is True
    assert harness.repository.count_products("42") == 200
    assert harness.sheets.calls == [("42", first.run_id)]
    assert harness.review_delivery.sent_package_ids == list(first.package_ids)
```

Add assertions that every package has a 30-90 second script, storyboard, AI
prompts, evidence URLs, warnings, and rights metadata. Patch `requests`,
`HermesLLMGateway`, Google discovery, and Telegram bot construction to raise if
called.

- [ ] **Step 2: Run acceptance test and verify missing configuration/harness**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_affiliate_research_acceptance.py -q
```

Expected: test fails until the production composition and configuration are
complete.

- [ ] **Step 3: Add redacted configuration**

Add these values to `config.py` and empty/documented entries to `.env.example`:

```python
AFFILIATE_IMPORT_DIR = os.environ.get(
    "AFFILIATE_IMPORT_DIR",
    str(Path(HERMES_DATA_DIR) / "affiliate_imports"),
)
GOOGLE_SHEETS_ENABLED = os.environ.get("GOOGLE_SHEETS_ENABLED", "0")
GOOGLE_SHEETS_CREDENTIALS_FILE = os.environ.get("GOOGLE_SHEETS_CREDENTIALS_FILE", "")
GOOGLE_SHEETS_SPREADSHEET_ID = os.environ.get("GOOGLE_SHEETS_SPREADSHEET_ID", "")
AFFILIATE_RESEARCH_SHORTLIST_LIMIT = os.environ.get("AFFILIATE_RESEARCH_SHORTLIST_LIMIT", "25")
AFFILIATE_RESEARCH_PACKAGE_LIMIT = os.environ.get("AFFILIATE_RESEARCH_PACKAGE_LIMIT", "10")
```

Validate numeric limits to `15..25` and `5..10` in the composition root. Do not
print credential values in `verify_config()` or settings output.

- [ ] **Step 4: Write the operating runbook**

Document:

- how to verify whether Shopee Affiliate Product Feed is enabled;
- the supported CSV columns and aliases;
- where to place exports under `AFFILIATE_IMPORT_DIR`;
- how to enqueue one `affiliate_product_research` job;
- how to configure a Google service account without committing credentials;
- Google Sheet tab ownership and which fields the user may edit;
- Telegram approve/revise/reject commands;
- retry, cancel, and recovery behavior;
- the explicit prohibition on Shopee/TikTok scraping and third-party media
  download;
- how to run the offline acceptance suite.

- [ ] **Step 5: Run focused and broader verification**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/hermes/test_affiliate_research_acceptance.py -q
.\.venv\Scripts\python.exe -m pytest tests/hermes/domain/test_affiliate_research.py tests/hermes/test_affiliate_research_repository.py tests/hermes/adapters/test_shopee_affiliate_csv.py tests/hermes/adapters/test_tiktok_public_reference.py tests/hermes/application/test_affiliate_catalog_service.py tests/hermes/application/test_affiliate_content_service.py tests/hermes/application/test_affiliate_run_service.py tests/hermes/adapters/test_google_sheets_projection.py tests/hermes/test_telegram_affiliate_review.py tests/hermes/test_affiliate_research_job.py -q
.\.venv\Scripts\python.exe -m pytest tests/hermes -q
git diff --check
```

Expected: every command exits `0`; no test reports a live network call.

- [ ] **Step 6: Commit Task 9**

```powershell
git add config.py .env.example tests/hermes/test_affiliate_research_acceptance.py docs/runbooks/affiliate-product-research.md
git commit -m "docs: complete affiliate research rollout"
```

---

## Final Verification Gate

- [ ] Confirm `git status --short` contains no unintended staged files.
- [ ] Confirm schema migration from a version-2 fixture database preserves all existing tables and records.
- [ ] Confirm the 200-row import and same-key rerun are idempotent.
- [ ] Confirm package count is 5-10 and shortlist count is 15-25.
- [ ] Confirm all package claims have evidence and all assets have rights status.
- [ ] Confirm disabled Google Sheets mode succeeds without credentials.
- [ ] Confirm unauthorized Telegram callbacks cannot change package state.
- [ ] Confirm `tests/hermes -q` passes without paid or live external calls.
- [ ] Run a two-stage code review: spec compliance first, then code quality and regression risk.

## Out Of Scope Follow-Up

After this plan is implemented and accepted, create a separate design/spec for
AI asset generation, voice-over, video rendering, CapCut/project export, and
publishing. Do not add those features opportunistically to this implementation.
