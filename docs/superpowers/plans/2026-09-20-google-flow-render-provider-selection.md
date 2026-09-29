# Google Flow Render Provider Selection — Implementation Plan

**Status:** Single-Google-Flow contract, active capability binding, and recovery hardening implemented; Task 5 remains intentionally unstarted  
**Specification:** `docs/superpowers/specs/2026-09-20-google-flow-render-provider-selection.md`

## Constraints

- Preserve `vertex_provider.py` and its REST behavior.
- Do not add browser logic to `server.py`.
- Do not add a second Product Video workflow, renderer, composer, QC repository, or artifact store.
- Do not submit a second paid operation after an accepted or ambiguous outcome.
- Use deterministic local/fake-page tests only; no live Flow or Vertex generation.
- Keep all behavioral settings in `config.yaml`.

## Task 1: Lock the Provider-Neutral Contract with Tests — Done

Add `tests/hermes_personal/product_video/test_render_provider_selection.py` covering:

1. the active `video.render` snapshot binding is the only dispatched render wire;
2. `video_generate` and an ambiguous/missing render binding fail closed;
3. Google Flow unavailability never submits Vertex;
4. restart with a Google Flow checkpoint polls only Google Flow;
5. a legacy Vertex checkpoint requires operator reconciliation and is not polled;
6. an ambiguous/submitting Flow checkpoint returns reconciliation-required and never calls Vertex;
7. selection does not change the final canonical owner/project/workflow/artifact/version/SHA;
8. conflicting provider selection for the same scene attempt fails closed.

The deterministic tests cover one active binding, durable Google Flow pinning,
no fallback, restart polling, ambiguous checkpoints, unavailable Flow, and
legacy Vertex fail-closed behavior. They use fake providers only.

## Task 2: Persist Provider Identity Before Submission — Done

`SceneRenderOperationStore` now has an additive `provider_kind` migration, an immutable bind operation for operator/migration use, and an atomic submission claim:

```python
def bind_provider_kind(operation_id: str, provider_kind: str) -> dict[str, Any]: ...
def claim_provider_for_submission(request, provider_kind) -> ProviderClaimResult: ...
```

The claim pins the provider and changes `planned` to `submitting` in one SQLite transaction. Only `claimed` may submit; competing workers receive an explicit claim result and do not call another provider. Legacy single-provider rows without a pin are not inferred after a provider operation ID exists.

Add migration/restart tests using a real SQLite file.

## Task 3: Add a Concrete Resolver — Partial

Keep `VideoGenerationPort` generic, but make Product Video composition resolve one
`google_flow` provider. `_video_provider()` accepts only
`video_factory.render_provider: google_flow`; adapter absence is unavailable,
not a reason to construct Vertex.

## Task 4: Make Runtime Poll the Pinned Provider — Done

Update `SceneRenderRuntime` so it:

1. reads the durable operation row;
2. polls only a `google_flow`-pinned submitted/running row;
3. atomically claims and pins Google Flow before submission for new rows;
4. never evaluates a fallback;
5. returns reconciliation-required for unknown outcomes;
6. continues through existing `finalize_provider_result()` validation;
7. uses only the canonical optional `lookup_by_request_id()` reconciliation hook.

`server.render()` accepts the provider registry through its existing override boundary, and `server.get_job_status()` resolves the durable pin for polling. A submitting checkpoint without an operation ID is reconciled or returns `RECONCILIATION_REQUIRED`; it is never returned as indefinite `running`. No provider-specific browser logic was added to the server.

Compatibility parameters are ignored by Product Video production composition;
they cannot re-enable a fallback. Runtime and server reconciliation share one
no-I/O validator before checkpoint binding. It rejects a result for a
different request, a missing external operation ID, or provider metadata that
conflicts with the durable pin. Operation-ID binding remains compare-and-set
safe for concurrent same-identity retries and conflicting identities.

## Task 5: Implement Google Flow as a Real Provider — Not started by this refactor

Create `google_flow_provider.py` with an injected Playwright/browser-session boundary and a dedicated page object. Implement:

- availability/login-state probe;
- prompt and reference upload;
- one-shot Generate click;
- accepted operation URL/ID capture;
- resumable polling by operation ID;
- completed MP4 download to staging;
- explicit terminal, ambiguous, timeout, and user-action-required classifications;
- redacted diagnostics.

The default constructor lazily imports Playwright and returns deterministic pre-submit unavailability when the dependency or configured browser profile is absent. It must not silently launch with a fresh unauthenticated profile and then fall back after interacting with the page.

## Task 6: Deterministic Page and Recovery Tests

When Task 5 is separately authorized, use an injected local fake page/browser boundary to prove:

- prompt and references are submitted exactly once;
- accepted operation identity is returned before polling;
- retry/restart never clicks Generate again;
- completed download bytes are passed into the canonical validation path and hashed there;
- login/MFA/CAPTCHA returns user-action-required;
- timeout/ambiguous state does not trigger another provider;
- deterministic pre-submit unavailability fails closed;
- cookies, storage state, tokens, and page secrets are absent from SQLite and logs.

Do not mock `SceneRenderRuntime` or `SceneRenderOperationStore` in restart tests.

## Task 7: Production-Path Integration Verification

Run the provider-selection tests together with:

```powershell
uv run pytest tests/hermes_personal/product_video/test_scene_render_runtime.py -q
uv run pytest tests/hermes_personal/product_video/test_artifact_storage_and_recovery.py -q
uv run pytest tests/hermes_personal/product_video/test_production_integrity.py -q
uv run pytest tests/hermes_personal/product_video/test_happy_path_e2e.py -q
```

Then run the full Product Video suite and Ruff. Acceptance requires zero live provider calls, no duplicate submit after restart, no Product Video Vertex call, validated media before completion, and unchanged exact render/QC/export lineage.
