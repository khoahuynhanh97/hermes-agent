---
name: hermes-personal-product-research
description: Governed Hermes personal skill for product market research and resource pack draft generation.
allowed-capabilities:
  - product.research
  - product.resource_pack.build
---

# Hermes Personal Product Research Skill

## Architectural Boundary
The Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the sole brain for all execution turns. This skill provides a governed domain contract and metadata boundary for product intelligence and market research workflows; it is not an independent agent or router.

## Governed Capabilities
- `product.research`: Execute market research, feature analysis, and domain discovery for target product lines.
- `product.resource_pack.build`: Construct initial resource pack drafts for product evaluation.

## Operational Rules
- All turns are subject to `CapabilityPolicyEvaluator` authorization and budget gating.
- Capabilities must be requested via governed capability search/discovery; raw un-bound wire names are not permitted.
