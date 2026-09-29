# Hermes Vertex Video Provider Port Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the smallest proven Google Vertex Veo integration into the current Hermes Video Factory structure so `render`, `get_job_status`, and deterministic `export` work truthfully offline and are ready for a separately authorized live acceptance run.

**Architecture:** Keep `D:/work/hermes-upstream-rearchitecture` as the only writable implementation worktree. Reuse the Vertex request/poll contract proven by commit `d975d948c6`, but refactor it into the current `src/hermes` ports/adapters layout and reuse `agent.vertex_adapter` for profile-scoped ADC. Existing `hermes_personal.product_video.handlers` remains responsible for budget reservation, accepted-job checkpointing, heartbeat polling, and restart-safe no-resubmit behavior.

**Tech Stack:** Python, MCP/FastMCP, Vertex AI Veo REST, existing `requests`, optional `google-auth`, SQLite-backed Video Factory state, pytest, Ruff.

## Global Constraints

- Writable repository and commit target: `D:/work/hermes-upstream-rearchitecture`, branch `codex/hermes-upstream-rearchitecture`.
- `D:/work/hermes-agent` is read-only reference only. Do not edit, stage, commit, reset, checkout, clean, or otherwise mutate its working tree.
- Read legacy source only through Git objects such as `git show d975d948c6:<path>` from the writable worktree. Do not merge or cherry-pick the legacy commit.
- Preserve existing modified `.hermes/coordination.md`, untracked `reports/`, and every unrelated dirty/untracked file.
- Provider is `google_vertex`; first acceptance model is the previously live-proven `veo-3.1-generate-001`; location is `us-central1` unless existing profile configuration explicitly overrides it.
- Do not add credentials, project IDs, service-account identities, key paths, or secret values to source/tests/reports.
- Do not edit user config or `.env`. Non-secret routing belongs in existing `config.yaml` resolution; credentials remain in the existing secret mechanism.
- No live Vertex call, token mint, model probe, package installation, browser automation, generation, render, export-provider call, or publish in this assignment.
- Tests must inject fake auth and fake HTTP responses. They must not import/start broad MCP discovery or instantiate a live `AIAgent`.
- No new workflow/job/budget framework. Reuse existing `MCPVideoFactoryAdapter` polling and `ProductVideoJobHandlers` checkpoint/budget behavior.
- `export` is local deterministic finalization of a verified generated MP4. It must not submit another paid provider operation.

---

## File Map

- Create: `src/hermes/ports/video_generation.py` — request/result/provider protocol.
- Create: `src/hermes/adapters/google/__init__.py` — package marker only.
- Create: `src/hermes/adapters/google/vertex_video_provider.py` — Vertex submit/poll adapter with injected auth/HTTP for tests.
- Modify: `src/hermes/mcp/video_factory/server.py` — lazy provider construction and truthful `render/get_job_status/export` tools.
- Create: `tests/hermes/adapters/google/test_vertex_video_provider.py` — adapter contract tests with no network.
- Modify: `tests/mcp_servers/test_video_factory_server.py` — wire behavior, startup safety, idempotent resume and local export tests.
- Read only: `agent/vertex_adapter.py`, `hermes_personal/product_video/handlers.py`, `hermes_personal/workflows/budgets.py`.
- Read legacy via Git only: `d975d948c6:providers/vertex_video_provider.py`, `d975d948c6:providers/vertex_auth.py`, `d975d948c6:hermes/ports/video_generation.py`, `d975d948c6:docs/PVID1B_FINAL_REPORT.md`, `d975d948c6:docs/VF_E2E_FINAL_REPORT.md`.

## Task 1: Port the Video Generation Boundary and Vertex Adapter

**Interfaces:**

```python
@dataclass(frozen=True)
class VideoGenerationRequest:
    request_id: str
    owner_user_id: str
    project_id: str
    scene_id: str
    prompt: str
    duration_seconds: int
    reference_image_paths: tuple[str, ...] = ()
    aspect_ratio: str = "9:16"
    provider_options: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class VideoGenerationResult:
    request_id: str
    status: Literal["submitted", "running", "completed", "failed"]
    provider_operation_id: str | None = None
    video_path: str | None = None
    error_code: str = ""
    error_message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

class VideoGenerationPort(Protocol):
    def submit(self, request: VideoGenerationRequest) -> VideoGenerationResult: ...
    def get_status(self, operation_id: str) -> VideoGenerationResult: ...
```

- [ ] Add failing adapter tests for exact `predictLongRunning` and `fetchPredictOperation` endpoints, full operation-name preservation, one readable reference image encoded with its real MIME type, 4/6/8-second duration validation, 9:16/16:9 validation, running/completed/error normalization, and deterministic workspace-contained MP4 output.
- [ ] Add tests proving construction/import performs no network/token mint and missing auth fails closed before HTTP submission.
- [ ] Implement the port and adapter. Inject `credential_resolver` and `post` callables; production defaults may lazily call `agent.vertex_adapter.get_vertex_credentials` and `requests.post` only inside `submit/get_status`.
- [ ] Reuse the legacy Vertex wire contract exactly: `{model}:predictLongRunning`, `{model}:fetchPredictOperation`, body `{"operationName": full_name}`, and inline `bytesBase64Encoded` MP4 decoding.
- [ ] Reject GCS-only output with structured `GCS_OUTPUT_UNSUPPORTED` unless an already existing reviewed GCS downloader is found. Do not add a GCS subsystem in this task.
- [ ] Use a deterministic output filename derived from the trailing operation UUID; resolve and verify it remains below the configured Video Factory workspace.

## Task 2: Wire the Existing MCP Compatibility Surface

**Production behavior:**

```text
render(new idempotency key)
  -> validate project/storyboard approval and readable reference image
  -> provider.submit(...)
  -> return {status: "pending", job_id: <full Vertex operation name>}

render(active_job_id supplied by upstream workflow)
  -> do not submit
  -> return pending for the same job ID

get_job_status(job_id)
  -> provider.get_status(job_id)
  -> running | completed with real workspace MP4 | failed with structured code

export(completed render result)
  -> validate readable non-empty MP4 inside workspace
  -> copy/promote deterministically below workspace/exports
  -> return completed final_video_url; zero provider calls
```

- [ ] Add failing MCP tests for startup safety: importing/registering tools must not resolve credentials or call HTTP.
- [ ] Add a test proving missing provider configuration retains `VF_PROVIDER_UNAVAILABLE` and performs no side effect.
- [ ] Add a test proving approved storyboard + explicit prompt/reference input submits once and returns the full provider operation name as `job_id`.
- [ ] Add a no-resubmit test: `active_job_id` returns/resumes that ID and the provider submit mock remains untouched.
- [ ] Add status tests for running, terminal failure, and completed real local MP4. Completion must include `video_url`/`output_url`, stable render ID, provider operation ID and non-empty file evidence.
- [ ] Add export tests for workspace containment, missing/empty/non-MP4 rejection, deterministic replay, and successful local promotion with no provider call.
- [ ] Implement a lazy `_video_provider()` seam in `server.py`; resolve non-secret model/region from existing config-loading patterns and auth from `agent.vertex_adapter`. Do not read raw shared process credentials directly.
- [ ] Map only explicit caller/project data. Never invent prompt, image, job ID, completed state, URL, approval, or provider output.
- [ ] Preserve all six MCP wire tool names and the Worker 120 JSON schemas unless a typed optional field is strictly required; if schema changes, update and capture the exact focused schema assertion.

## Task 3: Focused Verification and Handoff

- [ ] Run only:

```powershell
uv run pytest tests/hermes/adapters/google/test_vertex_video_provider.py tests/mcp_servers/test_video_factory_server.py tests/hermes_personal/product_video/test_video_factory_client.py -v
uv run ruff check src/hermes/ports/video_generation.py src/hermes/adapters/google src/hermes/mcp/video_factory/server.py tests/hermes/adapters/google/test_vertex_video_provider.py tests/mcp_servers/test_video_factory_server.py
git diff --check
```

- [ ] If the optional Vertex dependency is unavailable, keep production imports lazy and tests injected; do not install packages. Report the missing runtime dependency separately.
- [ ] Review `git status --short`; stage only task-owned implementation/tests. This local plan is ignored by repository policy and must not be force-added. Do not stage the HTML report or unrelated SSOT changes.
- [ ] Commit with a focused message such as `feat(video_factory): port Vertex Veo provider behind durable wire tools`.
- [ ] Update SSOT with exact changed files, commit, focused test counts, Ruff/diff-check, proof of zero live calls, and any remaining credential/cap/product/home/HITL inputs.
- [ ] Handoff to PLANNER and exit. Do not begin live acceptance.

## Acceptance Boundary

This assignment is complete when the Vertex adapter and MCP compatibility tools are implemented and verified offline with truthful async operation semantics, restart-safe no-resubmit compatibility, workspace containment, and deterministic local export. It does not prove credentials, quota, current model access, pricing, a real product run, video quality, or `MVP_DONE`. Those remain a separately authorized supervised Task 5 live acceptance.
