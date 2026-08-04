# Product Research Script Supervisor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first Hermes personal-assistant workflow that understands a product research request, collects crawler-first product data, exports reviewable sheets, and generates short affiliate scripts.

**Architecture:** Add a thin supervisor workflow above existing affiliate modules. SQLite remains canonical; local CSV/XLSX and Google Sheets are projections. The workflow uses safe local operations by default and gates marketplace crawling, Playwright crawling, Google Sheets sync, and LLM generation through configuration.

**Tech Stack:** Python 3.10+, pytest, SQLite, existing Hermes affiliate domain/application services, optional Google Sheets adapter, optional Playwright crawler, optional openpyxl for XLSX output.

## Global Constraints

- Hermes remains a personal assistant first; TikTok affiliate, marketplace research, sheets, and script generation are supporting modules.
- Video rendering, detailed storyboard production, voice generation, publishing, and media download are out of scope.
- Default source order is Shopee crawler, then CSV/feed fallback.
- Marketplace crawler requires `HERMES_ENABLE_MARKETPLACE_CRAWLER=true`.
- Playwright/browser crawler requires a separate explicit enable flag.
- Google Sheets sync requires configured credentials and spreadsheet id.
- LLM script generation may run automatically only when the model provider is configured for assistant workflows; otherwise script rows are marked `pending_generation`.
- The workflow must not store Shopee cookies, passwords, session tokens, private media, or secrets in jobs, sheets, reports, or logs.
- Local sheet output is required even when Google Sheets is unavailable.
- SQLite remains the canonical run store.
- Preserve existing user changes and avoid destructive Git operations.

---

## File Structure

- Create `hermes/application/product_research_intent.py`
  - Parses natural requests into a serializable `ProductResearchIntent`.
  - Holds bounded defaults and deterministic idempotency-key generation.
- Create `tests/hermes/application/test_product_research_intent.py`
  - Covers Vietnamese category/price parsing, defaults, and assistant routing.
- Modify `core/assistant_runtime.py`
  - Adds `product_research_script` as a first-class assistant module and intent rule.
- Modify `hermes/affiliate_config.py`
  - Adds non-secret settings for marketplace crawler, Playwright crawler, local sheet output, and auto script generation.
- Create `hermes/adapters/local/sheet_projection.py`
  - Writes `Products.csv`, `Shortlist.csv`, `Scripts.csv`, and `Runs_Errors.csv`.
  - Writes `product_research_run.xlsx` when `openpyxl` is importable.
- Create `tests/hermes/adapters/local/test_sheet_projection.py`
  - Verifies CSV headers, stable IDs, JSON cell encoding, and no failure when `openpyxl` is unavailable.
- Create `hermes/application/product_source_selector.py`
  - Chooses crawler-first source when enabled.
  - Falls back to CSV/feed with an explicit fallback status when crawler is disabled or blocked.
- Create `tests/hermes/application/test_product_source_selector.py`
  - Uses fake crawler and fake CSV source; no network.
- Create `hermes/application/product_research_script_workflow.py`
  - Coordinates intent, source selection, affiliate import/score, local sheet export, optional Google Sheets, script generation, and report output.
- Create `tests/hermes/application/test_product_research_script_workflow.py`
  - Offline acceptance tests for crawler enabled, crawler disabled, Google Sheets failure, and LLM unavailable.
- Create `scripts/product_research_script.py`
  - CLI entrypoint for manual local runs and acceptance checks.
- Modify `telegram_bot.py`
  - Routes natural product research messages to the supervisor in a minimal gated path.
- Create `tests/hermes/test_product_research_script_cli.py`
  - Verifies CLI calls the workflow with parsed intent and prints local sheet/report paths.

---

### Task 1: Product Research Intent And Config

**Files:**
- Create: `hermes/application/product_research_intent.py`
- Modify: `core/assistant_runtime.py`
- Modify: `hermes/affiliate_config.py`
- Test: `tests/hermes/application/test_product_research_intent.py`
- Test: `tests/hermes/test_affiliate_research_acceptance.py`

**Interfaces:**
- Consumes: existing `HermesAssistantRuntime.classify(message: str) -> str`.
- Produces: `ProductResearchIntent.from_message(owner_user_id: str, message: str) -> ProductResearchIntent`.
- Produces: `ProductResearchIntent.to_payload() -> dict[str, object]`.
- Produces: `AffiliateResearchSettings.marketplace_crawler_enabled: bool`.
- Produces: `AffiliateResearchSettings.playwright_crawler_enabled: bool`.
- Produces: `AffiliateResearchSettings.local_sheet_output_dir: Path`.
- Produces: `AffiliateResearchSettings.auto_generate_scripts: bool`.

- [ ] **Step 1: Write the failing intent tests**

Create `tests/hermes/application/test_product_research_intent.py`:

```python
from __future__ import annotations

from pathlib import Path


def test_vietnamese_product_research_request_parses_category_price_and_defaults():
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message(
        "42",
        "crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản",
    )

    assert intent.owner_user_id == "42"
    assert intent.category == "bàn phím"
    assert intent.keyword == "bàn phím"
    assert intent.min_price_vnd == 200_000
    assert intent.max_price_vnd == 500_000
    assert intent.source_preference == "crawler_first"
    assert intent.script_limit == 5
    assert intent.idempotency_key.startswith("product-research-script-")
    assert intent.to_payload()["category"] == "bàn phím"


def test_product_research_request_uses_conservative_defaults():
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message("42", "tìm sản phẩm hub rồi xuất sheet")

    assert intent.category == "hub"
    assert intent.min_price_vnd == 200_000
    assert intent.max_price_vnd == 500_000
    assert intent.script_limit == 5


def test_assistant_runtime_routes_product_research_script_request():
    from core.assistant_runtime import HermesAssistantRuntime

    runtime = HermesAssistantRuntime(Path.cwd())

    assert (
        runtime.classify("crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản")
        == "product_research_script"
    )


def test_affiliate_settings_include_product_research_gates(tmp_path):
    from hermes.affiliate_config import load_affiliate_research_settings

    settings = load_affiliate_research_settings(
        {
            "AFFILIATE_IMPORT_DIR": str(tmp_path / "imports"),
            "GOOGLE_SHEETS_ENABLED": "0",
            "HERMES_ENABLE_MARKETPLACE_CRAWLER": "1",
            "HERMES_ENABLE_PLAYWRIGHT_CRAWLER": "0",
            "PRODUCT_RESEARCH_OUTPUT_DIR": str(tmp_path / "exports"),
            "PRODUCT_RESEARCH_AUTO_GENERATE_SCRIPTS": "1",
        }
    )

    assert settings.marketplace_crawler_enabled is True
    assert settings.playwright_crawler_enabled is False
    assert settings.local_sheet_output_dir == (tmp_path / "exports").resolve()
    assert settings.auto_generate_scripts is True
    assert "GOOGLE" not in repr(settings)
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_intent.py -q
```

Expected: FAIL because `hermes.application.product_research_intent` does not exist and runtime routing has no `product_research_script`.

- [ ] **Step 3: Implement the intent module**

Create `hermes/application/product_research_intent.py`:

```python
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass


_PRICE_RANGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(k|tr|triệu|m)?\s*[-–]\s*(\d+(?:[.,]\d+)?)\s*(k|tr|triệu|m)?", re.I)
_CATEGORY = re.compile(r"(?:ngành|nganh|category|sản phẩm|san pham)\s+([^,;.]+)", re.I)
_KNOWN_CATEGORIES = ("bàn phím", "ban phim", "keyboard", "chuột", "mouse", "hub", "đèn", "den", "tai nghe")


@dataclass(frozen=True)
class ProductResearchIntent:
    owner_user_id: str
    raw_message: str
    category: str
    keyword: str
    min_price_vnd: int
    max_price_vnd: int
    source_preference: str = "crawler_first"
    script_limit: int = 5
    idempotency_key: str = ""

    @classmethod
    def from_message(cls, owner_user_id: str, message: str) -> "ProductResearchIntent":
        owner = str(owner_user_id).strip()
        text = (message or "").strip()
        if not owner:
            raise ValueError("owner_user_id is required")
        if not text:
            raise ValueError("message is required")
        category = _extract_category(text)
        min_price, max_price = _extract_price_range(text)
        payload_key = hashlib.sha256(
            f"{owner}\0{category}\0{min_price}\0{max_price}\0{text.casefold()}".encode("utf-8")
        ).hexdigest()[:16]
        return cls(
            owner_user_id=owner,
            raw_message=text,
            category=category,
            keyword=category,
            min_price_vnd=min_price,
            max_price_vnd=max_price,
            idempotency_key=f"product-research-script-{payload_key}",
        )

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


def _extract_category(text: str) -> str:
    match = _CATEGORY.search(text)
    if match:
        value = match.group(1).strip().lower()
        value = re.split(r"\s+(?:giá|gia|price|xuất|xuat|rồi|roi)\b", value, maxsplit=1, flags=re.I)[0]
        return value.strip(" ,.;:") or "tech_product"
    lowered = text.casefold()
    for category in _KNOWN_CATEGORIES:
        if category in lowered:
            return category
    return "tech_product"


def _extract_price_range(text: str) -> tuple[int, int]:
    match = _PRICE_RANGE.search(text)
    if not match:
        return 200_000, 500_000
    low = _money_to_vnd(match.group(1), match.group(2))
    high = _money_to_vnd(match.group(3), match.group(4) or match.group(2))
    if low <= 0 or high <= 0 or low > high:
        raise ValueError("invalid price range")
    return low, high


def _money_to_vnd(number: str, unit: str | None) -> int:
    value = float(number.replace(",", "."))
    normalized = (unit or "").casefold()
    if normalized in {"k"}:
        value *= 1_000
    elif normalized in {"tr", "triệu", "m"}:
        value *= 1_000_000
    return int(value)
```

- [ ] **Step 4: Extend assistant runtime routing**

Modify `core/assistant_runtime.py`:

```python
ASSISTANT_MODULES["product_research_script"] = {
    "description": "Research marketplace products, export review sheets, and generate short affiliate scripts.",
    "owner_paths": [
        "hermes/application/product_research_script_workflow.py",
        "hermes/application/product_source_selector.py",
        "hermes/adapters/local/sheet_projection.py",
    ],
    "risk": "medium",
}
```

Add this tuple near the top of `INTENT_RULES`, before generic `video_factory` matching:

```python
(
    "product_research_script",
    [
        "crawl ngành",
        "crawl nganh",
        "xuất sheet",
        "xuat sheet",
        "tạo kịch bản",
        "tao kich ban",
        "affiliate",
        "giá",
        "gia",
        "shortlist",
    ],
),
```

Add to `action_for_module`:

```python
if module == "product_research_script":
    return "Run a gated product research workflow: collect products, export sheets, and generate short affiliate scripts."
```

Add to `_permissions_for`:

```python
elif task.module == "product_research_script":
    permissions.add("marketplace_crawler_when_enabled")
    permissions.add("write_local_sheet_exports")
    permissions.add("optional_model_script_generation")
```

- [ ] **Step 5: Extend affiliate settings**

Modify `hermes/affiliate_config.py`:

```python
    marketplace_crawler_enabled: bool = False
    playwright_crawler_enabled: bool = False
    local_sheet_output_dir: Path = Path("exports/product_research")
    auto_generate_scripts: bool = False
```

Inside `AffiliateResearchSettings.from_environment`, pass these fields:

```python
            marketplace_crawler_enabled=_boolean(values.get("HERMES_ENABLE_MARKETPLACE_CRAWLER", "0")),
            playwright_crawler_enabled=_boolean(values.get("HERMES_ENABLE_PLAYWRIGHT_CRAWLER", "0")),
            local_sheet_output_dir=_product_research_output_dir(values),
            auto_generate_scripts=_boolean(values.get("PRODUCT_RESEARCH_AUTO_GENERATE_SCRIPTS", "0")),
```

Add helper:

```python
def _product_research_output_dir(values: Mapping[str, str]) -> Path:
    configured = str(values.get("PRODUCT_RESEARCH_OUTPUT_DIR", "")).strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (load_settings().data_dir / "product_research_exports").resolve()
```

- [ ] **Step 6: Run tests and verify they pass**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_intent.py tests\hermes\test_affiliate_research_acceptance.py::test_affiliate_configuration_validates_limits_and_redacts_credentials -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

Run:

```powershell
git add -- hermes/application/product_research_intent.py core/assistant_runtime.py hermes/affiliate_config.py tests/hermes/application/test_product_research_intent.py tests/hermes/test_affiliate_research_acceptance.py
git commit -m "feat: parse product research script intents"
```

---

### Task 2: Local Sheet Projection

**Files:**
- Create: `hermes/adapters/local/sheet_projection.py`
- Test: `tests/hermes/adapters/local/test_sheet_projection.py`

**Interfaces:**
- Consumes: `repository.projection_rows(owner_user_id: str, run_id: str) -> dict[str, list[dict]]`.
- Produces: `LocalSheetProjection.sync(owner_user_id: str, run_id: str) -> ProjectionResult`.
- Produces: `LocalSheetProjection.output_paths(owner_user_id: str, run_id: str) -> dict[str, str]`.

- [ ] **Step 1: Write failing local sheet projection tests**

Create `tests/hermes/adapters/local/test_sheet_projection.py`:

```python
from __future__ import annotations

import csv
import json


class FakeRepository:
    def projection_rows(self, owner_user_id: str, run_id: str):
        assert owner_user_id == "42"
        assert run_id == "run-1"
        return {
            "products": [
                {
                    "id": "product-1",
                    "name": "Keyboard A",
                    "price_vnd": 350000,
                    "image_urls": ["https://example.test/image.jpg"],
                }
            ],
            "packages": [
                {
                    "id": "pkg-1",
                    "product_id": "product-1",
                    "hook": "Góc bàn làm việc cần gọn hơn?",
                    "script": "Đây là kịch bản ngắn.",
                    "warnings": ["Verify price"],
                }
            ],
            "runs": [{"id": "run-1", "status": "completed"}],
        }


def test_local_sheet_projection_writes_required_csv_files_with_stable_id(tmp_path):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection

    projection = LocalSheetProjection(FakeRepository(), tmp_path)
    result = projection.sync("42", "run-1")

    assert result.ok is True
    paths = projection.output_paths("42", "run-1")
    assert set(paths) >= {"Products", "Shortlist", "Scripts", "Runs_Errors"}

    with open(paths["Products"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["stable_id"] == "product-1"
    assert rows[0]["name"] == "Keyboard A"
    assert json.loads(rows[0]["image_urls"]) == ["https://example.test/image.jpg"]


def test_local_sheet_projection_returns_retryable_failure_without_leaking_secret(tmp_path):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection

    class BrokenRepository:
        def projection_rows(self, owner_user_id: str, run_id: str):
            raise RuntimeError("failed with token secret-value")

    result = LocalSheetProjection(BrokenRepository(), tmp_path).sync("42", "run-1")

    assert result.ok is False
    assert result.retryable is True
    assert "secret-value" not in result.detail
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\adapters\local\test_sheet_projection.py -q
```

Expected: FAIL because `hermes.adapters.local.sheet_projection` does not exist.

- [ ] **Step 3: Implement local sheet projection**

Create `hermes/adapters/local/sheet_projection.py`:

```python
from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from hermes.domain.affiliate_research import ProjectionResult


class LocalSheetProjection:
    _TABS = {
        "Products": "Products.csv",
        "Shortlist": "Shortlist.csv",
        "Scripts": "Scripts.csv",
        "Runs_Errors": "Runs_Errors.csv",
    }

    def __init__(self, repository: Any, output_root: str | Path):
        self._repository = repository
        self._output_root = Path(output_root).expanduser().resolve()

    def sync(self, owner_user_id: str, run_id: str) -> ProjectionResult:
        try:
            payloads = self._payloads(self._repository.projection_rows(owner_user_id, run_id))
            run_dir = self._run_dir(owner_user_id, run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            for tab_name, filename in self._TABS.items():
                self._write_csv(run_dir / filename, payloads.get(tab_name, []))
            self._write_xlsx_if_available(run_dir, payloads)
        except Exception as error:
            return ProjectionResult(ok=False, retryable=True, detail=_redact(str(error))[:1000])
        return ProjectionResult(ok=True, retryable=False, detail=str(self._run_dir(owner_user_id, run_id)))

    def output_paths(self, owner_user_id: str, run_id: str) -> dict[str, str]:
        run_dir = self._run_dir(owner_user_id, run_id)
        paths = {tab: str((run_dir / filename).resolve()) for tab, filename in self._TABS.items()}
        xlsx = run_dir / "product_research_run.xlsx"
        if xlsx.exists():
            paths["Workbook"] = str(xlsx.resolve())
        return paths

    def _run_dir(self, owner_user_id: str, run_id: str) -> Path:
        return self._output_root / _safe_segment(owner_user_id) / _safe_segment(run_id)

    def _payloads(self, rows: dict[str, list[dict]]) -> dict[str, list[dict]]:
        products = rows.get("products", [])
        return {
            "Products": products,
            "Shortlist": [row for row in products if row.get("eligibility_status") == "shortlisted"],
            "Scripts": rows.get("packages", []),
            "Runs_Errors": rows.get("runs", []),
        }

    @staticmethod
    def _write_csv(path: Path, rows: list[dict]) -> None:
        header = ["stable_id", *sorted({key for row in rows for key in row if key != "id"})]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(header)
            for row in rows:
                stable_id = str(row.get("id", ""))
                writer.writerow([stable_id, *[_cell(row.get(column)) for column in header[1:]]])

    @staticmethod
    def _write_xlsx_if_available(run_dir: Path, payloads: dict[str, list[dict]]) -> None:
        try:
            from openpyxl import Workbook
        except ImportError:
            return
        workbook = Workbook()
        default = workbook.active
        workbook.remove(default)
        for tab_name, rows in payloads.items():
            sheet = workbook.create_sheet(tab_name)
            header = ["stable_id", *sorted({key for row in rows for key in row if key != "id"})]
            sheet.append(header)
            for row in rows:
                sheet.append([str(row.get("id", "")), *[_cell(row.get(column)) for column in header[1:]]])
        workbook.save(run_dir / "product_research_run.xlsx")


def _cell(value: Any) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return "" if value is None else value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_segment(value: str) -> str:
    segment = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    return segment.strip("._") or "unknown"


def _redact(value: str) -> str:
    return re.sub(r"(?i)(secret|token|api[_-]?key|password)[^\\s,;]*", "[redacted]", value)
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\adapters\local\test_sheet_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- hermes/adapters/local/sheet_projection.py tests/hermes/adapters/local/test_sheet_projection.py
git commit -m "feat: export product research sheets locally"
```

---

### Task 3: Crawler-First Source Selector

**Files:**
- Create: `hermes/application/product_source_selector.py`
- Test: `tests/hermes/application/test_product_source_selector.py`

**Interfaces:**
- Consumes: `ProductResearchIntent`.
- Consumes: `AffiliateResearchSettings.marketplace_crawler_enabled`.
- Produces: `ProductSourceSelection.load(owner_user_id: str) -> list[ProductCandidate]`.
- Produces: `ProductSourceSelection.status: str`.
- Produces: `ProductSourceSelection.warnings: tuple[str, ...]`.

- [ ] **Step 1: Write failing source selector tests**

Create `tests/hermes/application/test_product_source_selector.py`:

```python
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from hermes.domain.affiliate_research import ProductCandidate


def candidate(number: int) -> ProductCandidate:
    return ProductCandidate(
        owner_user_id="42",
        platform="shopee",
        external_product_id=str(number),
        name=f"Keyboard {number}",
        category="keyboard",
        price_vnd=350000,
        sold_count=100 + number,
        rating=4.8,
        review_count=20,
        commission_rate=None,
        shop_name="Shop",
        product_url=f"https://example.test/{number}",
        image_urls=(),
        visual_signals=("tactile_interaction",),
        source_type="fake_crawler",
        source_url=f"https://example.test/{number}",
        authorization_scope="public_scrape",
        rights_status="reference_only",
        content_hash=f"hash-{number}",
    )


class FakeCrawler:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.called = False

    def load(self, owner_user_id: str):
        self.called = True
        if self.error:
            raise self.error
        return self.rows


def settings(tmp_path, enabled: bool):
    from hermes.affiliate_config import AffiliateResearchSettings

    return AffiliateResearchSettings(
        import_directory=tmp_path,
        google_sheets_enabled=False,
        google_sheets_credentials_file="",
        google_sheets_spreadsheet_id="",
        marketplace_crawler_enabled=enabled,
        playwright_crawler_enabled=False,
        local_sheet_output_dir=tmp_path / "exports",
        auto_generate_scripts=False,
    )


def intent():
    from hermes.application.product_research_intent import ProductResearchIntent

    return ProductResearchIntent.from_message("42", "crawl ngành bàn phím, giá 200k-500k")


def test_selector_uses_crawler_when_enabled(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler([candidate(1)])
    selected = ProductSourceSelector(settings(tmp_path, True), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "crawler"
    assert selected.load("42") == [candidate(1)]
    assert crawler.called is True


def test_selector_does_not_call_crawler_when_disabled(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler([candidate(1)])
    selected = ProductSourceSelector(settings(tmp_path, False), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "needs_csv_feed"
    assert selected.load("42") == []
    assert selected.warnings == ("Marketplace crawler is disabled; provide CSV/feed fallback.",)
    assert crawler.called is False


def test_selector_converts_crawler_block_to_csv_fallback(tmp_path):
    from hermes.application.product_source_selector import ProductSourceSelector

    crawler = FakeCrawler(error=RuntimeError("403 Forbidden"))
    selected = ProductSourceSelector(settings(tmp_path, True), crawler_factory=lambda request: crawler).select(intent())

    assert selected.status == "crawler"
    assert selected.load("42") == []
    assert "CSV/feed fallback" in selected.warnings[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_source_selector.py -q
```

Expected: FAIL because `product_source_selector` does not exist.

- [ ] **Step 3: Implement source selector**

Create `hermes/application/product_source_selector.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from hermes.application.product_research_intent import ProductResearchIntent
from hermes.domain.affiliate_research import ProductCandidate


@dataclass(frozen=True)
class ProductSourceSelection:
    status: str
    source: Any | None = None
    warnings: tuple[str, ...] = ()

    def load(self, owner_user_id: str) -> list[ProductCandidate]:
        if self.source is None:
            return []
        try:
            return list(self.source.load(owner_user_id))
        except Exception as error:
            object.__setattr__(
                self,
                "warnings",
                (f"Marketplace crawler failed; use CSV/feed fallback: {str(error)[:200]}",),
            )
            return []


class ProductSourceSelector:
    def __init__(
        self,
        settings: Any,
        *,
        crawler_factory: Callable[[ProductResearchIntent], Any] | None = None,
    ):
        self._settings = settings
        self._crawler_factory = crawler_factory or self._default_crawler

    def select(self, intent: ProductResearchIntent) -> ProductSourceSelection:
        if not getattr(self._settings, "marketplace_crawler_enabled", False):
            return ProductSourceSelection(
                status="needs_csv_feed",
                warnings=("Marketplace crawler is disabled; provide CSV/feed fallback.",),
            )
        return ProductSourceSelection(status="crawler", source=self._crawler_factory(intent))

    @staticmethod
    def _default_crawler(intent: ProductResearchIntent) -> Any:
        from hermes.adapters.shopee.experimental_scraper import (
            ShopeeExperimentalScraper,
            ShopeeSearchConfig,
        )

        return ShopeeExperimentalScraper(
            ShopeeSearchConfig(
                min_price=int(intent.min_price_vnd),
                max_price=int(intent.max_price_vnd),
                limit_per_category=50,
            )
        )
```

- [ ] **Step 4: Run source selector tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_source_selector.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- hermes/application/product_source_selector.py tests/hermes/application/test_product_source_selector.py
git commit -m "feat: select gated crawler product sources"
```

---

### Task 4: Product Research Script Workflow

**Files:**
- Create: `hermes/application/product_research_script_workflow.py`
- Test: `tests/hermes/application/test_product_research_script_workflow.py`

**Interfaces:**
- Consumes: `ProductResearchIntent`.
- Consumes: `ProductSourceSelector.select(intent) -> ProductSourceSelection`.
- Consumes: `AffiliateCatalogService.import_candidates(source, owner_user_id, run_id, snapshot_date)`.
- Consumes: `AffiliateCatalogService.score_and_shortlist(...)`.
- Consumes: `LocalSheetProjection.sync(owner_user_id, run_id)`.
- Consumes: `GoogleSheetsProjection.sync(owner_user_id, run_id)` through an injected projection.
- Produces: `ProductResearchScriptWorkflow.run(intent: ProductResearchIntent) -> ProductResearchScriptResult`.
- Produces: `ProductResearchScriptResult.to_report() -> str`.

- [ ] **Step 1: Write failing workflow tests**

Create `tests/hermes/application/test_product_research_script_workflow.py`:

```python
from __future__ import annotations

import csv
from dataclasses import dataclass

from hermes.domain.affiliate_research import ProductCandidate, ProjectionResult


def candidate(number: int) -> ProductCandidate:
    return ProductCandidate(
        owner_user_id="42",
        platform="shopee",
        external_product_id=str(number),
        name=f"Keyboard {number}",
        category="keyboard",
        price_vnd=350000,
        sold_count=1000 + number,
        rating=4.8,
        review_count=100,
        commission_rate=None,
        shop_name="Shop",
        product_url=f"https://example.test/{number}",
        image_urls=(f"https://example.test/{number}.jpg",),
        visual_signals=("tactile_interaction", "visible_problem_solution"),
        source_type="fake_crawler",
        source_url=f"https://example.test/{number}",
        authorization_scope="public_scrape",
        rights_status="reference_only",
        content_hash=f"hash-{number}",
    )


class FakeSource:
    def __init__(self, rows):
        self.rows = rows

    def load(self, owner_user_id: str):
        return self.rows


@dataclass
class FakeSelection:
    status: str
    rows: list[ProductCandidate]
    warnings: tuple[str, ...] = ()

    def load(self, owner_user_id: str):
        return self.rows


class FakeSelector:
    def __init__(self, selection):
        self.selection = selection

    def select(self, intent):
        return self.selection


class FakeSheets:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def sync(self, owner_user_id, run_id):
        self.calls.append((owner_user_id, run_id))
        return self.result


class FakeGateway:
    def __init__(self, fail=False):
        self.fail = fail

    def generate(self, product, references):
        if self.fail:
            raise RuntimeError("model offline")
        return {
            "audience": "affiliate shopper",
            "angle": "quick buying decision",
            "angle_reason": "Product row has price, sales, and rating evidence.",
            "hook": f"{product.name} có đáng để góc làm việc gọn hơn?",
            "script": "Mở bằng vấn đề, nêu điểm chính, nhắc người xem kiểm tra giá hiện tại.",
            "duration_seconds": 45,
            "storyboard": [],
            "ai_prompts": [],
            "voiceover_plan": "Natural Vietnamese voice.",
            "text_overlays": ["Kiểm tra giá trước khi mua"],
            "claims": [{"text": "Price comes from product row", "evidence_url": product.product_url}],
            "warnings": ["Verify price and commission before publishing."],
        }


def intent():
    from hermes.application.product_research_intent import ProductResearchIntent

    return ProductResearchIntent.from_message("42", "crawl ngành bàn phím, giá 200k-500k")


def build_workflow(tmp_path, selection, gateway=None, sheets=None):
    from hermes.adapters.local.sheet_projection import LocalSheetProjection
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.application.product_research_script_workflow import ProductResearchScriptWorkflow
    from hermes.db import Database

    repository = SQLiteAffiliateResearchRepository(Database(tmp_path / "hermes.db"))
    return ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, gateway or FakeGateway()),
        source_selector=FakeSelector(selection),
        local_projection=LocalSheetProjection(repository, tmp_path / "exports"),
        google_projection=sheets,
        snapshot_date=lambda: "2026-08-04",
    )


def test_workflow_exports_local_sheets_and_generates_short_scripts(tmp_path):
    workflow = build_workflow(tmp_path, FakeSelection("crawler", [candidate(i) for i in range(1, 31)]))

    result = workflow.run(intent())

    assert result.status == "completed"
    assert result.imported == 30
    assert result.shortlisted >= 15
    assert result.package_ids
    assert "Products" in result.local_sheet_paths
    with open(result.local_sheet_paths["Scripts"], encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows


def test_workflow_returns_csv_fallback_when_crawler_disabled(tmp_path):
    workflow = build_workflow(
        tmp_path,
        FakeSelection("needs_csv_feed", [], ("Marketplace crawler is disabled; provide CSV/feed fallback.",)),
    )

    result = workflow.run(intent())

    assert result.status == "needs_csv_feed"
    assert result.imported == 0
    assert "provide CSV/feed" in result.warnings[0]


def test_workflow_keeps_local_output_when_google_sheets_fails(tmp_path):
    sheets = FakeSheets(ProjectionResult(ok=False, retryable=True, detail="offline"))
    workflow = build_workflow(
        tmp_path,
        FakeSelection("crawler", [candidate(i) for i in range(1, 31)]),
        sheets=sheets,
    )

    result = workflow.run(intent())

    assert result.status == "completed_with_projection_warnings"
    assert result.retryable_projection_failures == ("google_sheets",)
    assert result.local_sheet_paths["Products"].endswith("Products.csv")


def test_workflow_marks_script_generation_pending_when_model_unavailable(tmp_path):
    workflow = build_workflow(
        tmp_path,
        FakeSelection("crawler", [candidate(i) for i in range(1, 31)]),
        gateway=FakeGateway(fail=True),
    )

    result = workflow.run(intent())

    assert result.status == "completed_with_script_warnings"
    assert result.package_ids == ()
    assert any("script generation" in warning for warning in result.warnings)
```

- [ ] **Step 2: Run workflow tests and verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_script_workflow.py -q
```

Expected: FAIL because `product_research_script_workflow` does not exist.

- [ ] **Step 3: Implement workflow result and orchestration**

Create `hermes/application/product_research_script_workflow.py`:

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable

from hermes.application.affiliate_run_service import DisabledSheetsProjection
from hermes.application.product_research_intent import ProductResearchIntent
from hermes.domain.affiliate_research import ProjectionResult


@dataclass(frozen=True)
class ProductResearchScriptResult:
    run_id: str
    status: str
    imported: int
    shortlisted: int
    package_ids: tuple[str, ...]
    local_sheet_paths: dict[str, str]
    warnings: tuple[str, ...] = ()
    retryable_projection_failures: tuple[str, ...] = ()
    nonretryable_projection_failures: tuple[str, ...] = ()

    def to_report(self) -> str:
        lines = [
            "# Product Research Script Run",
            "",
            f"Run ID: {self.run_id}",
            f"Status: {self.status}",
            f"Imported: {self.imported}",
            f"Shortlisted: {self.shortlisted}",
            f"Scripts: {len(self.package_ids)}",
            "",
            "## Local Sheets",
        ]
        for name, path in sorted(self.local_sheet_paths.items()):
            lines.append(f"- {name}: `{path}`")
        if self.warnings:
            lines.extend(["", "## Warnings"])
            lines.extend(f"- {warning}" for warning in self.warnings)
        return "\n".join(lines) + "\n"


class ProductResearchScriptWorkflow:
    def __init__(
        self,
        *,
        repository: Any,
        catalog_service: Any,
        content_service: Any,
        source_selector: Any,
        local_projection: Any,
        google_projection: Any | None = None,
        snapshot_date: Callable[[], str] | None = None,
        shortlist_limit: int = 25,
    ):
        self._repository = repository
        self._catalog = catalog_service
        self._content = content_service
        self._source_selector = source_selector
        self._local_projection = local_projection
        self._google_projection = google_projection or DisabledSheetsProjection()
        self._snapshot_date = snapshot_date or (lambda: date.today().isoformat())
        self._shortlist_limit = shortlist_limit

    def run(self, intent: ProductResearchIntent) -> ProductResearchScriptResult:
        run_id = _run_id(intent.owner_user_id, intent.idempotency_key)
        warnings: list[str] = []
        selection = self._source_selector.select(intent)
        products = selection.load(intent.owner_user_id)
        warnings.extend(selection.warnings)
        if not products:
            return ProductResearchScriptResult(
                run_id=run_id,
                status="needs_csv_feed",
                imported=0,
                shortlisted=0,
                package_ids=(),
                local_sheet_paths={},
                warnings=tuple(warnings or ["No products were collected; provide CSV/feed fallback."]),
            )

        self._repository.create_run(run_id, intent.owner_user_id, intent.idempotency_key)
        imported = self._catalog.import_candidates(
            _ListProductSource(products),
            owner_user_id=intent.owner_user_id,
            run_id=run_id,
            snapshot_date=self._snapshot_date(),
        )
        shortlisted = self._catalog.score_and_shortlist(
            owner_user_id=intent.owner_user_id,
            run_id=run_id,
            minimum=15,
            maximum=self._shortlist_limit,
        )
        package_ids: tuple[str, ...] = ()
        script_failed = False
        try:
            packages = self._content.create_packages(
                intent.owner_user_id,
                run_id,
                [item.product if hasattr(item, "product") else item for item in shortlisted],
                (),
                per_run=intent.script_limit,
            )
            package_ids = tuple(package.id for package in packages)
        except Exception as error:
            script_failed = True
            warnings.append(f"script generation pending: {str(error)[:200]}")

        counters = {
            "imported": int(imported.imported),
            "updated": int(getattr(imported, "updated", 0)),
            "rejected": int(getattr(imported, "rejected", 0)),
            "errors": int(getattr(imported, "errors", 0)),
            "shortlisted": len(shortlisted),
            "packaged": len(package_ids),
        }
        complete_run = getattr(self._repository, "complete_run", None)
        if complete_run is None:
            self._repository.finish_run(run_id, counters)
        else:
            complete_run(run_id, counters, ("local_sheets", "google_sheets"), projection_items={})

        local_result = self._local_projection.sync(intent.owner_user_id, run_id)
        if not local_result.ok:
            warnings.append(f"local sheet export failed: {local_result.detail}")
        google_result = self._google_projection.sync(intent.owner_user_id, run_id)
        retryable, nonretryable = _projection_failures("google_sheets", google_result)
        status = "completed"
        if script_failed:
            status = "completed_with_script_warnings"
        elif retryable or nonretryable or not local_result.ok:
            status = "completed_with_projection_warnings"
        return ProductResearchScriptResult(
            run_id=run_id,
            status=status,
            imported=int(imported.imported),
            shortlisted=len(shortlisted),
            package_ids=package_ids,
            local_sheet_paths=self._local_projection.output_paths(intent.owner_user_id, run_id),
            warnings=tuple(warnings),
            retryable_projection_failures=retryable,
            nonretryable_projection_failures=nonretryable,
        )


class _ListProductSource:
    def __init__(self, products):
        self._products = list(products)

    def load(self, owner_user_id: str):
        return list(self._products)


def _run_id(owner_user_id: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{owner_user_id}\0{idempotency_key}".encode("utf-8")).hexdigest()
    return f"affiliate_run_{digest[:24]}"


def _projection_failures(name: str, result: ProjectionResult):
    if result.ok:
        return (), ()
    return ((name,), ()) if result.retryable else ((), (name,))
```

- [ ] **Step 4: Run workflow tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_script_workflow.py -q
```

Expected: PASS.

- [ ] **Step 5: Run integration safety checks**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_intent.py tests\hermes\application\test_product_source_selector.py tests\hermes\adapters\local\test_sheet_projection.py tests\hermes\application\test_product_research_script_workflow.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

Run:

```powershell
git add -- hermes/application/product_research_script_workflow.py tests/hermes/application/test_product_research_script_workflow.py
git commit -m "feat: orchestrate product research script runs"
```

---

### Task 5: CLI Wiring And Acceptance Verification

**Files:**
- Create: `scripts/product_research_script.py`
- Modify: `telegram_bot.py`
- Test: `tests/hermes/test_product_research_script_cli.py`
- Test: `tests/hermes/test_telegram_product_research_routing.py`
- Modify: `docs/superpowers/specs/2026-08-04-product-research-script-supervisor-design.md` only if implementation discovers a required clarification.

**Interfaces:**
- Consumes: `ProductResearchIntent.from_message(owner_user_id, message)`.
- Consumes: `ProductResearchScriptWorkflow.run(intent)`.
- Produces: CLI command `python scripts\product_research_script.py --owner 42 --message "..."`
- Produces: Telegram natural-message routing into `product_research_script` when the message contains product crawl/sheet/script intent.

- [ ] **Step 1: Write failing CLI test**

Create `tests/hermes/test_product_research_script_cli.py`:

```python
from __future__ import annotations

from types import SimpleNamespace


def test_product_research_script_cli_prints_report(monkeypatch, capsys):
    from scripts import product_research_script

    class FakeWorkflow:
        def run(self, intent):
            assert intent.owner_user_id == "42"
            return SimpleNamespace(to_report=lambda: "Run ID: run-1\nStatus: completed\n")

    monkeypatch.setattr(product_research_script, "build_workflow", lambda: FakeWorkflow())

    assert product_research_script.main(
        ["--owner", "42", "--message", "crawl ngành bàn phím, giá 200k-500k"]
    ) == 0
    assert "Status: completed" in capsys.readouterr().out
```

- [ ] **Step 2: Write failing Telegram routing test**

Create `tests/hermes/test_telegram_product_research_routing.py`:

```python
from __future__ import annotations


def test_product_research_detector_matches_sheet_and_script_request():
    import telegram_bot

    assert telegram_bot.is_product_research_script_request(
        "crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản"
    )
    assert not telegram_bot.is_product_research_script_request("hôm nay thời tiết sao")
```

- [ ] **Step 3: Run tests to verify failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_product_research_script_cli.py tests\hermes\test_telegram_product_research_routing.py -q
```

Expected: FAIL because CLI and Telegram detector do not exist.

- [ ] **Step 4: Implement CLI**

Create `scripts/product_research_script.py`:

```python
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def build_workflow():
    from hermes.adapters.google.sheets_projection import DisabledSheetsProjection, GoogleSheetsProjection
    from hermes.adapters.local.sheet_projection import LocalSheetProjection
    from hermes.adapters.model.affiliate_content_gateway import AffiliateContentGateway
    from hermes.adapters.sqlite.affiliate_research_repository import SQLiteAffiliateResearchRepository
    from hermes.affiliate_config import load_affiliate_research_settings
    from hermes.application.affiliate_catalog_service import AffiliateCatalogService
    from hermes.application.affiliate_content_service import AffiliateContentService
    from hermes.application.product_research_script_workflow import ProductResearchScriptWorkflow
    from hermes.application.product_source_selector import ProductSourceSelector
    from hermes.db import Database

    settings = load_affiliate_research_settings()
    repository = SQLiteAffiliateResearchRepository(Database())
    google_projection = (
        GoogleSheetsProjection.from_environment(repository)
        if settings.google_sheets_enabled
        else DisabledSheetsProjection()
    )
    return ProductResearchScriptWorkflow(
        repository=repository,
        catalog_service=AffiliateCatalogService(repository),
        content_service=AffiliateContentService(repository, AffiliateContentGateway()),
        source_selector=ProductSourceSelector(settings),
        local_projection=LocalSheetProjection(repository, settings.local_sheet_output_dir),
        google_projection=google_projection,
        shortlist_limit=settings.shortlist_limit,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Hermes product research sheet + script workflow")
    parser.add_argument("--owner", required=True, help="Owner user id")
    parser.add_argument("--message", required=True, help="Natural product research request")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    from hermes.application.product_research_intent import ProductResearchIntent

    intent = ProductResearchIntent.from_message(args.owner, args.message)
    result = build_workflow().run(intent)
    print(result.to_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Add minimal Telegram detector**

Modify `telegram_bot.py` near other text-routing helpers:

```python
def is_product_research_script_request(text: str) -> bool:
    lowered = (text or "").casefold()
    has_research = any(token in lowered for token in ("crawl", "tìm sản phẩm", "tim san pham", "ngành", "nganh"))
    has_output = any(token in lowered for token in ("sheet", "kịch bản", "kich ban", "script"))
    return has_research and has_output
```

If `default_chat_handler` has a clear routing block, insert this branch before generic chat response:

```python
    if is_product_research_script_request(user_text):
        await update.message.reply_text(
            "Mình nhận diện yêu cầu product research -> sheet -> kịch bản. "
            "Workflow CLI đã sẵn sàng; Telegram execution sẽ chạy qua queue có gate cấu hình."
        )
        return
```

- [ ] **Step 6: Run CLI and Telegram tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_product_research_script_cli.py tests\hermes\test_telegram_product_research_routing.py -q
```

Expected: PASS.

- [ ] **Step 7: Run full focused acceptance suite**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_intent.py tests\hermes\application\test_product_source_selector.py tests\hermes\adapters\local\test_sheet_projection.py tests\hermes\application\test_product_research_script_workflow.py tests\hermes\test_product_research_script_cli.py tests\hermes\test_telegram_product_research_routing.py tests\hermes\test_affiliate_research_acceptance.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit**

Run:

```powershell
git add -- scripts/product_research_script.py telegram_bot.py tests/hermes/test_product_research_script_cli.py tests/hermes/test_telegram_product_research_routing.py
git commit -m "feat: expose product research script workflow"
```

---

## Final Verification

- [ ] Run focused product research suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_research_intent.py tests\hermes\application\test_product_source_selector.py tests\hermes\adapters\local\test_sheet_projection.py tests\hermes\application\test_product_research_script_workflow.py tests\hermes\test_product_research_script_cli.py tests\hermes\test_telegram_product_research_routing.py -q
```

Expected: PASS.

- [ ] Run existing affiliate regression suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_research_acceptance.py tests\hermes\test_affiliate_research_job.py tests\hermes\application\test_affiliate_catalog_service.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\adapters\test_google_sheets_projection.py -q
```

Expected: PASS.

- [ ] Run one dry local CLI check with crawler disabled:

```powershell
$env:HERMES_ENABLE_MARKETPLACE_CRAWLER = "0"
.\.venv\Scripts\python.exe scripts\product_research_script.py --owner 42 --message "crawl ngành bàn phím, giá 200k-500k, xuất sheet rồi tạo kịch bản"
```

Expected output includes `Status: needs_csv_feed` and a warning asking for CSV/feed fallback.

## Self-Review Notes

- Spec coverage: intent routing, crawler-first source order, risk gates, local sheet output, optional Google Sheets, short script rows, and failure handling are each covered by a task.
- Placeholder scan: no incomplete implementation markers are intentionally present.
- Type consistency: `ProductResearchIntent`, `ProductSourceSelection`, `LocalSheetProjection`, and `ProductResearchScriptWorkflow` signatures are defined before use.
