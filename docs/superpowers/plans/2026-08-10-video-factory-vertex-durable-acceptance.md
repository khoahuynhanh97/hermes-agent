# Video Factory Vertex Durable Acceptance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the canonical source runtime execute the Baseus Video Factory workflow through explicit HITL gates and durable image, video, and TTS jobs, then complete tightly bounded Vertex live acceptance.

**Architecture:** Hermes uses 9Router `reason_combo` for text and creative decisions. Video Factory lifecycle state remains in `video_factory.sqlite`; a dedicated instance of the canonical worker claims media jobs from that same database and writes only under `workspaces/video-factory`. Provider adapters remain behind ports/factories, and all paid calls require an explicit user confirmation immediately before submission.

**Tech Stack:** Python 3.10+, FastMCP, aiohttp, SQLite, pytest, PowerShell, React/TypeScript, Google Vertex AI adapters.

## Global Constraints

- Source root: `D:\work\hermes-agent`.
- Business/generated data root: `D:\work\hermes-agent-data`.
- Hermes configuration/session state may remain under `%LOCALAPPDATA%\hermes`; it is not business data.
- Text/reasoning uses only 9Router `http://127.0.0.1:20128/v1` with `reason_combo`.
- Vertex is selected only through media provider ports/factories; no direct text-LLM routing to Vertex.
- Tests use fake or mocked providers and must never make paid/external calls.
- Preserve all existing uncommitted changes. Do not stage or commit unrelated files.
- Do not terminate unknown Python processes.
- Project acceptance identity: owner `ninak`, project `baseus-bowie-wm02-promo`.
- Resource identity lock, Creative Brief approval, Scene Plan approval, Storyboard approval, Final Video approval, and every paid-call batch require direct user confirmation.
- Veo smoke duration is exactly 4 seconds. Do not request 5 seconds because the adapter normalizes it to 6.

---

## File Map

- Modify `mcp_servers/video_factory/server.py`: typed schemas and read-only runtime identity tool.
- Modify `workers/job_worker.py`: explicit worker CLI paths plus durable `tts_generate` and `audio_mix` handlers.
- Create `providers/tts_provider_factory.py`: config-based TTS provider ownership.
- Create `providers/fake_tts_provider.py`: deterministic no-network TTS test adapter.
- Modify `video_factory_api.py`: separate resource save/lock, enqueue TTS jobs, apply TTS results.
- Modify `start.ps1`: launch distinct Video and Video Factory worker processes with explicit DB/workspace arguments.
- Modify `web/src/features/video-factory/VideoFactoryPage.tsx`: explicit resource lock and asynchronous TTS job handling.
- Modify `.env.example`: safe fake media defaults.
- Modify focused tests under `tests/mcp_servers`, `tests/hermes`, and `tests/workers`.
- Modify `docs/runbooks/hermes-canonical-operations.md`: document both worker instances and paid gates.

---

### Task 1: Runtime Identity Must Be Observable and Verifiable

**Files:**
- Modify: `mcp_servers/video_factory/server.py`
- Modify: `tests/mcp_servers/test_video_factory_server.py`
- Modify: `tests/hermes/test_canonical_runtime.py`

**Interfaces:**
- Produces: `video_factory_runtime_info() -> dict[str, Any]`.
- Result fields: `python_executable`, `module_file`, `database_path`, `workspace_path`.
- The tool returns paths only; it must never return environment secrets.

- [ ] **Step 1: Add a failing MCP test** asserting `video_factory_runtime_info` is registered and reports resolved absolute paths from `HERMES_VIDEO_FACTORY_DB_PATH` and `HERMES_VIDEO_FACTORY_WORKSPACE`.
- [ ] **Step 2: Run the red test.**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/mcp_servers/test_video_factory_server.py -q --basetemp .\.tmp-vf-runtime-red -p no:cacheprovider
  ```

  Expected: failure because the tool does not exist.

- [ ] **Step 3: Implement the read-only tool** with this contract:

  ```python
  def video_factory_runtime_info() -> dict[str, Any]:
      return {
          "python_executable": str(Path(sys.executable).resolve()),
          "module_file": str(Path(__file__).resolve()),
          "database_path": str(_database_path()),
          "workspace_path": str(_workspace_path()),
      }
  ```

  Extract `_database_path()` and `_workspace_path()` helpers and reuse them from `_service()`; do not duplicate path resolution.

- [ ] **Step 4: Run the focused tests and verify green.**
- [ ] **Step 5: Restart Hermes and call `video_factory_runtime_info` in a fresh session.** Require exact equality with:

  ```text
  D:\work\hermes-agent\.venv\Scripts\python.exe
  D:\work\hermes-agent\mcp_servers\video_factory\server.py
  D:\work\hermes-agent-data\db\video_factory.sqlite
  D:\work\hermes-agent-data\workspaces\video-factory
  ```

  Stop execution if any path differs.

---

### Task 2: Start the Worker That Owns Video Factory Jobs

**Files:**
- Modify: `workers/job_worker.py`
- Modify: `start.ps1`
- Modify: `tests/workers/test_canonical_job_worker.py`
- Modify: `tests/hermes/test_canonical_runtime.py`

**Interfaces:**
- `build_worker(db_path: str | None = None, workspace: str | None = None) -> CanonicalJobWorker`.
- CLI options: `--db-path PATH`, `--workspace PATH`, existing `--daemon`, `--once`, `--poll-seconds`.

- [ ] **Step 1: Add failing tests** showing CLI/build overrides win over `HERMES_VIDEO_DB_PATH` and `HERMES_VIDEO_WORKSPACE` defaults.
- [ ] **Step 2: Run the worker tests and confirm red.**
- [ ] **Step 3: Implement explicit path arguments** while preserving current defaults for the canonical Video capability.
- [ ] **Step 4: Update `start.ps1` to launch two owned workers:**

  ```text
  Video worker:
    DB        D:\work\hermes-agent-data\db\video.sqlite
    Workspace D:\work\hermes-agent-data\workspaces\video

  Video Factory worker:
    DB        D:\work\hermes-agent-data\db\video_factory.sqlite
    Workspace D:\work\hermes-agent-data\workspaces\video-factory
  ```

  Use separate logs: `video-worker.*.log` and `video-factory-worker.*.log`. Add both processes to `$ownedProcesses` so normal launcher shutdown stops both.

- [ ] **Step 5: Run focused tests.**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest tests/workers/test_canonical_job_worker.py tests/hermes/test_canonical_runtime.py -q --basetemp .\.tmp-vf-workers -p no:cacheprovider
  ```

- [ ] **Step 6: Add and run `test_worker_cli_uses_explicit_database_and_workspace`.** The test uses `tmp_path`, invokes `python -m workers.job_worker --once --db-path <tmp DB> --workspace <tmp workspace>` through `subprocess.run`, and asserts one queued fake `image_generate` job becomes `completed` with output inside `<tmp workspace>/images`.

---

### Task 3: Normalize Resource Save and Identity Lock

**Files:**
- Modify: `mcp_servers/video_factory/server.py`
- Modify: `video_factory_api.py`
- Modify: `web/src/features/video-factory/VideoFactoryPage.tsx`
- Modify: `tests/mcp_servers/test_video_factory_server.py`
- Modify: `tests/hermes/test_ui1_api.py`

**Interfaces:**
- Keep MCP tools `resource_pack_save` and `resource_pack_lock` separate.
- API `POST /api/vf/projects/{project_id}/resources` saves only.
- Add API `POST /api/vf/projects/{project_id}/resources/lock` to lock the presented identity.

- [ ] **Step 1: Retain and verify the typed `ResourcePackInput` schema.** Required nested keys are `product_references`, `primary_product_asset_id`, and `product_identity_description`; aliases `files`, `images`, and `product_name` are absent.
- [ ] **Step 2: Add a failing API test** proving resource save leaves `locked_at` empty and lock requires a separate request.
- [ ] **Step 3: Remove automatic `lock_resource_pack()` from `save_resources()` and add `lock_resources()` using `ResourceIdentity` fields `description`, `shape`, `color`, `materials`, `logo_placement`, and `distinctive_features`.**
- [ ] **Step 4: Add separate Save and Lock actions in the UI.** Lock must display the identity being committed and require an explicit confirmation action.
- [ ] **Step 5: Run MCP/API tests.**

---

### Task 4: Move TTS Behind the Durable Job Plane

**Files:**
- Create: `providers/tts_provider_factory.py`
- Create: `providers/fake_tts_provider.py`
- Modify: `workers/job_worker.py`
- Modify: `video_factory_api.py`
- Modify: `web/src/features/video-factory/VideoFactoryPage.tsx`
- Modify: `tests/hermes/test_tts1.py`
- Modify: `tests/workers/test_canonical_job_worker.py`
- Modify: `tests/hermes/test_ui1_api.py`

**Interfaces:**
- `get_tts_provider(output_dir: str | None = None) -> TextToSpeechPort`.
- Supported config: `TTS_PROVIDER=fake|google_vertex`; default `fake` requires `HERMES_ALLOW_FAKE_PROVIDERS=1` before execution.
- New job type: `tts_generate`.
- Job payload: `owner_user_id`, `request_id`, `text`, `voice`, `language`, `style_prompt`, `max_attempts`.
- Job result: `task_type`, `request_id`, `wav_path`, `provider`, `model`, `voice`.
- New deterministic job type: `audio_mix`.
- Audio-mix payload: `owner_user_id`, `video_path`, `audio_path`, `output_path`, `max_attempts`.
- Audio-mix result: `task_type`, `output_path`.

- [ ] **Step 1: Add failing factory and fake-provider tests.** Fake synthesis writes a valid deterministic WAV under the supplied output directory without network calls.
- [ ] **Step 2: Add a failing worker test** for `tts_generate`, including containment and missing-text rejection.
- [ ] **Step 3: Implement `get_tts_provider()` and `FakeTTSProvider`** following the existing image/video factory safety pattern.
- [ ] **Step 4: Register `tts_generate` in `CanonicalJobWorker.handlers` and implement `_execute_tts()`** writing only to `<worker workspace>/audio`.
- [ ] **Step 5: Change `generate_voiceover()`** to enqueue a `tts_generate` job and return `202` with `job_id`; remove the direct `GoogleVertexTTSProvider` import/call.
- [ ] **Step 6: Extend job result application** so a completed TTS job durably sets `timeline.audio_track_asset_id` using the returned WAV asset identity. Reject owner mismatch, failed jobs, and paths outside the Video Factory workspace.
- [ ] **Step 7: Replace direct FFmpeg mixing** in `mix_voiceover()` with an `audio_mix` job. Implement a worker handler that validates all three paths against its workspace, calls `runtime.ffmpeg.render_with_audio()`, and persists the output path in the terminal job result.
- [ ] **Step 8: Update the UI** to poll/apply TTS and audio-mix jobs and render the returned canonical media path instead of the hardcoded `audio/tts1_acceptance.wav`.
- [ ] **Step 9: Run TTS, worker, and API tests.** No test may access Vertex.

---

### Task 5: Enforce Correct Media Gate Ordering

**Files:**
- Modify: `hermes/application/video_factory_service.py`
- Modify: `video_factory_api.py`
- Modify: `tests/hermes/application/test_video_factory_f2_f5.py`
- Modify: `tests/hermes/test_ui1_api.py`

**Interfaces:**
- Storyboard image generation is allowed after Scene Plan approval and Storyboard save, while Storyboard approval is pending.
- Storyboard approval requires every frame to have a completed generated image asset.
- Video and TTS submission require approved Storyboard.

- [ ] **Step 1: Add lifecycle tests** proving image jobs are allowed before Storyboard approval, but video and TTS jobs are rejected with `STORYBOARD_APPROVAL_REQUIRED` before approval.
- [ ] **Step 2: Add `require_storyboard_approved(owner_user_id, project_id)`** to `VideoFactoryService`; return the project when approved and otherwise raise `STORYBOARD_APPROVAL_REQUIRED`.
- [ ] **Step 3: Call this service guard before TTS submission.** Keep `save_generated_scene()` as the video generation guard.
- [ ] **Step 4: Preserve the existing requirement that every generated frame is complete before `approve_storyboard()` succeeds.**
- [ ] **Step 5: Run application and API tests.**

---

### Task 6: Make Environment Defaults Non-Paid

**Files:**
- Modify: `.env.example`
- Modify: `tests/hermes/test_canonical_runtime.py`
- Modify: `docs/runbooks/hermes-canonical-operations.md`

- [ ] **Step 1: Add a failing configuration test** asserting `.env.example` selects `fake` for `IMAGE_PROVIDER`, `VIDEO_PROVIDER`, and `TTS_PROVIDER`.
- [ ] **Step 2: Set safe template values:**

  ```dotenv
  IMAGE_PROVIDER=fake
  VIDEO_PROVIDER=fake
  TTS_PROVIDER=fake
  HERMES_ALLOW_FAKE_PROVIDERS=0
  ```

  Document that hermetic demos set the allow flag to `1`; live acceptance sets each approved provider explicitly to `google_vertex`.

- [ ] **Step 3: Keep model names configurable.** Do not add hardcoded production model IDs outside provider defaults/template configuration.
- [ ] **Step 4: Run canonical runtime tests.**

---

### Task 7: Hermetic Full Workflow Acceptance

**Files:**
- Modify: `tests/hermes/test_ui1_api.py`
- Modify: `tests/hermes/test_tts1.py`
- Modify: `tests/workers/test_canonical_job_worker.py`

- [ ] **Step 1: Extend the fresh-project API test** to use a temporary DB/workspace and fake providers through this exact order:

  ```text
  resource save
  explicit identity lock
  raw idea save
  creative brief save + approve
  scene plan save + approve
  storyboard save
  image jobs + worker + apply results
  storyboard approve
  video job + worker + apply result
  timeline save
  TTS job + worker + apply result
  draft render
  final approve
  final export
  fresh service instance retrieval
  ```

- [ ] **Step 2: Assert owner isolation, job durability, approval ordering, output containment, and no network calls.**
- [ ] **Step 3: Run the focused suite:**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest `
    tests/mcp_servers/test_video_factory_server.py `
    tests/hermes/application/test_video_factory_service.py `
    tests/hermes/application/test_video_factory_f2_f5.py `
    tests/hermes/providers/test_image_provider.py `
    tests/hermes/providers/test_video_provider.py `
    tests/hermes/test_tts1.py `
    tests/hermes/test_ui1_api.py `
    tests/hermes/test_job_repository.py `
    tests/workers/test_canonical_job_worker.py `
    tests/tools/test_mcp_tool_circuit_breaker.py `
    -q --basetemp .\.tmp-vf-focused -p no:cacheprovider
  ```

  Required result: zero failures and zero external provider requests.

---

### Task 8: Real Hermes F1/F2 Acceptance for Baseus

**Data only; no provider calls until the paid gates below.**

- [ ] **Step 1: Restart canonical Hermes and verify `video_factory_runtime_info`.** Stop if any path differs from Task 1.
- [ ] **Step 2: Retrieve owner `ninak`, project `baseus-bowie-wm02-promo`; record versions and approval states from the raw MCP result and direct read-only SQLite query.**
- [ ] **Step 3: Save the five canonical product references already under `baseus-bowie-wm02-promo/references/`; retrieve in a fresh session and require `resource_version > 0` with five assets.**
- [ ] **Step 4: Present the white primary identity** including case shape, white color, transparent lid, logo placement, and distinctive earbud shape. Wait for direct user confirmation before `resource_pack_lock`.
- [ ] **Step 5: Save Raw Idea and Creative Brief.** Claims derived only from supplied marketing images use `user_provided_unverified` plus their asset IDs in `evidence_refs`; do not label them `verified` without independent evidence.
- [ ] **Step 6: Present Creative Brief and wait for direct approval before `creative_brief_approve`.**
- [ ] **Step 7: Save a four-scene plan using four 4-second generation clips.** The final timeline uses durations `3, 4, 4, 4` seconds to produce a 15-second ad. Present the plan and wait for direct approval before `scene_plan_approve`.
- [ ] **Step 8: Save Storyboard frame plans.** Do not approve yet because generated frame assets are required.

---

### Task 9: Bounded Paid Vertex Acceptance

**No step in this task starts without an explicit user confirmation naming provider, count, and maximum duration.**

- [ ] **Step 1: Preflight without generation.** Verify ADC/project/location, provider configuration, worker health, DB paths, workspace free space, and model configuration. Restart the Video Factory worker after changing provider environment because a running worker retains its original environment. Do not print credentials.
- [ ] **Step 2: Request Paid Gate A:** one Vertex image generation for one Storyboard frame.
- [ ] **Step 3: Submit exactly one image job, record job ID/provider operation ID, apply the result, verify file containment and visually inspect product identity.**
- [ ] **Step 4: If the first image is accepted, request Paid Gate B** for the exact remaining frame count. Generate no batch without this second confirmation.
- [ ] **Step 5: After every frame is complete, present all frames and wait for direct Storyboard approval before calling `storyboard_approve`.**
- [ ] **Step 6: Request Paid Gate C:** one Veo clip, 4 seconds, 720p, one sample.
- [ ] **Step 7: Submit one video job through the durable worker.** Verify submit/poll/restart-resume behavior, operation ID persistence, output containment, and fresh-session result retrieval.
- [ ] **Step 8: If the smoke clip is accepted, request Paid Gate D** for the exact remaining clip count and durations.
- [ ] **Step 9: Request Paid Gate E:** one TTS voiceover call with the exact text, voice, and language shown to the user.
- [ ] **Step 10: Mix audio and render the draft through durable deterministic jobs.** Present the draft; wait for Final Video approval before final export.

---

### Task 10: Closure and Regression

**Files:**
- Modify: `docs/runbooks/hermes-canonical-operations.md`
- Create: `docs/VIDEO_FACTORY_VERTEX_ACCEPTANCE_REPORT.md`

- [ ] **Step 1: Run `git diff --check` and review only task-owned diffs.** Do not revert unrelated changes.
- [ ] **Step 2: Run the focused suite from Task 7.**
- [ ] **Step 3: Run canonical regression:**

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -q --basetemp .\.tmp-vf-regression -p no:cacheprovider
  ```

  Record exact pass/fail counts. Any unrelated baseline failure must be identified by test name and reproduced against the pre-task baseline before being classified as pre-existing.

- [ ] **Step 4: Fresh-session durable verification** must confirm project status, all versions/approvals, job terminal states, provider operation IDs, and canonical artifact paths.
- [ ] **Step 5: Write the acceptance report** with no credentials, no unsupported success claims, and a clear distinction among implementation pass, hermetic acceptance pass, and paid live acceptance pass.
- [ ] **Step 6: Declare `FULL PASS` only when all required approvals, focused tests, canonical regression, durable retrieval, and approved paid acceptance gates pass.**

---

## Stop Conditions

Stop immediately and report evidence if any of these occurs:

- Hermes runtime info points outside the source `.venv`, canonical DB, or canonical workspace.
- MCP reports success but the raw result or fresh SQLite read shows no version change.
- A paid provider call is about to occur without an immediately preceding explicit confirmation.
- A worker claims from the wrong DB or writes outside its configured workspace.
- A claim is promoted to `verified` without independent evidence.
- Storyboard, video, TTS, or final export advances past its required gate.
- Tests attempt a real provider request.

## Completion Definition

The work is complete only when runtime identity is proven, both canonical workers are healthy, TTS is durable, resource locking is explicit, the hermetic workflow passes, the Baseus lifecycle is retrievable from a fresh session, all approved paid smoke calls complete within their bounds, and regression evidence is recorded.
