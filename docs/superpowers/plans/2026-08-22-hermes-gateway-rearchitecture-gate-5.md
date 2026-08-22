# Product Intelligence To Video Factory Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the working product-research and AI-video capabilities behind typed anti-corruption adapters and execute the full product-to-video flow through the durable workflow and HITL gates.

**Architecture:** Product Intelligence and Video Factory remain independent bounded contexts and canonical writers. Hermes stores only opaque, versioned, digest-verified references and owns their workflow binding, approvals, budget, and job dispatch. Initial migration is additive and reconciled; legacy stores remain readable and untouched.

**Tech Stack:** Python 3.10+, MCP client abstractions, SQLite, SHA-256, Gate 3 capability catalog, Gate 4 workflow/jobs, pytest fakes, `uv`.

## Global Constraints

- Gate 4 must pass before this plan starts.
- Legacy `D:\work\hermes-agent\src\hermes` is read-only migration source during implementation.
- Product Intelligence owns evidence, product identity, media, resource packs, and immutable locks.
- Video Factory owns creative briefs, scene plans, storyboards, renders, and exports.
- Hermes owns workflow, approval, budget, jobs, and cross-context binding only.
- Cross-context contracts use opaque IDs, schema versions, artifact versions, and digests; never absolute paths.
- Every paid provider call is behind a fake in automated tests.
- No legacy database, artifact, or user media is deleted or overwritten.

---

## File Map

- `hermes_personal/integrations/product_intelligence/contracts.py`: PI request/result references.
- `hermes_personal/integrations/product_intelligence/client.py`: stable capability to MCP client adapter.
- `hermes_personal/integrations/video_factory/contracts.py`: creative/render artifact references.
- `hermes_personal/integrations/video_factory/client.py`: VF capability adapter.
- `hermes_personal/product_video/binding.py`: immutable PI-to-VF resource binding.
- `hermes_personal/product_video/workflow.py`: exact state handlers and invalidation rules.
- `hermes_personal/product_video/handlers.py`: deterministic durable job handlers.
- `hermes_personal/migration/inventory.py`: read-only legacy inventory.
- `hermes_personal/migration/reconcile.py`: counts, checksums, versions, and rollback manifest.

### Task 1: Freeze Cross-Context Product And Video Contracts

**Files:**
- Create: `hermes_personal/integrations/product_intelligence/contracts.py`
- Create: `hermes_personal/integrations/video_factory/contracts.py`
- Create: `hermes_personal/integrations/product_intelligence/__init__.py`
- Create: `hermes_personal/integrations/video_factory/__init__.py`
- Test: `tests/hermes_personal/product_video/test_integration_contracts.py`

**Interfaces:**
- Consumes: stable capability input/output schemas from Gate 3.
- Produces: typed opaque references accepted by Gate 4 artifacts.

- [ ] **Step 1: Write serialization and ownership tests**

```python
def test_resource_lock_is_opaque_versioned_and_digest_verified():
    ref = ProductResourceLockRef("pi", "lock_7", 3, "1.0", "sha256:abc", "product_9")
    assert ref.to_artifact_ref().owner == "product_intelligence"
    assert not hasattr(ref, "absolute_path")

def test_video_artifact_rejects_wrong_owner():
    with pytest.raises(ValueError, match="video_factory"):
        VideoArtifactRef("pi", "storyboard_1", "storyboard", 1, "1.0", "sha256:x")
```

- [ ] **Step 2: Verify red and implement exact records**

Run: `uv run pytest tests/hermes_personal/product_video/test_integration_contracts.py -q`

Expected: FAIL on missing packages.

Define `ProductResearchRef`, `ResourcePackDraftRef`, `ProductResourceLockRef`, and `VideoArtifactRef`. Every reference validates nonblank opaque ID, positive artifact version, declared schema version, `sha256:` digest, and canonical owner. Define request records for product URL/research criteria, brief creation, scene-plan creation, storyboard creation, render, and export; each carries workflow/job/idempotency IDs.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/product_video/test_integration_contracts.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/integrations tests/hermes_personal/product_video/test_integration_contracts.py
git commit -m "feat: define product video integration contracts"
```

### Task 2: Port Product Intelligence Behind A Stable Client

**Files:**
- Create: `hermes_personal/integrations/product_intelligence/client.py`
- Test: `tests/hermes_personal/product_video/test_product_intelligence_client.py`
- Reference only: `D:\work\hermes-agent\src\hermes\application\product_resource_service.py`
- Reference only: `D:\work\hermes-agent\src\hermes\mcp\product\server.py`
- Reference only: `D:\work\hermes-agent\src\hermes\product_intelligence\tools.py`

**Interfaces:**
- Consumes: Gate 3 `product.research`, `product.resource_pack.build`, and `product.resource_pack.lock` bindings.
- Produces: `ProductIntelligenceClient.research`, `build_resource_pack`, and `lock_resource_pack`.

- [ ] **Step 1: Write fake-MCP client tests**

Test stable-ID resolution to current wire name, owner/schema/digest validation, product URL and criteria inputs, idempotency propagation, unavailable binding failure, malformed provider output rejection, and immutable lock response.

- [ ] **Step 2: Verify red and implement the adapter**

Run: `uv run pytest tests/hermes_personal/product_video/test_product_intelligence_client.py -q`

Expected: FAIL on missing client.

The client must resolve policy and schema through `CapabilityCatalogService`, call an injected `ToolInvoker.invoke(wire_name, payload, idempotency_key)`, parse structured JSON into the Gate 5 contracts, and return references only. It must not copy provider files into Hermes storage or synthesize missing evidence/media IDs.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/product_video/test_product_intelligence_client.py -q`

Expected: all adapter cases pass.

```powershell
git add -- hermes_personal/integrations/product_intelligence/client.py tests/hermes_personal/product_video/test_product_intelligence_client.py
git commit -m "feat: adapt product intelligence capabilities"
```

### Task 3: Port Video Factory Behind A Stable Client

**Files:**
- Create: `hermes_personal/integrations/video_factory/client.py`
- Test: `tests/hermes_personal/product_video/test_video_factory_client.py`
- Reference only: `D:\work\hermes-agent\src\hermes\mcp\video_factory\server.py`
- Reference only: `D:\work\hermes-agent\src\hermes\domain\video_factory.py`
- Reference only: `D:\work\hermes-agent\src\hermes\adapters\sqlite\video_factory_repository.py`

**Interfaces:**
- Consumes: Gate 3 video capability bindings and a locked product-resource reference.
- Produces: typed creative, scene, storyboard, render, and export references.

- [ ] **Step 1: Write fake-MCP client tests**

Test each stable video capability, input lock digest propagation, workflow/job/idempotency correlation, malformed artifact rejection, unavailable provider, actual-cost forwarding, and prohibition of placeholder/fake artifact IDs.

- [ ] **Step 2: Verify red and implement**

Run: `uv run pytest tests/hermes_personal/product_video/test_video_factory_client.py -q`

Expected: FAIL on missing client.

Use the same injected `ToolInvoker` boundary as PI. Validate that every output owner is `video_factory`, artifact type matches the requested capability, version is positive, digest is present, and render/export outputs include real provider-issued artifact IDs. Return provider cost metadata separately for the Gate 4 ledger.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/product_video/test_video_factory_client.py -q`

Expected: all client tests pass.

```powershell
git add -- hermes_personal/integrations/video_factory/client.py tests/hermes_personal/product_video/test_video_factory_client.py
git commit -m "feat: adapt video factory capabilities"
```

### Task 4: Implement Product-To-Video Binding And Invalidation

**Files:**
- Create: `hermes_personal/product_video/binding.py`
- Create: `hermes_personal/product_video/workflow.py`
- Create: `hermes_personal/product_video/__init__.py`
- Test: `tests/hermes_personal/product_video/test_binding.py`

**Interfaces:**
- Consumes: PI lock ref, VF artifact refs, Gate 4 aggregate/events.
- Produces: immutable `ProductVideoBinding` versions and downstream invalidation commands.

- [ ] **Step 1: Write dependency invalidation tests**

```python
def test_new_product_lock_invalidates_all_video_artifacts(binding_service, binding_factory):
    current = binding_factory(brief=True, scene=True, storyboard=True, render=True)
    updated = binding_service.replace_product_lock(current, lock_ref(version=2, digest="sha256:new"))
    assert updated.version == current.version + 1
    assert updated.brief_ref is None
    assert updated.scene_plan_ref is None
    assert updated.storyboard_ref is None
    assert updated.render_ref is None

def test_new_scene_plan_invalidates_storyboard_and_render_but_not_brief(binding_service, binding_factory):
    updated = binding_service.replace_scene_plan(binding_factory(all_artifacts=True), scene_ref(version=2))
    assert updated.brief_ref is not None
    assert updated.storyboard_ref is None
    assert updated.render_ref is None
```

- [ ] **Step 2: Verify red and encode exact dependency graph**

Run: `uv run pytest tests/hermes_personal/product_video/test_binding.py -q`

Expected: FAIL on missing binding.

Dependencies are `product_lock -> brief -> scene_plan -> storyboard -> render -> export`. Any changed upstream ID/version/digest clears every descendant reference and invalidates corresponding pending/approved approvals through `ApprovalService.invalidate_for_artifact`.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/product_video/test_binding.py -q`

Expected: all invalidation cases pass.

```powershell
git add -- hermes_personal/product_video tests/hermes_personal/product_video/test_binding.py
git commit -m "feat: bind product locks to video artifacts"
```

### Task 5: Register Deterministic Product-To-Video Job Handlers

**Files:**
- Create: `hermes_personal/product_video/handlers.py`
- Test: `tests/hermes_personal/product_video/test_handlers.py`

**Interfaces:**
- Consumes: Gate 4 `JobContext`, PI/VF clients, workflow engine, budget service.
- Produces: registered handlers for research, resource pack, lock, brief, scene, storyboard, render, and export.

- [ ] **Step 1: Write stage-boundary tests**

For each exact workflow state, assert only its legal handler can run. Assert no job is dispatched from `AwaitingProductLock`, `AwaitingBriefApproval`, `AwaitingSceneApproval`, `AwaitingStoryboardApproval`, or `AwaitingFinalApproval` until the matching approval command commits.

- [ ] **Step 2: Verify red and implement handler protocol**

Run: `uv run pytest tests/hermes_personal/product_video/test_handlers.py -q`

Expected: FAIL on missing handlers.

Each handler must load workflow/version, validate expected state and input refs, reserve budget before a paid invocation, call exactly one client method, record actual cost/release reservation, and return `JobSucceeded(artifact_ref, next_command)` or typed `JobFailed(retryable, code)`. It cannot call another handler directly.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/product_video/test_handlers.py -q`

Expected: every HITL and stage-ownership test passes.

```powershell
git add -- hermes_personal/product_video/handlers.py tests/hermes_personal/product_video/test_handlers.py
git commit -m "feat: execute product video workflow stages"
```

### Task 6: Inventory And Reconcile Legacy Data Without Deletion

**Files:**
- Create: `hermes_personal/migration/inventory.py`
- Create: `hermes_personal/migration/reconcile.py`
- Create: `hermes_personal/migration/__init__.py`
- Test: `tests/hermes_personal/migration/test_reconciliation.py`
- Create: `docs/hermes-personal/product-video-migration.md`

**Interfaces:**
- Consumes: configured read-only legacy stores and target adapter exports.
- Produces: `MigrationManifest`, per-entity counts/checksums/versions, and rollback instructions.

- [ ] **Step 1: Write fixture-based reconciliation tests**

Test identical inventory, missing target row, digest mismatch, duplicate source identity, unsupported schema version, rerun idempotency, and rollback manifest completeness. Open source SQLite with URI `mode=ro`.

- [ ] **Step 2: Verify red and implement additive migration records**

Run: `uv run pytest tests/hermes_personal/migration/test_reconciliation.py -q`

Expected: FAIL on missing migration package.

Inventory by bounded context and entity type. Compute count plus SHA-256 over sorted `(opaque_id, version, digest)` tuples. Store source URI fingerprint, source schema version, target IDs created, started/completed timestamps, and status. Rollback removes only target records named in that manifest and never touches source data or media.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/migration/test_reconciliation.py -q`

Expected: all reconciliation cases pass.

```powershell
git add -- hermes_personal/migration tests/hermes_personal/migration/test_reconciliation.py docs/hermes-personal/product-video-migration.md
git commit -m "feat: reconcile legacy product video data"
```

### Task 7: Prove The Full Fake Product-To-Video Flow

**Files:**
- Create: `tests/hermes_personal/product_video/test_product_to_video_e2e.py`
- Create: `tests/hermes_personal/product_video/test_restart_recovery.py`
- Create: `docs/hermes-personal/product-video-runbook.md`

**Interfaces:**
- Consumes: Gates 2-5 services with fake PI/VF invokers.
- Produces: end-to-end acceptance evidence and operator runbook.

- [ ] **Step 1: Implement the complete acceptance scenario**

Start from a TikTok Shop PDP request; fake PI returns research and resource pack; pause at Product Lock; approve from Web; create and approve brief, scene plan, storyboard; reserve render budget; render; approve final from Telegram; export. Assert the exact fourteen states in order, real fake-provider artifact IDs/digests, one approval per gate, and one cost ledger entry per paid call.

- [ ] **Step 2: Add restart and failure matrix**

Restart repository/engine/worker objects at every awaiting and executing state. Cover retryable provider timeout, permanent schema failure, stale approval after changed storyboard, budget overrun, MCP unavailable, duplicate terminal event, and worker lease expiry. Assert no gate is skipped and no duplicate paid effect occurs.

- [ ] **Step 3: Run Gate 5 verification**

```powershell
uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/approvals tests/hermes_personal/budgets tests/hermes_personal/jobs -q
git diff --check
```

Expected: all suites pass without network; diff check is empty.

- [ ] **Step 4: Commit acceptance evidence**

```powershell
git add -- tests/hermes_personal/product_video/test_product_to_video_e2e.py tests/hermes_personal/product_video/test_restart_recovery.py docs/hermes-personal/product-video-runbook.md
git commit -m "test: prove durable product to video workflow"
```

## Gate 5 Exit Criteria

- PI and VF are callable only through stable, policy-checked capability adapters.
- Hermes persists only opaque cross-context refs with owner/schema/version/digest.
- The exact product-to-video state sequence pauses at all five HITL gates.
- Changed artifacts invalidate stale approval and every affected descendant.
- Paid calls obey idempotency and budget policy; tests make no live paid calls.
- Restart recovery works in waiting and executing states.
- Legacy data reconciliation has no unexplained count/checksum/version differences and a tested rollback manifest.
