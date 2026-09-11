# Phase 3 Daily Product Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automatically publish an ordered daily product pool from Product-Intelligence and have Hermes safely start three to five previously unproduced Product-to-Video workflows without repeating broad research.

**Architecture:** Product-Intelligence publishes immutable, digest-verified batches under `D:\work\TikTok\data-product\runs`. A small Hermes polling process validates those batches, records decisions in the existing SQLite database, copies claimed inputs into workflow-owned storage, and creates source-backed workflows directly at `AwaitingProductLock`. Existing approval, outbox, Resource Pack, rendering, and export paths remain authoritative.

**Tech Stack:** Python 3.11+, Pydantic, PyYAML-compatible existing YAML loader, SQLite, pathlib, hashlib, pytest, Ruff, Windows Task Scheduler.

## Global Constraints

- Do not move or restructure either Git repository.
- Product-Intelligence remains at `D:\work\Personal\Product-Intelligence` and Hermes remains at `D:\work\hermes-upstream-rearchitecture`.
- Behavioral paths and intervals belong in YAML config, not new environment variables.
- Product-Intelligence publishes eight to ten ordered candidates by default; Hermes starts only `target_count` eligible workflows, where `target_count` is between three and five.
- Hermes never edits or moves a published run and never conducts broad market research for a source-backed item.
- Keep the five existing Product-to-Video HITL gates unchanged.
- Keep optional image metadata non-blocking; require only identity, evidence, a persisted snapshot, provider bindings, and the configured minimum number of readable images.
- Use the existing SQLite workflow/outbox transaction boundary. Do not add RabbitMQ, Redis, Kafka, a DLQ, or a filesystem-watcher dependency.
- Use native PowerShell commands for verification on Windows.
- Commit Product-Intelligence changes in its repository and Hermes changes in its repository. Never combine the two repositories in one Git commit.

---

## Task 1: Product-Intelligence Request and Publication Contract

**Repository:** `D:\work\Personal\Product-Intelligence`

**Files:**
- Create: `product_scout/daily_contract.py`
- Create: `tests/test_daily_contract.py`

**Interfaces:**
- Produces: `DailyProductRequest`, `DailyProductItem`, `DailyProductBatch`, `load_daily_request()`, `sha256_file()`, `validate_published_run()`, and `publish_ready_marker()`.
- Consumes: Pydantic already used by Product-Intelligence and filesystem paths supplied by the caller.

- [ ] **Step 1: Write failing request-contract tests**

Create `tests/test_daily_contract.py` with these behavior tests:

```python
from pathlib import Path

import pytest

from product_scout.daily_contract import DailyProductRequest, load_daily_request


def test_load_daily_request_accepts_three_to_five_target(tmp_path: Path):
    request_path = tmp_path / "request.yaml"
    request_path.write_text(
        """schema: daily_product_request
version: 1
enabled: true
timezone: Asia/Bangkok
category: Gia dụng
market: VN
platforms: [tiktok]
price: {currency: VND, min: 200000, max: 1500000}
candidate_limit: 10
target_count: 3
minimum_images: 2
defaults: {image_provider: visual_browser, video_provider: vertex}
""",
        encoding="utf-8",
    )

    request = load_daily_request(request_path)

    assert request.target_count == 3
    assert request.candidate_limit == 10
    assert request.defaults.image_provider == "visual_browser"


@pytest.mark.parametrize("target_count", [2, 6])
def test_request_rejects_target_outside_daily_range(target_count: int):
    with pytest.raises(ValueError, match="target_count"):
        DailyProductRequest.model_validate(
            {
                "schema": "daily_product_request",
                "version": 1,
                "category": "Gia dụng",
                "candidate_limit": 10,
                "target_count": target_count,
            }
        )


def test_request_rejects_target_above_candidate_limit():
    with pytest.raises(ValueError, match="candidate_limit"):
        DailyProductRequest.model_validate(
            {
                "schema": "daily_product_request",
                "version": 1,
                "category": "Gia dụng",
                "candidate_limit": 3,
                "target_count": 5,
            }
        )
```

- [ ] **Step 2: Run the request tests and confirm the missing module failure**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_contract.py -q
```

Expected: collection fails with `ModuleNotFoundError: product_scout.daily_contract`.

- [ ] **Step 3: Implement the typed request and batch models**

Create `product_scout/daily_contract.py` with Pydantic models whose public shape is:

```python
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from pydantic import BaseModel, Field, model_validator
from yaml import safe_load


class PriceRange(BaseModel):
    currency: str = "VND"
    min: int = 0
    max: int | None = None


class ProviderDefaults(BaseModel):
    image_provider: str = "visual_browser"
    video_provider: str = "vertex"


class DailyProductRequest(BaseModel):
    schema: str = "daily_product_request"
    version: int = 1
    enabled: bool = True
    timezone: str = "Asia/Bangkok"
    category: str
    market: str = "VN"
    platforms: list[str] = Field(default_factory=lambda: ["tiktok"])
    price: PriceRange = Field(default_factory=PriceRange)
    candidate_limit: int = Field(default=10, ge=3, le=30)
    target_count: int = Field(default=3, ge=3, le=5)
    minimum_images: int = Field(default=2, ge=1)
    defaults: ProviderDefaults = Field(default_factory=ProviderDefaults)

    @model_validator(mode="after")
    def validate_target(self) -> "DailyProductRequest":
        if self.target_count > self.candidate_limit:
            raise ValueError("target_count cannot exceed candidate_limit")
        if self.price.max is not None and self.price.max < self.price.min:
            raise ValueError("price.max cannot be lower than price.min")
        return self


class DailyProductItem(BaseModel):
    product_key: str
    priority: int = Field(ge=1)
    product_path: str
    product_digest: str


class DailyProductBatch(BaseModel):
    schema: str = "daily_product_batch"
    version: int = 1
    run_id: str
    run_date: str
    published_at: str
    request_digest: str
    target_count: int = Field(ge=3, le=5)
    candidate_count: int = Field(ge=0)
    items: list[DailyProductItem]

    @model_validator(mode="after")
    def validate_items(self) -> "DailyProductBatch":
        if self.candidate_count != len(self.items):
            raise ValueError("candidate_count must equal len(items)")
        priorities = [item.priority for item in self.items]
        keys = [item.product_key for item in self.items]
        if len(priorities) != len(set(priorities)):
            raise ValueError("item priorities must be unique")
        if len(keys) != len(set(keys)):
            raise ValueError("product_key values must be unique within a run")
        return self


def load_daily_request(path: Path) -> DailyProductRequest:
    raw = safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("daily product request must be a YAML object")
    return DailyProductRequest.model_validate(raw)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def publish_ready_marker(run_dir: Path, manifest_path: Path) -> Path:
    digest = sha256_file(manifest_path)
    temporary = run_dir / "READY.tmp"
    ready = run_dir / "READY"
    temporary.write_text(f"{digest}\n", encoding="ascii")
    os.replace(temporary, ready)
    return ready
```

Add `validate_published_run(run_dir: Path) -> DailyProductBatch` in the same
file. It must validate the `READY` digest, parse `manifest.json`, reject
unsupported schema/version values, reject absolute or escaping
`product_path` values, and verify each `product_digest`.

- [ ] **Step 4: Add publication integrity tests**

Add tests that write one valid product and manifest, call
`publish_ready_marker()`, and assert `validate_published_run()` succeeds. Add
separate tests for a changed manifest, duplicate priority, absolute path, and
`../escape.json`; each must raise `ValueError` with the failing field in the
message.

- [ ] **Step 5: Run the focused contract tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_contract.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 1 in Product-Intelligence**

```powershell
git add product_scout\daily_contract.py tests\test_daily_contract.py
git commit -m "feat: define daily product batch contract"
```

---

## Task 2: Publish Daily Runner Output in the Shared Contract

**Repository:** `D:\work\Personal\Product-Intelligence`

**Files:**
- Modify: `product_scout/daily_runner.py`
- Modify: `scripts/daily_scout.py`
- Modify: `scripts/setup_windows_task.ps1`
- Modify: `tests/test_daily_scout.py`
- Create: `tests/test_daily_publication.py`

**Interfaces:**
- Consumes: Task 1 contract types and `ResearchPersistenceService.save()`.
- Produces: `DailyScoutRunner.run_daily()` output containing `run_id`,
  `manifest_path`, and `ready_path`; CLI option `--data-root`; a Windows task
  that passes the configured shared root explicitly.

- [ ] **Step 1: Write the failing publication test**

Create `tests/test_daily_publication.py`. Use injected fake discovery, media,
and snapshot functions so the test performs no network calls:

```python
from datetime import date
from pathlib import Path

from product_scout.daily_contract import validate_published_run
from product_scout.daily_runner import DailyScoutRunner


def test_daily_runner_publishes_ranked_ready_batch(
    tmp_path: Path,
    fake_discover_products,
    fake_acquire_images,
    fake_persist_snapshot,
):
    data_root = tmp_path / "data-product"
    request_path = data_root / "request.yaml"
    request_path.parent.mkdir(parents=True)
    request_path.write_text(VALID_REQUEST_YAML, encoding="utf-8")

    runner = DailyScoutRunner(
        base_dir=tmp_path,
        request_file=request_path,
        runs_dir=data_root / "runs",
        discover_products=fake_discover_products,
        acquire_images=fake_acquire_images,
        persist_snapshot=fake_persist_snapshot,
    )
    result = runner.run_daily(target_date=date(2026, 9, 11))

    run_dir = Path(result["output_dir"])
    batch = validate_published_run(run_dir)
    assert batch.target_count == 3
    assert [item.priority for item in batch.items] == list(range(1, len(batch.items) + 1))
    assert all((run_dir / item.product_path).is_file() for item in batch.items)
    assert (run_dir / "READY").is_file()
```

Define fixtures in the same test file. They must return two small valid PNG
files per product and a deterministic `{snapshot_id, persistence_status}`
result. Do not patch the filesystem contract functions under test.

- [ ] **Step 2: Run the test and verify it fails before runner integration**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_publication.py -q
```

Expected: failure because the existing runner writes `products.json` directly
under the date directory and does not publish the versioned batch contract.

- [ ] **Step 3: Add a narrow structured-request path to `DailyScoutRunner`**

Keep legacy `request.txt` support for existing callers. When the supplied
request path ends in `.yaml` or `.yml`, call `load_daily_request()` and map its
fields into the existing `ParsedCriteria`. Set discovery limit from
`candidate_limit`, not `target_count`.

Add injectable callables with production defaults:

```python
def __init__(
    self,
    base_dir: Path,
    request_file: Path | None = None,
    runs_dir: Path | None = None,
    discover_products=None,
    acquire_images=None,
    persist_snapshot=None,
) -> None:
    self.base_dir = Path(base_dir)
    self.request_file = request_file or self.base_dir / "request.txt"
    self.runs_dir = runs_dir or self.base_dir / "data" / "daily_runs"
    self._discover_products = discover_products or DailyPromptParser.discover_candidates
    self._acquire_images = acquire_images or self._acquire_product_images
    self._persist_snapshot = persist_snapshot or self._persist_daily_snapshot
```

Implement `_persist_daily_snapshot()` using the existing research models and
`ResearchPersistenceService`. The result must be a real retrievable snapshot
whose canonical identity, evidence references, and media asset paths correspond
to the published product. If the persistence status is not `saved`, omit that
candidate from the published pool and log the reason.

- [ ] **Step 4: Publish one immutable run directory**

Use a stable run ID such as `pi-<date>-<first_8_hex(request_digest)>`. For each
admitted candidate, write `products/<safe_product_key>/product.json`, then build
`manifest.json`, validate it, and write `READY` last. Return these additional
fields from `run_daily()`:

```python
return {
    "status": "success",
    "date": day_str,
    "run_id": batch.run_id,
    "total_products": len(batch.items),
    "products_with_images": sum(bool(product["images"]) for product in products),
    "manifest_path": str(manifest_path),
    "ready_path": str(ready_path),
    "output_dir": str(run_dir),
}
```

Write the existing Markdown report inside the same run directory. Stop treating
the legacy `products.json` file as the completion marker; completion is a valid
`READY` file.

- [ ] **Step 5: Add `--data-root` to the CLI and Task Scheduler setup**

In `scripts/daily_scout.py`, add:

```python
p_run.add_argument("--data-root", type=Path, required=True)
```

Construct the runner with:

```python
data_root = args.data_root.resolve()
runner = DailyScoutRunner(
    base_dir=PROJECT_ROOT,
    request_file=data_root / "request.yaml",
    runs_dir=data_root / "runs",
)
```

In `scripts/setup_windows_task.ps1`, accept a required parameter and pass it to
the existing batch/CLI invocation without placing secrets in the command line:

```powershell
param(
    [Parameter(Mandatory = $true)]
    [string]$DataProductRoot,
    [string]$DailyTime = "07:00"
)
```

Update the task description to refer to `request.yaml` and use `$DailyTime` for
the trigger. Preserve `StartWhenAvailable` and `MultipleInstances IgnoreNew`.

- [ ] **Step 6: Run all focused Product-Intelligence tests**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_contract.py tests\test_daily_scout.py tests\test_daily_publication.py -q
```

Expected: all tests pass without network access.

- [ ] **Step 7: Commit Task 2 in Product-Intelligence**

```powershell
git add product_scout\daily_runner.py scripts\daily_scout.py scripts\setup_windows_task.ps1 tests\test_daily_scout.py tests\test_daily_publication.py
git commit -m "feat: publish scheduled product batches"
```

---

## Task 3: Hermes Daily Source Ledger and Cursor-aware Workflow Commit

**Repository:** `D:\work\hermes-upstream-rearchitecture`

**Files:**
- Modify: `hermes_personal/storage/sqlite.py`
- Modify: `hermes_personal/workflows/repository.py`
- Create: `tests/hermes_personal/product_video/test_daily_automation_repository.py`

**Interfaces:**
- Produces: SQLite tables `daily_product_run` and `daily_product_item`.
- Produces: `WorkflowRepository.commit_workflow()` with an optional `cursor` so the
  coordinator can commit its claim and workflow creation in one transaction.

- [ ] **Step 1: Write failing schema and transaction tests**

Create `tests/hermes_personal/product_video/test_daily_automation_repository.py`:

```python
import json

import pytest

from hermes_personal.storage.sqlite import connect
from hermes_personal.workflows.repository import WorkflowRepository


def test_daily_product_tables_are_created(tmp_path):
    conn = connect(tmp_path / "hermes.db")
    names = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"daily_product_run", "daily_product_item"} <= names


def test_cursor_commit_rolls_back_workflow_with_outer_transaction(tmp_path):
    conn = connect(tmp_path / "hermes.db")
    repo = WorkflowRepository(conn)

    with pytest.raises(RuntimeError, match="rollback"):
        with conn:
            cursor = conn.cursor()
            repo.commit_workflow(
                workflow_id="wf-atomic",
                aggregate_json=json.dumps({"state": "AwaitingProductLock"}),
                events=[],
                expected_version=0,
                cursor=cursor,
            )
            raise RuntimeError("rollback")

    assert repo.get_workflow("wf-atomic") is None
```

- [ ] **Step 2: Run the focused tests and verify failure**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_repository.py -q
```

Expected: schema assertions fail and `commit_workflow()` rejects `cursor`.

- [ ] **Step 3: Add the two ledger tables to `SCHEMA_SQL`**

Add the exact SQL from section 12 of the approved design spec, including both
unique constraints and `daily_product_item_identity_idx`. Keep migrations
additive through `CREATE TABLE IF NOT EXISTS`; do not alter existing workflow
tables.

- [ ] **Step 4: Make `WorkflowRepository.commit_workflow` cursor-aware**

Add an optional cursor argument:

```python
def commit_workflow(
    self,
    workflow_id: str,
    aggregate_json: str,
    events: list[dict[str, Any]],
    outbox_message: str | None = None,
    expected_version: int | None = None,
    cursor: sqlite3.Cursor | None = None,
) -> CommitResult:
```

Move the current SQL body into a private `_commit_workflow` method that receives
the cursor and the existing commit arguments. When `cursor`
is supplied, execute without opening or closing a transaction. When it is
absent, retain the current `with self.conn:` behavior. Do not change version,
duplicate-command, event, or outbox semantics.

- [ ] **Step 5: Run repository regression tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_repository.py tests/hermes_personal/workflows -q
```

Expected: all tests pass and the rollback test proves the outer transaction
owns the commit.

- [ ] **Step 6: Commit Task 3 in Hermes**

```powershell
git add hermes_personal\storage\sqlite.py hermes_personal\workflows\repository.py tests\hermes_personal\product_video\test_daily_automation_repository.py
git commit -m "feat: add daily product source ledger"
```

---

## Task 4: Hermes Batch Reader and Safe Input Materialization

**Repository:** `D:\work\hermes-upstream-rearchitecture`

**Files:**
- Create: `hermes_personal/product_video/daily_automation.py`
- Create: `tests/hermes_personal/product_video/test_daily_automation_reader.py`

**Interfaces:**
- Produces: `DailyAutomationConfig`, `SourceBatch`, `SourceProduct`,
  `discover_ready_runs()`, `load_source_batch()`, and
  `materialize_workflow_input()`.
- Consumes: the exact version-1 JSON contract from Task 1 without importing the
  Product-Intelligence package.

- [ ] **Step 1: Write failing reader security tests**

Create tests that build batch fixtures directly in `tmp_path` and assert:

```python
def test_reader_ignores_run_without_ready(tmp_path):
    run_dir = write_source_run(tmp_path, ready=False)
    assert discover_ready_runs(tmp_path) == []


def test_reader_rejects_manifest_digest_mismatch(tmp_path):
    run_dir = write_source_run(tmp_path, ready=True)
    (run_dir / "manifest.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SourceContractError, match="READY digest"):
        load_source_batch(run_dir)


@pytest.mark.parametrize("bad_path", ["../outside.json", "C:/outside.json"])
def test_reader_rejects_escaping_product_path(tmp_path, bad_path):
    run_dir = write_source_run(tmp_path, product_path=bad_path, ready=True)
    with pytest.raises(SourceContractError, match="product_path"):
        load_source_batch(run_dir)
```

Also test image digest mismatch, a junction/symlink payload when supported by
the host, and one valid two-image product.

- [ ] **Step 2: Run the reader tests and verify the missing module failure**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_reader.py -q
```

Expected: `ModuleNotFoundError` for `daily_automation`.

- [ ] **Step 3: Implement strict local contract dataclasses**

In `daily_automation.py`, define frozen dataclasses rather than adding a new
runtime dependency:

```python
@dataclass(frozen=True)
class DailyAutomationConfig:
    source_root: Path
    work_root: Path
    export_root: Path
    poll_interval_seconds: float = 60.0
    owner_user_id: str = "local-owner"


@dataclass(frozen=True)
class SourceProduct:
    run_id: str
    run_date: str
    product_key: str
    priority: int
    product_digest: str
    product_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class SourceBatch:
    run_id: str
    run_date: str
    manifest_digest: str
    target_count: int
    run_dir: Path
    products: Sequence[SourceProduct]
```

Parse only `schema= daily_product_batch`, `version=1`, and
`schema=product_video_source`, `version=1`. Reject booleans where integer fields
are required. Sort by numeric `priority` after enforcing uniqueness.

- [ ] **Step 4: Implement containment, digest, image, and copy checks**

Use helpers with these exact signatures:

```python
def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def resolve_child(root: Path, relative: str, field: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        raise SourceContractError(f"{field} must be relative")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise SourceContractError(f"{field} escapes run directory") from exc
    if resolved.is_symlink():
        raise SourceContractError(f"{field} cannot be a symlink")
    return resolved


def load_source_batch(run_dir: Path) -> SourceBatch:
    manifest_path = run_dir / "manifest.json"
    ready_digest = (run_dir / "READY").read_text(encoding="ascii").strip()
    if ready_digest != sha256_path(manifest_path):
        raise SourceContractError("READY digest does not match manifest.json")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if raw.get("schema") != "daily_product_batch" or raw.get("version") != 1:
        raise SourceContractError("unsupported daily product batch schema/version")
    products: list[SourceProduct] = []
    for item in raw["items"]:
        product_path = resolve_child(run_dir, item["product_path"], "product_path")
        if sha256_path(product_path) != item["product_digest"]:
            raise SourceContractError("product_digest mismatch")
        payload = json.loads(product_path.read_text(encoding="utf-8"))
        products.append(parse_and_validate_product(raw, item, product_path, payload))
    validate_unique_priorities_and_keys(products)
    return SourceBatch(
        run_id=raw["run_id"],
        run_date=raw["run_date"],
        manifest_digest=ready_digest,
        target_count=raw["target_count"],
        run_dir=run_dir.resolve(),
        products=tuple(sorted(products, key=lambda product: product.priority)),
    )


def materialize_workflow_input(product: SourceProduct, destination: Path) -> Path:
    temporary = destination.with_name(f"{destination.name}.tmp")
    prepare_empty_bounded_directory(temporary, destination.parent)
    shutil.copy2(product.product_path, temporary / "product.json")
    copy_validated_images(product, temporary / "images")
    (temporary / "SOURCE_DIGEST").write_text(product.product_digest, encoding="ascii")
    if destination.exists():
        verify_existing_materialization(destination, product.product_digest)
        shutil.rmtree(temporary)
        return destination
    os.replace(temporary, destination)
    return destination
```

The implementation must stream hashes, reject absolute paths, call
`resolved.relative_to(root.resolve())`, reject symlinks/junctions, use the
existing image decoder/validation helper, and copy through a sibling
`<workflow_id>.tmp` directory before an atomic rename to the final input path.
If the final directory already contains the same product digest, return it
unchanged. If it contains another digest, raise `SourceConflictError`.

- [ ] **Step 5: Run the reader tests and Ruff**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_reader.py -q
uv run ruff check hermes_personal\product_video\daily_automation.py tests\hermes_personal\product_video\test_daily_automation_reader.py
```

Expected: all checks pass.

- [ ] **Step 6: Commit Task 4 in Hermes**

```powershell
git add hermes_personal\product_video\daily_automation.py tests\hermes_personal\product_video\test_daily_automation_reader.py
git commit -m "feat: validate daily product source batches"
```

---

## Task 5: Start a Source-backed Workflow at Product Lock

**Repository:** `D:\work\hermes-upstream-rearchitecture`

**Files:**
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/product_video/__init__.py`
- Create: `tests/hermes_personal/product_video/test_source_workflow_start.py`

**Interfaces:**
- Produces: `start_product_video_from_source()` with an optional cursor and a
  string workflow ID result.
- Consumes: cursor-aware `WorkflowRepository.commit_workflow()`, cursor-aware
  `ApprovalService.submit_request()`, and a validated source product.

- [ ] **Step 1: Write the failing source-start behavior test**

```python
def test_source_start_enters_product_lock_without_research(tmp_path):
    conn = connect(tmp_path / "hermes.db")
    repo = WorkflowRepository(conn)
    source = valid_source_product_payload()

    workflow_id = start_product_video_from_source(
        workflow_repository=repo,
        workflow_id="pv-run-a38f27a912bc",
        project_id="proj-pv-run-a38f27a912bc",
        owner_user_id="owner-1",
        source_run_id="pi-2026-09-11-01",
        source_product=source,
        source_digest="sha256:abc",
        image_provider="visual_browser",
        video_provider="vertex",
        idempotency_key="daily-source:pi-2026-09-11-01:key",
    )

    aggregate, version = repo.get_workflow(workflow_id)
    assert version == 1
    assert aggregate["state"] == "AwaitingProductLock"
    assert aggregate["source_run_id"] == "pi-2026-09-11-01"
    assert aggregate["image_provider"] == "visual_browser"
    assert aggregate["video_provider"] == "vertex"
    assert aggregate["pending_approval_id"]
    assert conn.execute(
        "SELECT COUNT(*) FROM workflow_outbox WHERE workflow_id=?",
        (workflow_id,),
    ).fetchone()[0] == 0
```

Add a second test that calls the function twice and expects the same workflow
ID with one event and one approval request. Add a third test that approves the
request and proves the next outbox job is `product_video.resource_pack`, not
`product_video.research`.

- [ ] **Step 2: Run the test and verify the missing entry point failure**

```powershell
uv run pytest tests/hermes_personal/product_video/test_source_workflow_start.py -q
```

Expected: import failure for `start_product_video_from_source`.

- [ ] **Step 3: Implement source-backed start atomically**

Add the function beside `start_product_video_workflow()`. Validate the required
snapshot and provider fields, create the Product Lock approval with
`ApprovalService.submit_request()` with the same cursor, then commit:

```python
aggregate = {
    "state": ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value,
    "project_id": project_id,
    "owner_user_id": owner_user_id,
    "source_mode": "daily_product_batch",
    "source_run_id": source_run_id,
    "source_digest": source_digest,
    "product_key": source_product["product_key"],
    "image_provider": image_provider,
    "video_provider": video_provider,
    "latest_artifact": {
        **source_product["research"],
        "artifact_id": source_product["research"]["snapshot_id"],
        "version": 1,
        "product": source_product,
    },
    "pending_approval_id": approval_request_id,
    "pending_approval_gate": ProductVideoWorkflowState.AWAITING_PRODUCT_LOCK.value,
}
```

The approval payload must contain the exact workflow, owner, project, gate,
artifact ID, artifact version, and `workflow_version=1` bindings enforced by
`approve_and_advance_workflow()`.

When `cursor` is absent, open one `with repo.conn:` transaction. When supplied,
participate in the caller's transaction. If the deterministic workflow already
exists with the same source digest, return it unchanged. If it exists with a
different digest, raise `SourceConflictError`.

- [ ] **Step 4: Export the entry point and run approval regressions**

Export the function from `hermes_personal/product_video/__init__.py`, then run:

```powershell
uv run pytest tests/hermes_personal/product_video/test_source_workflow_start.py tests/hermes_personal/product_video/test_happy_path_e2e.py -q
```

Expected: the source path reaches Gate 1 directly and the existing normal path
still starts with research.

- [ ] **Step 5: Commit Task 5 in Hermes**

```powershell
git add hermes_personal\product_video\handlers.py hermes_personal\product_video\__init__.py tests\hermes_personal\product_video\test_source_workflow_start.py
git commit -m "feat: start product video from published source"
```

---

## Task 6: Duplicate-aware Ordered Coordinator

**Repository:** `D:\work\hermes-upstream-rearchitecture`

**Files:**
- Modify: `hermes_personal/product_video/daily_automation.py`
- Create: `tests/hermes_personal/product_video/test_daily_automation_coordinator.py`

**Interfaces:**
- Produces: `DailyProductCoordinator.scan_once() -> ScanReport` and repository
  methods for ingesting runs, recording item decisions, and querying production
  history.
- Consumes: Task 4 reader/materializer and Task 5 source-backed entry point.

- [ ] **Step 1: Write the failing ordered-selection test**

Build one ready batch with ten products and `target_count=3`. Seed the workflow
database so rank 1 is completed, rank 2 is active, and rank 3 is invalid. Assert
ranks 4, 5, and 6 are claimed:

```python
report = coordinator.scan_once()

assert report.claimed_product_keys == ("product-04", "product-05", "product-06")
assert report.completed_duplicates == 1
assert report.active_duplicates == 1
assert report.invalid == 1
assert connection.execute(
    "SELECT COUNT(*) FROM workflow WHERE workflow_id LIKE 'pv-%'"
).fetchone()[0] == 5
```

The count includes the two seeded workflows. Add assertions for the exact
`skipped_duplicate` and `skipped_invalid` reasons in the ledger.

- [ ] **Step 2: Write replay and transaction-failure tests**

Run `scan_once()` twice and assert workflow/event/approval counts do not change.
Inject a failure immediately before outer transaction commit and assert neither
the `claimed` ledger row nor workflow exists afterward. Then rerun normally and
assert one workflow is created.

- [ ] **Step 3: Run tests and verify coordinator failures**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_coordinator.py -q
```

Expected: failures because the coordinator and ledger repository methods do not
exist.

- [ ] **Step 4: Implement the ledger repository in the existing module**

Add `DailyProductLedger` to `daily_automation.py`. Its public methods are
`ingest_run(batch: SourceBatch) -> None`,
`production_status(product_key: str) -> str`,
`record_skip(queue_id: str, run_id: str, product: SourceProduct, status: str,
reason: str) -> None`, and `claimed_count(run_id: str) -> int`.

`ingest_run()` inserts `daily_product_run` and all item rows with
SQLite `INSERT OR IGNORE`, then compares the stored manifest digest
with the incoming digest and raises `SourceConflictError` when they differ.
`record_skip()` updates only rows still in `new`. `claimed_count()` executes
`SELECT COUNT(*) FROM daily_product_item WHERE run_id=? AND status='claimed'`.

`production_status()` joins earlier claimed items to `workflow` and
`workflow_outbox`:

- workflow aggregate `state=completed` returns `completed`;
- pending or leased outbox, or any HITL state, returns `active`;
- quarantined outbox for a non-completed workflow returns `terminal_failure`;
- no earlier claimed item returns `new`.

- [ ] **Step 5: Implement `DailyProductCoordinator.scan_once()`**

Use this control flow exactly:

```python
for run_dir in discover_ready_runs(self.config.source_root):
    batch = load_source_batch(run_dir)
    self.ledger.ingest_run(batch)
    needed = batch.target_count - self.ledger.claimed_count(batch.run_id)
    if needed <= 0:
        continue

    for product in batch.products:
        if needed <= 0:
            break
        decision = self.ledger.production_status(product.product_key)
        if decision != "new":
            self.ledger.record_duplicate(batch, product, decision)
            continue
        try:
            workflow_id = self.claim_product(batch, product)
        except SourceValidationError as exc:
            self.ledger.record_invalid(batch, product, str(exc))
            continue
        claimed.append((product.product_key, workflow_id))
        needed -= 1
```

`claim_product()` materializes input first, then opens one SQLite transaction
that inserts the claimed item and calls `start_product_video_from_source()` with
the same cursor. Generate IDs using the formulas in section 10 of the approved
spec. Catch unique-constraint races by re-reading the deterministic workflow;
do not generate a random replacement ID.

- [ ] **Step 6: Run coordinator, source-start, and workflow tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_daily_automation_coordinator.py tests/hermes_personal/product_video/test_source_workflow_start.py tests/hermes_personal/product_video -q
```

Expected: all Product-to-Video tests pass.

- [ ] **Step 7: Commit Task 6 in Hermes**

```powershell
git add hermes_personal\product_video\daily_automation.py tests\hermes_personal\product_video\test_daily_automation_coordinator.py
git commit -m "feat: coordinate ordered daily video work"
```

---

## Task 7: Runtime Configuration and Supervised Polling Process

**Repository:** `D:\work\hermes-upstream-rearchitecture`

**Files:**
- Modify: `hermes_personal/runtime/config.py`
- Modify: `hermes_personal/runtime/processes.py`
- Modify: `tests/hermes_personal/runtime/test_processes.py`
- Modify: `hermes_personal/product_video/daily_automation.py`
- Create: `tests/hermes_personal/product_video/test_daily_automation_runner.py`

**Interfaces:**
- Produces: nested `DailyProductAutomationRuntimeConfig` loaded from
  `personal.product_video.automation` and CLI entry
  `python -m hermes_personal.product_video.daily_automation`.
- Consumes: `DailyProductCoordinator.scan_once()`.

- [ ] **Step 1: Write failing config and topology tests**

Add a config-loading test with:

```yaml
runtime:
  mode: development
  enable_telegram: false
  enable_web: false
personal:
  product_video:
    automation:
      enabled: true
      source_root: D:\work\TikTok\data-product\runs
      work_root: D:\work\TikTok\data-product\work
      export_root: D:\work\TikTok\export
      poll_interval_seconds: 60
      owner_user_id: local-owner
```

Assert `build_process_topology()` contains exactly one optional process named
`daily_product_automation`, invoked with argument-array entries rather than a
shell command string. Add a disabled-config test asserting the process is
absent. Add validation tests for missing roots and a non-positive interval.

- [ ] **Step 2: Run the config tests and verify failure**

```powershell
uv run pytest tests/hermes_personal/runtime/test_processes.py -q
```

Expected: failures because the nested config and process are not recognized.

- [ ] **Step 3: Add the nested runtime config**

Define:

```python
@dataclass(frozen=True)
class DailyProductAutomationRuntimeConfig:
    enabled: bool = False
    source_root: Path | None = None
    work_root: Path | None = None
    export_root: Path | None = None
    poll_interval_seconds: float = 60.0
    owner_user_id: str = "local-owner"
```

Add it as `daily_product_automation` on `RuntimeConfig`. Parse only the
`personal.product_video.automation` mapping in `RuntimeConfig.from_file()`.
When enabled, require all three roots, positive interval, and a non-empty owner.

- [ ] **Step 4: Register the optional supervised process**

Add this shape to `build_process_topology()` after `durable_worker`:

```python
if config.daily_product_automation.enabled:
    automation = config.daily_product_automation
    specs.append(
        ProcessSpec(
            name="daily_product_automation",
            argv=(
                py,
                "-m",
                "hermes_personal.product_video.daily_automation",
                "--source-root",
                str(automation.source_root),
                "--work-root",
                str(automation.work_root),
                "--export-root",
                str(automation.export_root),
                "--poll-interval",
                str(automation.poll_interval_seconds),
                "--owner-user-id",
                automation.owner_user_id,
            ),
            cwd=root,
            env_keys=("HERMES_HOME",),
            required=False,
            readiness_probe=ProbeSpec(probe_type="noop"),
        )
    )
```

Do not put any credential values in `argv`.

- [ ] **Step 5: Implement the runner loop and one-shot mode**

Add `main(argv=None) -> int` to `daily_automation.py` with explicit arguments
for all roots, owner, polling interval, and `--once`. The loop must scan
immediately, sleep only after a completed scan, return non-zero for fatal manifest
or database initialization failures, and continue after an item-level error.

Use an injectable `stop_event` and clock in the loop function so tests do not
sleep:

```python
def run_poll_loop(
    coordinator: DailyProductCoordinator,
    *,
    poll_interval_seconds: float,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        coordinator.scan_once()
        stop_event.wait(poll_interval_seconds)
```

- [ ] **Step 6: Test startup catch-up and bounded logging**

In `test_daily_automation_runner.py`, publish a ready run before constructing
the coordinator, call `main()` with the explicit root arguments and `--once`,
and assert it is ingested.
Call it again and assert no new workflow and no repeated per-item completion
log. Test that one invalid product logs once and later valid products are still
claimed.

- [ ] **Step 7: Run runtime and Product-to-Video verification**

```powershell
uv run pytest tests/hermes_personal/runtime/test_processes.py tests/hermes_personal/product_video/test_daily_automation_runner.py tests/hermes_personal/product_video -q
uv run ruff check hermes_personal tests/hermes_personal
```

Expected: all tests and Ruff pass.

- [ ] **Step 8: Commit Task 7 in Hermes**

```powershell
git add hermes_personal\runtime\config.py hermes_personal\runtime\processes.py hermes_personal\product_video\daily_automation.py tests\hermes_personal\runtime\test_processes.py tests\hermes_personal\product_video\test_daily_automation_runner.py
git commit -m "feat: supervise daily product automation"
```

---

## Task 8: Export Layout, Cross-repository E2E, and Operator Documentation

**Repositories:** Both repositories; commit separately.

**Hermes files:**
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Create: `tests/hermes_personal/product_video/test_daily_automation_e2e.py`
- Modify: `docs/README.md`

**Product-Intelligence files:**
- Create: `docs/daily-product-automation.md`
- Create locally during cutover: `D:\work\TikTok\data-product\request.yaml`

**Interfaces:**
- Produces: deterministic final output under
  `<export_root>/<run_date>/<safe_product_key>/<workflow_id>/` and a complete
  cross-repository operating guide.
- Consumes: all earlier tasks and the existing fake Video Factory path for E2E.

- [ ] **Step 1: Write the failing export-layout test**

Create a workflow aggregate with `run_date`, `product_key`, `workflow_id`, and
`export_root`, then call the existing final export path through the handler.
Assert:

```python
expected_dir = export_root / "2026-09-11" / "jisulife-life-7-default" / workflow_id
assert (expected_dir / "final.mp4").read_bytes() == rendered_bytes
metadata = json.loads((expected_dir / "metadata.json").read_text(encoding="utf-8"))
assert metadata["source_run_id"] == "pi-2026-09-11-01"
assert metadata["product_key"] == "jisulife:life-7:default"
assert metadata["image_provider"] == "visual_browser"
assert metadata["video_provider"] == "vertex"
```

- [ ] **Step 2: Pass a bounded destination contract into export**

In `ProductVideoJobHandlers.export_job()`, derive the destination from the
trusted workflow aggregate, not from model-supplied parameters:

```python
params["automation_export"] = {
    "export_root": workflow_agg["export_root"],
    "run_date": workflow_agg["run_date"],
    "product_key": workflow_agg["product_key"],
    "workflow_id": ctx.workflow_id,
    "source_run_id": workflow_agg["source_run_id"],
    "image_provider": workflow_agg["image_provider"],
    "video_provider": workflow_agg["video_provider"],
}
```

In `video_factory/server.py`, accept this internal structure, sanitize the
product key for a directory name, resolve the destination beneath
`export_root`, copy the approved MP4 as `final.mp4`, and atomically write
`metadata.json`. Preserve the existing workspace export behavior when
`automation_export` is absent.

- [ ] **Step 3: Write the full Phase 3 E2E test**

The test must:

1. Produce a real version-1 batch fixture with ten items and `target_count=3`.
2. Seed one completed duplicate, one active duplicate, and one invalid image.
3. Run the coordinator once.
4. Assert ranks 4, 5, and 6 own the only three new workflows.
5. Assert all three are at `AwaitingProductLock` with no research outbox.
6. Restart the coordinator and assert all workflow, event, approval, and outbox
   counts remain unchanged.
7. Advance one workflow through the existing fake-provider five-gate path.
8. Assert a non-empty `final.mp4` and correct `metadata.json` exist under the
   configured export root.

- [ ] **Step 4: Add operating documentation**

Document these exact commands in Product-Intelligence:

```powershell
.\scripts\setup_windows_task.ps1 -DataProductRoot 'D:\work\TikTok\data-product' -DailyTime '07:00'
.\.venv\Scripts\python.exe scripts\daily_scout.py run --data-root 'D:\work\TikTok\data-product'
```

Document the Hermes YAML block from the approved spec and these inspection
queries:

```sql
SELECT run_id, status, imported_at, last_error
FROM daily_product_run
ORDER BY imported_at DESC;

SELECT run_id, priority, product_key, status, workflow_id, skip_reason
FROM daily_product_item
ORDER BY run_id DESC, priority ASC;
```

Explain that deleting or moving a published run while a workflow is active is
unsupported, and that `work/` may be cleaned only after the workflow is
completed and its export digest is verified.

- [ ] **Step 5: Run final verification in Product-Intelligence**

From `D:\work\Personal\Product-Intelligence`:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_daily_contract.py tests\test_daily_scout.py tests\test_daily_publication.py -q
```

Expected: all focused tests pass.

- [ ] **Step 6: Run final verification in Hermes**

From `D:\work\hermes-upstream-rearchitecture`:

```powershell
uv run pytest tests/hermes_personal/product_video -q
uv run pytest tests/hermes_personal/runtime -q
uv run ruff check hermes_personal tests/hermes_personal
```

Expected: all tests and Ruff pass. Before an upstream PR, additionally run
`scripts/run_tests.sh` from a supported shell as required by the repository.

- [ ] **Step 7: Perform a local dry run without paid providers**

Create `D:\work\TikTok\data-product\request.yaml` from the approved request
example. Publish one fixture or real discovery batch, then run Hermes automation
once in fake provider mode. Verify:

```powershell
uv run python -m hermes_personal.product_video.daily_automation `
  --source-root 'D:\work\TikTok\data-product\runs' `
  --work-root 'D:\work\TikTok\data-product\work' `
  --export-root 'D:\work\TikTok\export' `
  --owner-user-id 'local-owner' `
  --once
```

Expected: the summary reports the correct candidate, duplicate, invalid, and
claimed counts; exactly `target_count` workflows wait at Product Lock; a second
run reports no new claims.

- [ ] **Step 8: Commit documentation in Product-Intelligence**

From `D:\work\Personal\Product-Intelligence`:

```powershell
git add docs\daily-product-automation.md
git commit -m "docs: explain daily product publication"
```

- [ ] **Step 9: Commit E2E and documentation in Hermes**

From `D:\work\hermes-upstream-rearchitecture`:

```powershell
git add hermes_personal\product_video\handlers.py hermes_personal\integrations\video_factory\server.py tests\hermes_personal\product_video\test_daily_automation_e2e.py docs\README.md
git commit -m "feat: complete daily product automation phase 3"
```

---

## Completion Review

Before declaring Phase 3 complete, verify these invariants from fresh command
output:

- A run is invisible until `READY` contains the exact manifest digest.
- The same `run_id` and digest can be replayed safely; a changed digest is
  rejected.
- Product identity deduplication works across different daily runs.
- Skipped items do not consume the daily target.
- Claimed items consume the target even while awaiting human approval.
- Source-backed workflows contain no `product_video.research` job.
- Product Lock approval uses the persisted source snapshot.
- A single bad product does not stop later priorities.
- Restarting either process creates no duplicate workflow or paid request.
- The final exported MP4 and metadata are under the configured export root.
- No new core model tool, non-secret environment variable, broker, or duplicate
  workflow state machine was introduced.
