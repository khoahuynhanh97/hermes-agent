# Hermes Product Video — Fix Implementation Report

- **Date:** 2026-09-24
- **Authority:** [Technical Fix Specification](2026-09-23-hermes-product-video-fix-spec.md), current source and tests.
- **Scope:** FIX-001/002/003/004/008 (Milestone A) and FIX-005/006/011 (Milestone B). One real Google Flow clip was generated to verify the selected provider edge. No full Product Video run or Milestone C feature was implemented.

## Implemented fixes

| Fix | Changed boundary | Observable behavior and regression evidence |
| --- | --- | --- |
| FIX-001 | `integrations/video_factory/google_flow_provider.py`, `server.py`, `cli-config.yaml.example` | Flow no longer reports ready from Playwright importability or returns synthetic operation IDs. The page adapter now uses a dedicated authenticated profile, a deterministic request marker in a unique Flow project, one Generate action, the externally verifiable project URL, status/download through Playwright, and request lookup after restart. The project-local ignored config selects Flow; a missing profile still fails closed. One real submitted clip was recovered through the durable scene runtime and validated. The automated `submit()` path itself has not been charged/tested end to end; the paid UI action in this verification used the checkpointed diagnostic script. |
| FIX-002 | `product_video/handlers.py`, `mcp_adapters.py`, `integrations/video_factory/service.py` | The approved Scene Plan must produce a successful, matching canonical VF storyboard write before keyframe work. Failed, mismatched and ambiguous writes stop the stage; identical replay converges on the existing storyboard. Fault-injection tests prove zero keyframe submissions on write failure. |
| FIX-003 | `product_video/handlers.py` | Dossier claims now retain only resolvable claim-specific evidence and source identity from the locked PI records. Unknown, unsupported, cross-product or cross-variant references do not become verified; official-source selection uses PI source metadata instead of a Xiaomi host constant. `test_locked_research_grounding.py` covers distinct evidence, unsupported claims and a non-Xiaomi source. The configured external PI MCP presently exposes text/status without the claim IDs and evidence references needed for positive live grounding. |
| FIX-004 | `product_video/handlers.py`, `integrations/video_factory/ports.py`, `scene_renderer.py`, `server.py` | START and END frames retain one approved `scene_id`, separate role/ID, exact SHA/QC/package binding and request digest. Generated/required END conditioning is rejected before paid work if the selected provider does not implement it; an explicit omitted policy remains start-only. `test_end_keyframe_binding.py` covers one scene with two frames. |
| FIX-008 | The two `tests/mcp_servers/test_video_factory_*.py` files and test fixtures | Five stale fixtures/assertions were aligned with existing strict lineage, keyframe QC, approval and export contracts. The configured direct caller was audited; no production validation was weakened. MCP tests pass. |
| FIX-005 | `integrations/video_factory/keyframe_provider.py` | A SQLite `BEGIN IMMEDIATE` first-submission claim elects one worker before the paid call. Duplicate workers see the checkpoint; unknown outcome and terminal failed attempts are not blindly resubmitted under the same identity. Two-connection race tests assert one provider submit. |
| FIX-006 | `integrations/video_factory/domain.py`, `repository.py` | A monotonic project revision and compare-and-swap save reject divergent stale writes. Historical rows receive revision 0; identical stale replay is safe. Stale-reader, concurrent-writer and migration tests pass. |
| FIX-011 | `integrations/video_factory/capacity.py`, `keyframe_provider.py`, `scene_renderer.py`, `server.py`, `cli-config.yaml.example` | SQLite provider slots enforce configured in-flight limits and an optional exclusive Flow profile binding. Planned scene requests remain durable while waiting and submit when a slot opens. A process-stable lease owner lets status polling keep the same operation slot; expired ambiguous slots can be taken only for reconciliation. Transient Flow session loss preserves a submitted operation and its capacity reservation. Cross-connection contention, profile and recovery tests pass. The live smoke acquired one profile slot before the paid click and released it after reconciliation; multi-worker live contention has not been exercised. |

## Deferred fixes and working behavior preserved

- **FIX-007** automatic Video QC scene regeneration remains deferred. A non-PASS Video QC still blocks Final/export; manual/operator recovery remains the current safe path.
- **FIX-009** full export metadata provenance remains deferred. Existing full decode, exact SHA, Final approval, Video QC and immutable export checks remain in force; this is not a claim of full master-spec §10.2 metadata compliance.
- **FIX-010** automatic image reacquisition remains deferred. Image decode/hash/eligibility and minimum eligible reference checks remain in force.
- Product Lock, Brief, Scene Plan, Storyboard and Final approval gates remain mandatory. Atomic product claim, persisted workflow/outbox, V2 creative contracts, Image/Keyframe/Video QC, canonical render operations, composition and strict export were not relaxed.

## Test results

The full E2E-named test set uses substituted providers. At the user's direction it is excluded from the **live acceptance** evidence and from the final combined gate below. Its earlier passing result is recorded only as offline regression context.

| Command / exercise | Result | Evidence class |
| --- | --- | --- |
| `uv run pytest tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short` after Milestone A | 1,123 passed; 46 deprecation warnings | Offline regression only |
| `uv run pytest tests/hermes_personal/product_video/test_locked_research_grounding.py tests/hermes_personal/product_video/test_provider_capacity.py tests/hermes_personal/product_video/test_vf_project_conflict.py -q --tb=short` | 8 passed | Focused source/SQLite tests |
| `uv run pytest tests/hermes_personal/product_video/test_provider_capacity.py tests/hermes_personal/product_video/test_scene_render_runtime.py tests/hermes_personal/product_video/test_render_provider_selection.py -q --tb=short` | 59 passed | Provider/capacity regression |
| `uv run pytest tests/hermes_personal/product_video/test_provider_capacity.py tests/hermes_personal/product_video/test_render_provider_selection.py tests/hermes_personal/product_video/test_scene_render_runtime.py tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short` | 98 passed | Provider/MCP regression |
| `uv run pytest tests/hermes_personal/product_video/test_keyframe_pipeline.py tests/hermes_personal/product_video/test_vf_project_conflict.py tests/hermes_personal/product_video/test_end_keyframe_binding.py tests/hermes_personal/product_video/test_creative_handler_wiring.py tests/hermes_personal/product_video/test_locked_research_grounding.py -q --tb=short` | 21 passed | FIX-002/003/004/005/006 focused regression |
| `uv run pytest tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short` | 39 passed | FIX-008 MCP contract gate |
| `uv run pytest tests/hermes_personal/product_video/test_render_provider_selection.py::test_server_poll_session_loss_preserves_submitted_operation -q --tb=short` | 1 passed | Flow session-loss regression |
| `uv run pytest tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py -q --tb=short -k 'not e2e'` | 1,088 passed; 45 deselected; 46 deprecation warnings; rerun after Flow page implementation in 137.50 s | Combined non-E2E regression |
| `uv run ruff check hermes_personal tests/hermes_personal tests/mcp_servers/test_video_factory_server.py tests/mcp_servers/test_video_factory_paid_contract.py` | All checks passed | Static check |
| `uv run python -c "from hermes_personal.integrations.video_factory.server import get_job_status; from hermes_personal.integrations.video_factory.google_flow_provider import GoogleFlowPlaywrightProvider; print('video factory imports OK')"` | `video factory imports OK` | Import smoke |
| `uv run python -c "from hermes_personal.integrations.video_factory.google_flow_provider import GoogleFlowPlaywrightProvider; print('flow available:', GoogleFlowPlaywrightProvider.from_config().is_available())"` | `flow available: False` | Truthful configured Flow readiness |
| `uv run pytest tests/hermes_personal/product_video/test_render_provider_selection.py tests/hermes_personal/product_video/test_scene_render_runtime.py tests/hermes_personal/product_video/test_provider_capacity.py -q --tb=short` | 60 passed | Focused regression after Flow page implementation |
| `uv run ruff check hermes_personal/integrations/video_factory/google_flow_provider.py hermes_personal/integrations/video_factory/server.py` | All checks passed | Static check after Flow page implementation |
| `uv run python .hermes/flow_smoke_live.py` | First diagnostic stopped before Generate (0 paid clicks); after pre-click reset, second run made exactly 1 Generate click. Flow showed progress then one completed tile. | **Live Google Flow**; diagnostic script and checkpoint are under ignored `.hermes/` |
| Fresh Playwright Chromium process: `GoogleFlowBrowserPage.lookup_by_request_id("flow-smoke-20260924-jisulife-fa55-01")` | `completed`; project URL `https://flow.google.com/project/7000070f-32e5-4708-8744-9aef5a098a0a`; 720p MP4 downloaded | **Live Google Flow restart lookup** |
| Fresh `SceneRenderRuntime.run(request)` against the isolated smoke SQLite row in `submitting` | Bound the Flow URL and transitioned to `completed` with an output SHA; a later fresh run reused the completed clip. | **Live provider / durable reconciliation**, not a full Product Video E2E |
| `validate_scene_output(output_path=..., expected_duration=4, expected_aspect_ratio="9:16")` | Valid; 4.01 s, 720×1280, H.264, 24 fps, 96 fully decoded frames; SHA-256 `e40e5142bcaf022392d1501a2135ac5488ac19386353b672eec5d120bb5184ef` | Real downloaded media |
| Playwright Chromium `GoogleFlowBrowserPage.get_status(project_url)` with a 30 s post-download observation | `completed` after 40.2 s; downloaded file still had the same 96 frames and SHA | **Live Google Flow download stability** |
| `GoogleFlowPlaywrightProvider.submit(existing_request)` with the smoke project already present | Raised `GOOGLE_FLOW_REQUEST_PROJECT_EXISTS_RECONCILE` before Generate | **Live duplicate prevention**; no second paid click |

## Google Flow Playwright observation

The old `D:\AI_HERMES\HERMES\playwright_profile` and the other repository-local candidate had no Flow visits in Chrome history. The most relevant existing Chrome profile had recent Flow project visits. A cache-trimmed copy of that profile was placed at `.hermes/browser_profiles/google_flow` (115 MB); the existing `.gitignore` excludes `.hermes/` from Git. No cookie or credential values were printed.

The operator signed into the dedicated profile using normal Chrome. Playwright then opened the authenticated Flow home and project editor. One genuine Jisulife fan reference image was attached as the START frame in a unique project. The selected UI configuration was **Omni 1.1 Flash, Frames, 9:16, 4 seconds, x1**; Flow displayed **7 credits**. The diagnostic script made exactly one paid Generate click. The tile progressed to completion, remained present when a fresh process opened the project, and yielded a real MP4. The clip is at `.hermes/flow_smoke_20260924/flow-smoke-720p.mp4` and is ignored by Git. Five inspected frames showed the same silver handheld fan, a hand, and a moving ribbon; this visual spot check is not Product Video QC approval.

The installed Chrome executable crashed with Windows exit code `3221225477` (`0xC0000005`) on later download attempts. Playwright's bundled Chromium reopened the same authenticated profile, downloaded the identical MP4 repeatedly, and passed the 30-second post-download observation. Production page automation now uses Playwright Chromium. The saved session and a project-local, ignored `config.yaml` live under `.hermes/`; the configured composition check used process-scoped `HERMES_HOME=D:\work\hermes-upstream-rearchitecture\.hermes`. The global Hermes config was not changed. No cookies, tokens or account address are stored in source, SQLite or this report.

An ignored private RPC snapshot used to identify Flow's project/media relationship remains at `.hermes/flow_smoke_20260924/project_rpc.private.txt`: automatic approval review blocked its deletion. It is diagnostic data, not a production artifact, and should not be committed or shared.

## Remaining runtime verification and blockers

1. **Flow automated submission:** The real paid UI action used the one-shot diagnostic script. The production page adapter's `submit()` has not itself made a paid call, and its upload/model/credit selectors must be monitored against Flow UI changes. The read-only production status, download and lookup paths were exercised against the real completed project; no synthetic operation ID was used.
2. **PI wire grounding:** The configured PI MCP response lacks claim-level support and source references. The dossier now excludes unverifiable claims, but a real factual creative run still needs a PI result with the required relationships or a separately approved adapter contract change.
3. **Live acceptance:** One authentic Flow scene clip and restart reconciliation were observed. The full Product Video path through the five approvals, authentic research/model/QC, composition and immutable export has not been run. Live multi-worker profile contention and external quota behavior have not been exercised.

### Disposition for one real Product Video

| Priority | Remaining action | Why it matters |
| --- | --- | --- |
| **MUST FIX / VERIFY** | Supply claim-specific evidence and source relationships on the configured PI wire, then inspect the locked dossier. | Unsupported factual claims must not enter a real brief or scene. Current code correctly rejects ungrounded claims, but the configured PI response lacks the positive data. |
| **MUST VERIFY** | Run the production Flow `submit()` path once under the durable budget, scene-operation and profile-capacity claims, then complete Product Lock, Brief, Scene Plan, Storyboard and Final gates with actual QC and immutable export for the same product. | The one paid diagnostic and provider-edge recovery prove Flow can make a clip; they do not prove the whole Product Video workflow. |
| **SHOULD FIX / VERIFY** | Exercise Flow terminal failure/login/quota UI states and live multi-worker profile contention before concurrent production use. | Success and offline contention are verified, but these real external cases have not occurred in the test. Ambiguous outcomes currently stop for reconciliation. |
| **CAN WAIT** | FIX-007 automatic Video QC scene regeneration, FIX-009 fuller export metadata provenance, FIX-010 automatic image reacquisition. | The initial happy path can remain manually recoverable and fail closed; current QC and export integrity checks stay enforced. |

## Readiness

| Gate | Assessment |
| --- | --- |
| Milestone A code ready for an explicitly selected Vertex-only diagnostic | **Conditional:** source fixes and offline gate are green; configured PI claim grounding and live provider credentials still need verification. |
| Google Flow provider smoke | **PASS for the observed one-clip path:** authenticated profile, real generation, project URL, restart lookup, MP4 download, full decode and SHA were observed. The production `submit()` paid path remains unproven. |
| Milestone B concurrency mechanism | **Offline verified** by the combined non-E2E gate; one real profile lease was used, but live multi-worker contention remains. |
| Controlled real Product Video E2E through Flow | **NO-GO:** PI claim-level evidence is unavailable, and the five approvals/QC/export checks have not been observed on the same live product. The Flow smoke is not that end-to-end acceptance. |
