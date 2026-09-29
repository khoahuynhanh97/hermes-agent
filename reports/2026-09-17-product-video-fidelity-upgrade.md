# Hermes Product Video Fidelity Upgrade Report

**Date:** 2026-09-17  
**Scope:** Product reference filtering/ranking, scene fidelity contracts, keyframe/video prompts, Keyframe QC recovery  
**Status:** Implemented and verified offline; configured live-provider acceptance remains pending

## Source Review

The canonical master spec and plan already required grounded research, generated
keyframes, QC thresholds, five HITL gates, immutable hashes, and resumable provider
operations. The implementation had these foundations, but five fidelity gaps remained:

1. Image QC returned eligible references in source order and did not carry angle,
   visible-detail, suitability, or risk metadata into `ResearchDossier`.
2. Script scenes described action/start/end state but did not require product
   placement, lighting, identity cues, important visible details, or cross-scene continuity.
3. Keyframe/video prompts did not repeat the full scene lock; one generic keyframe
   prompt also contained product-category-specific wording (`another lamp`).
4. Failed Keyframe QC blocked Gate 4 but provided no structured recovery plan for
   reselecting references, rewriting prompts, adjusting composition, and regenerating.
5. The first hardening pass did not bind the QC receipt to the full creative package,
   and its retry path could reevaluate the same keyframe bytes. These were closed in
   the final integration pass below.

## Implemented

- Image QC now rejects exact duplicate bytes before evaluator calls, keeps rejected
  reasons for audit, and ranks clean references by identity/usability/clarity.
- The eligible manifest now carries `reference_rank`, component scores, `view_angle`,
  `shot_type`, `visible_details`, `scene_suitability`, `risk_flags`, and text coverage.
- `EligibleAsset` and `ResearchDossier` preserve the ranked profile without breaking
  older artifacts that omit the new fields.
- New generated plans use prompt provenance `script-scene-plan-v3`; every scene must
  include identity cues, placement, lighting, continuity, required visible details,
  reference requirements, and selected reference IDs.
- Scene reference selection is deterministic and ranks the selected candidates against
  scene requirements before keyframe generation.
- Keyframe prompts lock model/variant, shape, color, material, controls/logo placement,
  composition, lighting, start/end state, continuity, and identity details. Generic
  category wording was removed; seller/shop/marketplace identity and generated text remain forbidden.
- Video prompts repeat the approved scene and keyframe fidelity lock and use the
  QC-passed keyframe as the exact visual start state.
- Keyframe QC now records prompt/reference consistency, important-detail preservation,
  composition usability, and animation suitability. Failed frames produce ordered
  recovery actions and the workflow persists the recovery plan while staying blocked.
- `storyboard-package-v2` now stores the exact positive and negative prompts used for
  every generated keyframe. Its digest covers script, scene fields, storyboard frames,
  recovery attempt, prompts, references, and keyframe hashes; Keyframe QC and paid render
  recompute it and reject a changed package.
- QC response contracts are fail-closed for reference profiles and keyframe fidelity
  booleans. Cached rubric/policy versions were bumped so old reports cannot silently
  authorize the new contract.
- Keyframe retry is executable through both CLI and operator API: it requires the
  persisted recovery plan, creates a new attempt and idempotency key, reselects/reframes
  the failed scene where requested, regenerates it, and runs fresh QC before Gate 4.
  The old keyframe bytes are never accepted as the retry artifact.
- Locked identity cues now retain shape, color, material and logo placement in the
  production dossier and downstream prompts. The compatibility render prompt is
  product-neutral and no longer hardcodes Xiaomi.
- Both source and distributed Product Research/Product Video skills now document the
  ranked-reference, prompt-fidelity, post-production-text, and controlled-recovery rules.
- The optional product-image cleaner now fails closed when detection is unavailable,
  malformed, unlocalized, low-confidence, or asks to modify an unsafe fraction of the
  image. Cleaned images are derived assets with source/output SHA-256 lineage and must
  pass fresh Image QC; detector failure is never reported as a clean image.
- New creative generation uses exactly five bounded archetypes and a consistent
  16-50 second, 4-10 scene contract. Every V3 scene binds at least one verified claim
  and one eligible reference asset, including hook and CTA/payoff scenes.
- Image/video generation prompts no longer contain any concrete seller example such as
  a shop name. They express only generic seller/shop/source-store exclusions, so a
  negative prompt cannot accidentally seed the unwanted text it is meant to suppress.
- Vertex video provider selection is read from `config.yaml`; no new behavioral
  `HERMES_*` environment variable is required. Credentials remain profile-scoped secrets.

## Files Changed

- Creative contracts/prompts/validation: `hermes_personal/product_video/creative/`
- Image and Keyframe QC: `hermes_personal/product_video/qc/`
- Video prompt compiler: `hermes_personal/integrations/video_factory/scene_renderer.py`
- Derived-image preprocessing: `hermes_personal/product_video/preprocessing/image_cleaner.py`
- Vertex Veo adapter: `hermes_personal/integrations/video_factory/vertex_provider.py`
- Workflow recovery persistence: `hermes_personal/product_video/handlers.py`
- Skill sources: `.agents/skills/hermes-personal-product-{research,video-production}/SKILL.md`
- Distributed skills: `skills/{research,video}/hermes-personal-product-*/SKILL.md`
- Regression coverage: `tests/hermes_personal/product_video/test_fidelity_pipeline.py`,
  `test_image_qc.py`, `test_keyframe_gate_qc.py`, and
  `tests/skills/test_product_video_fidelity_skills.py`

## Architectural Decisions

- Extended current manifests/dataclasses rather than adding a second media catalog,
  workflow, model loop, provider port, approval gate, or storage service.
- Kept artifact schema `script-scene-plan-v2` readable and used prompt provenance V3
  to apply stricter validation only to newly generated plans.
- Kept recovery fail-closed at the existing operator/cost boundary. QC feedback is
  persisted; a retry moves back to the existing `creating_storyboard` state and is
  enqueued through the durable outbox. Gate 4 and video render remain unavailable until
  the regenerated keyframe package passes fresh QC.
- Kept CTA/overlay text in post-production rather than asking image/video models to draw it.
- Added one shared storyboard package digest contract and reused it in QC and render;
  no new provider, queue, approval gate, or core model tool was introduced.

## Before / After Observations

| Check | Before | After |
| --- | --- | --- |
| Exact duplicate references | Each file could consume an evaluator call and count independently | Duplicate digest is rejected before evaluation and cannot satisfy the two-reference gate |
| Reference order | Resource-pack/source order | Deterministic QC rank plus scene-use profile |
| Scene specificity | Action/start/end fields only | Identity cues, placement, lighting, visible details, continuity, angle/use requirements |
| Keyframe prompt | General identity preservation; category-specific `another lamp` wording | Product-neutral exact identity/composition/continuity lock with stronger negatives |
| Video prompt | Action and basic identity | Approved keyframe start state plus full scene fidelity lock |
| Keyframe failure | Score/reason and generic retry wait | Structured per-frame recovery plan; video remains blocked |
| QC/package binding | Receipt could be reused after prompt/scene edits | Full package digest is recomputed by QC and renderer |
| Retry behavior | Same artifact could be evaluated again | New recovery attempt regenerates failed scene before QC |
| Cleaner detector outage | Could be mislabeled as a clean image | `unknown`; original retained and blocked from implicit promotion |
| Cleaner provenance | `local_path` changed without complete byte lineage | Source asset snapshot plus source/output SHA-256 and mandatory fresh Image QC |
| Seller exclusions | A concrete shop name appeared inside negative prompts | Generic seller/shop/source-store constraints only |

The Xiaomi Mijia Desk Lamp Lite fixture verifies that a control-detail reference ranks
ahead of a generic hero image for an interaction scene, the full lamp identity remains
in both keyframe and video prompts, and no unrelated shop/CTA text is requested.
The existing grounded E2E suite also exercises the Baseus product fixtures and real
decodable PNG/MP4 artifacts through the current SQLite/HITL pipeline.

## Verification

- `uv run pytest tests/hermes_personal/product_video/test_fidelity_pipeline.py tests/hermes_personal/product_video/test_keyframe_gate_qc.py -q` -> 20 passed.
- Current reconciled Product Video + Video Factory MCP suite -> 322 passed, 4 known FastAPI deprecation warnings.
- `uv run pytest tests/hermes_personal/product_video/test_image_cleaner.py -q` -> 11 passed.
- `uv run pytest tests/hermes/adapters/google/test_vertex_video_provider.py -q` -> 8 passed.
- Operator/recovery/render regression set -> 27 passed.
- `uv run pytest tests/skills/test_product_video_fidelity_skills.py -q` -> 4 passed.
- `uv run pytest tests/hermes_personal -q` -> 885 passed, 1 unrelated timing-sensitive
  `JobDispatcher` assertion, 46 known FastAPI deprecation warnings. The failed test
  passed immediately when rerun alone (`1 passed`).
- `uv run ruff check` on all changed Product Video, integration, application, skill-test files -> all checks passed.
- `git diff --check` -> exit 0; only line-ending warnings from the already dirty worktree.

## Reconciliation of the 2026-09-17 Agent Report

- The cleaner, deep creative prompts, PyAV composer, and Vertex Veo adapter exist in
  source and have focused offline tests.
- The cleaner was not wired into the durable workflow. This remains deliberate until a
  governed, budget-admitted preprocessing operation can persist the derived pack before
  Image QC; calling a metered detector implicitly inside QC would bypass cost governance.
- The reported Xiaomi and Jisulife paths
  `video_factory_workspace/exports/export_proj_xiaomi_lamp_veo/final.mp4` and
  `video_factory_workspace/jisulife_life7_veo/exports/final.mp4` were not found in the
  repository, Hermes home, Codex home, or `hermes-agent-data`, so they are not accepted
  as live-run evidence.
- The available `composite_05e7b8bf3f97fd6258e88918.mp4` was fully decoded: 20.0s,
  720x1280, H.264, 24fps, 480 frames, no audio, SHA-256
  `e83282417298c40b407a8f386673537e04f7c2ff9b61d84b25f1ed54fd4485ed`.

## Remaining Blockers and Failure Cases

- No new paid image/video provider call was made in this task. A scoped cost
  authorization and configured credentials are still required to measure live keyframe
  fidelity, video drift, and provider QC pass rate.
- Derived-image cleaning is implemented as a safe library boundary but is not yet a
  durable, budgeted workflow stage. Until then, cleaned assets must be invoked explicitly
  and submitted through fresh Image QC before Product Lock.
- Exact-byte duplicate detection does not yet detect visually near-identical recompressed
  images. Perceptual duplicate scoring can be added later inside Image QC if real packs show
  this failure frequently.
- Recovery regeneration is now implemented but remains operator-gated; no paid retry runs
  without the existing explicit authorization and budget policy.
- Full Hermes Personal verification observed one unrelated timing-sensitive failure in
  `tests/hermes_personal/workflows/test_jobs.py::test_dispatch_successful_job`: the worker
  completed before the assertion sampled `PENDING`. It passed when rerun alone.
- The known FastAPI `on_event("shutdown")` deprecation warnings remain outside this slice.

## Next Steps

1. Run one authorized live Xiaomi lamp workflow using the ranked references and V3 scene plan.
2. Compare Keyframe QC item flags and video sample-frame QC against the previous failed export.
3. Apply the persisted recovery plan once if a frame fails, then record attempt cost and pass/fail delta.
4. Complete Task 10 acceptance only after operator review and a fresh immutable export package.
