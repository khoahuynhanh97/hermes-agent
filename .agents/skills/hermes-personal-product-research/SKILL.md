---
name: hermes-personal-product-research
description: Research products and build packs for Hermes Product Video.
allowed-capabilities:
  - product.research
  - product.resource_pack.build
allowed-tools:
  - web_search
  - fetch_web_page
---

# Hermes Personal Product Research Skill

## Architectural Boundary
The Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the sole brain for all execution turns. This skill provides a governed domain contract and metadata boundary for product intelligence and market research workflows; it is not an independent agent or router.

Stable `allowed-capabilities` are the authoritative source of truth for policy evaluation; wire names listed under `allowed-tools` are advisory candidate bindings resolved dynamically through capability discovery and catalog snapshots.

## Governed Capabilities
- `product.research`: Execute market research, feature analysis, and domain discovery for target product lines.
- `product.resource_pack.build`: Construct initial resource pack drafts for product evaluation.

## Operational Rules
- All turns are subject to `CapabilityPolicyEvaluator` authorization and budget gating.
- Capabilities must be requested via governed capability search/discovery; raw un-bound wire names are not permitted.

## Product Reference Contract
- Keep brand, model, variant, color/material, distinctive shape, controls, logo placement, and evidence-bound facts separate from seller provenance.
- Reject or penalize low-resolution, blurry, duplicate, wrong variant, unclear-identity, misleading-angle, screenshot, banner, collage, excessive-text, watermark, seller/shop, marketplace UI, price/rating, and unrelated-logo media.
- Image QC must emit a ranked clean-reference profile: `reference_rank`, QC component scores, `view_angle`, `shot_type`, `visible_details`, `scene_suitability`, and `risk_flags`.
- Preserve at least two genuinely distinct eligible references. An exact duplicate does not count toward Product Lock readiness.
- Scene suitability is contextual: hero/context images establish the product; interaction/detail/side/rear/top images support only scenes that need those views. Downstream script generation selects by scene need rather than treating images equally.
- Treat text/watermark removal as generation of a derived asset, never a rewrite of source evidence. Preserve the original path and digest, record the cleaner method and output digest, and require fresh Image QC on the cleaned bytes.
- If artifact detection is unavailable, malformed, low-confidence, or proposes an unsafe region that could alter the product, return `unknown` and keep the original asset ineligible. Never label detector failure as a clean image.
