# Hermes Agent Platform Standardization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standardize Hermes as a secure general-purpose agent platform with one conversational runtime, governed capability contracts, durable media projection, a canonical FastAPI operator API, and an explicit Product Intelligence to Video Factory boundary.

**Architecture:** Preserve `agent/conversation_loop.py` and `tools.registry` as canonical runtime foundations. Standardize metadata and security around existing native/MCP capabilities, keep Product Intelligence external, move job completion projection into the durable execution plane, and migrate Web and legacy channels through compatibility adapters rather than a big-bang rewrite.

**Tech Stack:** Python 3.10+, FastAPI, FastMCP, Pydantic, SQLite, React 18, TypeScript, Vite, Playwright, pytest, native PowerShell.

## Global Constraints

- Do not modify `agent/conversation_loop.py` unless a separately reproduced defect proves it necessary.
- Do not import `product_scout` or `media` from Hermes source.
- Do not merge Product Intelligence, Hermes, and Video Factory databases.
- Preserve Affiliate Product scoring, commission, shortlist, and review ownership.
- Preserve existing uncommitted user changes.
- Keep compatibility paths until parity, rollback, and an observation window are verified.
- Use fake providers in automated tests; do not call paid image, video, or TTS providers.
- Browser media access must use opaque asset IDs, never arbitrary filesystem paths.
- Bind owner/principal identity from authenticated runtime context, never from model-selected arguments.
- Use TDD for every behavioral task: focused failing test, minimal implementation, focused pass, then broader regression.

---

## Program Gates

The program is divided into independently releasable gates:

1. **Gate A - Security baseline:** Tasks 1-3.
2. **Gate B - Durable production plane:** Tasks 4-5.
3. **Gate C - Product Intelligence contract:** Tasks 6-7.
4. **Gate D - Canonical operator plane:** Tasks 8-9.
5. **Gate E - Channel convergence and retirement:** Tasks 10-11.

Do not begin a later gate while a P0 test in the previous gate is failing.

### Task 1: Freeze the Platform Architecture Contract

**Files:**
- Create: `docs/architecture-decisions/010-general-purpose-agent-platform.md`
- Modify: `docs/architecture-decisions/001-hermes-agent-migration-audit.md`
- Modify: `docs/architecture-decisions/009-canonical-source-runtime.md`
- Create: `tests/hermes/test_platform_architecture_contract.py`
- Reference: `docs/superpowers/specs/2026-08-12-hermes-agent-platform-standardization-design.md`

**Interfaces:**
- Consumes: the approved design spec.
- Produces: one current architecture authority and executable import-boundary checks.

- [ ] **Step 1: Write the failing architecture tests**

```python
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_hermes_does_not_import_product_intelligence_packages():
    production_roots = (
        "agent", "apps", "core", "gateway", "gui", "hermes", "hermes_cli",
        "mcp_servers", "providers", "server", "tools", "workers",
    )
    forbidden_roots = {"product_scout", "media"}
    violations = []
    for directory in production_roots:
        for path in (ROOT / directory).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name.split(".", 1)[0] in forbidden_roots for name in names):
                    violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_workers_do_not_import_agent_or_channel_layers():
    violations = []
    for path in (ROOT / "workers").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "agent.conversation_loop" in text or "telegram_bot" in text or "gui." in text:
            violations.append(str(path.relative_to(ROOT)))
    assert violations == []


def test_current_adr_marks_adr_001_as_superseded():
    text = (ROOT / "docs/architecture-decisions/001-hermes-agent-migration-audit.md").read_text(encoding="utf-8")
    assert "Status: Superseded" in text
    assert "ADR-010" in text
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_platform_architecture_contract.py -q
```

Expected: the ADR status test fails because ADR-001 is still marked `Proposed`.
Any direct PI import or syntax-invalid file still classified as a production root
is an additional architecture failure that must be resolved or explicitly
classified as retired before this gate passes.

- [ ] **Step 3: Publish ADR-010 and mark conflicting history**

Create ADR-010 by promoting the decisions and ownership tables from the design spec. Change the top of ADR-001 to:

```markdown
**Status: Superseded by ADR-007, ADR-009, and ADR-010**

This document records the pre-cutover position from 2026-08-05. It is retained
for history and must not be used as the current runtime authority.
```

Add ADR-010 to ADR-009's references and state that FastAPI cutover, capability governance, and channel convergence remain active migration work.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the command from Step 2. Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add docs/architecture-decisions/001-hermes-agent-migration-audit.md docs/architecture-decisions/009-canonical-source-runtime.md docs/architecture-decisions/010-general-purpose-agent-platform.md tests/hermes/test_platform_architecture_contract.py
git commit -m "docs: establish Hermes platform architecture authority"
```

### Task 2: Isolate MCP Trust Domains and Registration Semantics

**Files:**
- Modify: `tools/mcp_tool.py`
- Modify: `hermes/runtime_layout.py`
- Test: `tests/tools/test_mcp_tool_security.py`
- Test: `tests/tools/test_mcp_tool_cache.py`
- Test: `tests/hermes/test_canonical_runtime.py`

**Interfaces:**
- Consumes: existing `mcp_servers` configuration.
- Produces: `_build_safe_env(user_env, allowed_secret_names)`, one registration validator used by eager/lazy/refresh paths, and operator-respecting managed MCP config.

- [ ] **Step 1: Add failing secret-scope and collision-parity tests**

```python
def test_external_mcp_receives_only_allowlisted_secret(monkeypatch):
    monkeypatch.setenv("PATH", "safe-path")
    monkeypatch.setenv("SECRET_A", "alpha")
    monkeypatch.setenv("SECRET_B", "beta")
    monkeypatch.setattr("hermes_cli.env_loader.get_secret_source", lambda key: "vault" if key.startswith("SECRET_") else None)

    env = _build_safe_env({"SECRET_A": "${SECRET_A}"}, allowed_secret_names={"SECRET_A"})

    assert env["SECRET_A"] == "alpha"
    assert "SECRET_B" not in env


def test_external_mcp_rejects_interpolation_outside_allowlist(monkeypatch):
    monkeypatch.setenv("SECRET_A", "alpha")
    monkeypatch.setenv("SECRET_B", "beta")
    with pytest.raises(SecretScopeError):
        _build_safe_env({"X": "${SECRET_B}"}, allowed_secret_names={"SECRET_A"})


def test_eager_and_lazy_discovery_reject_same_normalized_collision():
    tools = [fake_tool("read-file"), fake_tool("read_file")]
    assert normalized_registration_result(tools, mode="eager") == normalized_registration_result(tools, mode="lazy")
    assert normalized_registration_result(tools, mode="eager").accepted == ()
```

Also change the canonical runtime expectation so an explicit `enabled: false` remains false after normalization.

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_tool_cache.py tests\hermes\test_canonical_runtime.py -q
```

Expected: failures show secret-source variables are inherited globally, eager/lazy collision results differ, and runtime normalization forces enabled state.

- [ ] **Step 3: Implement explicit secret allowlisting**

Use this contract in `tools/mcp_tool.py`:

```python
def _build_safe_env(
    user_env: dict[str, str] | None,
    allowed_secret_names: set[str] | None = None,
) -> dict[str, str]:
    allowed = allowed_secret_names or set()
    env = {
        key: value
        for key, value in os.environ.items()
        if key in _SAFE_ENV_KEYS
        or key.upper() in _SAFE_ENV_KEYS_CASE_INSENSITIVE
        or key.startswith("XDG_")
    }
    for key in allowed:
        if key in os.environ:
            env[key] = os.environ[key]
    for key, value in (user_env or {}).items():
        references = _find_env_references(str(value))
        denied = references - allowed
        if denied:
            raise SecretScopeError(f"environment references are not allowlisted: {sorted(denied)}")
        env[key] = _interpolate_env_value(str(value), source=env)
    return env
```

Read `secret_allowlist` from each MCP server config. Do not infer permission from presence in a secret backend.

- [ ] **Step 4: Unify normalized registration**

Extract one pure function returning the complete accepted/rejected set before registry mutation. Call it from initial discovery, lazy cache restore, and dynamic refresh. Commit registry changes only after the complete server tool list validates.

- [ ] **Step 5: Preserve operator disable and platform Python resolution**

In `hermes/runtime_layout.py`, populate missing managed-server fields but preserve an explicit boolean `enabled`. Resolve the executable as `Scripts/python.exe` on Windows and `bin/python` elsewhere.

- [ ] **Step 6: Verify GREEN and run MCP regression**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_tool_cache.py tests\tools\test_mcp_tool_circuit_breaker.py tests\hermes\test_canonical_runtime.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add tools/mcp_tool.py hermes/runtime_layout.py tests/tools/test_mcp_tool_security.py tests/tools/test_mcp_tool_cache.py tests/hermes/test_canonical_runtime.py
git commit -m "security: isolate MCP trust domains"
```

### Task 3: Add Capability Metadata and Skill Contract Validation

**Files:**
- Create: `hermes/capabilities/__init__.py`
- Create: `hermes/capabilities/models.py`
- Create: `hermes/capabilities/catalog.py`
- Create: `hermes/security/__init__.py`
- Create: `hermes/security/principal.py`
- Modify: `tools/registry.py`
- Modify: `tools/skills_guard.py`
- Modify: `tools/skill_manager_tool.py`
- Modify: `run_agent.py`
- Modify: `hermes_cli/oneshot.py`
- Modify: `gateway/run.py`
- Modify: `gateway/platforms/api_server.py`
- Modify: `telegram_bot.py`
- Modify: `gui/tabs/assistant_tab.py`
- Modify: `gui/app.py`
- Modify: `gui/app_staged.py`
- Modify: `skills/video-production/SKILL.md`
- Modify: `skills/research/SKILL.md`
- Modify: `skills/knowledge-learning/SKILL.md`
- Modify: `skills/affiliate-product-research/SKILL.md`
- Modify: `skills/product-research/SKILL.md`
- Test: `tests/hermes/test_capability_catalog.py`
- Test: `tests/tools/test_skill_contracts.py`
- Test: `tests/hermes/test_principal_ingress.py`

**Interfaces:**
- Produces: `CapabilityDescriptor`, `CapabilityCatalog.from_registry_snapshot()`, `PrincipalContext`, session-bound owner injection at every current free-text entry point, and a validator that resolves every skill tool reference.
- Does not replace: `tools.registry.registry` dispatch ownership.

- [ ] **Step 1: Write failing model/catalog tests**

```python
def test_catalog_distinguishes_external_and_first_party_mcp():
    catalog = CapabilityCatalog.from_entries([
        fake_entry("mcp__hermes_video__video_analyze", toolset="mcp-hermes_video"),
        fake_entry("mcp__product_intelligence__research_product", toolset="mcp-product_intelligence"),
    ], managed_servers={"hermes_video"})
    assert catalog.require("mcp__hermes_video__video_analyze").source == "hermes_mcp"
    assert catalog.require("mcp__product_intelligence__research_product").source == "external_mcp"


def test_bundled_skill_tool_references_resolve_to_canonical_names():
    errors = validate_bundled_skill_tools(ROOT / "skills", runtime_tool_names())
    assert errors == []


def test_first_party_owner_argument_is_bound_from_principal():
    principal = PrincipalContext("actor-1", "owner-1", "cli", "session-1", ("admin",))
    args = bind_principal_arguments(
        {"owner_user_id": "impersonated", "run_id": "run-1"},
        principal,
        principal_mode="session",
    )
    assert args["owner_user_id"] == "owner-1"


def test_every_current_entrypoint_binds_and_clears_principal(entrypoint_matrix):
    for entrypoint in entrypoint_matrix:
        entrypoint.run_fake_turn(owner_user_id="owner-1")
        assert entrypoint.dispatched_principal.owner_user_id == "owner-1"
        assert current_principal.get(None) is None
```

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py tests\tools\test_skill_contracts.py -q
```

- [ ] **Step 3: Implement immutable descriptor metadata**

```python
@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    wire_name: str
    owner: str
    source: Literal["native", "hermes_mcp", "external_mcp", "generated"]
    trust: Literal["first_party", "configured_external", "untrusted"]
    version: str
    toolset: str
    side_effects: Literal["read", "write", "external", "paid"]
    principal_mode: Literal["session", "server", "none"]
    idempotency: Literal["required", "supported", "none"]
    approval_policy: str
    data_classification: str
```

Build descriptors from a coherent registry snapshot. Metadata lookup may fail closed, but tool dispatch remains in `tools.registry`.

- [ ] **Step 4: Bind principal identity before first-party dispatch**

```python
@dataclass(frozen=True)
class PrincipalContext:
    actor_id: str
    owner_user_id: str
    platform: str
    session_id: str
    roles: tuple[str, ...]
```

Store the active principal in a turn-scoped context variable. Bind and clear it
around turns in every current CLI, gateway/API, Telegram, and GUI entry point
before enabling enforcement. Before dispatching a descriptor with
`principal_mode="session"`, overwrite identity fields such as `owner_user_id`
from the active principal. Only after ingress coverage tests pass, reject
dispatch when no principal is bound. External MCP servers receive identity only
when their descriptor explicitly declares a supported principal contract.

- [ ] **Step 5: Enforce canonical skill references**

Require `allowed-tools` in bundled skill frontmatter and add `metadata.hermes.requires_tools`. Replace raw ambiguous names such as `video_analyze` with `mcp__hermes_video__video_analyze` when the skill intends the offline Hermes MCP. Mark paid native alternatives explicitly.

- [ ] **Step 6: Verify GREEN and scan all bundled skills**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py tests\tools\test_skill_contracts.py tests\hermes\test_product_intelligence_integration.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add hermes/capabilities hermes/security tools/registry.py tools/skills_guard.py tools/skill_manager_tool.py run_agent.py hermes_cli/oneshot.py gateway telegram_bot.py gui/tabs/assistant_tab.py skills tests/hermes/test_capability_catalog.py tests/hermes/test_principal_ingress.py tests/tools/test_skill_contracts.py
git commit -m "feat: govern runtime capabilities and skill contracts"
```

### Task 4: Restore a Single Video Factory MCP Surface

**Files:**
- Modify: `mcp_servers/video_factory/server.py`
- Test: `tests/mcp_servers/test_video_factory_server.py`
- Test: `tests/hermes/test_video_factory_mcp_wire.py`

**Interfaces:**
- Produces: one definition per public Video Factory tool and Python 3.10/3.11-compatible FastMCP schemas.

- [ ] **Step 1: Add a wire-level failing test**

```python
def test_video_factory_mcp_lists_unique_tools(mcp_client):
    names = [tool.name for tool in mcp_client.list_tools()]
    assert len(names) == len(set(names))
    assert names.count("storyboard_save") == 1
    assert names.count("video_scene_update_status") == 1
```

Add an import test under Python 3.11-compatible validation that constructs every FastMCP tool schema.

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\mcp_servers\test_video_factory_server.py tests\hermes\test_video_factory_mcp_wire.py -q
```

Expected: collection or schema generation fails on `typing.TypedDict`, or duplicate source definitions are detected.

- [ ] **Step 3: Repair schema imports and remove duplicate definitions**

Import `TypedDict` and `NotRequired` from `typing_extensions`. Keep exactly one public function and one helper for each contract. Preserve current wire names and response shapes.

- [ ] **Step 4: Verify GREEN**

Run Step 2, then:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_video_factory_service.py tests\hermes\application\test_video_factory_f2_f5.py -q
```

- [ ] **Step 5: Commit**

```powershell
git add mcp_servers/video_factory/server.py tests/mcp_servers/test_video_factory_server.py tests/hermes/test_video_factory_mcp_wire.py
git commit -m "fix: restore canonical Video Factory MCP surface"
```

### Task 5: Make Job Completion Project into Durable Assets

**Files:**
- Modify: `hermes/db.py`
- Modify: `hermes/jobs.py`
- Modify: `hermes/application/job_event_delivery.py`
- Create: `hermes/domain/generated_asset.py`
- Create: `hermes/ports/generated_asset_repository.py`
- Create: `hermes/adapters/sqlite/generated_asset_repository.py`
- Create: `hermes/application/video_factory_job_projector.py`
- Modify: `workers/job_worker.py`
- Modify: `hermes/application/video_factory_service.py`
- Modify: `hermes/adapters/sqlite/video_factory_repository.py`
- Test: `tests/hermes/test_job_events.py`
- Test: `tests/hermes/application/test_video_factory_job_projector.py`
- Test: `tests/workers/test_canonical_job_worker.py`
- Test: `tests/hermes/adapters/sqlite/test_media_schema_migration.py`

**Interfaces:**
- Consumes: terminal job result containing project/artifact identity and provider output metadata.
- Produces: append-only terminal event, `GeneratedAsset`, and idempotent project update without a browser callback.

- [ ] **Step 1: Write failing outbox and offline-browser tests**

```python
def test_complete_appends_terminal_event_in_same_transaction(job_repository):
    job_repository.enqueue("job-1", "owner-1", "image_generate", {"project_id": "p1"})
    job_repository.claim_next("image_generate")
    job_repository.complete("job-1", {"output_path": "images/frame.png"})
    events = job_repository.list_events("job-1")
    assert [(e["event_type"], e["job_id"]) for e in events] == [("job.completed", "job-1")]


def test_completed_frame_updates_project_when_no_ui_is_running(projector_fixture):
    projector_fixture.complete_frame_job()
    projector_fixture.run_projector_once()
    project = projector_fixture.project_repository.get("owner-1", "p1")
    assert project.storyboard.frames[0].generated_asset_id == projector_fixture.asset_id
    assert projector_fixture.asset_repository.get("owner-1", projector_fixture.asset_id) is not None
```

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_job_events.py tests\hermes\application\test_video_factory_job_projector.py -q
```

- [ ] **Step 3: Migrate job-event and generated-asset schemas**

Add a forward schema version for `job_events`, the projection ledger, and the
missing generated-asset fields (`job_id`, `artifact_version`, `storage_key`,
`checksum_sha256`). Backfill legacy `local_path` values only after resolving
them under the configured workspace root; retain a compatibility read during
the observation window. Add upgrade-from-previous-version, rollback, and
round-trip tests against a copied fixture database.

- [ ] **Step 4: Append terminal events transactionally**

Add `job_events` append/list/claim/ack operations to `JobRepository`. `complete`, terminal `fail`, and `cancel` must update the job and append one event in the same SQLite transaction.

- [ ] **Step 5: Implement generated asset persistence**

```python
@dataclass(frozen=True)
class GeneratedAsset:
    asset_id: str
    owner_user_id: str
    project_id: str
    job_id: str
    artifact_type: str
    artifact_id: str
    artifact_version: int
    storage_key: str
    mime_type: str
    checksum_sha256: str
```

Use the existing `video_factory_generated_assets` table. Store a workspace-relative `storage_key`, never an unvalidated browser path.

- [ ] **Step 6: Implement the idempotent projector**

`VideoFactoryJobProjector.project(event_id)` must:

1. claim the event;
2. validate owner/project/artifact/version from the job payload;
3. normalize provider output to one asset record;
4. insert the asset idempotently;
5. update the Video Factory aggregate with optimistic version checking;
6. record the event in a projection ledger;
7. acknowledge the event.

On restart, a duplicate event must return the existing projection without submitting another provider job.

- [ ] **Step 7: Remove browser ownership of apply**

Keep `/jobs/{job_id}/apply` as a temporary internal compatibility endpoint that calls the same projector. Mark it deprecated and reject cross-owner/project requests. The React UI must no longer need it after Task 9.

- [ ] **Step 8: Verify GREEN and crash recovery**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_job_events.py tests\hermes\application\test_video_factory_job_projector.py tests\hermes\adapters\sqlite\test_media_schema_migration.py tests\workers\test_canonical_job_worker.py -q
```

- [ ] **Step 9: Commit**

```powershell
git add hermes/db.py hermes/jobs.py hermes/application/job_event_delivery.py hermes/domain/generated_asset.py hermes/ports/generated_asset_repository.py hermes/adapters/sqlite/generated_asset_repository.py hermes/application/video_factory_job_projector.py hermes/application/video_factory_service.py hermes/adapters/sqlite/video_factory_repository.py workers/job_worker.py tests
git commit -m "feat: project completed jobs into durable assets"
```

### Task 6: Publish Product Intelligence Query, Draft, and Lock Contracts

**Working directory:** `D:\work\Personal\Product-Intelligence`

**Files:**
- Modify: `product_scout/mcp_server.py`
- Modify: `media/research_persistence/repository.py`
- Create: `media/research_query/__init__.py`
- Create: `media/research_query/models.py`
- Create: `media/research_query/service.py`
- Modify: `media/resource_pack/models.py`
- Modify: `media/resource_pack/service.py`
- Create: `media/resource_pack/draft_store.py`
- Modify: `media/resource_pack/lock_store.py`
- Modify: `tools/workspace_exporter/run_research.py`
- Test: `tests/test_mcp_surface.py`
- Create: `tests/test_research_query.py`
- Create: `tests/test_resource_pack_drafts.py`
- Create: `tests/test_resource_pack_lock_contract.py`

**Interfaces:**
- Produces: paginated research/media query, persistent draft revisions, explicit immutable lock, schema version, and digest.
- Hermes consumes only these public MCP contracts.
- Scope: the initial PI catalog is admin-global. Every list/detail/media method
  requires an admin principal attestation; it is not a project-owner endpoint.

- [ ] **Step 1: Add failing contract tests**

```python
def test_build_draft_is_retrievable_and_does_not_create_lock(service, snapshot):
    draft = service.build_draft(snapshot, variant_id=None, idempotency_key="draft-1")
    assert service.get_draft(draft.draft_id, draft.revision) == draft
    assert service.get_lock(draft.resource_pack_id) is None


def test_lock_pins_full_manifest_and_digest(service, ready_draft):
    approval = fake_approval(actor_id="admin-1", role="admin", reference="review-7")
    lock = service.lock_draft(ready_draft.draft_id, ready_draft.revision, "lock-1", approval)
    assert lock.snapshot_id == ready_draft.snapshot_id
    assert lock.manifest_digest
    assert lock.schema_version == "1.0"
    assert lock.manifest["claims"] == [claim.model_dump(mode="json") for claim in ready_draft.claims]


def test_lock_rejects_missing_or_unauthorized_approval(service, ready_draft):
    with pytest.raises(LockAuthorizationError):
        service.lock_draft(ready_draft.draft_id, ready_draft.revision, "lock-2", None)
```

Add cursor pagination and media path-redaction tests.

- [ ] **Step 2: Verify RED**

```powershell
& 'D:\work\Personal\Product-Intelligence\.venv\Scripts\python.exe' -m pytest tests\test_mcp_surface.py tests\test_research_query.py tests\test_resource_pack_drafts.py tests\test_resource_pack_lock_contract.py -q
```

- [ ] **Step 3: Implement public query summaries**

Expose:

```python
def list_product_research(
    query: str = "",
    canonical_product_id: str = "",
    statuses: list[str] | None = None,
    created_after: str = "",
    created_before: str = "",
    cursor: str = "",
    limit: int = 50,
) -> dict: ...

def list_product_media(
    snapshot_id: str = "",
    canonical_product_id: str = "",
    match_status: str = "",
    usage_policy: str = "",
    cursor: str = "",
    limit: int = 50,
) -> dict: ...
```

Return opaque cursor, stable IDs, counts, timestamps, status, and MCP resource
URIs. Do not return absolute host paths. Validate an admin principal attestation
at the PI boundary and record access in the audit log.

- [ ] **Step 4: Implement durable draft revisions and explicit lock**

Expose distinct MCP names:

```text
build_resource_pack_draft
get_resource_pack_draft
list_resource_pack_drafts
lock_resource_pack
get_resource_pack_lock
list_resource_pack_locks
```

`ready_to_lock` is a draft assessment, not a lock. `lock_resource_pack`
requires expected revision, idempotency key, principal ID, actor role, approval
reference, and audit timestamp. PI authorizes and persists the approval
attestation with a complete normalized manifest. Compute SHA-256 over UTF-8
canonical JSON with recursively sorted object keys, no insignificant whitespace,
order-preserving arrays, and an explicit digest schema version. Return the
canonical manifest and digest metadata so Hermes can verify the attestation.

- [ ] **Step 5: Repair workspace export semantics**

Export from the top-level retrieval envelope and a selected draft/lock. Do not call lock retrieval immediately after draft build. Structured JSON is canonical for the export; Markdown remains human-readable output only.

- [ ] **Step 6: Verify GREEN and backfill fixture snapshots**

Run Step 2. Then run the repository's broader resource/research tests without live network calls.

- [ ] **Step 7: Commit in Product Intelligence**

```powershell
git add product_scout/mcp_server.py media/research_persistence media/research_query media/resource_pack tools/workspace_exporter tests
git commit -m "feat: publish durable product resource contracts"
```

### Task 7: Bind Product Intelligence Locks to Hermes Projects

**Files:**
- Create: `hermes/domain/product_resource.py`
- Create: `hermes/ports/product_intelligence.py`
- Create: `hermes/ports/product_resource_binding_repository.py`
- Create: `hermes/adapters/mcp/product_intelligence.py`
- Create: `hermes/adapters/sqlite/product_resource_binding_repository.py`
- Create: `hermes/application/product_resource_service.py`
- Modify: `hermes/db.py`
- Modify: `hermes/domain/video_factory.py`
- Modify: `hermes/application/video_factory_service.py`
- Modify: `hermes/adapters/sqlite/video_factory_repository.py`
- Modify: `mcp_servers/video_factory/server.py`
- Test: `tests/hermes/application/test_product_resource_service.py`
- Test: `tests/hermes/adapters/test_product_intelligence_adapter.py`
- Test: `tests/hermes/adapters/sqlite/test_product_resource_migration.py`
- Test: `tests/hermes/adapters/sqlite/test_video_factory_resource_compatibility.py`

**Interfaces:**
- Consumes: `ProductResourceLockReference` from Product Intelligence MCP.
- Produces: `ProjectResourceBinding` and a Video Factory resource draft.

- [ ] **Step 1: Write failing fail-closed adapter tests**

```python
@pytest.mark.parametrize("status", ["partial", "needs_review", "incomplete", "rejected"])
def test_non_locked_product_resource_cannot_bind(adapter, status):
    adapter.client.response = {"status": status}
    with pytest.raises(ProductResourceNotLocked):
        adapter.get_lock("pack-1", version=1)


def test_digest_mismatch_cannot_bind(service, valid_lock):
    tampered = replace(valid_lock, manifest_digest="0" * 64)
    with pytest.raises(ProductResourceDigestMismatch):
        service.bind("owner-1", "project-1", tampered)
```

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_resource_service.py tests\hermes\adapters\test_product_intelligence_adapter.py -q
```

- [ ] **Step 3: Implement the anti-corruption port and adapter**

```python
class ProductIntelligencePort(Protocol):
    def get_resource_lock(self, resource_pack_id: str, version: int) -> ProductResourceLockReference: ...


@dataclass(frozen=True)
class ProjectResourceBinding:
    project_id: str
    source_system: str
    resource_pack_id: str
    lock_version: int
    manifest_digest: str
    canonical_product_id: str
    variant_id: str | None
```

The adapter validates status, schema version, digest, one canonical product, selected variant, restrictions, and asset URI shape. It never imports PI code.

Digest verification uses the returned canonical manifest and declared digest
schema; reject absent manifests, unknown schemas, non-canonical serialization,
or digest mismatch. PI catalog queries use the separate admin-authorized route;
project asset access must resolve through a stored binding.

- [ ] **Step 4: Persist project bindings and migrate the Video Factory concept**

Add a versioned `ProjectResourceBindingRepository` and schema migration. Rename
the existing Video Factory `ResourcePack` to `ProductionResourceSet` in the
domain, service, and SQLite repository. During compatibility, deserialize the
old `resource_pack` field into the new type and write only the new schema.
Backfill existing rows, prove old/new round-trip compatibility, and test rollback
against the prior schema. Its identity lock becomes a Hermes project
binding/approval, not a mutation of the PI lock.

- [ ] **Step 5: Verify GREEN and MCP namespace isolation**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\application\test_product_resource_service.py tests\hermes\adapters\test_product_intelligence_adapter.py tests\hermes\adapters\sqlite\test_product_resource_migration.py tests\hermes\adapters\sqlite\test_video_factory_resource_compatibility.py tests\hermes\test_product_intelligence_integration.py tests\mcp_servers\test_video_factory_server.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add hermes/db.py hermes/domain/product_resource.py hermes/ports/product_intelligence.py hermes/ports/product_resource_binding_repository.py hermes/adapters/mcp/product_intelligence.py hermes/adapters/sqlite/product_resource_binding_repository.py hermes/adapters/sqlite/video_factory_repository.py hermes/application/product_resource_service.py hermes/domain/video_factory.py hermes/application/video_factory_service.py mcp_servers/video_factory/server.py tests
git commit -m "feat: bind product resource locks to Video Factory projects"
```

### Task 8: Secure and Wire the Canonical FastAPI Composition Root

**Files:**
- Create: `server/container.py`
- Create: `server/auth.py`
- Modify: `server/dependencies.py`
- Modify: `server/app.py`
- Create: `server/routes/video_factory.py`
- Create: `server/routes/product_research.py`
- Create: `server/routes/assets.py`
- Modify: `server/routes/projects.py`
- Modify: `web/vite.config.ts`
- Test: `tests/server/test_auth.py`
- Test: `tests/server/test_assets_api.py`
- Test: `tests/server/test_video_factory_api.py`
- Test: `tests/server/test_product_research_api.py`

**Interfaces:**
- Produces: a dark-launch FastAPI process for operator APIs, session-bound principal context, admin-authorized PI catalog streaming, and project-scoped generated asset streaming.
- Compatibility: `web_studio.py` remains available behind an explicit legacy command until Task 11.

- [ ] **Step 1: Write failing security and composition tests**

```python
def test_asset_endpoint_rejects_cross_owner(client, asset_fixture):
    response = client.get(
        f"/api/projects/{asset_fixture.project_id}/assets/{asset_fixture.asset_id}/content",
        headers=auth_headers("other-owner"),
    )
    assert response.status_code == 404


@pytest.mark.parametrize("asset_id", ["../secret", "%2e%2e%2fsecret", "C:\\Windows\\win.ini", "\\\\host\\share"])
def test_asset_endpoint_rejects_path_input(client, asset_id):
    response = client.get(f"/api/projects/p1/assets/{asset_id}/content", headers=auth_headers("owner-1"))
    assert response.status_code in {400, 404}


def test_runtime_composition_has_no_unwired_dependencies(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/api/projects", headers=auth_headers("owner-1")).status_code == 200
```

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\server\test_auth.py tests\server\test_assets_api.py tests\server\test_video_factory_api.py tests\server\test_product_research_api.py -q
```

- [ ] **Step 3: Build one dependency container**

`server/container.py` constructs repositories and services once per process from `HermesPaths`. `server/dependencies.py` returns these instances instead of raising `NotImplementedError`.

- [ ] **Step 4: Bind principal context at HTTP ingress**

For the local single-admin phase, bind `PrincipalContext.owner_user_id` from `HERMES_OWNER_USER_ID` and never from a query parameter. Bind the server to `127.0.0.1` by default. Refuse a non-loopback bind unless `HERMES_WEB_SESSION_TOKEN` is configured; for non-loopback requests require `Authorization: Bearer <token>`. Remove all public `owner_user_id` selectors and query parameters.

- [ ] **Step 5: Implement opaque asset streaming**

Resolve generated `asset_id` through the generated asset repository. Resolve a
bound PI asset through `ProjectResourceBinding` and the PI adapter. In both
cases verify owner/project binding, resolve against an explicitly configured root, reject
traversal/symlink escape, set the real MIME type,
`X-Content-Type-Options: nosniff`, and range support for video. Serve PI catalog
media through a separate `/api/admin/product-research/assets/{asset_id}/content`
route that requires the admin role and delegates to the PI adapter; do not
fabricate a project binding for unbound catalog browsing.

- [ ] **Step 6: Migrate Video Factory and Product Research read/command routes**

Routes call application services only. They must not instantiate repositories, call provider SDKs, parse PI SQLite, or run crawlers in request handlers. Long work submits a durable job.

- [ ] **Step 7: Dark-launch FastAPI without changing canonical startup**

Start the candidate backend explicitly:

```powershell
& $Python -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Remote bind requires an explicit configuration switch and authentication. Proxy `/api` and `/assets` through Vite.
Keep `start.ps1` and the existing operator backend unchanged until Task 9 UI
parity and Task 11 rollback/observation gates pass.

- [ ] **Step 8: Verify GREEN and start smoke**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\server -q
& .\.venv\Scripts\python.exe -m uvicorn server.app:app --host 127.0.0.1 --port 8000
```

Verify `/health`, `/api/projects`, product research listing, Video Factory project retrieval, and an authorized image preview. Stop services after smoke.

- [ ] **Step 9: Commit**

```powershell
git add server web/vite.config.ts tests/server
git commit -m "feat: dark launch FastAPI operator API"
```

### Task 9: Build the Product Research and Media Studio Read Experience

**Files:**
- Modify: `web/src/app.tsx`
- Modify: `web/src/lib/api.ts`
- Create: `web/src/features/product-research/types.ts`
- Create: `web/src/features/product-research/ProductResearchPage.tsx`
- Create: `web/src/features/product-research/ProductDetailPage.tsx`
- Create: `web/src/features/product-research/AssetGallery.tsx`
- Create: `web/src/features/product-research/AssetInspector.tsx`
- Create: `web/src/features/media-studio/MediaStudioPage.tsx`
- Modify: `web/src/features/video-factory/VideoFactoryPage.tsx`
- Modify: `web/playwright.config.ts`
- Create: `web/e2e/product-research.spec.ts`
- Create: `web/e2e/media-studio.spec.ts`

**Interfaces:**
- Consumes: FastAPI product/project/asset read models.
- Produces: searchable Product Research gallery and project-scoped storyboard/generated media browser.

- [ ] **Step 1: Write failing Playwright journeys**

```typescript
test('opens a product asset without exposing a filesystem path', async ({ page }) => {
  await page.goto('/product-research')
  await page.getByPlaceholder('Search products').fill('Baseus MA10')
  await page.getByRole('link', { name: /Baseus Bowie MA10/i }).click()
  await page.getByRole('tab', { name: 'Assets' }).click()
  await page.getByRole('img').first().click()
  await expect(page.getByText(/snapshot_/)).toBeVisible()
  await expect(page.getByText(/D:\\/)).toHaveCount(0)
})


test('renders generated storyboard assets by returned asset id', async ({ page }) => {
  await page.goto('/projects/project-1/media-studio')
  await expect(page.getByRole('img', { name: /frame 1/i })).toHaveAttribute('src', /\/api\/projects\/project-1\/assets\/asset-/)
})
```

- [ ] **Step 2: Verify RED**

```powershell
Set-Location web
npm run test:e2e -- product-research.spec.ts media-studio.spec.ts
```

- [ ] **Step 3: Normalize the API client**

Use relative URLs and throw structured errors on non-2xx responses:

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const payload = await response.json()
  if (!response.ok) throw new ApiError(response.status, payload)
  return payload as T
}
```

- [ ] **Step 4: Implement Product Research pages**

Provide Products, Runs, Reviews, search/date/status filters, Product Detail, Research, Assets, and Product Resource Lock views. Display PI truth without fabricating visual verification or readiness. Treat missing draft/lock as an explicit state.

- [ ] **Step 5: Implement Media Studio asset browsing**

Render storyboard frames, generated scenes, draft/final video, TTS, and export from returned `asset.content_url`. Remove all hard-coded filenames and the browser-side job apply call.

- [ ] **Step 6: Start both backend and Vite in Playwright config**

Configure two `webServer` entries: fake-provider FastAPI on port 8000 and Vite on port 3000. Tests use temporary data roots.

- [ ] **Step 7: Verify GREEN and production build**

```powershell
Set-Location web
npm run test:e2e -- product-research.spec.ts media-studio.spec.ts
npm run build
```

- [ ] **Step 8: Commit**

```powershell
git add web
git commit -m "feat: add Product Research and Media Studio views"
```

### Task 10: Converge Free-Text Channels on One Agent Turn Boundary

**Files:**
- Create: `agent/turn_runtime.py`
- Modify: `run_agent.py`
- Modify: `hermes_cli/oneshot.py`
- Modify: `gateway/run.py`
- Modify: `gateway/platforms/api_server.py`
- Modify: `telegram_bot.py`
- Modify: `gui/tabs/assistant_tab.py`
- Rename: `core/assistant_runtime.py` to `core/assistant_plan_builder.py`
- Test: `tests/agent/test_turn_runtime.py`
- Test: `tests/hermes/test_channel_runtime_parity.py`
- Modify: `tests/hermes/test_p2_routing_ownership.py`
- Modify: `tests/gui/`

**Interfaces:**
- Produces: `AgentTurnRequest`, `AgentTurnResult`, and `AgentTurnRuntime.run()`.
- Preserves: slash commands, deterministic ingestion, channel auth, gateway cache policy, CLI one-shot lifecycle, and GUI threading.
- Prerequisite: Task 3 has already bound and cleared `PrincipalContext` at every
  current entry point; this task centralizes that behavior without weakening it.

- [ ] **Step 1: Write failing fake-engine parity tests**

```python
def test_all_free_text_channels_build_same_turn_identity(fake_engine):
    requests = [
        cli_request("hello"),
        gateway_request("hello"),
        telegram_request("hello"),
        gui_request("hello"),
    ]
    normalized = [AgentTurnRuntime(fake_engine).normalize(request) for request in requests]
    assert {item.message for item in normalized} == {"hello"}
    assert all(item.principal.owner_user_id for item in normalized)


def test_telegram_slash_command_does_not_enter_agent_runtime(fake_runtime):
    handle_telegram_text("/knowledge pending", runtime=fake_runtime)
    assert fake_runtime.calls == []
```

- [ ] **Step 2: Verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agent\test_turn_runtime.py tests\hermes\test_channel_runtime_parity.py tests\hermes\test_p2_routing_ownership.py -q
```

Before migration, classify `gui/app.py` and `gui/app_staged.py` as canonical or
retired. A canonical GUI root must compile and pass `tests/gui`; a retired root
must be removed from startup/import paths and recorded in the retirement matrix.

- [ ] **Step 3: Implement the channel-neutral boundary**

```python
@dataclass(frozen=True)
class AgentTurnRequest:
    message: str
    principal: PrincipalContext
    platform: str
    conversation_history: tuple[dict[str, object], ...]
    enabled_toolsets: tuple[str, ...]


@dataclass(frozen=True)
class AgentTurnResult:
    content: str
    messages: tuple[dict[str, object], ...]
    usage: dict[str, int]
    session_id: str
    completed: bool
```

`AgentTurnRuntime` owns construction/config normalization and invokes the existing `AIAgent.run_conversation`. It does not duplicate the loop.

- [ ] **Step 4: Migrate channel factories incrementally**

Migrate CLI and API factory duplication first. Then route standalone Telegram free text through the boundary while retaining slash commands and ingestion callbacks. Run GUI turns on a worker thread with cancel support. Rename the deterministic dry planner and keep a compatibility import for one release.

- [ ] **Step 5: Verify GREEN and channel regressions**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\agent\test_turn_runtime.py tests\hermes\test_channel_runtime_parity.py tests\hermes\test_p2_routing_ownership.py -q
.\.venv\Scripts\python.exe -m compileall -q gui
.\.venv\Scripts\python.exe -m pytest tests\gui -q
```

- [ ] **Step 6: Commit**

```powershell
git add agent/turn_runtime.py run_agent.py hermes_cli/oneshot.py gateway telegram_bot.py gui/tabs/assistant_tab.py core/assistant_plan_builder.py tests
git commit -m "refactor: converge free-text channels on AIAgent"
```

### Task 11: Cut Over, Observe, and Retire Compatibility Paths

**Files:**
- Modify: `start.ps1`
- Modify: `web_studio.py`
- Modify: `video_factory_api.py`
- Modify: `start_web.bat`
- Modify: `docs/runbooks/hermes-canonical-operations.md`
- Create: `docs/runbooks/hermes-platform-migration.md`
- Modify: `docs/architecture-decisions/010-general-purpose-agent-platform.md`
- Test: `tests/contract/test_legacy_baseline.py`
- Test: `tests/hermes/test_canonical_runtime.py`
- Create: `tests/conftest_no_live_providers.py`

**Interfaces:**
- Consumes: all previous gates.
- Produces: one documented source/runtime path and an explicit compatibility retirement table.

- [ ] **Step 1: Add failing canonical-entrypoint assertions**

```python
def test_start_scripts_launch_canonical_fastapi_backend():
    start = (ROOT / "start.ps1").read_text(encoding="utf-8")
    start_web = (ROOT / "start_web.bat").read_text(encoding="utf-8")
    assert "uvicorn" in start
    assert "server.app:app" in start
    assert "web_studio.py" not in start
    assert "server.app:app" in start_web
```

- [ ] **Step 2: Verify RED before retirement**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\contract\test_legacy_baseline.py tests\hermes\test_canonical_runtime.py -q
```

- [ ] **Step 3: Cut canonical startup only after parity and rollback rehearsal**

Switch `start.ps1` and `start_web.bat` to `server.app:app` only after Task 9 E2E
passes against FastAPI, the legacy startup command has been rehearsed, and the
candidate has completed the documented observation window. Record both startup
commands and rollback evidence before merging the switch.

- [ ] **Step 4: Convert legacy servers into explicit compatibility entrypoints**

`web_studio.py` prints a deprecation message and redirects local users to the React/FastAPI URL, or remains invocable only through an explicit `--legacy` command for the observation window. Remove production startup references to `video_factory_api.py`; do not delete the file until the observation gate passes.

- [ ] **Step 5: Publish the retirement matrix**

For every legacy component record classification, remaining callers,
replacement, parity evidence, rollback command, and earliest removal date.
Include `core/assistant_plan_builder`, standalone Telegram free-text routing,
`gui/app.py`, `gui/app_staged.py`, `web_studio.py`, `video_factory_api.py`,
`.agent_jobs`, `core/job_watcher.py`, and `core/tool_registry.py`.

- [ ] **Step 6: Run the full non-paid verification matrix**

```powershell
$env:IMAGE_PROVIDER='fake'
$env:VIDEO_PROVIDER='fake'
$env:TTS_PROVIDER='fake'
$env:HERMES_FAKE_PROVIDERS='1'
Remove-Item Env:GOOGLE_API_KEY,Env:VERTEX_API_KEY,Env:OPENAI_API_KEY,Env:ELEVENLABS_API_KEY -ErrorAction SilentlyContinue
.\.venv\Scripts\python.exe -m pytest tests\hermes tests\tools tests\mcp_servers tests\server tests\workers -q
.\.venv\Scripts\python.exe -m compileall -q gui
.\.venv\Scripts\python.exe -m pytest tests\gui -q
Set-Location web
npm run test:e2e
npm run build
```

`tests/conftest_no_live_providers.py` is an autouse process guard that fails any
live provider HTTP/auth attempt. Expected: all selected tests pass; all provider
factories use fake implementations; no Product Intelligence internal database
is opened by Hermes.

- [ ] **Step 7: Run real read-only smoke**

Using existing data only:

1. start Hermes with `start.ps1 -UI`;
2. ask a natural-language product research question and verify the external PI MCP is selected;
3. search Product Research Studio for an existing projection;
4. preview a reference asset by opaque asset ID;
5. open a Video Factory project and preview generated media by asset ID;
6. verify closing the browser does not prevent a fake completed job from projecting;
7. verify no paid provider call is made.

- [ ] **Step 8: Mark ADR-010 accepted after observation**

Record exact commands, results, remaining compatibility paths, and rollback status in ADR-010 and the migration runbook.

- [ ] **Step 9: Commit**

```powershell
git add start.ps1 web_studio.py video_factory_api.py start_web.bat docs tests/conftest_no_live_providers.py tests/contract/test_legacy_baseline.py tests/hermes/test_canonical_runtime.py
git commit -m "chore: complete Hermes platform standardization cutover"
```

## Cross-Repository Sequence

Tasks 2-5 can proceed in Hermes while Task 6 is implemented in Product
Intelligence. Task 7 is blocked on the final Task 6 wire schema. Tasks 8-9 are
blocked on Tasks 5 and 7 because the API/UI must consume stable asset and
resource-binding contracts. Task 10 depends on Task 3 because every current
entry point must produce principal context before the shared turn boundary can
enforce it. Task 11 requires every previous task; it is the only task allowed to
switch canonical startup from the legacy backend to FastAPI.

## Stop Conditions

Stop the rollout and keep compatibility enabled when any of these conditions occurs:

- an external MCP receives a secret outside its allowlist;
- a caller can select another owner's identity;
- a completed job requires a browser callback to update project state;
- a Product Intelligence draft is represented as a lock;
- Hermes persists a second canonical copy of PI evidence/media;
- a Video Factory project accepts an unverified or digest-mismatched PI lock;
- an asset endpoint accepts an arbitrary path or serves a cross-owner asset;
- automated tests attempt to use a paid provider;
- FastAPI parity is incomplete when startup is switched;
- Telegram or GUI free text bypasses authorization before entering the agent runtime.

## Completion Definition

The standardization program is complete when:

- all conversational free-text surfaces use the Agent Turn boundary backed by `AIAgent`;
- deterministic UI and domain actions use application APIs directly;
- every model-visible tool has governed ownership/trust metadata;
- MCP secret scope, principal binding, and collision behavior fail closed;
- Product Intelligence exposes searchable research/media and explicit draft/lock contracts;
- Hermes stores only project bindings to immutable PI product resource locks;
- Video Factory job completion projects durable assets without browser participation;
- React displays reference, storyboard, generated, and rendered media by opaque asset ID;
- FastAPI is the only production operator API composition root;
- legacy paths are either retired or explicitly classified with verified rollback;
- focused, integration, Web E2E, and build verification pass without paid calls.

## Self-Review

- Spec coverage: Agent runtime, channels, MCP governance, Product Intelligence, Affiliate Product, Video Factory, jobs, Web/API, media security, UI, and retirement are each mapped to a task.
- Dependency consistency: Task 6 defines the PI lock wire contract consumed by Task 7; Task 5 defines generated assets consumed by Tasks 8-9.
- Boundary consistency: no task imports PI packages into Hermes, moves PI media, merges databases, or modifies the canonical conversation loop.
- Rollout safety: every production cutover follows characterization tests and retains a rollback-compatible path until Task 11.
