# Product Video Fidelity and Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use test-driven-development and verification-before-completion. Execute this plan inline in the current task.

**Goal:** Keep the locked product identity and scene intent intact from source-image selection through keyframe and video QC, with actionable recovery when fidelity checks fail.

**Architecture:** Extend the existing Image QC manifest, `ResearchDossier`, scene contract, storyboard compiler, and QC reports. Do not add a second workflow, provider abstraction, approval gate, or model loop. Recovery remains fail-closed and records a deterministic action plan for the existing operator-controlled retry boundary.

**Tech Stack:** Python dataclasses, SQLite-backed Product Video workflow, Vertex image/video provider ports, pytest, Ruff.

## Global Constraints

- Preserve the five existing HITL gates and all cost/idempotency checks.
- Reuse `research_snapshot`, Resource Pack, Product Intelligence, provider ports, and QC repositories.
- Generated media must contain no seller/shop/marketplace identity or generated CTA text.
- Legacy V2 artifacts remain readable; newly generated scene plans use the stricter prompt contract.

---

### Task 1: Rank Clean Product References

**Files:**
- Modify: `hermes_personal/product_video/qc/rubric.py`
- Modify: `hermes_personal/product_video/qc/evaluator.py`
- Modify: `hermes_personal/product_video/qc/image_qc.py`
- Test: `tests/hermes_personal/product_video/test_fidelity_pipeline.py`

**Interface:** Image QC emits an `eligible_reference_manifest` sorted by `reference_rank`, with component scores, viewing profile, visible details, suitability tags, and risk flags. Exact duplicate bytes are rejected before paid evaluation.

- [ ] Write and run failing tests for duplicate rejection and ranking.
- [ ] Add the structured reference-profile fields to the evaluator prompt and normalization.
- [ ] Build the ranked manifest and retain rejection reasons for audit.
- [ ] Run focused Image QC tests.

### Task 2: Carry Reference Semantics Into Scene Generation

**Files:**
- Modify: `hermes_personal/product_video/creative/contracts.py`
- Modify: `hermes_personal/product_video/creative/dossier.py`
- Modify: `hermes_personal/product_video/creative/prompts.py`
- Modify: `hermes_personal/product_video/creative/generator.py`
- Modify: `hermes_personal/product_video/creative/validation.py`
- Test: `tests/hermes_personal/product_video/test_fidelity_pipeline.py`

**Interface:** Eligible assets expose ranked scene-use metadata. New scenes explicitly include product identity cues, placement, lighting, continuity, required visible details, and reference requirements.

- [ ] Write and run failing contract/validation tests.
- [ ] Extend dataclasses with backward-compatible defaults and preserve digest stability rules.
- [ ] Upgrade script prompt/schema and mark new generations with `script-scene-plan-v3` prompt provenance.
- [ ] Validate the richer fields only for newly generated V3 plans.

### Task 3: Compile Fidelity-Locked Keyframe and Video Prompts

**Files:**
- Modify: `hermes_personal/product_video/creative/storyboard.py`
- Modify: `hermes_personal/integrations/video_factory/scene_renderer.py`
- Test: `tests/hermes_personal/product_video/test_fidelity_pipeline.py`
- Test: `tests/hermes_personal/product_video/test_scene_render_runtime.py`

**Interface:** Keyframe requests use ranked scene references and include explicit immutable identity, composition, placement, lighting, continuity, and negative constraints. Video prompts repeat the approved keyframe/scene invariants and never use product-category-specific hardcoding.

- [ ] Write and run failing prompt/reference tests.
- [ ] Add deterministic scene-reference scoring and selection.
- [ ] Compile strengthened keyframe and video prompts.
- [ ] Run storyboard and scene-render tests.

### Task 4: Produce Controlled QC Recovery Plans

**Files:**
- Modify: `hermes_personal/product_video/qc/rubric.py`
- Modify: `hermes_personal/product_video/qc/evaluator.py`
- Modify: `hermes_personal/product_video/qc/keyframe_qc.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Test: `tests/hermes_personal/product_video/test_fidelity_pipeline.py`
- Test: `tests/hermes_personal/product_video/test_keyframe_gate_qc.py`

**Interface:** Failed keyframe items record consistency/composition/detail/animation flags plus ordered actions: reselect reference, rewrite prompt, adjust composition, regenerate, then rerun QC. The workflow persists this plan and remains operator-blocked.

- [ ] Write and run failing recovery-plan tests.
- [ ] Normalize richer QC fields without invalidating legacy evaluator fixtures.
- [ ] Build deterministic per-frame and package recovery plans.
- [ ] Persist the plan in `WAITING_FOR_OPERATOR`; never open Gate 4 on failure.

### Task 5: Update Skills, Master Plan, and Evidence

**Files:**
- Modify: `.agents/skills/hermes-personal-product-video-production/SKILL.md`
- Modify: `.agents/skills/hermes-personal-product-research/SKILL.md`
- Modify: `skills/video/hermes-personal-product-video-production/SKILL.md`
- Modify: `skills/research/hermes-personal-product-research/SKILL.md`
- Modify: `docs/superpowers/plans/product-video-master-plan.md`
- Create: `reports/2026-09-17-product-video-fidelity-upgrade.md`

- [ ] Add the canonical reference-ranking, prompt-fidelity, QC, and recovery rules to both skill surfaces.
- [ ] Update the master plan status without rewriting historical evidence.
- [ ] Run focused tests, full Product Video tests, Ruff, and `git diff --check`.
- [ ] Record before/after observations, executed commands, remaining failures, and live-provider blockers.

