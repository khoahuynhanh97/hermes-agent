---
name: hermes-personal-product-video-production
description: Produce product videos from locked research & media.
allowed-capabilities:
  - product.research
  - product.resource_pack.build
  - product.resource_pack.lock
  - video.brief.create
  - video.scene_plan.create
  - video.storyboard.create
  - video.render
  - video.export
allowed-tools:
  - web_search
  - fetch_web_page
  - image_generate
  - video_render
  - video_export
---

# Hermes Personal Product Video Production Skill

## Architectural Boundary
The Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the sole brain for all execution turns. This skill provides a governed domain contract for the end-to-end product-to-video pipeline; it is not an independent agent or router.

Stable `allowed-capabilities` are the authoritative source of truth for policy evaluation; wire names listed under `allowed-tools` are advisory candidate bindings resolved dynamically through capability discovery and catalog snapshots.

## Governed Capabilities
- `product.research`: Execute product research and market positioning.
- `product.resource_pack.build`: Construct resource pack drafts for product media.
- `product.resource_pack.lock`: Human-in-the-loop lock gate for product specifications.
- `video.brief.create`: Create creative video brief (requires locked product precondition).
- `video.scene_plan.create`: Structure video scene breakdown (requires approved brief precondition).
- `video.storyboard.create`: Generate visual storyboard (requires approved scene plan precondition).
- `video.render`: Render video assets (requires storyboard & budget HITL approval).
- `video.export`: Final export and packaging (requires final render HITL approval).

## Operational Rules
- All stage transitions require strict precondition satisfaction or explicit HITL approval grants.
- Metered and paid rendering steps require positive cost authorization.
- AI scene video may use only the Vertex AI Veo API (`vertex_ai`) or Playwright
  Google Flow (`google_flow`). Never generate a substitute clip by zooming,
  panning, looping, or assembling still images.
- Pin the selected provider before submission. Retries and recovery must use the
  same provider; provider failure is not permission to fabricate a local video.

## Grounded Fidelity Contract
Use this chain without skipping a boundary:

`product facts -> filtered/ranked references -> script + scene intent -> scene image prompt -> keyframe -> Keyframe QC -> video prompt -> video -> final QC`

- Every scene records observable action plus `product_identity_cues`, product placement, framing, camera direction, lighting, required visible details, and continuity into/out of the scene.
- Newly generated V3 plans contain 4-10 scenes totaling 16-50 seconds; every scene uses a provider-supported 4s, 6s, or 8s duration and binds at least one verified `claim_id` plus one eligible `asset_id`.
- Select references per scene from the Image QC manifest. Prefer low `reference_rank` values whose `view_angle`, `shot_type`, `visible_details`, and `scene_suitability` match the scene. Do not attach every available image.
- Keyframe and video prompts repeat the locked model/variant, shape, color, material, control/logo placement, composition, start/end state, and continuity. Seller/shop names, marketplace UI, source-image text watermarks, third-party watermarks, prices, and CTA text are forbidden in generated media; overlays and CTA belong in post-production. A native Google Flow watermark is acceptable only on a clip whose Google Flow provider provenance is verified.
- Gate 4 requires every generated keyframe to have a fresh Keyframe QC PASS bound to its bytes and approved references. Video render must use that keyframe, never a raw listing image.

## Controlled Recovery
When QC fails, keep the workflow blocked. Apply the persisted feedback in this order when relevant: `reselect_reference`, `rewrite_prompt`, `adjust_composition`, `regenerate_keyframe`, then rerun Keyframe QC. Do not approve Gate 4, render video, or reuse a failed keyframe. Paid retries still require the existing scoped cost authorization and idempotency rules.
