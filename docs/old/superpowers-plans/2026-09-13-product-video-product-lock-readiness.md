> **Status: Historical** — This document is superseded by [Product Video Master Plan](product-video-master-plan.md). Do not use as implementation target.

---

# Product Video Product-Lock Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `executing-plans` in a separate implementation session. Use `test-driven-development` for every behavior change and `verification-before-completion` before any production-ready claim.

**Goal:** Make the scheduled Product-Intelligence â†’ exchange inbox â†’ Hermes Coordinator â†’ MCP research â†’ Product Lock path run reliably on the existing production database, start at most three products, and return success only when every newly started workflow is durably parked at `AwaitingProductLock` with a pending approval bound to a reviewable Resource Pack.

**Architecture:** Keep Product-Intelligence as the producer and the immutable exchange inbox as the boundary. Keep `ProductVideoCoordinator` as the only Scheduler/CLI/REST coordinator, SQLite as the durable source of truth, and the transactional outbox as the worker boundary. Move Resource Pack construction before Product Lock so the operator approves the actual versioned pack. Product Lock approval may enqueue only the lock operation; brief generation remains impossible until the approved pack is locked.

**Tech Stack:** Python 3.11, SQLite, pytest, Ruff, Windows Task Scheduler, existing Hermes MCP registry and Product-Intelligence MCP server.

## Audit Baseline (2026-09-13)

- Windows task `ProductIntelligenceDailyScout` ran at `07:00:01`, returned `1`, and is scheduled next for `2026-09-14 07:00`.
- Product-Intelligence successfully published `run_20260913_000105` with `READY`, schema `1.0.0`, ten products, and priorities `1..10`.
- The scheduled Hermes command uses `python -m hermes_cli`; the package has no `__main__.py`. The supported entry point is `python -m hermes_cli.main` (also exposed as `hermes.exe`).
- The live table `daily_product_video_import` still checks only `reserved`, `started`, and `error`. It contains three `started` rows from `2026-09-12` and no row for `2026-09-13`.
- On a copy of the live database, the corrected module entry point returned exit code `0` while all claims failed the legacy `CHECK` constraint. The CLI printed that there was nothing new and left the ledger empty.
- Hermes focused verification is green (`283 passed`; Ruff clean), proving the current tests do not reproduce the runtime-shaped migration or false-success path.
- Product-Intelligence tests are green (`230 passed`) but repository-wide Ruff reports 19 errors.
- Current `AwaitingProductLock` approval is bound to the research result. Approval then builds and locks the Resource Pack automatically. This contradicts the capability contract that Product Lock consumes Resource Pack content and that brief creation requires a locked product.
- Current admission trusts producer-supplied `match_score`; it checks readability and path safety but does not independently prove exact brand/model/variant image identity.
- The automation files in both repositories are currently untracked or mixed into dirty working trees. They are not reproducibly deployable from version control.

## Target Invariants

1. The exact command configured in Task Scheduler is executable from its configured working directory.
2. Opening an existing production-shaped database migrates the ledger transactionally and preserves every legacy row.
3. `start --auto` accepts only `1..3`; manual selection accepts at most three unique products.
4. A zero exit code means every newly started workflow reached `AwaitingProductLock`, has one pending approval, has no eligible outbox work, and exposes a `ready_to_lock` Resource Pack artifact.
5. Claim, worker, MCP, persistence, quarantine, stale-lease, and postcondition failures produce a non-zero exit code and actionable durable/error output.
6. Product Lock approval is bound to the exact Resource Pack ID, version, digest, owner, project, workflow, gate, and workflow version.
7. Before Product Lock approval, no brief, scene plan, storyboard, render, or export job can be enqueued.
8. Replaying the same daily batch creates no duplicate workflow, approval, provider request, or outbox message.

---

## Task 1: Add Runtime-Shaped Failing Tests

**Repositories:** Hermes and Product-Intelligence

**Files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_exchange_automation.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_cli_video_commands.py`
- Create: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_daily_scheduler_e2e.py`
- Create: `D:/work/Personal/Product-Intelligence/tests/test_scheduler_contract.py`

- [ ] **Step 1: Capture the exact live legacy DDL as a fixture**

Create a helper that builds the current production shape, including its restrictive check:

```python
LEGACY_LEDGER_DDL = """
CREATE TABLE daily_product_video_import (
    product_key TEXT PRIMARY KEY,
    source_date TEXT NOT NULL,
    source_product_id TEXT NOT NULL,
    source_path TEXT NOT NULL,
    workflow_id TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK(status IN ('reserved', 'started', 'error')),
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    canonical_product_key TEXT NOT NULL DEFAULT '',
    source_batch_id TEXT NOT NULL DEFAULT '',
    worker_id TEXT,
    claimed_at TEXT,
    lease_expires_at TEXT
)
"""
```

Seed the three `2026-09-12` rows and assert repository initialization followed by a `2026-09-13` claim succeeds without changing the seeded rows.

- [ ] **Step 2: Reproduce false success at the CLI boundary**

Add tests where all requested claims return `ClaimResult(status="error", error="CHECK constraint failed")` and where the worker report has `failed`, `quarantined`, or `stale` work. Assert `cmd_start()` returns non-zero and does not print `HOÃ€N Táº¤T`.

- [ ] **Step 3: Exercise the real module entry point**

Use `subprocess.run()` with `sys.executable`, not an imported `main()`:

```python
completed = subprocess.run(
    [
        sys.executable,
        "-m",
        "hermes_cli.main",
        "personal",
        "video",
        "--db-path",
        str(db_path),
        "list",
        "--date",
        "2026-09-13",
    ],
    cwd=repo_root,
    text=True,
    capture_output=True,
    check=False,
)
assert completed.returncode == 0
```

- [ ] **Step 4: Lock down the scheduler command contract**

In Product-Intelligence, parse `scripts/run_daily.bat` and assert the Hermes invocation uses `-m hermes_cli.main` and propagates its exit code. This small static contract is justified because Task Scheduler executes the batch file itself, not Python's imported command handler.

- [ ] **Step 5: Run tests and record the expected red state**

```powershell
uv run pytest tests/hermes_personal/product_video/test_exchange_automation.py tests/hermes_personal/product_video/test_cli_video_commands.py tests/hermes_personal/product_video/test_daily_scheduler_e2e.py -q
```

```powershell
Set-Location 'D:\work\Personal\Product-Intelligence'
uv run pytest tests/test_scheduler_contract.py -q
```

Expected: failures for schema migration, false-success exit handling, and the current batch command.

---

## Task 2: Migrate the Daily Import Ledger Transactionally

**Repository:** Hermes

**Files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/storage/sqlite.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/automation/repository.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_exchange_automation.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py`

- [ ] **Step 1: Make central storage own the canonical schema**

Add `daily_product_video_import` to the canonical SQLite schema in `storage/sqlite.py`. Keep one status vocabulary:

```sql
CHECK(status IN ('discovered', 'imported', 'claimed', 'started', 'error', 'reserved'))
```

Do not leave a second competing DDL owner in the repository module.

- [ ] **Step 2: Implement an idempotent table-rebuild migration**

Add `_migrate_daily_product_video_import(connection)` and invoke it from `_migrate_schema()`. Inspect `sqlite_master.sql`, not only `PRAGMA table_info`, because column presence cannot detect an obsolete `CHECK` constraint.

Within one transaction/savepoint:

1. Create `daily_product_video_import_v2` with the canonical DDL.
2. Copy every common column, using explicit defaults only for columns absent from older shapes.
3. Assert source and destination row counts match.
4. Drop the legacy table and rename the v2 table.
5. Recreate the unique constraints/indexes.

Do not catch and downgrade migration errors. Startup must fail closed and roll back to the original table.

- [ ] **Step 3: Remove ad-hoc constraint migration from the repository**

`DailyImportRepository._ensure_schema()` may assert the canonical table exists, but it must not silently patch production schema with a partial `ALTER TABLE` sequence. Repository construction after `connect()` should be side-effect-free apart from `CREATE TABLE IF NOT EXISTS` compatibility for isolated tests, or tests should use the central connection factory.

- [ ] **Step 4: Prove migration preservation and retry safety**

Add tests for:

- exact live DDL â†’ canonical DDL;
- three legacy `started` rows remain byte-for-byte equivalent;
- a new `claimed` row can be inserted;
- migration rerun makes no change;
- injected copy/count failure rolls back, after which a retry succeeds.

- [ ] **Step 5: Verify the focused migration path**

```powershell
uv run pytest tests/hermes_personal/product_video/test_exchange_automation.py tests/hermes_personal/runtime/test_startup_readiness_lifecycle.py -q
```

---

## Task 3: Make Batch Results and Exit Codes Honest

**Repository:** Hermes

**Files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/automation/contracts.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/automation/coordinator.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/candidate_service.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/cli.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/workflows/outbox_repository.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/workflows/outbox_dispatcher.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/workflows/worker.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_cli_video_commands.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/workflows/test_worker.py`

- [ ] **Step 1: Preserve structured start results through every adapter**

Do not collapse `BatchStartResult` to `list[str]`. Extend it with explicit counts/reasons and expose `has_errors`:

```python
@dataclass(frozen=True)
class BatchStartResult:
    started: tuple[StartedProduct, ...]
    skipped: tuple[SkippedProduct, ...]

    @property
    def has_errors(self) -> bool:
        return any(item.reason.startswith(("CLAIM_ERROR", "START_FAILED")) for item in self.skipped)
```

Differentiate `already_started`/`already_claimed` from actual claim errors. Never prefix a claim error as `ALREADY_ERROR`.

- [ ] **Step 2: Enforce the hard daily bound in the coordinator**

Validate `1 <= limit <= 3` in `start_auto()`. Deduplicate manual keys while preserving order and reject more than three. CLI and REST validation should mirror this, but the coordinator remains the authoritative guard.

- [ ] **Step 3: Add exact workflow targeting to worker queries**

Add an optional `workflow_ids` filter through `run_worker()`, `OutboxDispatcher.process_batch()`, and the repository claim query. Parameterize the SQL placeholders; do not construct values into SQL strings. Existing callers without the filter retain current behavior.

- [ ] **Step 4: Add a bounded `advance_to_product_lock()` loop**

For the workflow IDs returned by the current start call only:

1. Process eligible outbox work.
2. Reload all target aggregates and approvals.
3. Stop when all targets satisfy the Product Lock postcondition or any target is terminal/quarantined.
4. Bound the loop by the known number of pre-lock jobs and return a structured failure if no progress occurs.

The loop must not process an unrelated old `pv-daily-*` workflow merely because it shares a prefix.

- [ ] **Step 5: Make CLI success depend on durable postconditions**

Return `1` if `BatchStartResult.has_errors`, worker failures/quarantine/stale work, missing target workflow, wrong state, missing/non-pending approval, wrong gate, non-empty eligible target outbox, or missing/non-lockable Resource Pack. Print each failing product/workflow and reason to stderr.

A replay with no new starts returns `0` only when every skipped item is a benign duplicate (`already_started` or active claim). An empty result caused by errors is not â€œall processed.â€

- [ ] **Step 6: Run focused orchestration tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_cli_video_commands.py tests/hermes_personal/product_video/test_exchange_automation.py tests/hermes_personal/workflows/test_worker.py -q
```

---

## Task 4: Correct Product Lock Artifact Semantics

**Repository:** Hermes

**Files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/handlers.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/workflow.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/application/operator_handler.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/workflows/recovery.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/workflows/test_product_video_outbox.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_happy_path_e2e.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_restart_recovery.py`

- [ ] **Step 1: Write the corrected state-path tests first**

Assert the exact path:

```text
researching
  -> building_resource_pack
  -> AwaitingProductLock
  -> locking_resource_pack
  -> creating_brief
  -> AwaitingBriefApproval
```

At `AwaitingProductLock`, assert the aggregate's `latest_artifact` is a `product_resource_pack` with `pack_status == "ready_to_lock"`, and the pending approval binds its ID/version/digest.

- [ ] **Step 2: Add an explicit `LOCKING_RESOURCE_PACK` state**

Add `locking_resource_pack` to `ProductVideoWorkflowState` and legal transitions:

- `RESEARCHING -> BUILDING_RESOURCE_PACK`
- `BUILDING_RESOURCE_PACK -> AWAITING_PRODUCT_LOCK`
- `AWAITING_PRODUCT_LOCK -> LOCKING_RESOURCE_PACK`
- `LOCKING_RESOURCE_PACK -> CREATING_BRIEF`

Update recovery so `BUILDING_RESOURCE_PACK` can recover only the build job and `LOCKING_RESOURCE_PACK` can recover only the lock job. This avoids inferring the required job from an ambiguous shared state.

- [ ] **Step 3: Enqueue Resource Pack construction after research**

On successful `product_video.research`, persist the research artifact, transition to `BUILDING_RESOURCE_PACK`, and atomically enqueue `product_video.resource_pack`. Do not create an approval yet.

- [ ] **Step 4: Create Product Lock only for a lockable pack**

On successful `product_video.resource_pack`:

- require `resource_pack_id`;
- require `pack_status == "ready_to_lock"`;
- persist the full versioned artifact and digest;
- transition to `AwaitingProductLock`;
- create exactly one pending approval bound to that artifact;
- enqueue no next job.

Treat `rejected`, `incomplete`, `needs_review`, ambiguous identity, and missing evidence as explicit non-success outcomes. They must not be presented as ready for Product Lock approval until a supported correction/research path produces a new `ready_to_lock` pack.

- [ ] **Step 5: Make approval enqueue only the lock operation**

Change `approve_and_advance_workflow()` for Product Lock to transition to `LOCKING_RESOURCE_PACK` and enqueue `product_video.lock` with the approved Resource Pack artifact. On lock success, require a locked artifact reference, transition to `CREATING_BRIEF`, and only then enqueue creative brief generation.

- [ ] **Step 6: Prove the safety boundary**

Add negative tests proving that before approval:

- no `product_video.lock`, creative brief, scene, storyboard, render, or export message exists;
- direct calls in `AwaitingProductLock` return `ILLEGAL_WORKFLOW_STATE`;
- stale approval artifact ID/version/digest fails without mutation;
- restart/replay creates neither a second approval nor a second build/lock request.

- [ ] **Step 7: Run state-machine and outbox regressions**

```powershell
uv run pytest tests/hermes_personal/workflows/test_product_video_outbox.py tests/hermes_personal/product_video/test_happy_path_e2e.py tests/hermes_personal/product_video/test_restart_recovery.py tests/hermes_personal/product_video/test_binding.py -q
```

---

## Task 5: Enforce Research and Exact Product Evidence Before the Gate

**Repositories:** Hermes and Product-Intelligence

**Hermes files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/automation/coordinator.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/product_video/handlers.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/hermes_personal/integrations/product_intelligence/client.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_pi_mcp_contract.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/workflows/test_product_video_outbox.py`

**Product-Intelligence files:**
- Modify only if needed after contract tests: `D:/work/Personal/Product-Intelligence/product_scout/mcp_server.py`
- Modify: `D:/work/Personal/Product-Intelligence/tests/test_mcp_surface.py`
- Modify: `D:/work/Personal/Product-Intelligence/tests/test_resource_pack.py`

- [ ] **Step 1: Pass canonical identity to MCP explicitly**

Extend the existing research call; do not add a new core model tool. Pass `brand`, `model`, `variant`, `canonical_product_key`, source URL, and the admitted exchange-image metadata through the existing MCP tool contract. Include these fields in input digest/idempotency calculations.

- [ ] **Step 2: Separate technical admission from semantic proof**

Rename UI/report wording from â€œtrusted/valid imageâ€ to â€œtechnically readable candidate imageâ€ at exchange admission. Producer `match_score` remains a hint, not proof. Exact identity/variant and media eligibility are decided from the Product-Intelligence research/resource-pack result.

- [ ] **Step 3: Fail closed on semantically empty research**

Configured-mode research must not count as success solely because a snapshot was saved. Reject or keep out of Product Lock when any of these hold:

- status is `no_product_evidence`, `failed`, `error`, or `cancelled`;
- `canonical_products` is empty;
- no canonical product matches the requested brand/model/variant;
- Resource Pack has fewer than two eligible matching media assets;
- Resource Pack is not `ready_to_lock`.

Preserve challenged/unusable sources as evidence and diagnostics, but do not promote them to product proof.

- [ ] **Step 4: Use Product-Intelligence's existing variant/media rules**

Exercise the existing tests that prove high `match_score` alone cannot upgrade unknown or conflicting variants. Add a cross-boundary test showing an image for a sibling model/variant is excluded even if its producer score is `1.0`.

- [ ] **Step 5: Move idempotency cache lookup behind guards**

For research, resource-pack, lock, brief, scene, storyboard, render, and export handlers, validate workflow state, expected version, and input digests before returning an in-memory cached result. Include workflow version and input digest in cache keys, or rely on the durable outbox/idempotency record where possible. A cache hit must never bypass HITL or stale-version checks.

- [ ] **Step 6: Run both sides of the contract**

```powershell
uv run pytest tests/hermes_personal/product_video/test_pi_mcp_contract.py tests/hermes_personal/workflows/test_product_video_outbox.py -q
```

```powershell
Set-Location 'D:\work\Personal\Product-Intelligence'
uv run pytest tests/test_mcp_surface.py tests/test_resource_pack.py tests/test_acceptance.py -q
```

---

## Task 6: Repair and Harden the Windows Scheduled Entry Point

**Repository:** Product-Intelligence

**Files:**
- Modify: `D:/work/Personal/Product-Intelligence/scripts/run_daily.bat`
- Modify: `D:/work/Personal/Product-Intelligence/scripts/setup_windows_task.ps1`
- Modify: `D:/work/Personal/Product-Intelligence/tests/test_scheduler_contract.py`
- Create: `D:/work/Personal/Product-Intelligence/docs/daily-product-video-operations.md`

- [ ] **Step 1: Use the existing supported Hermes entry point**

Change the batch invocation to:

```bat
"%HERMES_PYTHON%" -m hermes_cli.main personal video start --auto --limit 3 --owner-user-id local-owner
```

Do not add `hermes_cli/__main__.py` solely for this scheduler.

- [ ] **Step 2: Add explicit preflight checks**

Before publishing/starting, verify both repository roots, both Python executables, the exchange inbox parent, and Hermes CLI importability. Fail with a distinct non-zero exit code and message for each boundary.

- [ ] **Step 3: Configure bounded retry and durable logs**

In `setup_windows_task.ps1`, configure three retries at 15-minute intervals, preserve `StartWhenAvailable` and `MultipleInstances IgnoreNew`, and write stdout/stderr to a dated log under Product-Intelligence's `logs/` directory. Do not put secrets in arguments or logs.

Keep the execution limit bounded. Document that `InteractiveToken` and `WakeToRun=False` mean the task cannot run while no user session is available or wake a sleeping machine; either accept this operating mode explicitly or change the principal/power policy as a separate operator-approved deployment decision.

- [ ] **Step 4: Make setup failure observable**

The setup script must return non-zero when registration fails and must re-read the registered task to verify action, working directory, trigger, retry settings, and next-run time. Avoid printing success solely because `Register-ScheduledTask` returned.

- [ ] **Step 5: Clean Product-Intelligence quality gates**

Fix all current Ruff errors in files touched by this automation. Then run:

```powershell
uv run pytest -q
uv run ruff check .
```

Expected: `230+ passed` and `All checks passed!` from fresh output.

---

## Task 7: Cross-Repository E2E, Cutover, and Production Proof

**Repositories:** Both; commit separately.

**Files:**
- Modify: `D:/work/hermes-upstream-rearchitecture/tests/hermes_personal/product_video/test_daily_scheduler_e2e.py`
- Modify: `D:/work/hermes-upstream-rearchitecture/docs/hermes-personal/current-daily-product-video-architecture.md`
- Modify: `D:/work/hermes-upstream-rearchitecture/docs/hermes-personal/product-video-runbook.md`
- Modify: `D:/work/Personal/Product-Intelligence/docs/daily-product-video-operations.md`

- [ ] **Step 1: Add one real-path, fake-provider E2E test**

The test must use a production-shaped legacy SQLite file and a real exchange directory fixture with `manifest.json`, images, and `READY`. Invoke the public CLI in a subprocess and the real coordinator/worker path with registered fake MCP handlers. Do not mock the importer, repository, coordinator, outbox, approval service, or state transitions.

Assert:

1. The top three eligible priorities are chosen; ambiguous `30W / 65W` is excluded.
2. Exactly three deterministic workflows and three unique pending approvals exist.
3. Every workflow is `AwaitingProductLock` with a `ready_to_lock` Resource Pack bound to its approval.
4. No downstream job is eligible and no brief/storyboard/video artifact exists.
5. A second identical CLI run creates no additional workflow, event, approval, outbox row, or MCP call.
6. A deliberate MCP `no_product_evidence` response yields non-zero exit and never reaches Product Lock.

- [ ] **Step 2: Run the complete focused verification**

From Hermes:

```powershell
uv run pytest tests/hermes_personal/product_video tests/hermes_personal/workflows -q
uv run ruff check hermes_personal/product_video hermes_personal/workflows tests/hermes_personal/product_video tests/hermes_personal/workflows
```

Before an upstream PR, also run `scripts/run_tests.sh` from a supported shell.

From Product-Intelligence:

```powershell
uv run pytest -q
uv run ruff check .
```

- [ ] **Step 3: Prepare a recoverable database cutover**

Stop the scheduled task temporarily. Resolve the exact live DB path, use SQLite's backup API (or a verified file copy while all writers are stopped), and record its SHA-256. Run the migration command against a second copy first. Compare row counts, primary keys, workflow IDs, statuses, and `PRAGMA integrity_check` before touching the live file.

Never delete or overwrite the only production database copy.

- [ ] **Step 4: Perform one supervised production run without approval**

Register the corrected task, invoke it once manually, and capture its actual task result and dated log. Do not approve Product Lock during this proof.

Verify with read-only queries:

```sql
SELECT source_date, source_batch_id, product_key, workflow_id, status, last_error
FROM daily_product_video_import
WHERE source_date = '2026-09-13'
ORDER BY created_at;
```

For each new workflow verify state, pending approval binding, Resource Pack identity/version/digest, and target-specific outbox state. Then run the same batch again and prove counts are unchanged.

- [ ] **Step 5: Update documentation to runtime truth**

Remove claims that Product Lock approves research content or that Resource Pack is built only after approval. Record the exact supported CLI module path, migration behavior, failure exit semantics, scheduler retry policy, and the evidence required before declaring a daily run successful.

- [ ] **Step 6: Commit the two repositories independently**

First inspect the dirty worktrees and stage only automation-related files. Do not absorb unrelated user changes. Commit Product-Intelligence and Hermes separately so either side can be reviewed and rolled back independently.

Suggested commit sequence:

```text
Hermes:
  fix: migrate daily product ledger safely
  fix: report daily video start failures
  fix: bind product lock to resource pack
  test: cover scheduled product video path

Product-Intelligence:
  fix: invoke supported Hermes CLI entrypoint
  fix: harden daily task observability
  docs: document daily product video operations
```

## Completion Gate

Do not call the automation production-ready until fresh evidence proves all of the following:

- Task Scheduler's latest result is `0` for the corrected code, not for an older checkout.
- The live database passed migration integrity checks and retained the three historical `2026-09-12` rows.
- The selected count is `<= 3` at the coordinator boundary.
- Each selected workflow has a semantically valid, exact-product, `ready_to_lock` Resource Pack.
- Each approval is pending, unique, and bound to that exact pack/version/digest.
- Target workflows have no eligible work after reaching `AwaitingProductLock`.
- No brief, scene plan, storyboard, render, or export was created.
- Replay changes none of the workflow/approval/outbox/provider-call counts.
- Both repositories' tests and Ruff checks pass.
- All automation source, tests, scripts, and docs used by Task Scheduler are tracked in Git.


