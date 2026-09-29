# Product Video Master Spec
## Product-Intelligence → Grounded AI Video Factory

**Status:** Canonical — supersedes all older Product Video design/spec files  
**Version:** 2.0  
**Date:** 2026-09-16  
**Scope:** Single-machine personal deployment; TikTok publishing remains manual.

---

## 1. Product Goal

Product-Intelligence discovers and verifies products daily. Hermes turns one approved product into a product-specific short-form video by researching first, building a grounded creative direction and script, generating QC-approved keyframes, rendering independent video scenes, composing a valid MP4, and stopping at five human approval gates.

The output must be a story about the approved product. A slideshow, pan/zoom loop, source-listing animation, or generic gadget montage is not a successful video.

```text
Product-Intelligence READY batch
  → research snapshot + evidence + source media
  → Image QC
  → [Gate 1] Product Lock
  → Research Dossier
  → grounded Creative Direction
  → [Gate 2] Creative Direction Approval
  → grounded Script + Scene Plan
  → [Gate 3] Script & Scene Plan Approval
  → Keyframe Specs
  → generate keyframes → Keyframe QC
  → Video Scene Specs
  → [Gate 4] Storyboard + Keyframes + Render Authorization
  → render each scene → scene checkpoint
  → compose overlays/transitions/audio policy
  → Technical QC + Content Video QC
  → [Gate 5] Final Video Approval
  → immutable MP4 + caption + metadata export
  → user posts to TikTok manually
```

## 2. Current Defects This Spec Corrects

The 2026-09-16 runtime audit found:

- Creative briefs were populated by generic defaults such as “thiết kế hiện đại, tính năng vượt trội”.
- Scene plans converted content blocks into repeated “Demonstrate product” actions.
- Storyboards contained text prompts but no generated keyframe artifact.
- Every scene could reuse the same source image, leaving the video provider to pan, zoom, rotate, or distort it.
- Historical outputs contained seller branding, marketplace graphics, black bars, malformed text, and unrelated presenter frames.
- `export_proj-pv-daily-88c43128656d9472_composite.mp4` and `export_proj-pv-daily-cd0118d89e8ee21c_composite.mp4` were byte-identical, mostly zero-filled, undecodable containers while metadata claimed valid 25.5-second 1080×1920 videos.

Therefore prompt improvements alone are insufficient. Artifact contracts, stage ordering, QC and export verification are part of the required fix.

## 3. Scope and Non-goals

### In scope

- One configured model implementation for grounded content generation.
- Structured, versioned prompts for creative direction, script, keyframes and video scenes.
- Actual generated keyframes before Gate 4.
- Keyframe and video QC with fail-closed behavior.
- Persisted state, digest-bound approvals, cumulative budget and paid-operation resume.
- An interface that can later be implemented by a multi-agent creative panel.

### Not in scope

- A second Hermes brain or a new general-purpose agent runtime.
- Multiple autonomous creative agents in the MVP.
- TikTok upload, scheduling or account management.
- Distributed queues, Redis, Kafka, RabbitMQ or a cloud database.
- A new UI. Existing CLI/operator console may display the upgraded artifacts.

## 4. Architectural Boundaries

Hermes `AIAgent` remains the sole orchestrating brain. Product Video remains a bounded workflow using existing CLI, MCP and SQLite infrastructure.

Scene rendering is capability-driven: the active `video.render` snapshot must
resolve exactly one canonical `mcp__video_factory__render` binding. The Video
Factory keeps the generic `VideoRenderProvider` port, but Product Video
accepts exactly two scene-render identities: `provider_kind="vertex_ai"` for
the Vertex AI Veo API and `provider_kind="google_flow"` for Playwright-driven
Google Flow. The configured provider is pinned durably before submission. An
explicit ordered policy may choose the other official provider only before that
claim; polling and recovery never switch a pinned operation. A local still-image,
pan/zoom, slideshow or synthetic video renderer is never a fallback. Both live
adapters still require provider-specific acceptance evidence.

```python
from typing import Protocol

class CreativeGenerationPort(Protocol):
    def create_direction(self, dossier: "ResearchDossier") -> "CreativeBriefV2":
        raise NotImplementedError

    def create_script(
        self,
        dossier: "ResearchDossier",
        brief: "CreativeBriefV2",
    ) -> "ScriptScenePlanV2":
        raise NotImplementedError

    def create_storyboard(
        self,
        dossier: "ResearchDossier",
        brief: "CreativeBriefV2",
        script: "ScriptScenePlanV2",
    ) -> "StoryboardSpecV2":
        raise NotImplementedError

    def create_video_scenes(
        self,
        dossier: "ResearchDossier",
        script: "ScriptScenePlanV2",
        storyboard: "StoryboardPackageV2",
    ) -> tuple["VideoSceneSpecV2", ...]:
        raise NotImplementedError
```

MVP implementation: `SingleModelCreativeGenerator`.  
Future implementation: `MultiAgentCreativePanel`, behind the same port and contracts.

No new Hermes core model tool is added. The implementation extends the existing Product Video/Video Factory edges.

## 5. Five Approval Gates

| Gate | Existing state | Operator approves | Entry requirements |
|---|---|---|---|
| 1. Product Lock | `AwaitingProductLock` | Exact identity, evidence-backed claims, eligible source images | Image QC PASS; at least two eligible images |
| 2. Creative Direction | `AwaitingBriefApproval` | Audience, insight, problem, angle, hook, promise, tone, CTA | Valid Research Dossier; no generic/fabricated claims |
| 3. Script & Scene Plan | `AwaitingSceneApproval` | Narrative, narration, overlay text, actions, environments, timing and transitions | Every factual line grounded; every scene visually actionable |
| 4. Storyboard & Keyframes | `AwaitingStoryboardApproval` | Generated keyframes, per-scene visual plan and video prompts | Every keyframe exists, matches digest and passes QC ≥80 |
| 5. Final Video | `AwaitingFinalApproval` | Decodable composed video after technical/content QC | Every scene present; Video QC PASS; metadata matches bytes |

Approvals bind to artifact ID, artifact version and SHA-256 digest. Changing an upstream artifact invalidates all dependent approvals and render plans.

## 6. State Machine

Five human gates are retained; internal persisted states become more explicit.

```text
researching
→ building_resource_pack
→ running_image_qc
→ AwaitingProductLock                         Gate 1
→ locking_resource_pack
→ building_research_dossier
→ creating_brief
→ AwaitingBriefApproval                       Gate 2
→ creating_scene_plan
→ AwaitingSceneApproval                       Gate 3
→ creating_storyboard
→ generating_keyframes
→ running_keyframe_qc
→ AwaitingStoryboardApproval                  Gate 4
→ rendering_scenes
→ composing_video
→ running_video_qc
→ AwaitingFinalApproval                       Gate 5
→ exporting
→ COMPLETED
```

Any recoverable error, QC `FAIL`/`UNKNOWN`, exhausted budget, malformed model output, missing evidence, ambiguous paid-provider outcome, or stale digest transitions to `WaitingForOperator`. Artifacts and paid-operation records are preserved.

## 7. Canonical Data Contracts

### 7.1 Research Dossier

`ResearchDossier` is the only creative input. It is deterministically assembled from the locked Resource Pack, persisted Product-Intelligence snapshot and optionally approved Hermes knowledge.

```json
{
  "schema_version": "research-dossier-v2",
  "workflow_id": "pv-live-baseus-wm02-20260916",
  "product_identity": {
    "brand": "Baseus",
    "model": "Bowie WM02",
    "variant": null,
    "display_name": "Baseus Bowie WM02",
    "distinctive_features": []
  },
  "verified_claims": [
    {
      "claim_id": "claim-01",
      "text": "Tai nghe được bảo quản trong hộp sạc nhỏ gọn",
      "evidence_refs": ["evidence-01"]
    }
  ],
  "restricted_claims": [],
  "audience_signals": [],
  "pain_points": [],
  "use_cases": [],
  "differentiators": [],
  "eligible_assets": [
    {
      "asset_id": "asset-01",
      "path": "D:/work/hermes-agent-data/inbox/baseus-wm02-01.jpg",
      "sha256": "6f1d7d7e6c8a737f0ec92d98bcfe31e4d80dc0bd2817ba5e67fe8e7848485521",
      "qc_report_id": "iqc-pv-live-baseus-wm02-20260916-01",
      "visual_observations": []
    }
  ],
  "approved_learnings": [],
  "source_refs": [],
  "dossier_digest": "sha256:5f7b39cc385b92f319313174dbb5906fa7ee268434f8837b68d2ea0d038574aa"
}
```

Invariants:

- Identity, claim text and media bytes must trace to evidence.
- Seller/shop/source branding is provenance, never product identity or creative content.
- A missing `verified_claims` list permits observed visual description only; it never permits invented specifications.
- Fewer than two eligible assets blocks the dossier.
- Approved learnings are optional and retrieval-only; unapproved memories cannot influence content.

### 7.2 Creative Brief V2

```json
{
  "schema_version": "creative-brief-v2",
  "audience": {
    "segment": "Người thường xuyên mang tai nghe khi di chuyển",
    "situation": "Cất tai nghe nhanh trước khi rời bàn làm việc",
    "desired_outcome": "Một bộ tai nghe gọn, dễ mang theo và dễ cất"
  },
  "consumer_insight": "Tai nghe chỉ tiện khi việc lấy ra và cất lại không làm gián đoạn nhịp di chuyển",
  "problem": "Tai nghe và hộp sạc cồng kềnh dễ bị bỏ lại hoặc chiếm chỗ trong túi nhỏ",
  "creative_angle": "Theo chân một lần rời bàn làm việc và cất tai nghe vào túi",
  "hook": "Rời bàn trong vài giây: tai nghe của bạn có cất gọn kịp không?",
  "promise": "Cho thấy trực quan cách bộ tai nghe và hộp sạc đi cùng một tình huống di chuyển ngắn",
  "reason_to_believe": [
    {"text": "Tai nghe được bảo quản trong hộp sạc nhỏ gọn", "evidence_refs": ["claim-01"]}
  ],
  "tone": "Quan sát đời thường, nhanh và rõ",
  "story_archetype": "problem_solution_demo",
  "cta": "Xem thêm thông tin sản phẩm.",
  "restrictions": [],
  "target_duration_seconds": 20,
  "prompt_version": "creative-direction-v2",
  "dossier_digest": "sha256:5f7b39cc385b92f319313174dbb5906fa7ee268434f8837b68d2ea0d038574aa"
}
```

Allowed MVP story archetypes:

- `problem_solution_demo`
- `day_in_the_life`
- `feature_proof_sequence`
- `before_after_experience` when the change is supported and visually representable
- `product_discovery_reveal`

The generator selects the archetype from evidence. It must not force the same four-beat template onto every product.

### 7.3 Script and Scene Plan V2

```json
{
  "schema_version": "script-scene-plan-v2",
  "language": "vi-VN",
  "target_duration_seconds": 20,
  "brief_digest": "sha256:9400d3f96dfa0cf5e981927f08a8ca010773bd61af185c4aa983b309dbc31ad0",
  "scenes": [
    {
      "scene_id": "scene-01",
      "order": 1,
      "story_role": "hook",
      "duration_seconds": 4,
      "narration": "Đến lúc rời bàn, mình chỉ cần đặt hai tai nghe lại vào hộp.",
      "overlay_text": "Cất gọn trước khi đi",
      "visual_objective": "Cho thấy thao tác cất tai nghe vào đúng hộp sạc",
      "environment": "Bàn làm việc cạnh một túi đeo nhỏ",
      "subject_action": "Một bàn tay tháo tai nghe và đặt lần lượt vào hộp",
      "product_interaction": "Hai tai nghe nằm đúng vị trí trong hộp sạc mở",
      "start_state": "Hộp sạc mở trên bàn, người dùng vẫn đeo tai nghe",
      "end_state": "Hai tai nghe đã nằm trong hộp và tay chuẩn bị đóng nắp",
      "visual_change": "Tai nghe chuyển từ tai người dùng vào hai khe của hộp sạc",
      "camera_framing": "Cận cảnh tay, tai nghe và hộp sạc theo khung dọc",
      "camera_movement": "Dolly-in rất nhẹ theo hướng bàn tay",
      "transition_out": "Match cut theo chuyển động đóng nắp hộp",
      "claim_refs": ["claim-01"],
      "reference_asset_ids": ["asset-01"]
    }
  ],
  "script_digest": "sha256:1df83b4a897ff670132469ad7325a310eed3aeeab0487e87bb16e7c809914858"
}
```

Scene invariants:

- Camera motion is not subject action. Zoom, pan, orbit or rotation alone is invalid.
- Each scene requires a visible `visual_change` from start state to end state.
- A scene with narration containing a factual claim requires matching `claim_refs`.
- The sequence must include at least two distinct visual setups and two distinct meaningful actions.
- `overlay_text` is stored separately and never baked into a generated keyframe/video.
- Total scene duration must equal target duration within 0.5 seconds.
- Repeated generic phrases such as “modern design”, “outstanding feature”, “daily convenience”, “demonstrate product” or their English equivalents are rejected unless made product-specific and evidence-grounded.

### 7.4 Storyboard and Keyframe Contracts

`StoryboardSpecV2` defines keyframes before generation. Each scene requires one start keyframe; an end keyframe is required when the provider supports first/last-frame conditioning or when the visual transition cannot be expressed safely from one frame.

```json
{
  "schema_version": "storyboard-spec-v2",
  "script_digest": "sha256:1df83b4a897ff670132469ad7325a310eed3aeeab0487e87bb16e7c809914858",
  "frames": [
    {
      "frame_id": "scene-01-start",
      "scene_id": "scene-01",
      "frame_role": "start",
      "visual_state": "Hộp sạc mở trên bàn, tay người dùng đang đưa tai nghe về đúng khe",
      "prompt": {
        "subject": "Bàn tay người dùng và bộ tai nghe Baseus Bowie WM02",
        "product_identity": "Baseus Bowie WM02 đúng màu và hình dáng theo ảnh tham chiếu",
        "product_state": "Hộp mở, hai khe tai nghe nhìn rõ, không có phụ kiện lạ",
        "environment": "Bàn làm việc gọn cạnh túi đeo nhỏ, không có logo cửa hàng",
        "composition": "Sản phẩm chiếm trung tâm dưới của khung dọc, bàn tay đi từ trên xuống",
        "camera": "Cận cảnh tương đương 50 mm, góc hơi cao",
        "lighting": "Ánh sáng cửa sổ mềm từ bên trái",
        "action_state": "Một tai nghe đang được đặt vào khe, tai nghe còn lại ở tay kia",
        "reference_asset_ids": ["asset-01"],
        "negative_constraints": []
      }
    }
  ]
}
```

After generation and QC it becomes `StoryboardPackageV2`:

```json
{
  "schema_version": "storyboard-package-v2",
  "script_digest": "sha256:1df83b4a897ff670132469ad7325a310eed3aeeab0487e87bb16e7c809914858",
  "frames": [
    {
      "frame_id": "scene-01-start",
      "generated_asset_id": "keyframe-scene-01-start-v1",
      "file_path": "D:/work/hermes-agent-data/workspaces/video-factory/keyframes/scene-01-start-v1.png",
      "sha256": "6d58078720fdf16ace6f4dc2c795d165923a09c8d5ba18ee473e097533f84775",
      "generation_operation_id": "keyframe-op-scene-01-start-v1",
      "qc_report_id": "kqc-scene-01-start-v1",
      "qc_score": 88,
      "qc_verdict": "PASS"
    }
  ],
  "video_scenes": [],
  "package_digest": "sha256:98b33db8c25f40c0638b13f459bd9c88cdd36ecf2a51bfd76be19cce3a26e91b"
}
```

Gate 4 opens only after all required keyframe bytes exist and each frame passes configured Keyframe QC with score ≥80 and no hard failure.

### 7.5 Video Scene V2

```json
{
  "schema_version": "video-scene-v2",
  "scene_id": "scene-01",
  "duration_seconds": 4,
  "start_keyframe_id": "scene-01-start",
  "end_keyframe_id": null,
  "subject_action": "Bàn tay đặt lần lượt hai tai nghe vào hộp rồi đóng nắp",
  "product_interaction": "Tai nghe khớp vào hai khe trong hộp sạc",
  "start_visual_state": "Hộp mở và một tai nghe đang ở trên tay",
  "end_visual_state": "Hai tai nghe nằm trong hộp và nắp vừa đóng",
  "camera_framing": "Cận cảnh dọc tập trung vào tay và hộp sạc",
  "camera_movement": "Dolly-in nhẹ, không xoay sản phẩm",
  "environment_motion": "Chuyển động tay tự nhiên, hậu cảnh gần như tĩnh",
  "motion_constraints": [],
  "identity_constraints": [],
  "negative_constraints": [],
  "provider_prompt": "A hand places both approved Baseus Bowie WM02 earbuds into the matching open charging case and closes the lid in one continuous natural action; restrained dolly-in; preserve exact product identity; no text or seller branding",
  "prompt_version": "video-scene-v2"
}
```

The deterministic compiler appends locked identity, selected keyframe digest, no-source-branding policy, no-readable-generated-text policy, scene timing and provider-specific constraints. The model cannot remove these suffixes.

## 8. Prompt Specification

### 8.1 Common grounded system prompt

```text
You are the grounded creative system for a short-form product video.
Use only the supplied ResearchDossier and previously approved artifacts.
Create content specific to the approved product, audience situation and verified evidence.

GROUNDING RULES
1. Every factual product claim must cite one or more claim_id values from verified_claims.
2. Never invent specifications, performance, price, promotions, comparisons or guarantees.
3. Seller, shop and marketplace information is provenance only and must not appear in creative content.
4. Do not use generic gadget language when a product-specific observation is available.
5. Do not design scenes whose only action is zooming, rotating or panning an image.
6. Each scene must contain an observable subject action, product interaction or cause-and-effect change.
7. Preserve the approved brand, model, variant, color and physical product identity.
8. Do not ask image/video models to draw readable text, prices, ratings, logos or marketplace UI.
9. Return only valid JSON matching the requested schema. Do not use Markdown.
```

### 8.2 Creative Direction prompt

```text
TASK
Create one focused CreativeBriefV2 for a vertical TikTok product video.

INPUT
research_dossier={{research_dossier_json}}

DECISIONS
- Select the audience situation supported best by the dossier.
- Select exactly one story_archetype from the allowed list.
- Build a hook from a real pain point, use case, observable detail or verified differentiator.
- Make the promise narrow enough to prove in a 16–24 second video.
- Provide reason_to_believe entries with valid claim references.
- Use a neutral manual-posting CTA; do not claim a promotion or authentic-store status.

OUTPUT
Return one CreativeBriefV2 JSON object.
```

### 8.3 Script and Scene Plan prompt

```text
TASK
Convert the approved creative direction into ScriptScenePlanV2.

INPUT
research_dossier={{research_dossier_json}}
approved_brief={{creative_brief_json}}

STORY REQUIREMENTS
- Use 3 to 5 scenes and a total duration between 16 and 24 seconds.
- The sequence must progress; no two scenes may repeat the same setup and action.
- Start with a product-relevant situation or action, not a title card.
- Demonstrate a real use case or visible product interaction before the CTA.
- Keep narration conversational Vietnamese suitable for manual TikTok posting.
- Keep overlay_text short; it will be composited later and must not appear in generated media.
- Every factual narration line must cite verified claim IDs.
- The approved scene narration may be requested as off-screen Vietnamese voiceover in the video provider prompt. Audio is optional: a valid silent clip remains usable and must not trigger an automatic second paid render. The final technical probe records whether the composed MP4 actually has audio.
- Describe start_state, end_state and visual_change concretely enough to generate keyframes.

REJECTION CHECK
Before returning, reject your own draft if camera movement is the only motion, the product could be replaced by any gadget without changing the script, or an unsupported claim appears.

OUTPUT
Return one ScriptScenePlanV2 JSON object.
```

### 8.4 Keyframe prompt

```text
TASK
Create StoryboardSpecV2 keyframe specifications for the approved scene plan.

INPUT
research_dossier={{research_dossier_json}}
approved_brief={{creative_brief_json}}
approved_script={{script_scene_plan_json}}

KEYFRAME RULES
- Ground product appearance in eligible reference_asset_ids.
- Create a real environment and action state that advances the approved story.
- Preserve product proportions, controls, ports, colors and distinctive features.
- Avoid floating products, duplicated parts, impossible hand contact and invented accessories.
- Do not reproduce source listing layouts, source backgrounds, watermarks or seller branding.
- Do not render readable text. overlay_text is compositor-owned.
- Request an end keyframe only when it materially constrains the scene transition.

OUTPUT
Return one StoryboardSpecV2 JSON object.
```

### 8.5 Video Scene prompt

```text
TASK
Create one VideoSceneSpecV2 for every approved scene and QC-passed keyframe.

INPUT
research_dossier={{research_dossier_json}}
approved_script={{script_scene_plan_json}}
approved_keyframes={{storyboard_package_json}}

MOTION RULES
- Animate the approved subject_action and product_interaction, not merely the camera.
- State the initial action, progression and final state.
- Keep motion physically plausible and identity-preserving.
- Use restrained camera movement that supports the action.
- Do not introduce people, accessories or product features not approved by the scene.
- Do not generate readable text, subtitles, prices, ratings, marketplace UI or source branding.
- Use the exact approved duration for each scene.

OUTPUT
Return a JSON array of VideoSceneSpecV2 objects in approved scene order.
```

Prompt templates are repository versioned. Every generated artifact stores `prompt_version`, configured model, input digests, raw response, parse error and output digest.

## 9. Validation and QC

### 9.1 Structured-output validation

Model output is rejected before persistence if JSON is malformed, contains unknown required-enum values, references missing claim/asset IDs, changes approved duration, or omits a required field. One repair call may be attempted using the validation errors and the original response. A second invalid response transitions to `WaitingForOperator`.

### 9.2 Keyframe QC policy

| Criterion | Weight/rule |
|---|---|
| Product identity match | 45 points |
| Scene/script adherence | 25 points |
| Composition and generation quality | 20 points |
| Reference usability | 10 points |
| PASS threshold | ≥80 for every required frame |
| Hard failure | Wrong model/variant/color, seller branding, watermark, marketplace UI, malformed product, unreadable/invented logo, missing required action state |

Keyframe QC is a paid stage covered by the cumulative campaign/workflow authorization. A semantic failure is not retried automatically; the workflow waits for operator rework.

### 9.3 Video QC policy

Technical QC must open and fully decode the composed container and derive duration, width, height, FPS, codec, audio presence and SHA-256 from the final bytes. Metadata values are written from this probe; caller-supplied media facts are not trusted.

Content QC samples at least start/middle/end of every approved scene and evaluates:

- product identity consistency: 35 points;
- approved action and visual-change adherence: 25 points;
- temporal stability and physical plausibility: 20 points;
- cleanliness/branding/text artifacts: 20 points.

Every scene and overall video must score ≥80. Wrong product, missing scene, wrong order, seller branding, watermark, malformed product, undecodable media or metadata mismatch is a hard failure.

## 10. Storage Architecture, Render, Composition and Export

### 10.1 Canonical Workspace Layout

One canonical workspace resolver (`ProductVideoWorkspaceLayout`) governs all components:

```text
<workspace>/
  projects/<project_id>/
    project-manifest.json
    assets/references/<sha256>.<ext>
    assets/cleaned/<sha256>.png
    creative/v<version>/
    storyboard/v<version>/
      storyboard-manifest.json
      scenes/scene-001/
        scene.json
        image-prompt.json
        video-prompt.json
        references.json
        keyframes/attempt-001/start.png
        keyframes/attempt-001/end.png
        qc/keyframe-report.json
    renders/v<version>/
      render-batch.json
      scenes/scene-001/attempt-001/
        clip.mp4
        clip-manifest.json
        technical-probe.json
      composite/
        draft.mp4
        timeline.json
        technical-probe.json
        video-qc-report.json
  exports/export_<project_id>_<version>/
    final.mp4
    caption.txt
    metadata.json
    keyframes/
    qc/
```

- Paths in SQLite and manifests must be stored as workspace-relative strings (`to_relative_path()`) and resolved dynamically via `resolve_path()`.
- External references are content-addressed and ingested into `assets/references/<sha256>.<ext>` before Product Lock; SHA-256 is verified on every read.
- File writes and copies are atomic using same-filesystem staging (`.tmp/`) and `os.replace`.

### 10.2 Render, Composition and Export Rules

- Render uses generated QC-passed keyframes, never raw seller/listing images directly.
- Each scene has a durable deterministic operation ID and persisted provider operation ID.
- Multi-scene rendering is managed via durable `RenderBatch` records and `video_factory_render_batches` in SQLite.
- Accepted operations are polled on resume and never resubmitted.
- Scene duration comes from the approved script; provider incompatibilities are surfaced before Gate 4.
- Composition normalizes to 720×1280, H.264, yuv420p and 24 FPS for MVP. Non-vertical or square inputs are rejected fail-closed; no non-uniform stretching is permitted.
- Overlay text is rendered by the compositor using the approved script, inside safe margins.
- Audio remains optional for MVP; presence/absence must be reported truthfully.
- The export directory is immutable and versioned. Existing artifacts are never overwritten.
- Export fails closed if the container cannot be fully decoded, is empty/zero-filled, has duplicate bytes unexpectedly reused across projects, differs from approved technical constraints, or lacks an authentic SQLite-verified PASS Video QC report bound to the exact composite SHA-256.

```text
exports/export_{project_id}_{version}/
  final.mp4
  caption.txt
  metadata.json
  keyframes/
  qc/
```

`metadata.json` includes all five approvals, dossier/brief/script/storyboard digests, prompt/model versions, selected source references, keyframe hashes and QC IDs, scene provider operation IDs, scene hashes, final technical probe, final video QC and cumulative spend.

## 11. Budget and Idempotency

```text
Campaign cap: $100 cumulative
Workflow/product cap: $10 cumulative
Covered paid stages: Image QC + creative model calls + keyframe generation/QC + scene render + Video QC
```

Admission is atomic before every paid call. Existing spend and reservations are included. A reusable workflow authorization may cover the whole pipeline until expiry/cap exhaustion; technical retries use new attempt IDs under the same authorization. No paid stage may infer authorization from a gate approval alone.

Deterministic identities include:

- creative artifact ID from workflow/stage/input digest/prompt version;
- keyframe generation ID from storyboard digest/frame ID/model/version;
- video scene operation ID from package digest/scene ID/model/version;
- composition/export ID from ordered scene hashes and composition spec.

## 12. Provider Interfaces

```python
class StructuredCreativeModel(Protocol):
    def generate_json(self, *, system_prompt: str, user_prompt: str, schema_name: str) -> dict:
        raise NotImplementedError

class KeyframeGenerationPort(Protocol):
    def submit(self, request: "KeyframeGenerationRequest") -> "ProviderOperation":
        raise NotImplementedError

    def poll(self, provider_operation_id: str) -> "ProviderOperation":
        raise NotImplementedError

class VideoRenderProvider(Protocol):
    def submit_scene(self, request: "VideoSceneRequest") -> "ProviderOperation":
        raise NotImplementedError

    def poll(self, provider_operation_id: str) -> "ProviderOperation":
        raise NotImplementedError
```

Provider/model/region settings live in `config.yaml`; credentials remain secrets. No provider name, project ID or region is hardcoded into the contracts.

## 13. Future Multi-agent Expansion

The MVP does not implement autonomous creative agents. Future `MultiAgentCreativePanel` may internally run Research Analyst, Creative Strategist, Scriptwriter, Visual Director and Grounding Critic roles. It must still:

- consume the same approved `ResearchDossier`;
- return the same four canonical artifact types;
- pass the same validators;
- preserve the same five gates;
- use the same cumulative budget and paid-operation records;
- store candidate and evaluation provenance without changing downstream contracts.

This permits option 3 later without speculative core hooks today.

## 14. Definition of Done

The upgraded MVP is complete only when one real configured product:

1. reaches Gate 1 with at least two Image-QC-eligible references;
2. receives a non-generic CreativeBriefV2 grounded in its dossier;
3. receives an approved 3–5 scene script with evidence-bound claims and meaningful actions;
4. generates real product-specific keyframes and passes Keyframe QC for every scene;
5. renders every scene from approved keyframes without duplicate paid submissions;
6. composes a fully decodable 720×1280 H.264 MP4 with correct timing;
7. passes per-scene and overall Video QC ≥80;
8. receives all five human approvals;
9. exports immutable MP4, caption and metadata whose facts match the actual files;
10. resumes safely after restart and reports cumulative spend.

Green unit tests, seeded QC reports, mock videos or historical MP4s do not replace configured live evidence.

## 15. Related Documents

| File | Status |
|---|---|
| `docs/superpowers/plans/product-video-master-plan.md` | Canonical implementation plan |
| `docs/hermes-personal/product-video-runbook.md` | Operational; update after implementation |
| Other dated Product Video specs/plans | Historical or superseded |
