# Affiliate Final Review Fix Report

## Status

DONE

Implementation commit:

- `57b869749 fix: complete affiliate final review wave`

The workspace still contains unrelated user changes. They were preserved and
were not staged with this fix wave.

## Findings Closed

### Dedicated Worker And Queue Isolation

- Added `scripts/affiliate_research_worker.py` as a runnable production entry
  point with `--once` and bounded polling modes.
- Worker startup recovers interrupted queue jobs.
- Untyped `JobRepository.claim_next()` excludes
  `affiliate_product_research`; only an explicit typed claim can take those
  jobs.
- Added startup, recovery, legacy claim, and dedicated claim isolation tests.

### Crash-Durable Completion And Projections

- Added the V4 `affiliate_projection_outbox`.
- `complete_run()` updates run status/counters and creates Sheets/Telegram
  outbox records in one immediate SQLite transaction.
- Pending outbox records are replayed by a fresh process after completion.
- Projection outcomes atomically update outbox checkpoint state and durable run
  failure counters.
- V3 retryable/non-retryable projection failures are backfilled into V4.
- Fault injection proves a bad outbox record rolls back run completion.

### Idempotent Package Generation And Atomic Revision

- Initial package IDs are deterministic for `(owner, run, product, revision)`.
- A retry skips already persisted products without another model call.
- Revision retries check deterministic lineage before invoking the gateway.
- Revision payloads are generated and validated before persistence.
- `save_revision()` atomically inserts the child revision, appends the approval
  event, and transitions the parent.
- Fault injection on approval-event insertion proves child insert and parent
  transition both roll back.
- Telegram's Revise button now only instructs the user to run
  `/affiliate_revise <package_id> <feedback>`; it does not transition canonical
  state.
- Command generation/validation failure leaves the parent unchanged.

### Run-Scoped Catalog And Intake

- Added the V4 `affiliate_run_products` observation table.
- Imports persist run/product observations and stale snapshot warnings.
- Scoring, shortlisting, references, and Sheets product projection use the
  current run instead of the owner's historical catalog.
- Run counters retain imported, updated, rejected, error, shortlisted, and
  packaged counts.
- Production job validation requires 100 to 200 valid CSV candidates while
  parser and catalog unit interfaces continue to support small fixtures.
- Integer parsing is strict; sold/review counts must be nonnegative integers,
  ratings must be 0 through 5, and commission rates must be 0 through 1.

### TikTok Production Wiring

- Added `TikTokReferenceCollector` to production composition.
- Submitted URLs are deterministically associated with sorted owner-scoped run
  products.
- Metadata is persisted through the canonical repository.
- References carry `source_type` and `content_hash`.
- Invalid, unavailable, or unauthorized URLs are permanent job errors;
  transport failures remain retryable.
- No media is downloaded.

### Canonical Briefs, Angles, And Evidence

- Added the V4 `affiliate_research_briefs` table with revision, verified specs,
  strengths, limitations, unverified claims, and abstract reference patterns.
- Content planning persists three ranked angles with score, rank, rationale,
  and one selected winner before package generation.
- The production model adapter receives the canonical brief and selected angle.
- Claims must resolve to owner-scoped product/reference evidence.
- Canonical claims persist evidence URL, source type, content hash, and
  collection time.
- Unsupported and stale evidence is rejected.
- Output wording is checked against reference title/caption overlap.
- AI prompts are augmented to preserve the supplied product's exact physical
  design, controls, proportions, and colors.

### Telegram And Sheets

- Telegram delivery uses the product image when available.
- Review content includes actual canonical score and score reason.
- Photo captions are bounded to 1,024 characters; text fallback is bounded to
  4,096 characters.
- Async photo failures safely fall back to a text message.
- Callback payloads of exactly 64 bytes are accepted.
- Sheets reconciliation keeps canonical columns authoritative while preserving
  `review_notes`, `operator_notes`, and `custom_*` operator columns.
- Added an edit-survives-resync test.

## V4 Migration

Created `hermes/adapters/sqlite/schema_v4.py` and advanced
`SCHEMA_VERSION`/`PRAGMA user_version` to 4.

New tables:

- `affiliate_run_products`
- `affiliate_projection_outbox`
- `affiliate_research_briefs`

New columns:

- `affiliate_references.source_type`
- `affiliate_references.content_hash`
- `affiliate_content_ideas.score`
- `affiliate_content_ideas.rank`
- `affiliate_content_ideas.selected`

Backfills:

- Existing V3 ideas/packages populate run/product observations.
- Existing V3 Sheets/Telegram projection failure counters populate outbox
  checkpoints.
- Partial V4 migration retries detect and add only missing columns.

## Changed Files

Production and composition:

- `core/affiliate_research_jobs.py`
- `scripts/affiliate_research_worker.py`
- `telegram_bot.py`

Domain, ports, queue, and database:

- `hermes/db.py`
- `hermes/jobs.py`
- `hermes/domain/affiliate_research.py`
- `hermes/ports/affiliate_research.py`

Application modules:

- `hermes/application/affiliate_catalog_service.py`
- `hermes/application/affiliate_content_service.py`
- `hermes/application/affiliate_reference_service.py`
- `hermes/application/affiliate_run_service.py`

Adapters and migration:

- `hermes/adapters/affiliate/shopee_csv.py`
- `hermes/adapters/google/sheets_projection.py`
- `hermes/adapters/model/affiliate_content_gateway.py`
- `hermes/adapters/sqlite/affiliate_research_repository.py`
- `hermes/adapters/sqlite/schema_v4.py`
- `hermes/adapters/telegram/affiliate_review.py`
- `hermes/adapters/tiktok/__init__.py`
- `hermes/adapters/tiktok/public_reference.py`

Tests:

- `tests/hermes/adapters/test_google_sheets_projection.py`
- `tests/hermes/adapters/test_shopee_affiliate_csv.py`
- `tests/hermes/application/test_affiliate_content_service.py`
- `tests/hermes/application/test_affiliate_run_service.py`
- `tests/hermes/test_affiliate_final_review.py`
- `tests/hermes/test_affiliate_research_job.py`
- `tests/hermes/test_database.py`
- `tests/hermes/test_job_repository.py`
- `tests/hermes/test_telegram_affiliate_review.py`

## TDD And Fault Injection Evidence

Initial final-review RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_final_review.py tests\hermes\test_job_repository.py::JobRepositoryTests::test_legacy_claim_never_takes_dedicated_affiliate_job tests\hermes\adapters\test_shopee_affiliate_csv.py::test_csv_source_strictly_validates_numeric_domains tests\hermes\application\test_affiliate_content_service.py::test_initial_package_retry_reuses_deterministic_id_without_model_call tests\hermes\application\test_affiliate_content_service.py::test_claim_evidence_is_canonicalized_and_unknown_urls_are_rejected tests\hermes\application\test_affiliate_content_service.py::test_revision_failure_does_not_transition_parent tests\hermes\adapters\test_google_sheets_projection.py::test_operator_editable_columns_survive_resync tests\hermes\test_telegram_affiliate_review.py::test_callback_payload_accepts_exactly_64_bytes tests\hermes\test_telegram_affiliate_review.py::test_review_delivery_uses_product_image_score_and_bounded_caption -q --basetemp .pytest-final-fix-red
```

Observed: `14 failed, 1 passed`. Failures covered missing V4, run scope,
outbox, collector, typed isolation, strict parsing, deterministic package IDs,
canonical evidence, Sheets edit preservation, callback length, and Telegram
photo/score delivery.

Revision invariant target:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_telegram_affiliate_review.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\test_affiliate_final_review.py -q --basetemp .pytest-final-revision-invariant
```

Result: `46 passed in 0.95s`.

Final focused affiliate and migration suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\domain\test_affiliate_research.py tests\hermes\test_affiliate_research_repository.py tests\hermes\adapters\test_shopee_affiliate_csv.py tests\hermes\adapters\test_tiktok_public_reference.py tests\hermes\application\test_affiliate_catalog_service.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\application\test_affiliate_run_service.py tests\hermes\adapters\test_google_sheets_projection.py tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_affiliate_research_job.py tests\hermes\test_affiliate_research_acceptance.py tests\hermes\test_affiliate_final_review.py tests\hermes\test_job_repository.py tests\hermes\test_database.py -q --basetemp .pytest-final-fix-final
```

Result: `124 passed in 7.55s`.

No focused test was slow or hung.

## Static Verification

`py_compile` was run against every changed Python production/test file,
including the new V4 migration, reference collector, worker entry point, and
final-review tests.

Result: exit code 0 with no output.

Scoped working-tree check:

```powershell
git diff --check -- <all scoped tracked paths>
```

Result: exit code 0; only Git's existing LF-to-CRLF notices were printed.

Staged check before the implementation commit:

```powershell
git diff --cached --check
```

Result: exit code 0 with no whitespace errors.

## Constraints And Unresolved Concerns

- No live Shopee, TikTok, Google Sheets, Telegram, network, or paid LLM calls
  were made.
- Only the focused affiliate/migration suite was run; no broad repository test
  suite was run.
- `core/job_watcher.py`, `config.py`, `.env.example`, `requirements.txt`,
  runtime data, and user media were not modified or staged by this fix wave.
- Existing unrelated dirty files remain in the workspace.
- No unresolved Critical or Important final-review finding remains within the
  requested scope.
