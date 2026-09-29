---
name: hermes-personal-knowledge-learning
description: Governed knowledge retrieval and candidate capture.
version: 1.0.0
author: Hermes Personal
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Learning, Knowledge]
allowed-capabilities:
  - knowledge.candidate.create
  - knowledge.retrieve
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Hermes Personal Knowledge Learning Skill

## Architectural Boundary
The Hermes Orchestrator (`AgentTurnRuntime` + `AIAgent`) is the sole brain for all execution turns. This skill provides a governed domain contract for knowledge capture, candidate proposal, and approved knowledge retrieval; it is not an independent agent or router.

Stable `allowed-capabilities` are the authoritative source of truth for policy evaluation; wire names listed under `allowed-tools` are advisory candidate bindings resolved dynamically through capability discovery and catalog snapshots.

## Governed Capabilities
- `knowledge.candidate.create`: Propose new knowledge lessons or candidate entries for human review.
- `knowledge.retrieve`: Retrieve officially approved knowledge entries from canonical storage.

## Operational Rules
- All candidate additions require explicit human-in-the-loop review (`review_required`); auto-approval is strictly forbidden.
- Retrieval is restricted to approved knowledge entries (`approved_only`); learning or retrieval from unapproved, failed, or raw unverified turns is prohibited.
