# Hermes Web-first Modernization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Hermes from duplicated Desktop/Web/Telegram workflows to a Web-first application with SQLite state, 9Router model access and local adapters for Desktop, Telegram and workers.

**Architecture:** Build deep application modules behind repository and adapter seams. Preserve the current system with compatibility adapters while each module migrates; do not perform a big-bang rewrite. Web owns workflow state; Desktop owns only local execution; Telegram owns only ingestion and notification.

**Tech Stack:** Python 3.12, FastAPI, Uvicorn, React, TypeScript, Vite, SQLite, pytest, Playwright, 9Router OpenAI-compatible HTTP API, CustomTkinter compatibility adapter, python-telegram-bot.

## Global Constraints

- Web is the full-control interface for one administrator.
- SQLite is the source of truth; filesystem stores only assets, artifacts, exports and backup manifests.
- All model responses use `fast`, `reason`, `vision` or `code` through the 9Router Model Gateway.
- UI and Telegram must not call providers, FFmpeg, SQLite or job folders directly.
- Desktop only runs registered local capabilities and never owns workflow state.
- Telegram only creates ingestion requests and sends notifications.
- Preserve legacy data and flows with explicit adapters until an audited migration phase switches the reader.
- Every mutation has a focused test first, a passing verification command and its own commit.
- Do not expose 9Router publicly; use `127.0.0.1` by default.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `hermes/domain/` | Domain types, stable errors and workflow state transitions. |
| `hermes/application/` | Project, Prompt Studio, Knowledge, Job and Video use cases. |
| `hermes/ports/` | Repository, model, storage, notification and local-capability interfaces. |
| `hermes/adapters/sqlite/` | SQLite implementations and schema migrations. |
| `hermes/adapters/router/` | 9Router HTTP Model Gateway adapter. |
| `hermes/adapters/filesystem/` | Asset/artifact filesystem adapter. |
| `hermes/adapters/telegram/` | Telegram ingestion and notification adapters. |
| `hermes/adapters/local/` | Desktop/FFmpeg local capability adapters. |
| `server/` | FastAPI composition root, routes, SSE and Web authentication. |
| `web/` | React Web Admin. |
| `legacy/` | Compatibility adapters for old `core/`, `gui/`, Telegram and JSON/Markdown reads. |
| `tests/` | Unit, integration, API, migration and browser tests grouped by module. |

## Phase 0: Safety Baseline

### Task 1: Establish a repeatable modernization baseline

**Files:**
- Create: `docs/runbooks/modernization-baseline.md`
- Create: `tests/contract/test_legacy_baseline.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `pytest` markers `unit`, `integration`, `contract`, `migration`, `web`.
- Produces: a documented command matrix for Desktop, Web, Telegram and worker smoke checks.

- [ ] **Step 1: Write failing contract tests for current data paths**

```python
def test_legacy_configuration_declares_a_sqlite_target(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_DB_PATH", str(tmp_path / "hermes.db"))
    from hermes.config import load_settings
    assert load_settings().database_path == tmp_path / "hermes.db"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/contract/test_legacy_baseline.py -q`

Expected: FAIL because the baseline configuration contract is not defined.

- [ ] **Step 3: Add test markers, fixture roots and baseline runbook**

Define markers in `pytest.ini`, add deterministic temporary data roots, and document exact commands for `pytest`, SQLite integrity, API smoke and local worker smoke. Do not change business behavior in this task.

- [ ] **Step 4: Run baseline verification**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/contract/test_legacy_baseline.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add pytest.ini requirements.txt docs/runbooks/modernization-baseline.md tests/contract/test_legacy_baseline.py
git commit -m "test: establish modernization baseline"
```

## Phase 1: Domain and SQLite Foundation

### Task 2: Introduce stable domain result and error contracts

**Files:**
- Create: `hermes/domain/results.py`
- Create: `hermes/domain/errors.py`
- Test: `tests/hermes/domain/test_results.py`

**Interfaces:**
- Produces: `Result[T]` with `value`, `error_code`, `message`, `ok`.
- Produces: error codes `not_found`, `conflict`, `invalid_input`, `unsupported_capability`, `unavailable`, `retryable`.

- [ ] **Step 1: Write the failing result contract test**

```python
from hermes.domain.results import Result

def test_failure_result_keeps_a_stable_error_code():
    result = Result.failure("not_found", "Project p-1 was not found")
    assert result.ok is False
    assert result.error_code == "not_found"
    assert result.value is None
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/domain/test_results.py -q`

Expected: FAIL because `hermes.domain.results` does not exist.

- [ ] **Step 3: Implement the immutable result interface**

```python
@dataclass(frozen=True)
class Result(Generic[T]):
    value: T | None = None
    error_code: str | None = None
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.error_code is None
```

Add `success(value)` and `failure(error_code, message)` constructors; reject success values combined with an error code.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/domain/test_results.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/domain/results.py hermes/domain/errors.py tests/hermes/domain/test_results.py
git commit -m "feat: add Hermes domain result contract"
```

### Task 3: Add project and workflow persistence schema

**Files:**
- Create: `hermes/adapters/sqlite/schema_v2.py`
- Create: `hermes/ports/project_repository.py`
- Create: `hermes/adapters/sqlite/project_repository.py`
- Modify: `hermes/db.py`
- Test: `tests/hermes/adapters/test_project_repository.py`

**Interfaces:**
- Produces: `ProjectRepository.create(name) -> Result[Project]`, `get(project_id)`, `list_active()`, `archive(project_id)`.
- Produces tables `projects`, `workflows`, `workflow_steps`, `assets`, `artifacts` with foreign keys enabled.

- [ ] **Step 1: Write a failing SQLite repository test**

```python
def test_project_repository_persists_a_project_across_connections(tmp_path):
    db_path = tmp_path / "hermes.db"
    created = ProjectRepository(Database(db_path)).create("Phone Stand")
    loaded = ProjectRepository(Database(db_path)).get(created.value.id)
    assert loaded.value.name == "Phone Stand"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_project_repository.py -q`

Expected: FAIL because schema v2 and repository are absent.

- [ ] **Step 3: Implement schema migration and repository**

Use a transaction for schema version registration and foreign-key tables. Give each project a UUID, created/updated timestamps, `active` status and filesystem root reference. The repository returns domain results and never exposes sqlite exceptions.

- [ ] **Step 4: Run repository and integrity verification**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_project_repository.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/db.py hermes/ports/project_repository.py hermes/adapters/sqlite/schema_v2.py hermes/adapters/sqlite/project_repository.py tests/hermes/adapters/test_project_repository.py
git commit -m "feat: persist projects and workflows in SQLite"
```

### Task 4: Define Prompt Studio workflow as an application module

**Files:**
- Create: `hermes/domain/prompt_studio.py`
- Create: `hermes/application/prompt_studio_service.py`
- Create: `hermes/ports/workflow_repository.py`
- Test: `tests/hermes/application/test_prompt_studio_service.py`

**Interfaces:**
- Consumes: `ProjectRepository`, `WorkflowRepository`, `Result`.
- Produces: `load(project_id)`, `save_draft(project_id, step, content)`, `approve(project_id, step, content)`, `invalidate_from(project_id, step)`.
- Step identifiers: `product`, `analysis`, `script`, `storyboard`, `image_prompt`, `video_prompt`, `result`.

- [ ] **Step 1: Write a failing sequential approval test**

```python
def test_approving_script_invalidates_storyboard_and_later_steps(service, project):
    service.approve(project.id, "product", {"name": "Stand"})
    service.approve(project.id, "analysis", {"angle": "demo"})
    service.approve(project.id, "script", {"text": "v1"})
    service.approve(project.id, "storyboard", {"scenes": [1]})
    service.save_draft(project.id, "script", {"text": "v2"})
    state = service.load(project.id).value
    assert state.step("storyboard").approved is False
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_prompt_studio_service.py -q`

Expected: FAIL because the service contract is absent.

- [ ] **Step 3: Implement persisted seven-step state transitions**

Implement step ordering once in `PromptStudioWorkflow`. Persist draft and approval snapshots through `WorkflowRepository`. Reject approval of a future step with `conflict`; changing a step clears approval and downstream outputs.

- [ ] **Step 4: Run focused tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_prompt_studio_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/domain/prompt_studio.py hermes/application/prompt_studio_service.py hermes/ports/workflow_repository.py tests/hermes/application/test_prompt_studio_service.py
git commit -m "feat: add persisted Prompt Studio workflow"
```

## Phase 2: 9Router Model Gateway

### Task 5: Create the provider-neutral model gateway contract

**Files:**
- Create: `hermes/domain/model_request.py`
- Create: `hermes/ports/model_gateway.py`
- Test: `tests/hermes/domain/test_model_request.py`

**Interfaces:**
- Produces tiers `fast`, `reason`, `vision`, `code`.
- Produces `ModelRequest(tier, messages, correlation_id, timeout_seconds, json_schema)` and `ModelResponse(content, model, usage, retry_count)`.

- [ ] **Step 1: Write a failing tier validation test**

```python
def test_model_request_rejects_a_provider_name_as_a_tier():
    with pytest.raises(ValueError):
        ModelRequest(tier="gemini", messages=[Message.user("hello")])
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/domain/test_model_request.py -q`

Expected: FAIL because model request types are absent.

- [ ] **Step 3: Implement typed request and response contracts**

Accept only the four tiers. Do not include provider, base URL or API key in a domain request. Preserve correlation ID and request timeout for observability.

- [ ] **Step 4: Run the focused test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/domain/test_model_request.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/domain/model_request.py hermes/ports/model_gateway.py tests/hermes/domain/test_model_request.py
git commit -m "feat: define 9Router model gateway contract"
```

### Task 6: Adapt 9Router and migrate the first caller

**Files:**
- Create: `hermes/adapters/router/nine_router_gateway.py`
- Modify: `core/llm_gateway.py`
- Modify: `core/assistant_runtime.py`
- Test: `tests/hermes/adapters/test_nine_router_gateway.py`

**Interfaces:**
- Consumes: `ModelGateway.complete(ModelRequest) -> Result[ModelResponse]`.
- Produces: a 9Router adapter using only `LLM_BASE_URL`, `LLM_ROUTER_API_KEY` and tier aliases.

- [ ] **Step 1: Write a failing HTTP contract test**

```python
def test_gateway_sends_the_reason_alias_and_normalizes_content(httpx_mock):
    httpx_mock.add_response(json={"choices": [{"message": {"content": "answer"}}], "model": "selected"})
    result = gateway.complete(ModelRequest.reason("analyze"))
    assert result.value.content == "answer"
    assert result.value.model == "selected"
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_nine_router_gateway.py -q`

Expected: FAIL because the adapter does not exist.

- [ ] **Step 3: Implement the 9Router adapter and compatibility facade**

Translate tier aliases to configuration model aliases, map HTTP/network failures to stable domain errors, redact credentials and preserve existing `core.llm_gateway.complete` callers through a compatibility facade.

- [ ] **Step 4: Run gateway and assistant tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_nine_router_gateway.py tests/hermes/test_personal_assistant.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/adapters/router/nine_router_gateway.py core/llm_gateway.py core/assistant_runtime.py tests/hermes/adapters/test_nine_router_gateway.py
git commit -m "feat: route assistant model calls through 9Router"
```

## Phase 3: Job Runtime and Ingestion

### Task 7: Introduce SQLite-backed job lifecycle

**Files:**
- Create: `hermes/domain/job.py`
- Create: `hermes/application/job_service.py`
- Create: `hermes/ports/job_repository.py`
- Create: `hermes/adapters/sqlite/job_repository.py`
- Test: `tests/hermes/application/test_job_service.py`

**Interfaces:**
- Produces: `submit`, `claim(worker_id)`, `complete`, `fail`, `retry`, `cancel`, `events`.
- Valid statuses: `queued`, `running`, `succeeded`, `failed`, `cancelled`.

- [ ] **Step 1: Write a failing lease test**

```python
def test_only_one_worker_claims_a_queued_job(service):
    job = service.submit("video.cut", {"asset_id": "a-1"}).value
    assert service.claim("worker-a").value.id == job.id
    assert service.claim("worker-b").value is None
```

- [ ] **Step 2: Run focused test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_job_service.py -q`

Expected: FAIL because job lifecycle is absent.

- [ ] **Step 3: Implement job state, lease and append-only event history**

Use SQLite transactions for claim and terminal transitions. Store payload JSON, worker lease expiry, attempt count, error code and event history. Reject illegal transitions with `conflict`.

- [ ] **Step 4: Run focused test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_job_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/domain/job.py hermes/application/job_service.py hermes/ports/job_repository.py hermes/adapters/sqlite/job_repository.py tests/hermes/application/test_job_service.py
git commit -m "feat: add SQLite job lifecycle"
```

### Task 8: Convert Telegram into ingestion and notification adapters

**Files:**
- Create: `hermes/domain/ingestion.py`
- Create: `hermes/application/ingestion_service.py`
- Create: `hermes/adapters/telegram/ingestion_adapter.py`
- Create: `hermes/adapters/telegram/notification_adapter.py`
- Modify: `telegram_bot.py`
- Test: `tests/hermes/adapters/test_telegram_ingestion.py`

**Interfaces:**
- Produces: `IngestionService.submit(source, source_type, requested_action) -> Result[IngestionRequest]`.
- Consumes: `NotificationPort.publish(event) -> Result[None]`.

- [ ] **Step 1: Write a failing Telegram adapter test**

```python
def test_video_message_becomes_an_ingestion_request(adapter, fake_service):
    adapter.handle_video(FakeTelegramVideo(file_id="abc", caption="/hoc_kien_thuc"))
    assert fake_service.requests[0].requested_action == "learn_knowledge"
```

- [ ] **Step 2: Run the focused test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_telegram_ingestion.py -q`

Expected: FAIL because Telegram is still coupled to legacy job/model code.

- [ ] **Step 3: Implement thin Telegram adapters**

Map allowed commands/files to ingestion requests, then publish only normalized job events. Remove direct model/provider calls from the migrated Telegram paths.

- [ ] **Step 4: Run focused tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/adapters/test_telegram_ingestion.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add hermes/domain/ingestion.py hermes/application/ingestion_service.py hermes/adapters/telegram telegram_bot.py tests/hermes/adapters/test_telegram_ingestion.py
git commit -m "refactor: make Telegram an ingestion adapter"
```

## Phase 4: Web Control Plane

### Task 9: Create FastAPI composition root and Web API contracts

**Files:**
- Create: `server/app.py`
- Create: `server/dependencies.py`
- Create: `server/routes/projects.py`
- Create: `server/routes/jobs.py`
- Create: `server/routes/prompt_studio.py`
- Test: `tests/server/test_projects_api.py`

**Interfaces:**
- Produces REST resources `/api/projects`, `/api/projects/{id}/prompt-studio`, `/api/jobs`.
- Produces SSE endpoint `/api/events` for job/project updates.

- [ ] **Step 1: Write a failing API test**

```python
def test_create_project_returns_a_project_resource(client):
    response = client.post("/api/projects", json={"name": "Phone Stand"})
    assert response.status_code == 201
    assert response.json()["name"] == "Phone Stand"
```

- [ ] **Step 2: Run focused test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/server/test_projects_api.py -q`

Expected: FAIL because the FastAPI app does not exist.

- [ ] **Step 3: Implement composition root and routes**

Inject application services through `server.dependencies`. Map domain `Result` codes to HTTP responses without exposing SQLite/provider exceptions. Bind only to `127.0.0.1` in local development.

- [ ] **Step 4: Run focused tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/server/test_projects_api.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add server tests/server requirements.txt
git commit -m "feat: add Hermes Web API foundation"
```

### Task 10: Build the Web Admin shell and Prompt Studio journey

**Files:**
- Create: `web/package.json`
- Create: `web/src/app.tsx`
- Create: `web/src/features/projects/ProjectSelector.tsx`
- Create: `web/src/features/prompt-studio/PromptStudioPage.tsx`
- Create: `web/src/lib/api.ts`
- Test: `web/e2e/prompt-studio.spec.ts`

**Interfaces:**
- Consumes: project and Prompt Studio REST resources from Task 9.
- Produces: Web routes for project selection and seven Prompt Studio steps.

- [ ] **Step 1: Write a failing Playwright journey**

```typescript
test('approval advances one Prompt Studio step and locks the prior snapshot', async ({ page }) => {
  await page.goto('/projects/p-1/prompt-studio');
  await page.getByRole('button', { name: /Duyệt/ }).click();
  await expect(page.getByText('2. Phân tích')).toBeVisible();
  await expect(page.getByLabel('Tên sản phẩm')).toBeDisabled();
});
```

- [ ] **Step 2: Run the browser test to verify it fails**

Run: `cd web; npm run test:e2e -- prompt-studio.spec.ts`

Expected: FAIL because the Web Admin does not exist.

- [ ] **Step 3: Implement the minimum Web Admin shell**

Use React Query for REST state and SSE invalidation. Recreate the three major modules and seven-step Prompt Studio only through API state; do not copy CustomTkinter workflow logic into React.

- [ ] **Step 4: Run browser and API verification**

Run: `cd web; npm run test:e2e -- prompt-studio.spec.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add web server tests/server
git commit -m "feat: add Web Prompt Studio control plane"
```

## Phase 5: Module Migration and Legacy Retirement

### Task 11: Migrate knowledge, video and Desktop runtime through job handlers

**Files:**
- Create: `hermes/application/knowledge_service.py`
- Create: `hermes/application/video_service.py`
- Create: `hermes/adapters/local/ffmpeg_capability.py`
- Create: `hermes/adapters/local/desktop_runtime.py`
- Modify: `core/job_watcher.py`
- Modify: `gui/app.py`
- Test: `tests/hermes/application/test_knowledge_service.py`
- Test: `tests/hermes/application/test_video_service.py`

**Interfaces:**
- Produces job types `knowledge.ingest`, `knowledge.review`, `video.cut`, `video.render`.
- Desktop consumes `LocalCapabilityPort.execute(job) -> Result[JobEvent]`.

- [ ] **Step 1: Write failing application tests for knowledge approval and local video dispatch**

```python
def test_approved_knowledge_is_searchable_but_rejected_proposal_is_not(service):
    proposal = service.propose("lesson", "source").value
    service.approve(proposal.id)
    assert service.search("lesson").value[0].id == proposal.id

def test_video_cut_submits_a_local_capability_job(service):
    result = service.request_cut("asset-1", 0, 10)
    assert result.value.type == "video.cut"
```

- [ ] **Step 2: Run focused tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_knowledge_service.py tests/hermes/application/test_video_service.py -q`

Expected: FAIL because migrated services and handlers are absent.

- [ ] **Step 3: Implement services and adapters one job type at a time**

Move one legacy knowledge action and one video operation per commit. Register handler, move read/write logic into repository/storage ports, make legacy GUI invoke a job, then verify the old UI remains a thin client.

- [ ] **Step 4: Run focused tests and Desktop smoke test**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/application/test_knowledge_service.py tests/hermes/application/test_video_service.py -q`

Expected: PASS.

- [ ] **Step 5: Commit each migrated job type separately**

```powershell
git add hermes core/job_watcher.py gui/app.py tests/hermes/application
git commit -m "refactor: run video cut through local capability jobs"
```

### Task 12: Backfill legacy data and retire duplicated model/UI paths

**Files:**
- Create: `hermes/migration/legacy_backfill.py`
- Create: `scripts/verify_modernization_migration.py`
- Modify: `core/ai_router.py`
- Modify: `gui/prompt_compiler_tab.py`
- Modify: `web_studio.py`
- Test: `tests/hermes/test_legacy_backfill.py`
- Test: `tests/contract/test_no_direct_llm_calls.py`

**Interfaces:**
- Produces: `backfill(database, legacy_root) -> MigrationReport` with imported/skipped/error counts and checksum mismatches.
- Produces: a direct-LLM-call contract that permits only `hermes.adapters.router` and the temporary `core.llm_gateway` facade.

- [ ] **Step 1: Write failing idempotency and direct-call tests**

```python
def test_backfill_is_idempotent(database, legacy_fixture):
    first = backfill(database, legacy_fixture)
    second = backfill(database, legacy_fixture)
    assert first.imported_projects == 1
    assert second.imported_projects == 0

def test_only_router_adapter_imports_requests_for_llm_transport(source_tree):
    assert find_direct_llm_transports(source_tree) == []
```

- [ ] **Step 2: Run focused tests**

Run: `.\\venv\\Scripts\\python.exe -m pytest tests/hermes/test_legacy_backfill.py tests/contract/test_no_direct_llm_calls.py -q`

Expected: FAIL because the migration and transport guard are absent.

- [ ] **Step 3: Implement reportable backfill and retire adapters**

Import legacy JSON/Markdown/project state with deterministic source identifiers. Replace direct model transport callers with Model Gateway use cases. Convert `web_studio.py` to a redirect/deprecation entry point after the React Web Admin reaches parity; retain its launch command only if it proxies to FastAPI.

- [ ] **Step 4: Run migration, full test and manual smoke verification**

Run: `.\\venv\\Scripts\\python.exe -m pytest -q`

Expected: PASS.

Run: `.\\venv\\Scripts\\python.exe scripts\\verify_modernization_migration.py --database D:\\HermesData\\hermes.db --legacy-root .`

Expected: report contains zero checksum mismatches and zero unhandled errors.

- [ ] **Step 5: Commit**

```powershell
git add hermes scripts core gui web_studio.py tests
git commit -m "refactor: complete Web-first Hermes migration"
```

## Testing Decisions

- Test application behavior through public module interfaces, not private SQL queries or widget implementation details.
- Use temporary SQLite files for repository tests; each test owns its database.
- Use fake 9Router HTTP responses; do not require live model credentials in automated tests.
- Use Playwright only for the Web workflows that prove administrator-visible behavior.
- Use adapter fakes for Telegram and Desktop; verify native capabilities through a concise manual smoke checklist.
- Add a regression test before every compatibility fix or migration defect.

## Out of Scope

- Multi-user authorization, team workspace, billing and public tenant hosting.
- Postgres, distributed workers and cloud 9Router exposure.
- Automatic conversion of every existing legacy action in a single release.
- Removal of legacy data before successful backfill and a compatibility period.

## Plan Self-Review

- Spec coverage: Tasks 2–4 cover SQLite/domain/Prompt Studio; Tasks 5–6 cover 9Router; Tasks 7–8 cover jobs/Telegram; Tasks 9–10 cover Web; Tasks 11–12 cover video, Desktop, knowledge, migration and retirement.
- Placeholder scan: each task states files, contract, test command, expected result and commit.
- Type consistency: `Result`, `ModelRequest`, `ModelResponse`, repository ports, job statuses and Prompt Studio step identifiers are introduced before later tasks consume them.
