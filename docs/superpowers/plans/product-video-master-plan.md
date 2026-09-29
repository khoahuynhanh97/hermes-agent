# Grounded Product Video Factory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the generic image-pan workflow with a grounded pipeline that researches the approved product, creates a product-specific script, generates and QC-checks keyframes, renders resumable video scenes, and exports one verified MP4 through the existing five gates.

**Architecture:** Add a versioned creative package inside `hermes_personal/product_video` with a `CreativeGenerationPort`, deterministic dossier builder, structured prompts and validators. Extend Video Factory with keyframe generation/checkpointing and make Gate 4 bind to real QC-passed keyframe bytes; preserve the five existing HITL states and use existing SQLite, MCP, budget and approval infrastructure.

**Tech Stack:** Python 3.11+, dataclasses, JSON Schema, SQLite/WAL, Hermes `PluginLlm.complete_structured`, FastMCP, Vertex AI Veo API and Google Flow Playwright render edges, PyAV, pytest and Ruff.

## Global Constraints

- Exactly five human gates: Product Lock, Creative Direction, Script & Scene Plan, Storyboard & Keyframes, Final Video.
- Campaign budget is `$100` cumulative; workflow/product budget is `$10` cumulative across every paid stage.
- Image, keyframe and video QC PASS thresholds are `≥80`; Product Lock also requires at least two eligible source images.
- No gate is auto-approved and no TikTok upload is implemented.
- Render uses generated QC-passed keyframes, never raw seller/listing images directly.
- Paid requests use deterministic IDs and persist provider operation IDs before advancing.
- Recoverable failure transitions to `WaitingForOperator`; artifacts and reservations are preserved.
- Provider/model/region settings live in `config.yaml`; credentials remain secrets.
- Focused tests run after each task; the Product Video suite and Ruff run once before live execution.

---

## Runtime Baseline and Audit Evidence

The 2026-09-16 audit established the following baseline:

- Existing `handlers.py` creates generic default brief fields and a repeated four-block script.
- `server.py::create_scene_plan` converts content blocks into repeated `Demonstrate product` scenes.
- `server.py::storyboard_generate` creates prompt records but no keyframe image.
- `server.py::render` sends the same eligible source image directly to every video scene.
- Four historical 16-second exports decode but contain listing layouts, seller branding, black bars or repeated image motion.
- The two newest exports are byte-identical (`sha256:7b5dc700b7b124c54becf8e129f6abf3c50a82007bf7ce6587c29a2a3f6a7a00`) and cannot be decoded, although their metadata claims valid 25.5-second 1080×1920 videos.

Do not use those exports as acceptance evidence.

## 2026-09-17 Fidelity and Recovery Status

The fidelity-hardening slice in
`docs/superpowers/plans/2026-09-17-product-video-fidelity-recovery.md` is now
implemented in the existing V2 pipeline:

- Image QC rejects exact duplicate bytes before evaluator submission and emits a
  ranked reference manifest with component scores, angle/shot profile, visible
  details, scene suitability, text coverage, and risk flags.
- `ResearchDossier` preserves that profile; newly generated scene plans use the
  `script-scene-plan-v3` prompt contract while remaining readable as V2 artifacts.
- New scenes explicitly bind identity cues, placement, lighting, visible details,
  continuity, and scene-specific reference requirements.
- Keyframe and video prompts repeat those locks and prohibit wrong variants,
  duplicated products, seller/shop identity, marketplace UI, and generated CTA text.
- Keyframe QC now checks prompt/reference consistency, important details,
  composition, and animation suitability. A failure persists an ordered recovery
  plan and remains blocked before Gate 4/video rendering.
- The storyboard package now stores the exact positive/negative keyframe prompts and
  uses a recomputed digest over the script, scenes, prompts, references, keyframe
  hashes and recovery attempt. QC and the renderer reject any package changed after
  approval.
- Keyframe recovery is executable through CLI and operator API: an authorized retry
  requeues storyboard generation with the persisted plan, a new attempt/idempotency
  key, and fresh QC. It does not reevaluate the old keyframe bytes.
- QC profile/fidelity fields are fail-closed, rubric/policy versions are invalidated,
  and locked shape/color/material/logo cues survive into the production dossier.
- The image-cleaning boundary now preserves source/output digests, refuses unsafe
  inpaint regions, and returns `unknown` on detector failure. A cleaned derivative must
  receive fresh Image QC and cannot silently replace source evidence.
- New V3 generation consistently targets 4-10 scenes totaling 16-50 seconds, with each
  scene bound to at least one verified claim and one eligible reference asset.
- Seller exclusions are generic; concrete shop names have been removed from generation
  prompts and negative prompts.
- Product Video scene render config accepts only `video_factory.render_provider: google_flow` or `vertex_ai`; credentials/browser session state stay in protected profile resolution. The selected provider is durably pinned before submission, and no local pan/zoom or slideshow renderer is permitted as fallback.

This closes deterministic source-ranking, package-binding, and executable-recovery gaps. It does not
replace Task 10 live acceptance: configured image/video provider pass-rate evidence,
operator visual review, and a fresh verified export are still required before the
master plan can be marked complete.

The cleaner is not yet inserted as an automatic workflow stage because its vision call
is metered. Automatic use requires a durable preprocessing operation with the existing
budget authorization, idempotency, artifact persistence, and fresh Image QC boundaries.
The Xiaomi/Jisulife live export paths reported on 2026-09-17 were not present during
reconciliation and therefore do not close Task 10 acceptance.

## File Responsibility Map

### New files

| File | Responsibility |
|---|---|
| `hermes_personal/product_video/creative/contracts.py` | Immutable V2 dossier/brief/script/storyboard/video-scene contracts and canonical digests |
| `hermes_personal/product_video/creative/dossier.py` | Deterministic conversion from locked PI/Resource Pack/QC artifacts to `ResearchDossier` |
| `hermes_personal/product_video/creative/prompts.py` | Versioned system/stage prompts and JSON schemas |
| `hermes_personal/product_video/creative/ports.py` | `CreativeGenerationPort` and `StructuredCreativeModel` protocols |
| `hermes_personal/product_video/creative/generator.py` | `SingleModelCreativeGenerator`, one repair attempt and inference provenance |
| `hermes_personal/product_video/creative/validation.py` | Cross-artifact grounding, evidence, duration and non-generic scene validation |
| `hermes_personal/integrations/video_factory/keyframe_provider.py` | Configured keyframe provider adapter and normalized requests/results |
| `tests/hermes_personal/product_video/test_creative_contracts.py` | V2 schema/digest tests |
| `tests/hermes_personal/product_video/test_research_dossier.py` | PI/QC-to-dossier tests |
| `tests/hermes_personal/product_video/test_creative_generator.py` | Prompt/model/repair/provenance tests |
| `tests/hermes_personal/product_video/test_creative_validation.py` | Evidence and anti-generic validation tests |
| `tests/hermes_personal/product_video/test_keyframe_pipeline.py` | Keyframe checkpoint, QC and Gate 4 tests |
| `tests/hermes_personal/product_video/test_export_integrity.py` | Full decode and metadata truth tests |
| `tests/hermes_personal/product_video/test_grounded_video_e2e.py` | Real SQLite offline integration happy path |

### Existing files to modify

| File | Change |
|---|---|
| `hermes_personal/product_video/handlers.py` | Replace default copy generation with dossier-driven generator and add internal keyframe stages |
| `hermes_personal/product_video/workflow.py` | Persist new internal states while retaining five gate states |
| `hermes_personal/product_video/qc/models.py` | Add `KEYFRAME` stage and artifact bindings |
| `hermes_personal/product_video/qc/service.py` | Run Keyframe QC through existing authorization/attempt/budget machinery |
| `hermes_personal/product_video/qc/rubric.py` | Add keyframe rubric and updated motion/story video rubric |
| `hermes_personal/integrations/video_factory/domain.py` | Persist V2 artifacts, generated keyframes and prompt provenance |
| `hermes_personal/integrations/video_factory/ports.py` | Add normalized keyframe port and extend video request with start/end keyframes |
| `hermes_personal/integrations/video_factory/repository.py` | Additive migration and serialization for V2 artifacts/operations |
| `hermes_personal/integrations/video_factory/service.py` | Save/invalidate V2 artifacts and downstream approvals |
| `hermes_personal/integrations/video_factory/server.py` | Wire V2 create/generate/render/export paths; remove generic fallback from configured mode |
| `hermes_personal/integrations/video_factory/composer.py` | Overlay compositor, full decode probe and immutable versioned export |
| `hermes_personal/product_video/cli.py` | Display dossier/brief/script/keyframe/QC details and required operator actions |

---

### Task 1: Fail Closed on Invalid Export Bytes

**Files:**
- Modify: `hermes_personal/integrations/video_factory/composer.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Create: `tests/hermes_personal/product_video/test_export_integrity.py`

**Interfaces:**
- Produces: `probe_video(path: Path, *, decode_all: bool = True) -> VideoProbe`
- Produces: `validate_export(path: Path, expected: VideoExpectation) -> VideoProbe`
- Consumes later: final Video QC and `metadata.json` writer use only the returned `VideoProbe`.

- [ ] **Step 1: Add a failing test for zero-filled and truncated MP4s**

```python
from pathlib import Path

import pytest

from hermes_personal.integrations.video_factory.composer import InvalidVideoArtifact, probe_video


def test_probe_rejects_ftyp_followed_by_zero_bytes(tmp_path: Path) -> None:
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"\x00\x00\x00 ftypisom" + b"\x00" * 4096)

    with pytest.raises(InvalidVideoArtifact, match="decode"):
        probe_video(broken, decode_all=True)
```

- [ ] **Step 2: Run the focused test and confirm failure before implementation**

Run: `uv run pytest tests/hermes_personal/product_video/test_export_integrity.py -q`  
Expected: FAIL because `InvalidVideoArtifact` and `probe_video` do not exist.

- [ ] **Step 3: Implement a full-decode probe and expectation check**

```python
@dataclass(frozen=True)
class VideoProbe:
    path: str
    sha256: str
    duration_seconds: float
    width: int
    height: int
    fps: float
    codec: str
    frame_count: int
    audio_present: bool


class InvalidVideoArtifact(ValueError):
    pass


def validate_export(path: Path, expected: VideoExpectation) -> VideoProbe:
    probe = probe_video(path, decode_all=True)
    if (probe.width, probe.height) != (expected.width, expected.height):
        raise InvalidVideoArtifact("resolution mismatch")
    if abs(probe.duration_seconds - expected.duration_seconds) > 0.5:
        raise InvalidVideoArtifact("duration mismatch")
    if probe.codec != "h264" or probe.frame_count < 1:
        raise InvalidVideoArtifact("codec/frame validation failed")
    return probe
```

`probe_video` must open with PyAV, decode every video frame, reject decoder errors/zero frames, derive stream facts and compute SHA-256 from the final bytes. `server.py::export` must call `validate_export` before copying or writing metadata.

- [ ] **Step 4: Add the metadata truth assertion**

```python
def test_export_metadata_is_derived_from_probe(valid_vertical_mp4: Path) -> None:
    probe = probe_video(valid_vertical_mp4, decode_all=True)
    metadata = build_video_metadata(probe)
    assert metadata["sha256"] == probe.sha256
    assert metadata["duration_seconds"] == probe.duration_seconds
    assert metadata["resolution"] == f"{probe.width}x{probe.height}"
    assert metadata["fps"] == probe.fps
```

- [ ] **Step 5: Run focused verification and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_export_integrity.py tests/hermes_personal/product_video/test_composer.py -q
uv run ruff check hermes_personal/integrations/video_factory/composer.py tests/hermes_personal/product_video/test_export_integrity.py
git add hermes_personal/integrations/video_factory/composer.py hermes_personal/integrations/video_factory/server.py tests/hermes_personal/product_video/test_export_integrity.py
git commit -m "fix(product-video): fail closed on invalid exports"
```

Expected: focused tests PASS and Ruff reports `All checks passed!`.

---

### Task 2: Add V2 Creative Contracts and Research Dossier

**Files:**
- Create: `hermes_personal/product_video/creative/__init__.py`
- Create: `hermes_personal/product_video/creative/contracts.py`
- Create: `hermes_personal/product_video/creative/dossier.py`
- Create: `tests/hermes_personal/product_video/test_creative_contracts.py`
- Create: `tests/hermes_personal/product_video/test_research_dossier.py`

**Interfaces:**
- Produces: `build_research_dossier(workflow_id, resource_pack, qc_report, research_snapshot, approved_learnings=()) -> ResearchDossier`
- Produces: `canonical_digest(value) -> str`
- Consumes: locked Resource Pack, persisted PI snapshot and fresh Image QC report.

- [ ] **Step 1: Write contract and deterministic-digest tests**

```python
def test_dossier_digest_is_order_stable() -> None:
    left = valid_dossier(source_refs=("source-b", "source-a"))
    right = valid_dossier(source_refs=("source-a", "source-b"))
    assert left.digest() == right.digest()


def test_dossier_requires_two_eligible_assets() -> None:
    with pytest.raises(ValueError, match="at least two eligible assets"):
        valid_dossier(eligible_assets=(valid_asset("asset-1"),))
```

- [ ] **Step 2: Run tests to establish red state**

Run: `uv run pytest tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_research_dossier.py -q`  
Expected: FAIL because the creative package does not exist.

- [ ] **Step 3: Implement immutable contracts**

Define frozen dataclasses for:

```python
ResearchDossier
CreativeBriefV2
AudienceSpec
ReasonToBelieve
ScriptScenePlanV2
ScriptSceneV2
StoryboardSpecV2
KeyframeSpecV2
GeneratedKeyframeV2
StoryboardPackageV2
VideoSceneSpecV2
GenerationProvenance
```

Each artifact exposes `to_dict()` and `digest()` using UTF-8 canonical JSON with sorted keys, normalized tuples and no volatile timestamps in the digest payload.

- [ ] **Step 4: Implement fail-closed dossier construction**

```python
def build_research_dossier(
    *,
    workflow_id: str,
    resource_pack: Mapping[str, object],
    qc_report: QCReport,
    research_snapshot: Mapping[str, object],
    approved_learnings: Sequence[Mapping[str, object]] = (),
) -> ResearchDossier:
    assert_fresh_image_qc(resource_pack, qc_report)
    identity = normalize_locked_identity(resource_pack)
    claims = evidence_bound_claims(research_snapshot)
    assets = eligible_assets_from_report(resource_pack, qc_report)
    if len(assets) < 2:
        raise DossierBuildError("at least two eligible assets are required")
    return ResearchDossier.create(
        workflow_id=workflow_id,
        product_identity=identity,
        verified_claims=claims,
        restricted_claims=restricted_claims(research_snapshot),
        eligible_assets=assets,
        audience_signals=audience_signals(research_snapshot),
        pain_points=pain_points(research_snapshot),
        use_cases=use_cases(research_snapshot),
        differentiators=differentiators(research_snapshot),
        approved_learnings=approved_learnings,
        source_refs=source_refs(research_snapshot),
    )
```

Only explicitly approved learning records may populate `approved_learnings`. Seller names remain inside source provenance and are excluded from creative fields.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_research_dossier.py -q
uv run ruff check hermes_personal/product_video/creative tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_research_dossier.py
git add hermes_personal/product_video/creative tests/hermes_personal/product_video/test_creative_contracts.py tests/hermes_personal/product_video/test_research_dossier.py
git commit -m "feat(product-video): add grounded creative contracts"
```

---

### Task 3: Add Versioned Prompts and Single-model Generator

**Files:**
- Create: `hermes_personal/product_video/creative/prompts.py`
- Create: `hermes_personal/product_video/creative/ports.py`
- Create: `hermes_personal/product_video/creative/generator.py`
- Create: `tests/hermes_personal/product_video/test_creative_generator.py`

**Interfaces:**
- Produces: `CreativeGenerationPort` with four methods from the Master Spec.
- Produces: `SingleModelCreativeGenerator(model: StructuredCreativeModel)`.
- Reuses: `agent.plugin_llm.PluginLlm.complete_structured`; do not add a core tool or direct credential handling.

- [ ] **Step 1: Write tests proving the prompt is grounded and output is schema validated**

```python
def test_direction_prompt_contains_dossier_and_grounding_rules(fake_model, dossier) -> None:
    fake_model.enqueue(valid_brief_payload(dossier.digest()))
    generator = SingleModelCreativeGenerator(fake_model)
    brief = generator.create_direction(dossier)
    request = fake_model.requests[0]
    assert dossier.product_identity.display_name in request.user_prompt
    assert "Every factual product claim" in request.system_prompt
    assert request.schema_name == "creative-brief-v2"
    assert brief.dossier_digest == dossier.digest()


def test_generator_allows_one_repair_call_then_stops(fake_model, dossier) -> None:
    fake_model.enqueue({"creative_angle": "missing required fields"})
    fake_model.enqueue({"creative_angle": "still invalid"})
    with pytest.raises(StructuredGenerationError, match="two invalid responses"):
        SingleModelCreativeGenerator(fake_model).create_direction(dossier)
    assert len(fake_model.requests) == 2
```

- [ ] **Step 2: Run the generator test in red state**

Run: `uv run pytest tests/hermes_personal/product_video/test_creative_generator.py -q`  
Expected: FAIL because the prompt/model adapter modules do not exist.

- [ ] **Step 3: Implement prompt constants and JSON schemas**

`prompts.py` must export:

```python
COMMON_GROUNDED_SYSTEM_PROMPT
CREATIVE_DIRECTION_PROMPT_V2
SCRIPT_SCENE_PLAN_PROMPT_V2
KEYFRAME_PROMPT_V2
VIDEO_SCENE_PROMPT_V2
CREATIVE_BRIEF_V2_SCHEMA
SCRIPT_SCENE_PLAN_V2_SCHEMA
STORYBOARD_SPEC_V2_SCHEMA
VIDEO_SCENE_LIST_V2_SCHEMA
```

Copy the canonical wording and field requirements from Master Spec section 8. Set creative temperature to `0.4`, script/keyframe/video temperature to `0.3`, and use configured max-token limits.

- [ ] **Step 4: Implement the model boundary and one repair attempt**

```python
class StructuredCreativeModel(Protocol):
    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
        json_schema: Mapping[str, object],
        temperature: float,
    ) -> StructuredModelResult:
        raise NotImplementedError
```

`SingleModelCreativeGenerator` validates the first parsed response. On validation error it makes exactly one repair call containing the original raw response and exact validation errors. The second invalid response raises `StructuredGenerationError` containing provider/model/schema/prompt version without secrets.

- [ ] **Step 5: Persist inference provenance in returned artifacts**

```python
GenerationProvenance(
    prompt_version="creative-direction-v2",
    provider=result.provider,
    model=result.model,
    input_digests=(dossier.digest(),),
    raw_response=result.text,
    parse_error=None,
    token_usage=result.usage.total_tokens,
)
```

- [ ] **Step 6: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_creative_generator.py -q
uv run ruff check hermes_personal/product_video/creative tests/hermes_personal/product_video/test_creative_generator.py
git add hermes_personal/product_video/creative tests/hermes_personal/product_video/test_creative_generator.py
git commit -m "feat(product-video): generate structured grounded creative artifacts"
```

---

### Task 4: Enforce Evidence and Non-generic Story Validation

**Files:**
- Create: `hermes_personal/product_video/creative/validation.py`
- Create: `tests/hermes_personal/product_video/test_creative_validation.py`

**Interfaces:**
- Produces: `validate_brief(dossier, brief) -> None`
- Produces: `validate_script(dossier, brief, script) -> None`
- Produces: `validate_storyboard(dossier, script, storyboard) -> None`
- Produces: `validate_video_scenes(script, package, scenes) -> None`

- [ ] **Step 1: Write regression tests for the actual generic failure mode**

```python
@pytest.mark.parametrize(
    "subject_action,visual_change",
    [
        ("Zoom into product", "Camera gets closer"),
        ("Pan around product", "Camera moves left"),
        ("Rotate product image", "Product image rotates"),
        ("Demonstrate product", "Product remains centered"),
    ],
)
def test_script_rejects_camera_only_or_generic_action(dossier, brief, subject_action, visual_change) -> None:
    script = script_with_scene(subject_action=subject_action, visual_change=visual_change)
    with pytest.raises(CreativeValidationError, match="meaningful action"):
        validate_script(dossier, brief, script)
```

- [ ] **Step 2: Add evidence and variety tests**

```python
def test_script_rejects_unknown_claim_reference(dossier, brief) -> None:
    script = script_with_scene(narration="Pin dùng 40 giờ", claim_refs=("missing-claim",))
    with pytest.raises(CreativeValidationError, match="missing-claim"):
        validate_script(dossier, brief, script)


def test_script_requires_two_setups_and_actions(dossier, brief) -> None:
    script = repeated_scene_script(environment="white studio", subject_action="hand holds product")
    with pytest.raises(CreativeValidationError, match="distinct visual setups"):
        validate_script(dossier, brief, script)
```

- [ ] **Step 3: Implement normalized validation**

Normalize Vietnamese/English text to lowercase Unicode, collapse whitespace and reject configured generic/camera-only phrases. Validate:

```python
3 <= len(script.scenes) <= 5
16 <= script.target_duration_seconds <= 24
abs(sum(scene.duration_seconds for scene in script.scenes) - script.target_duration_seconds) <= 0.5
len({scene.environment.casefold() for scene in script.scenes}) >= 2
len({scene.subject_action.casefold() for scene in script.scenes}) >= 2
```

Each claim reference must exist in the dossier; each asset reference must be QC-eligible; overlay text is prohibited from keyframe/video provider prompts.

- [ ] **Step 4: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_creative_validation.py -q
uv run ruff check hermes_personal/product_video/creative/validation.py tests/hermes_personal/product_video/test_creative_validation.py
git add hermes_personal/product_video/creative/validation.py tests/hermes_personal/product_video/test_creative_validation.py
git commit -m "feat(product-video): validate grounded scripts and scenes"
```

---

### Task 5: Wire Creative Direction and Script into Existing Gates 2 and 3

**Files:**
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/product_video/workflow.py`
- Modify: `hermes_personal/integrations/video_factory/domain.py`
- Modify: `hermes_personal/integrations/video_factory/repository.py`
- Modify: `hermes_personal/integrations/video_factory/service.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `tests/hermes_personal/product_video/test_handlers.py`
- Modify: `tests/hermes_personal/product_video/test_restart_recovery.py`

**Interfaces:**
- Consumes: `ResearchDossier`, `CreativeGenerationPort`, validation functions.
- Produces: persisted V2 artifacts bound to Gate 2 and Gate 3 approvals.

- [ ] **Step 1: Add a failing configured-mode test that forbids generic fallback**

```python
def test_configured_brief_uses_dossier_generator_not_default_copy(configured_handler, dossier) -> None:
    result = configured_handler.create_brief(
        product_id="baseus-bowie-wm02",
        project_id="proj-wm02",
        research_dossier=dossier.to_dict(),
    )
    payload = json.loads(result["payload"])
    assert payload["schema_version"] == "creative-brief-v2"
    assert "tính năng vượt trội" not in json.dumps(payload, ensure_ascii=False).lower()
```

- [ ] **Step 2: Add additive persistence fields**

Add nullable/defaulted columns to `video_factory_projects`:

```sql
research_dossier_json TEXT NOT NULL DEFAULT '{}',
creative_brief_v2_json TEXT NOT NULL DEFAULT '{}',
script_scene_plan_v2_json TEXT NOT NULL DEFAULT '{}',
storyboard_package_v2_json TEXT NOT NULL DEFAULT '{}',
creative_generation_provenance_json TEXT NOT NULL DEFAULT '{}'
```

Repository startup performs additive `ALTER TABLE` migration checks and remains able to read V1 rows.

- [ ] **Step 3: Replace configured-mode brief and scene fallbacks**

`brief_job` builds/persists the dossier then calls `create_direction`. `scene_plan_job` loads the approved brief/dossier and calls `create_script`. Existing V1 fallback remains available only in explicit fake/test provider mode.

If generation/validation fails twice, return recoverable code `CREATIVE_GENERATION_INVALID` with artifact/provenance persisted and transition to `WaitingForOperator`.

- [ ] **Step 4: Bind approval digests**

Gate 2 payload includes `creative_brief_v2.digest()`. Gate 3 payload includes `script_scene_plan_v2.digest()`. Replacing dossier/brief/script invalidates downstream approvals, keyframes, render operations and export refs.

- [ ] **Step 5: Verify restart and gate behavior**

```powershell
uv run pytest tests/hermes_personal/product_video/test_handlers.py tests/hermes_personal/product_video/test_restart_recovery.py -q -k "brief or scene or creative"
uv run ruff check hermes_personal/product_video/handlers.py hermes_personal/product_video/workflow.py hermes_personal/integrations/video_factory
git add hermes_personal/product_video/handlers.py hermes_personal/product_video/workflow.py hermes_personal/integrations/video_factory tests/hermes_personal/product_video/test_handlers.py tests/hermes_personal/product_video/test_restart_recovery.py
git commit -m "feat(product-video): ground gates two and three in research"
```

---

### Task 6: Generate, Checkpoint and QC Real Keyframes Before Gate 4

**Files:**
- Create: `hermes_personal/integrations/video_factory/keyframe_provider.py`
- Modify: `hermes_personal/integrations/video_factory/ports.py`
- Modify: `hermes_personal/integrations/video_factory/domain.py`
- Modify: `hermes_personal/integrations/video_factory/repository.py`
- Modify: `hermes_personal/integrations/video_factory/service.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/product_video/qc/models.py`
- Modify: `hermes_personal/product_video/qc/rubric.py`
- Modify: `hermes_personal/product_video/qc/service.py`
- Create: `tests/hermes_personal/product_video/test_keyframe_pipeline.py`

**Interfaces:**
- Produces: `KeyframeGenerationPort.submit/get_status`.
- Produces: durable `KeyframeOperation` per frame.
- Produces: `StoryboardPackageV2` only after every required keyframe QC PASS.

- [ ] **Step 1: Write checkpoint and Gate 4 tests**

```python
def test_resume_polls_existing_keyframe_operation_without_resubmit(keyframe_runtime) -> None:
    keyframe_runtime.persist_accepted(frame_id="scene-01-start", provider_operation_id="operations/kf-1")
    keyframe_runtime.resume()
    assert keyframe_runtime.provider.submit_calls == []
    assert keyframe_runtime.provider.poll_calls == ["operations/kf-1"]


def test_gate_four_requires_qc_pass_for_every_keyframe(gate_service, storyboard_package) -> None:
    package = storyboard_package.with_qc(scene_id="scene-02", verdict="FAIL", score=76)
    with pytest.raises(ValueError, match="KEYFRAME_QC_REQUIRED"):
        gate_service.request_storyboard_approval(package)
```

- [ ] **Step 2: Add normalized keyframe requests/results and SQLite operation rows**

```python
@dataclass(frozen=True)
class KeyframeGenerationRequest:
    operation_id: str
    workflow_id: str
    project_id: str
    frame_id: str
    prompt: str
    reference_image_paths: tuple[str, ...]
    aspect_ratio: str = "9:16"


@dataclass(frozen=True)
class KeyframeGenerationResult:
    operation_id: str
    status: Literal["submitted", "running", "completed", "failed"]
    provider_operation_id: str | None
    image_path: str | None
    error_code: str
    error_message: str
```

Persist `operation_id`, provider operation ID, request digest, reservation ID, status, output path and SHA-256 before advancing to the next frame.

- [ ] **Step 3: Compile prompts and submit only eligible references**

Compile the V2 keyframe spec plus locked identity and mandatory negative constraints. Verify every selected source path/SHA-256 against the Image QC eligible manifest. Raw seller images are conditioning references only; their listing layouts must not be copied into the generated keyframe.

- [ ] **Step 4: Extend QC with `KEYFRAME` stage**

Use the rubric in Master Spec section 9.2. Reuse the existing authorization, attempt IDs, cumulative budget and evaluator response parser. Semantic fail/hard failure does not auto-retry; technical `UNKNOWN` may retry up to the configured maximum of three total attempts.

- [ ] **Step 5: Move `AwaitingStoryboardApproval` after keyframe QC**

Persist internal states `generating_keyframes` and `running_keyframe_qc`. Gate 4 payload contains thumbnails/paths, QC IDs/scores, video-scene prompts and the final `package_digest`. Approval of an older spec or stale keyframe digest is rejected.

- [ ] **Step 6: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_keyframe_pipeline.py tests/hermes_personal/product_video/test_qc_service.py -q
uv run ruff check hermes_personal/product_video/qc hermes_personal/integrations/video_factory/keyframe_provider.py tests/hermes_personal/product_video/test_keyframe_pipeline.py
git add hermes_personal/integrations/video_factory hermes_personal/product_video/qc tests/hermes_personal/product_video/test_keyframe_pipeline.py
git commit -m "feat(product-video): generate and approve qc-passed keyframes"
```

---

### Task 7: Render Meaningful Scenes with Budget and Resume Safety

**Files:**
- Modify: `hermes_personal/integrations/video_factory/ports.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/integrations/video_factory/repository.py`
- Modify: `hermes_personal/product_video/handlers.py`
- Modify: `hermes_personal/workflows/budgets.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Modify: `tests/hermes_personal/product_video/test_happy_path_e2e.py`
- Modify: `tests/hermes_personal/product_video/test_crash_recovery_boundaries.py`

**Interfaces:**
- Consumes: approved `StoryboardPackageV2` and exact keyframe hashes.
- Produces: one durable `SceneOperation` and one immutable clip per scene.

- [ ] **Step 1: Add tests for keyframe usage, action prompts and resume**

```python
def test_render_uses_generated_keyframe_not_source_listing(render_runtime) -> None:
    render_runtime.render_scene("scene-01")
    request = render_runtime.provider.requests[0]
    assert request.reference_image_paths == (render_runtime.keyframe_path("scene-01-start"),)
    assert "opens the charging case" in request.prompt
    assert "do not merely zoom or pan" in request.prompt.lower()


def test_resume_does_not_resubmit_accepted_video_scene(render_runtime) -> None:
    render_runtime.persist_accepted("scene-01", "operations/video-1")
    render_runtime.resume()
    assert render_runtime.provider.submit_calls == []
    assert render_runtime.provider.poll_calls == ["operations/video-1"]
```

- [ ] **Step 2: Compile provider prompts deterministically**

The final prompt concatenates approved scene action/progression/end state, identity constraints, start/end keyframe bindings, exact duration and mandatory negatives. Reject a scene if `subject_action` is camera-only or keyframe QC/digest is stale.

- [ ] **Step 3: Enforce per-scene duration and deterministic operation IDs**

```python
operation_id = stable_id(
    "video-scene",
    workflow_id,
    storyboard_package.package_digest,
    scene.scene_id,
    provider_name,
    model_name,
)
```

Replace process-random `hash()` usage with SHA-256-derived IDs. Use each approved scene duration; if provider-supported durations differ, block before Gate 4 and show the adjusted render plan for reapproval.

- [ ] **Step 4: Complete cumulative budget admission**

Before every creative model, keyframe, QC and video call, atomically check:

```text
campaign_spent + campaign_reserved + next_estimate <= 100
workflow_spent + workflow_reserved + next_estimate <= 10
```

An unknown estimate blocks before submission. An accepted provider operation commits/holds its reservation. An ambiguous response transitions to `WaitingForOperator` and is never resubmitted automatically.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_happy_path_e2e.py tests/hermes_personal/product_video/test_crash_recovery_boundaries.py -q -k "render or budget or resume or duration"
uv run ruff check hermes_personal/integrations/video_factory hermes_personal/product_video/handlers.py hermes_personal/workflows/budgets.py
git add hermes_personal/integrations/video_factory hermes_personal/product_video/handlers.py hermes_personal/workflows/budgets.py hermes_personal/storage/sqlite.py tests/hermes_personal/product_video/test_happy_path_e2e.py tests/hermes_personal/product_video/test_crash_recovery_boundaries.py
git commit -m "feat(product-video): render resumable grounded video scenes"
```

---

### Task 8: Compose Overlays, Run Video QC and Export Truthful Metadata

**Files:**
- Modify: `hermes_personal/integrations/video_factory/composer.py`
- Modify: `hermes_personal/integrations/video_factory/server.py`
- Modify: `hermes_personal/product_video/qc/video_qc.py`
- Modify: `hermes_personal/product_video/qc/rubric.py`
- Modify: `tests/hermes_personal/product_video/test_composer.py`
- Modify: `tests/hermes_personal/product_video/test_video_qc.py`
- Modify: `tests/hermes_personal/product_video/test_export_integrity.py`

**Interfaces:**
- Consumes: ordered immutable scene clips and approved overlay text.
- Produces: validated composite, Video QC report and immutable export package.

- [ ] **Step 1: Test overlays are compositor-owned**

```python
def test_overlay_text_is_not_sent_to_video_provider_but_is_in_timeline(render_request, timeline) -> None:
    assert "Pin 25 giờ" not in render_request.prompt
    assert timeline.clips[0].overlay_text == "Pin 25 giờ"
```

- [ ] **Step 2: Compose normalized clips and overlays**

Normalize every scene to 720×1280, H.264, yuv420p, 24 FPS. Render approved Vietnamese overlay text inside vertical safe margins with deterministic timing. Preserve silent output when no approved audio track exists and report `audio_present=false`.

- [ ] **Step 3: Upgrade Video QC to story/action coverage**

Sample start/middle/end inside each scene boundary. Evaluate identity, approved action/visual change, temporal stability/physical plausibility, cleanliness and forbidden branding/text artifacts. Any undecodable media, missing/wrong-order scene or hard failure blocks Gate 5.

- [ ] **Step 4: Write immutable export package from actual probe data**

```text
exports/export_{project_id}_{version}/
  final.mp4
  caption.txt
  metadata.json
  keyframes/
  qc/
```

Metadata includes the five approvals, dossier/brief/script/package digests, prompt/model versions, source/keyframe/scene/final hashes, provider operation IDs, QC reports, technical probe and cumulative spend. The export function refuses to overwrite an existing directory.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_composer.py tests/hermes_personal/product_video/test_video_qc.py tests/hermes_personal/product_video/test_export_integrity.py -q
uv run ruff check hermes_personal/integrations/video_factory/composer.py hermes_personal/product_video/qc/video_qc.py tests/hermes_personal/product_video
git add hermes_personal/integrations/video_factory/composer.py hermes_personal/integrations/video_factory/server.py hermes_personal/product_video/qc tests/hermes_personal/product_video/test_composer.py tests/hermes_personal/product_video/test_video_qc.py tests/hermes_personal/product_video/test_export_integrity.py
git commit -m "feat(product-video): compose and validate final product videos"
```

---

### Task 9: Add a Realistic Offline Integration Happy Path

**Files:**
- Create: `tests/hermes_personal/product_video/test_grounded_video_e2e.py`
- Modify: `hermes_personal/product_video/cli.py`
- Modify: `docs/hermes-personal/product-video-runbook.md`

**Interfaces:**
- Exercises real SQLite repositories, workflow/outbox/approvals, creative generator boundary, keyframe/video providers, compositor and QC services.
- Uses deterministic injected providers; does not mock whole service methods.

- [ ] **Step 1: Build the fixture with realistic product evidence**

Use a temporary `HERMES_HOME`, a Baseus Bowie WM02-like fixture with three local reference images, evidence-bound claims and evaluator responses. The injected creative model returns product-specific structured JSON; keyframe/video providers write real decodable PNG/MP4 fixtures.

- [ ] **Step 2: Assert all five gates and internal stages**

```python
assert states == [
    "researching",
    "building_resource_pack",
    "running_image_qc",
    "AwaitingProductLock",
    "building_research_dossier",
    "creating_brief",
    "AwaitingBriefApproval",
    "creating_scene_plan",
    "AwaitingSceneApproval",
    "creating_storyboard",
    "generating_keyframes",
    "running_keyframe_qc",
    "AwaitingStoryboardApproval",
    "rendering_scenes",
    "composing_video",
    "running_video_qc",
    "AwaitingFinalApproval",
    "exporting",
    "COMPLETED",
]
```

- [ ] **Step 3: Assert quality and replay invariants**

The test verifies:

- no generic brief phrases;
- every narration claim has evidence;
- every scene has meaningful action and visual change;
- generated keyframes, not seller images, condition video render;
- all keyframes and scenes have fresh QC reports;
- restart after the second scene polls existing provider operations;
- replay creates no duplicate paid operation;
- final MP4 fully decodes and metadata matches probe/hash facts.

- [ ] **Step 4: Update CLI/status and runbook**

`status` shows dossier digest, creative angle, complete script, keyframe paths/thumbnails, QC scores, provider operations, spend and the exact operator action. Update runbook commands and keep TikTok publishing manual.

- [ ] **Step 5: Run final offline verification and commit**

```powershell
uv run pytest tests/hermes_personal/product_video/test_grounded_video_e2e.py -q
uv run pytest tests/hermes_personal/product_video -q
uv run ruff check hermes_personal/product_video hermes_personal/integrations/video_factory tests/hermes_personal/product_video
git diff --check
git add tests/hermes_personal/product_video/test_grounded_video_e2e.py hermes_personal/product_video/cli.py docs/hermes-personal/product-video-runbook.md
git commit -m "test(product-video): prove grounded offline happy path"
```

Expected: all Product Video tests PASS, Ruff reports `All checks passed!`, and `git diff --check` reports no whitespace errors.

---

### Task 10: Run One Configured Live Happy Case

**Files:**
- Runtime state only; do not edit code while a paid operation is ambiguous.
- Evidence recorded in `docs/hermes-personal/product-video-runbook.md` after completion.

**Interfaces:**
- Consumes: one Product-Intelligence READY product, configured creative/keyframe/video/QC providers and one reusable budget authorization.
- Produces: one immutable configured export and audit evidence.

- [ ] **Step 1: Preflight without paid calls**

```powershell
hermes personal video list
hermes personal video doctor
```

Confirm active `HERMES_HOME`, MCP subprocesses, configured model/provider names, Vertex/ADC project resolution, workspace path, campaign remaining budget and product cap. Back up the exact SQLite files before the run.

- [ ] **Step 2: Grant one bounded reusable authorization**

Create one workflow authorization with campaign cap `$100`, workflow cap `$10`, an explicit expiry and scope covering creative inference, keyframe generation/QC, video render and Video QC. Do not grant a new authorization for each technical retry.

- [ ] **Step 3: Advance through the five human gates**

At every gate, inspect the current artifact and approve only its displayed ID/version/digest:

1. Product identity/evidence/source images.
2. Product-specific creative direction.
3. Full Vietnamese script, actions, environments, durations and evidence references.
4. Actual generated keyframes, Keyframe QC and provider-ready scene prompts.
5. Full composed MP4 after Video QC.

- [ ] **Step 4: Verify configured output independently**

Open the final MP4, inspect frames across every scene and run the same full-decode probe used by export. Confirm no listing layout, seller branding, marketplace UI, malformed product, black bars, camera-only scenes or generic CTA artifact remains.

- [ ] **Step 5: Verify replay safety**

Restart the worker and repeat status/render resume. Confirm accepted provider operation IDs are polled rather than resubmitted and budget totals do not change from replay.

- [ ] **Step 6: Record acceptance evidence**

Record workflow/project IDs, five approval IDs, dossier/brief/script/package digests, QC report IDs/scores, scene operation IDs, output paths/SHA-256, technical probe and actual/unknown spend in the runbook. Do not include credentials or raw tokens.

---

## Storage Layout, Artifact Inventory & Recovery Hardening (2026-09-17)

The offline storage, artifact inventory, and recovery architecture is now fully hardened and verified across 10 mandatory scenarios (`test_artifact_storage_and_recovery.py`):

1. **Per-Project Isolation**: Two products with identical scene IDs (`scene-001`) use isolated directories (`projects/<project_id>/`) and cannot collide.
2. **Crash-Safe Multi-Scene Resumption**: Render batches track individual scene attempts and statuses in `video_factory_scene_operation` and `video_factory_render_batches`. Restarts resume unfinished scenes without duplicate paid submissions.
3. **Downstream Invalidation**: Modified keyframes or prompts invalidate dependent clips, composites, QC reports, and Final Approval status.
4. **Strict Video Composition & Geometry**: Non-vertical, square, or distorted clips are rejected fail-closed; 720x1280 @ 24fps vertical geometry is strictly enforced without non-uniform stretching.
5. **Exact-Bytes Video QC Binding**: `export()` independently verifies in SQLite that a `stage='VIDEO'` and `verdict='PASS'` report matches the exact exported video bytes.
6. **Content-Addressed Reference Ingestion**: External references are ingested into project-owned `assets/references/<sha256>.<ext>` before Product Lock; references survive removal of external source files.
7. **Workspace Root Relocation Safety**: Paths are stored as workspace-relative strings in database and manifests; relative paths remain valid after moving the workspace root.
8. **Reachability-Based Cleanup**: Prunes only unreferenced, failed artifacts while preserving all approved keyframes, QC reports, active timeline clips, and immutable export directories.
9. **Full 4-6 Scene End-to-End Delivery**: Realistic 4-scene product produces one complete storyboard manifest, one clip per scene, one ordered composite, and one immutable export package.

Test suite status: **905/905 tests passing in `tests/hermes_personal`** (100% green), **0 ruff errors**.

## Completion Criteria

The plan is complete only when Task 10 produces one real configured export satisfying all ten Definition of Done items in the Master Spec. Offline tests, fake providers, seeded QC, historical videos and operator approval without artifact inspection do not qualify.

## Deferred After the First Live COMPLETE

- `MultiAgentCreativePanel` candidate generation and critic voting behind `CreativeGenerationPort`.
- Audio/voice-over generation and loudness normalization.
- Multi-image conditioning where the selected provider supports it.
- A/B creative variants and automated retention scoring.
- Dashboard redesign or TikTok upload.
