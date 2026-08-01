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

# Re-review Wave 2

Implementation commit: `5a7afa43e` (`fix: complete affiliate re-review wave 2`)

## Completed Findings

1. Production package IDs now use `pkg_` plus a deterministic 24-character
   digest. Revision suffixes remain compact, and actual production IDs pass
   through `TelegramReviewDelivery` with all callback payloads below Telegram's
   64-byte limit.
2. V4 now contains `affiliate_projection_items`. Run completion creates
   Telegram package checkpoints in the same transaction as the batch outbox.
   Each successful send persists package status, Telegram message ID when
   available, attempts, and delivery timestamps. Retry skips delivered
   packages.
3. Eligibility, score payload, reason, confidence, rank, shortlist flag,
   canonical evidence IDs, and snapshot timestamps now persist on
   `affiliate_run_products`. Run-scoped repository reads, projection rows, and
   Telegram review rendering use that observation. A later score for the same
   product no longer changes an older run projection.
4. Research briefs convert references into deterministic abstract
   hook/pacing/structure patterns without copying titles or captions. Content
   planning produces three deterministic, scored, ranked
   product/audience/evidence-specific angles and selects exactly one winner.
5. `ScoreBreakdown` now carries canonical evidence IDs and snapshot
   timestamps. Catalog scoring attaches owner/product-scoped source and
   snapshot IDs to eligible and ineligible results. Repository validation
   requires both evidence classes and at least one snapshot timestamp.

## V4 Extension

V3 was not modified.

New V4 table:

- `affiliate_projection_items`

New `affiliate_run_products` columns:

- `eligibility_status`
- `score`
- `score_json`
- `score_reason`
- `score_confidence`
- `rank`
- `shortlisted`
- `evidence_ids_json`
- `snapshot_timestamps_json`

V4 also backfills legacy global score state into pre-existing run observations
for backward compatibility. New production scoring writes only the run
observation.

## Wave 2 Changed Files

- `hermes/adapters/sqlite/affiliate_research_repository.py`
- `hermes/adapters/sqlite/schema_v4.py`
- `hermes/adapters/telegram/affiliate_review.py`
- `hermes/application/affiliate_catalog_service.py`
- `hermes/application/affiliate_content_service.py`
- `hermes/application/affiliate_run_service.py`
- `hermes/domain/affiliate_research.py`
- `hermes/ports/affiliate_research.py`
- `tests/hermes/test_affiliate_final_review.py`
- `tests/hermes/test_telegram_affiliate_review.py`

## Wave 2 TDD And Fault Evidence

Initial Wave 2 RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_final_review.py::test_v4_migration_creates_run_catalog_outbox_and_provenance tests\hermes\test_affiliate_final_review.py::test_later_run_score_does_not_mutate_older_projection tests\hermes\test_affiliate_final_review.py::test_catalog_score_persists_owner_scoped_source_and_snapshot_evidence tests\hermes\test_affiliate_final_review.py::test_reference_patterns_and_angles_are_abstract_and_evidence_specific tests\hermes\test_affiliate_final_review.py::test_telegram_crash_after_first_send_retries_only_unresolved_package tests\hermes\test_telegram_affiliate_review.py::test_actual_production_package_id_delivers_with_valid_callbacks -q --basetemp .pytest-wave2-red
```

Result: `6 failed in 0.60s`. The failures directly covered missing V4 item
checkpoints/run score fields, missing score evidence, raw reference copying,
unsupported per-item completion, and oversized production callbacks.

First Wave 2 GREEN command used the same six test nodes with
`--basetemp .pytest-wave2-green`.

Result: `6 passed in 0.56s`.

The focused suite then exposed one backward-compatibility regression:

```text
test_repository_persists_score_reference_ideas_runs_and_projection_rows
```

Observed result: `128 passed, 1 failed in 8.03s`. The legacy test writes
`save_score()` before creating a run observation. The observation insert now
copies legacy global score state only when it must create that missing row;
production run observations remain authoritative.

Isolated regression verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_research_repository.py::test_repository_persists_score_reference_ideas_runs_and_projection_rows -q --basetemp .pytest-wave2-isolated
```

Result: `1 passed in 0.11s`.

Tightened message-ID and same-product/different-evidence verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_final_review.py::test_later_run_score_does_not_mutate_older_projection tests\hermes\test_affiliate_final_review.py::test_catalog_score_persists_owner_scoped_source_and_snapshot_evidence tests\hermes\test_affiliate_final_review.py::test_reference_patterns_and_angles_are_abstract_and_evidence_specific tests\hermes\test_affiliate_final_review.py::test_telegram_crash_after_first_send_retries_only_unresolved_package tests\hermes\test_telegram_affiliate_review.py::test_actual_production_package_id_delivers_with_valid_callbacks -q --basetemp .pytest-wave2-tightened
```

Result: `5 passed in 0.54s`.

Final focused suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\domain\test_affiliate_research.py tests\hermes\test_affiliate_research_repository.py tests\hermes\adapters\test_shopee_affiliate_csv.py tests\hermes\adapters\test_tiktok_public_reference.py tests\hermes\application\test_affiliate_catalog_service.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\application\test_affiliate_run_service.py tests\hermes\adapters\test_google_sheets_projection.py tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_affiliate_research_job.py tests\hermes\test_affiliate_research_acceptance.py tests\hermes\test_affiliate_final_review.py tests\hermes\test_job_repository.py tests\hermes\test_database.py -q --basetemp .pytest-wave2-final-suite
```

Result: `129 passed in 7.90s`. No test was slow or hung.

## Wave 2 Static Verification

```powershell
.\.venv\Scripts\python.exe -m py_compile hermes\adapters\sqlite\schema_v4.py hermes\domain\affiliate_research.py hermes\ports\affiliate_research.py hermes\adapters\sqlite\affiliate_research_repository.py hermes\application\affiliate_catalog_service.py hermes\application\affiliate_content_service.py hermes\application\affiliate_run_service.py hermes\adapters\telegram\affiliate_review.py tests\hermes\test_affiliate_final_review.py tests\hermes\test_telegram_affiliate_review.py
```

Result: exit code 0 with no output.

Scoped `git diff --check` and staged `git diff --cached --check` both returned
exit code 0 with no whitespace errors. The staged implementation contained
exactly the ten Wave 2 files listed above.

## Wave 2 Constraints And Concerns

- No live network, Telegram, Sheets, TikTok, Shopee, or paid model call was
  made.
- No broad test suite was run.
- Protected files, runtime data, and user media were not modified or staged.
- Existing unrelated dirty files remain untouched.
- Telegram does not provide an idempotency key for sends. A process death
  after Telegram accepts a message but before SQLite records its returned
  message ID can still duplicate that one message. Persisted package
  checkpoints prevent repeats after the checkpoint transaction completes.

# Re-review Wave 3

Implementation commit: `a77af9970` (`fix: complete affiliate re-review wave 3`)

## Completed Findings

1. `hermes/adapters/sqlite/schema_v4.py` was restored to the exact shape
   committed at `57b869749`. Wave 2 schema fields, backfills, indexes, and the
   package checkpoint table now live in the idempotent
   `hermes/adapters/sqlite/schema_v5.py`. `SCHEMA_VERSION` and SQLite
   `user_version` are now 5.
2. V5 backfills a pending checkpoint for every pending-review package attached
   to a pending Telegram outbox. Runtime delivery calls
   `ensure_projection_item()` in an immediate SQLite transaction before any
   external send. Existing delivered checkpoints remain unchanged.
3. `ReferencePatternAbstractor` is an injected deterministic component. It
   maps observable title/caption/platform semantics to controlled structured
   `hook`, `pacing`, and `story` labels. It stores reference ID, source type,
   content hash, collection time, observable fields, and matched semantic
   signals as brief provenance. It never copies source title/caption wording
   into pattern labels.

## V5 Migration

V4 remains immutable and V3 remains unchanged.

V5 owns:

- `affiliate_projection_items`
- Run-scoped eligibility, score, score payload, reason, confidence, rank,
  shortlist, evidence IDs, and snapshot timestamps on
  `affiliate_run_products`
- `affiliate_research_briefs.reference_pattern_provenance_json`
- Legacy global score backfill into unscored run observations
- Pending Telegram package-checkpoint backfill
- `idx_affiliate_projection_items_pending`

The upgrade test constructs a real database using V1, V2, V3, and the restored
pre-Wave-2 V4 migration, confirms Wave 2 fields are absent, inserts a completed
run with a pending Telegram outbox/package, sets `user_version = 4`, then
upgrades through `Database.initialize()`. It also invokes V5 twice more to
verify direct migration idempotency.

## Wave 3 Changed Files

- `hermes/adapters/sqlite/affiliate_research_repository.py`
- `hermes/adapters/sqlite/schema_v4.py`
- `hermes/adapters/sqlite/schema_v5.py`
- `hermes/adapters/telegram/affiliate_review.py`
- `hermes/application/affiliate_content_service.py`
- `hermes/application/reference_pattern_abstractor.py`
- `hermes/db.py`
- `hermes/domain/affiliate_research.py`
- `hermes/ports/affiliate_research.py`
- `tests/hermes/application/test_affiliate_content_service.py`
- `tests/hermes/application/test_reference_pattern_abstractor.py`
- `tests/hermes/test_affiliate_final_review.py`
- `tests/hermes/test_database.py`

## Wave 3 TDD And Fault Evidence

Initial RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_database.py::DatabaseTests::test_pre_wave2_v4_upgrades_to_v5_and_backfills_telegram_packages tests\hermes\test_affiliate_final_review.py::test_v5_migration_creates_run_catalog_outbox_and_provenance tests\hermes\test_affiliate_final_review.py::test_telegram_creates_missing_checkpoint_before_external_send tests\hermes\application\test_reference_pattern_abstractor.py tests\hermes\application\test_affiliate_content_service.py::test_content_service_uses_injected_reference_pattern_abstractor -q --basetemp .pytest-wave3-red
```

Result: `6 failed in 0.64s`. Failures directly demonstrated the mutated V4,
missing V5/version bump, absent pre-send checkpoint, and missing
abstractor/injection.

First GREEN command added the evidence-specific angle test to those targets
and used `--basetemp .pytest-wave3-green1`.

Result: `7 passed in 0.62s`.

Tightened migration-idempotency, runtime checkpoint, semantic abstraction,
injection, and angle command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_database.py::DatabaseTests::test_pre_wave2_v4_upgrades_to_v5_and_backfills_telegram_packages tests\hermes\test_affiliate_final_review.py::test_telegram_creates_missing_checkpoint_before_external_send tests\hermes\application\test_reference_pattern_abstractor.py tests\hermes\application\test_affiliate_content_service.py::test_content_service_uses_injected_reference_pattern_abstractor tests\hermes\test_affiliate_final_review.py::test_reference_patterns_and_angles_are_abstract_and_evidence_specific -q --basetemp .pytest-wave3-tightened
```

Result: `6 passed in 0.56s`.

Final focused affiliate and migration suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\domain\test_affiliate_research.py tests\hermes\test_affiliate_research_repository.py tests\hermes\adapters\test_shopee_affiliate_csv.py tests\hermes\adapters\test_tiktok_public_reference.py tests\hermes\application\test_affiliate_catalog_service.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\application\test_reference_pattern_abstractor.py tests\hermes\application\test_affiliate_run_service.py tests\hermes\adapters\test_google_sheets_projection.py tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_affiliate_research_job.py tests\hermes\test_affiliate_research_acceptance.py tests\hermes\test_affiliate_final_review.py tests\hermes\test_job_repository.py tests\hermes\test_database.py -q --basetemp .pytest-wave3-final2
```

Result: `134 passed in 8.07s`. No test was slow or hung.

## Wave 3 Static Verification

`py_compile` was run against all 13 changed Python production/test files,
including V4, V5, the abstractor, repository, Telegram adapter, and migration
tests.

Result: exit code 0 with no output.

Scoped and staged `git diff --check` both returned exit code 0. The immutable
baseline command:

```powershell
git diff --exit-code 57b869749 -- hermes/adapters/sqlite/schema_v4.py
```

returned exit code 0 and
`schema_v4_matches_57b869749=True`.

## Wave 3 Constraints And Concerns

- No live network, Telegram, Sheets, TikTok, Shopee, LLM, or paid call was
  made.
- Only the focused affiliate and migration suite was run.
- Protected files, runtime data, user media, and unrelated dirty files were
  not modified or staged by Wave 3.
- No unresolved Wave 3 finding remains.

# Final V4 Brief Compatibility Fix

Implementation commit: `4f5266f9a` (`fix: normalize legacy affiliate briefs`)

## Finding Resolution

Pre-Wave-3 V4 databases may contain
`affiliate_research_briefs.reference_patterns_json` as `list[str]`, including
copied title/caption wording. The compatibility fix has two idempotent layers:

1. V5 detects arrays containing JSON text elements and atomically replaces
   both pattern and provenance payloads with empty arrays. This removes copied
   wording during the V4-to-V5 upgrade and is safe to run repeatedly.
2. `SQLiteAffiliateResearchRepository.save_brief()` validates the newly
   abstracted payload, verifies the existing brief identity, and uses one
   `BEGIN IMMEDIATE` transaction to replace legacy/missing structured patterns
   and provenance together. A structured provenanced row is reused unchanged
   on subsequent retries.

This guarantees `_ideas_for()` receives either structured pattern dictionaries
or its empty-pattern fallback, never a legacy raw string.

V4 remains byte-for-diff identical to commit `57b869749`. Only V5 and
repository retry behavior changed.

## Changed Files

- `hermes/adapters/sqlite/schema_v5.py`
- `hermes/adapters/sqlite/affiliate_research_repository.py`
- `tests/hermes/test_affiliate_final_review.py`

## TDD And Fault Evidence

The test creates a real V1/V2/V3/V4 database, inserts a V4 brief containing a
raw copied string, sets `user_version = 4`, upgrades through V5, and verifies
that raw wording is removed. It then injects a gateway failure after the
repository has persisted the structured brief, retries successfully, retries
again, and verifies:

- Pattern objects contain exactly `hook`, `pacing`, and `story`.
- Provenance contains the canonical reference ID.
- Both gateway attempts receive the same canonical brief.
- The third package retry does not call the gateway again.
- Persisted pattern/provenance JSON remains structured and raw-wording-free.

Initial RED command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_final_review.py::test_pre_v5_raw_brief_upgrade_and_fault_retry_becomes_structured -q --basetemp .pytest-final-compat-red
```

Result: `1 failed in 0.25s` because V5 retained the raw string.

GREEN command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_affiliate_final_review.py::test_pre_v5_raw_brief_upgrade_and_fault_retry_becomes_structured -q --basetemp .pytest-final-compat-green1
```

Result: `1 passed in 0.21s`.

Focused migration/content/final command:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_database.py tests\hermes\test_affiliate_research_repository.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\application\test_reference_pattern_abstractor.py tests\hermes\test_affiliate_final_review.py -q --basetemp .pytest-final-compat-targeted
```

Result: `61 passed in 1.98s`.

Final focused affiliate and migration suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\domain\test_affiliate_research.py tests\hermes\test_affiliate_research_repository.py tests\hermes\adapters\test_shopee_affiliate_csv.py tests\hermes\adapters\test_tiktok_public_reference.py tests\hermes\application\test_affiliate_catalog_service.py tests\hermes\application\test_affiliate_content_service.py tests\hermes\application\test_reference_pattern_abstractor.py tests\hermes\application\test_affiliate_run_service.py tests\hermes\adapters\test_google_sheets_projection.py tests\hermes\test_telegram_affiliate_review.py tests\hermes\test_affiliate_research_job.py tests\hermes\test_affiliate_research_acceptance.py tests\hermes\test_affiliate_final_review.py tests\hermes\test_job_repository.py tests\hermes\test_database.py -q --basetemp .pytest-final-compat-suite
```

Result: `135 passed in 8.11s`. No test was slow or hung.

## Static And Scope Verification

`py_compile` ran against the three changed Python files and returned exit code
0 with no output. Scoped and staged `git diff --check` returned exit code 0.

```powershell
git diff --exit-code 57b869749 -- hermes/adapters/sqlite/schema_v4.py
```

Result: exit code 0 and `schema_v4_matches_57b869749=True`.

No live/network/paid call or broad test suite was used. Protected files,
runtime data, user media, and unrelated dirty files were not modified or
staged. No unresolved compatibility finding remains.
