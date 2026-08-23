---
name: hermes-personal-product-video-production
description: Governed Hermes personal skill for the full product-to-video production pipeline.
allowed-capabilities:
  - product.research
  - product.resource_pack.build
  - product.resource_pack.lock
  - video.brief.create
  - video.scene_plan.create
  - video.storyboard.create
  - video.render
  - video.export
---

# Hermes Personal Product Video Production Skill

## Architectural Boundary
The Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the sole brain for all execution turns. This skill provides a governed domain contract for the end-to-end product-to-video pipeline; it is not an independent agent or router.

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
