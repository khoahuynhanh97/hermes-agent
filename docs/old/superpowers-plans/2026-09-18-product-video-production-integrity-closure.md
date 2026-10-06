# Product Video Production Integrity Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining Product Video integrity gaps on the actual render-poll-QC-export path so invalid or modified media cannot be marked complete, approved, or exported.

**Architecture:** Keep `ProductVideoWorkspaceLayout`, `SceneRenderOperationStore`, `QCReportRepository`, and the existing Video Factory workflow as the canonical components. Persist each scene's validation contract with its operation, make polling finalize through the operation store, bind every QC/export decision to complete artifact lineage, and fail closed when lineage or trusted digests are absent.

**Tech Stack:** Python 3.11+, SQLite, PyAV, pytest, Ruff, existing Hermes Product Video services and repositories.

## Global Constraints

- Preserve all unrelated user changes in the dirty worktree.
- Do not add another renderer, QC repository, workspace abstraction, or parallel workflow.
- Do not auto-resubmit a paid provider operation after an unknown outcome.
- Product Lock, Brief, Scene Plan, Storyboard, and Final approval remain mandatory HITL gates.
- Canonical render, QC, and export artifacts must live under `ProductVideoWorkspaceLayout.root`.
- External files are accepted only during reference ingestion and only from configured trusted exchange roots.
- Missing digests or lineage fields fail closed; never derive trust from current disk bytes.
- A changed clip or composite invalidates downstream Final approval and requires fresh Video QC.
- Every behavior change begins with a failing regression test against the production call path.

---

## File Map

- `hermes_personal/integrations/video_factory/scene_validator.py`: pure full-decode scene validation.
- `hermes_personal/integrations/video_factory/scene_renderer.py`: durable scene operation schema and monotonic finalization.
- `hermes_personal/integrations/video_factory/server.py`: production render polling, composite rebuild, export gate, and path handling.
- `hermes_personal/product_video/qc/service.py`: workflow-to-QC lineage extraction.
- `hermes_personal/product_video/qc/image_qc.py`: strict Image QC identity contract.
- `hermes_personal/product_video/qc/keyframe_qc.py`: strict Keyframe QC identity contract.
- `hermes_personal/product_video/qc/video_qc.py`: strict Video QC artifact contract.
- `hermes_personal/product_video/handlers.py`: preserve canonical render lineage across MCP adapter and workflow aggregate.
- `hermes_personal/product_video/creative/prompts.py`: require explicit end-keyframe decisions.
- `hermes_personal/product_video/creative/contracts.py`: reject omitted/fabricated end-keyframe decisions.
- `tests/hermes_personal/product_video/test_production_integrity.py`: adversarial production-path regressions.
- `tests/hermes_personal/product_video/test_happy_path_e2e.py`: real QC repository-to-export happy path.
- `docs/production-integrity-fixes-2026-09-18.md`: evidence-based completion report.

---

### Task 1: Persist The Scene Validation Contract

**Files:**
- Modify: `hermes_personal/integrations/video_factory/scene_renderer.py`
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`

**Interfaces:**
- Consumes: `VideoGenerationRequest.duration_seconds`, `VideoGenerationRequest.aspect_ratio`.
- Produces: operation columns `expected_duration_seconds REAL` and `expected_aspect_ratio TEXT`, available to production polling after restart.

- [ ] **Step 1: Add a failing migration and persistence test**

Create a `SceneRenderOperationStore`, call `mark_planned()` with a 6-second `9:16` request, reopen the SQLite connection, and assert the row contains `expected_duration_seconds == 6.0` and `expected_aspect_ratio == "9:16"`. Insert a legacy row with zero duration and assert finalization returns `VALIDATION_CONTRACT_MISSING` without touching output digest.

- [ ] **Step 2: Run the focused test and confirm it fails**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "validation_contract" -v
```

Expected: failure because the operation table does not persist the validation contract.

- [ ] **Step 3: Extend the operation schema and migration**

Add the columns to `SceneRenderOperationStore.DDL` and `_ensure_migrations()`:

```python
expected_duration_seconds REAL NOT NULL DEFAULT 0,
expected_aspect_ratio TEXT NOT NULL DEFAULT '9:16'
```

Populate both columns in `mark_planned()` and `mark_submitting()`. On conflict, only fill them while the operation is still `planned`; never rewrite a running or terminal operation's contract.

- [ ] **Step 4: Add a row-level finalization API**

Add this public method to `SceneRenderOperationStore`:

```python
def finalize_provider_result(
    self,
    operation_id: str,
    result: VideoGenerationResult,
) -> dict[str, Any]:
    """Validate a provider result and CAS the durable operation state."""
```

It must load the operation, verify `provider_operation_id`, reject missing validation fields, call `validate_scene_output()` before `completed`, and update using `WHERE operation_id = ? AND status NOT IN ('completed', 'failed')`. Validation failure transitions to `failed` with a specific error code and an empty trusted digest.

- [ ] **Step 5: Run the focused tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "validation_contract or scene_render_store" -v
```

Expected: all selected tests pass.

- [ ] **Step 6: Commit only Task 1 files**

```powershell
git add hermes_personal/integrations/video_factory/scene_renderer.py tests/hermes_personal/product_video/test_production_integrity.py
git commit -m "fix(product-video): persist scene validation contract"
```

---

### Task 2: Route Production Polling Through Validated CAS Finalization

**Files:**
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/integrations/video_factory/scene_renderer.py`
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`

**Interfaces:**
- Consumes: `SceneRenderOperationStore.finalize_provider_result()` from Task 1.
- Produces: a single state transition path for runtime submission and `get_job_status()` polling.

- [ ] **Step 1: Write production polling tests**

Create a real render batch and scene operation, then call `server.get_job_status()` with providers returning: a one-second clip for a four-second scene, a 16:9 clip, and an undecodable file. Assert each operation becomes `failed`, the batch never becomes `completed`, and no composite artifact is created.

- [ ] **Step 2: Prove the tests fail against current raw SQL polling**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "poll_rejects" -v
```

Expected: current `server.py` marks at least one invalid provider result `completed` before validation.

- [ ] **Step 3: Remove direct terminal-state SQL from `get_job_status()`**

Replace the `UPDATE video_factory_scene_operation SET status = 'completed'...` block with `SceneRenderOperationStore.finalize_provider_result()`. Reread the persisted row after finalization. Return its durable failure code when validation fails; append a clip to `completed_paths` only when the reread row is `completed` with a non-empty digest.

- [ ] **Step 4: Make invalid output recovery explicit**

Mark the render batch `failed` when scene validation fails. Do not reuse or resubmit that operation automatically. A retry must create a new attempt/operation through the existing operator recovery flow and budget authorization.

- [ ] **Step 5: Run production polling and restart tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "poll_rejects" -v
uv run pytest tests/hermes_personal/product_video/test_artifact_storage_and_recovery.py tests/hermes_personal/product_video/test_restart_recovery.py -q
```

Expected: all pass and provider submit counts remain unchanged on restart.

- [ ] **Step 6: Commit Task 2**

```powershell
git add hermes_personal/integrations/video_factory/server.py hermes_personal/integrations/video_factory/scene_renderer.py tests/hermes_personal/product_video/test_production_integrity.py
git commit -m "fix(product-video): validate polled scene output before completion"
```

---

### Task 3: Make Clip And Composite Tampering Invalidate Downstream State

**Files:**
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/integrations/video_factory/repository.py` only if an existing status update method is missing
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`

**Interfaces:**
- Consumes: stored clip digests, composite artifact digest, composite provenance.
- Produces: deterministic failure/rebuild behavior and `FinalApprovalStatus.PENDING` after any byte change.

- [ ] **Step 1: Add failing adversarial tests through `get_job_status()`**

Cover all three cases:

1. Completed scene row with empty `output_sha256`: return `SCENE_DIGEST_MISSING`, leave the digest empty, and do not modify another project with the same `scene_id`.
2. Completed clip with changed bytes: mark the batch failed, invalidate Final approval, and do not build from the changed clip.
3. Still-decodable composite with changed bytes while trusted clips remain intact: rebuild atomically from trusted clips, invalidate Final approval, and produce a new composite artifact digest. The old Video QC report must not authorize export.

- [ ] **Step 2: Confirm current behavior fails**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "missing_scene_digest or clip_tamper or composite_tamper" -v
```

Expected: current code backfills a digest or accepts a decodable modified composite.

- [ ] **Step 3: Delete digest backfilling**

Remove the branch that hashes current bytes and executes `WHERE scene_id = ? OR operation_id = ?`. Missing digest must immediately fail closed. Never mutate a scene operation based only on `scene_id`.

- [ ] **Step 4: Centralize downstream invalidation**

Add a private server helper:

```python
def _invalidate_final_approval(
    srv: VideoFactoryService,
    owner_user_id: str,
    project_id: str,
    reason: str,
) -> None:
```

Use it for clip mismatch, composite mismatch, and composite rebuild. Preserve immutable QC reports; exact digest lookup makes them stale. Record the reason in `final_approval_notes`.

- [ ] **Step 5: Force rebuild based on trusted artifact identity**

Set `need_rebuild=True` when the current composite SHA differs from the stored composite artifact SHA or its clip/request provenance differs. Never overwrite the stored artifact with a tampered digest before rebuilding. Promote only a fully decoded staging composite with `os.replace()`.

- [ ] **Step 6: Run integrity tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "digest or tamper" -v
uv run pytest tests/hermes_personal/product_video/test_export_integrity.py -q
```

Expected: all pass; tamper tests assert both bytes and approval state.

- [ ] **Step 7: Commit Task 3**

```powershell
git add hermes_personal/integrations/video_factory/server.py hermes_personal/integrations/video_factory/repository.py tests/hermes_personal/product_video/test_production_integrity.py
git commit -m "fix(product-video): invalidate approvals on artifact tampering"
```

---

### Task 4: Propagate Exact Render And QC Lineage End To End

**Files:**
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/product_video/qc/service.py`
- Modify: `hermes_personal/product_video/qc/image_qc.py`
- Modify: `hermes_personal/product_video/qc/keyframe_qc.py`
- Modify: `hermes_personal/product_video/qc/video_qc.py`
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`
- Test: `tests/hermes_personal/product_video/test_happy_path_e2e.py`

**Interfaces:**
- Produces and consumes the required lineage tuple: `owner_user_id`, `project_id`, `workflow_id`, `artifact_id`, `artifact_version`, `sha256`.

- [ ] **Step 1: Add failing lineage tests**

Assert that render polling returns the complete tuple, the MCP adapter preserves it, Video QC stores it unchanged, and export rejects missing or mismatched workflow, artifact ID, artifact version, owner, project, or SHA. Add a version-2 render case so hardcoded version 1 cannot pass.

- [ ] **Step 2: Confirm failures**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "lineage or version_two or workflow_required" -v
```

- [ ] **Step 3: Return canonical lineage from render polling**

Every completed batch response from `get_job_status()` must include:

```python
{
    "owner_user_id": batch.owner_user_id,
    "project_id": batch.project_id,
    "workflow_id": batch.workflow_id,
    "artifact_id": batch.composite_artifact_id,
    "artifact_version": batch.version,
    "version": batch.version,
    "sha256": composite_sha,
}
```

The fast reuse and newly composed branches must return the same contract.

- [ ] **Step 4: Preserve lineage through the adapter and aggregate**

In `MCPVideoFactoryAdapter.render_video()`, stop emitting a fixed version. Copy the six canonical fields from the polled response into the returned artifact, while retaining the raw payload for compatibility.

- [ ] **Step 5: Make QC runners strict**

Remove `default-owner`, `proj_{workflow_id}`, and artifact-version fallbacks from production QC runners. Require explicit owner, project, artifact ID, and positive artifact version. In `ProductVideoQCService.run()`, extract them from the render artifact, verify the artifact SHA against disk, and pass them to `run_video_qc()`.

- [ ] **Step 6: Make export strict**

Remove workflow inference by latest project report. Reject absent lineage before querying QC. Query only `get_verified_pass_report()` with all six fields and verify the source path corresponds to the canonical active composite artifact.

- [ ] **Step 7: Replace mocked QC in one happy-path E2E**

Use a deterministic evaluator stub, but invoke the real `ProductVideoQCService`, `QCReportRepository`, workflow aggregate, and `server.export()`. Do not monkeypatch `ProductVideoQCService.run()` in this test.

- [ ] **Step 8: Run lineage and happy-path tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py tests/hermes_personal/product_video/test_happy_path_e2e.py tests/hermes_personal/product_video/test_video_qc.py -q
```

Expected: all pass, including version 2 and missing-workflow rejection.

- [ ] **Step 9: Commit Task 4**

```powershell
git add hermes_personal/integrations/video_factory/server.py hermes_personal/product_video/handlers.py hermes_personal/product_video/qc tests/hermes_personal/product_video/test_production_integrity.py tests/hermes_personal/product_video/test_happy_path_e2e.py
git commit -m "fix(product-video): bind QC and export to exact render lineage"
```

---

### Task 5: Enforce Workspace Containment On Production Artifacts

**Files:**
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/product_video/storage/layout.py` only if a named resolver is needed
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`
- Test: `tests/hermes_personal/product_video/test_export_integrity.py`

**Interfaces:**
- Consumes: `ProductVideoWorkspaceLayout.resolve_path()` and `get_trusted_exchange_roots()`.
- Produces: separate strict resolution rules for canonical artifacts and external reference ingestion.

- [ ] **Step 1: Add failing server-path tests**

Call `server.export()` with a valid decodable MP4 outside the workspace and assert `CONTAINMENT_VIOLATION`. Call `resource_pack_save()` with a reference inside a configured exchange root and assert it is ingested, then stored as a workspace-relative URI.

- [ ] **Step 2: Confirm the valid outside-workspace video currently reaches export logic**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "server_path or exchange_root" -v
```

- [ ] **Step 3: Remove `_normalize_file_path()` fail-open behavior**

Make canonical callers use `get_workspace_layout().resolve_path()` directly. Do not catch containment exceptions. For `resource_pack_save()`, pass the original source URI to `ingest_reference()`, whose configured exchange-root check is the only permitted external-file boundary.

- [ ] **Step 4: Verify export source against the artifact repository**

Before decoding or QC lookup, fetch the exact composite artifact by owner and artifact ID, resolve its relative path under the workspace, and require it to equal the submitted source path and SHA.

- [ ] **Step 5: Run path and export tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -k "path or containment or exchange_root" -v
uv run pytest tests/hermes_personal/product_video/test_export_integrity.py -q
```

- [ ] **Step 6: Commit Task 5**

```powershell
git add hermes_personal/integrations/video_factory/server.py hermes_personal/product_video/storage/layout.py tests/hermes_personal/product_video/test_production_integrity.py tests/hermes_personal/product_video/test_export_integrity.py
git commit -m "fix(product-video): enforce canonical artifact containment"
```

---

### Task 6: Complete The End-Keyframe Contract

**Files:**
- Modify: `hermes_personal/product_video/creative/prompts.py`
- Modify: `hermes_personal/product_video/creative/contracts.py`
- Modify: `hermes_personal/product_video/handlers.py` only if persistence assertions expose a gap
- Test: `tests/hermes_personal/product_video/test_creative_contracts.py`
- Test: `tests/hermes_personal/product_video/test_storyboard_compiler.py`
- Test: `tests/hermes_personal/product_video/test_production_integrity.py`

**Interfaces:**
- Produces: an explicit per-scene policy and a model-supplied omission reason when policy is `omitted`.

- [ ] **Step 1: Add failing contract tests**

Assert `ScriptScenePlanV2.from_dict()` rejects a scene missing `end_keyframe_policy`, rejects omitted policy without `end_keyframe_omission_reason`, and does not synthesize `continuous_motion_single_shot`. Assert generated/required policies generate an end request and omitted policy persists its exact reason into storyboard digest and export provenance.

- [ ] **Step 2: Confirm current defaults make the tests fail**

```powershell
uv run pytest tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_storyboard_compiler.py -k "end_keyframe" -v
```

- [ ] **Step 3: Require both fields in generated JSON**

Add `end_keyframe_omission_reason` to the scene schema's `required` list. Require an empty string for `required`/`generated`; require a non-empty grounded reason for `omitted`.

- [ ] **Step 4: Remove parser fabrication**

In `ScriptScenePlanV2.from_dict()`, raise a descriptive `ValueError` when either decision field is missing or inconsistent. Do not provide a semantic omission default in `ScriptSceneV2`.

- [ ] **Step 5: Run creative and provenance tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_storyboard_compiler.py tests/hermes_personal/product_video/test_production_integrity.py -q
```

- [ ] **Step 6: Commit Task 6**

```powershell
git add hermes_personal/product_video/creative/prompts.py hermes_personal/product_video/creative/contracts.py hermes_personal/product_video/handlers.py tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_storyboard_compiler.py tests/hermes_personal/product_video/test_production_integrity.py
git commit -m "fix(product-video): require explicit end-keyframe decisions"
```

---

### Task 7: Verify The Real Pipeline And Correct The Report

**Files:**
- Modify: `tests/hermes_personal/product_video/test_production_integrity.py`
- Modify: `tests/hermes_personal/product_video/test_happy_path_e2e.py`
- Modify: `docs/production-integrity-fixes-2026-09-18.md`
- Modify: `reports/2026-09-17-three-product-video-remediation-report.md`

**Interfaces:**
- Consumes: all production behavior from Tasks 1-6.
- Produces: reproducible verification evidence and an accurate remaining-risk statement.

- [ ] **Step 1: Remove misleading tests and names**

Replace tests that only exercise `QCReportRepository` while claiming composite rebuild coverage. Every tamper test must call `server.get_job_status()` or `server.export()` and assert durable project, batch, operation, artifact, and approval state.

- [ ] **Step 2: Run focused integrity tests**

```powershell
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -v
```

Expected: all adversarial production-path tests pass.

- [ ] **Step 3: Run the full Product Video suite**

```powershell
uv run pytest tests/hermes_personal/product_video -q
```

Expected: zero failures.

- [ ] **Step 4: Run the full Hermes Personal and MCP suites**

```powershell
uv run pytest tests/hermes_personal -q
uv run pytest tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q
```

Expected: zero failures.

- [ ] **Step 5: Run lint**

```powershell
uv run ruff check hermes_personal tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py
```

Expected: `All checks passed!`

- [ ] **Step 6: Update reports with evidence, not claims**

Record exact commands, counts, elapsed times, and remaining limitations. Do not use `production-ready`, `all gaps closed`, or equivalent language unless every acceptance criterion below has a passing production-path test.

- [ ] **Step 7: Commit verification and reports**

```powershell
git add tests/hermes_personal/product_video/test_production_integrity.py tests/hermes_personal/product_video/test_happy_path_e2e.py docs/production-integrity-fixes-2026-09-18.md reports/2026-09-17-three-product-video-remediation-report.md
git commit -m "test(product-video): prove production integrity end to end"
```

---

## Final Acceptance Criteria

- Invalid provider media never reaches `completed` in the production polling path.
- Missing scene digest remains missing and causes a fail-closed result; no backfill occurs.
- No SQL update scopes scene operations by `scene_id` alone.
- Changed clip bytes invalidate Final approval and cannot be composed.
- Changed decodable composite bytes force an atomic rebuild and invalidate Final approval.
- Render, QC, approval, and export carry the same owner/project/workflow/artifact/version/SHA tuple.
- Export never infers workflow or artifact version and never accepts a digest-only QC match.
- Canonical artifacts outside the workspace are rejected before decode or QC.
- Trusted exchange roots remain usable only for reference ingestion.
- End-keyframe policy and omission reason are explicit model outputs, never parser-generated semantics.
- At least one E2E test invokes the real QC service and repository through export.
- Product Video, Hermes Personal, MCP, and Ruff verification all pass.

## Execution Prompt

```text
Implement the plan at docs/superpowers/plans/2026-09-18-product-video-production-integrity-closure.md task by task.

Use the existing Hermes Product Video architecture. Do not add parallel render, storage, QC, or workflow systems. Preserve unrelated changes in the dirty worktree.

Start by reproducing each defect with a failing test against the real production path. The critical path is server.get_job_status() -> durable scene operation -> composite artifact -> ProductVideoQCService/QCReportRepository -> Final Approval -> server.export(). A unit test of scene_validator.py or QCReportRepository alone is not sufficient evidence.

Mandatory outcomes:
- Remove scene digest backfilling and every scene_id-only update.
- Route provider completion in server.get_job_status() through full decode/duration/aspect/SHA validation before the operation becomes completed.
- Persist expected duration and aspect ratio so validation survives restart.
- Invalidate Final approval after any clip/composite byte change; rebuild a changed composite only from verified clips.
- Carry owner_user_id, project_id, workflow_id, artifact_id, artifact_version, and SHA unchanged from render through QC and export.
- Remove workflow/version inference and default-owner/project fallbacks from production QC/export.
- Make server-side artifact path handling fail closed; external paths are permitted only for reference ingestion through configured exchange roots.
- Finish, do not defer, the end-keyframe contract: explicit policy and explicit omission reason with no semantic parser default.

Do not report completion after the 11 current tests pass. Replace misleading tests with adversarial tests that call the production server methods and assert durable DB/project/approval state. Run every verification command in Task 7 and include exact outputs in the updated report.

Stop and report a concrete blocker only if the same blocking condition persists after three technically distinct attempts. Otherwise continue through implementation, verification, and report correction.
```
