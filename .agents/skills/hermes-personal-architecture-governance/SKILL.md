---
name: hermes-personal-architecture-governance
description: Enforce Hermes Personal and Product Video code, persistence, media, storyboard, manifest, QC, and final-export architecture. Use before moving or adding modules, contracts, repositories, schemas, JSON files, images, clips, or generated artifacts under hermes_personal.
---

# Hermes Personal Architecture Governance

Use this skill before changing the structure or ownership of Hermes Personal code
or data. It is a guardrail, not a second architecture specification.

## Read First

1. Read `docs/README.md` and follow its authority order.
2. Read [Code Architecture](references/code-architecture.md) for module ownership,
   dependency direction, APIs, workers, providers, or move-only refactors.
3. Read [Data Architecture](references/data-architecture.md) for SQLite, JSON,
   images, references, keyframes, storyboards, clips, QC, or final video.
4. Read the canonical Product Video master spec and current implementation before
   treating a planned surface as implemented.

## Required Method

1. Identify the existing owner of every symbol and artifact before editing.
2. State the affected boundary, source of truth, and compatibility surface.
3. Extend or move the existing owner. Do not create a parallel model, workflow,
   path resolver, repository, or output tree.
4. Keep domain contracts provider-neutral and ingress/UI layers thin.
5. Preserve immutable IDs, versions, digests, lineage, approvals, and idempotency.
6. Add behavior and recovery tests at the boundary that changed.
7. Update canonical documentation when a contract or layout intentionally changes.

## Non-Negotiable Invariants

- `AgentTurnRequest`, `AgentEvent`, and `HermesTurnService` remain the canonical
  channel-neutral turn path.
- SQLite repositories are the durable state and metadata source of truth.
- `ProductVideoWorkspaceLayout` is the only Product Video path authority.
- Persist workspace-relative paths; reject traversal and unapproved external roots.
- Store media by immutable identity and SHA-256 lineage; write files atomically.
- Never overwrite approved artifacts or versioned exports.
- Never bypass Product Lock, Brief, Scene Plan, Storyboard, or Final approval.
- Provider payloads and options stay behind provider adapters and ports.
- Configuration belongs in `config.yaml`; `.env` is for credentials only.
- Do not add brokers, caches, databases, provider calls, or cleanup behavior by
  assumption. Require an approved architecture change and executable evidence.

## Stop Conditions

Stop and reconcile the design before coding when an edit would:

- introduce a second owner for the same contract or data;
- persist an absolute local path or unversioned mutable artifact;
- detach an artifact from its parent IDs, input digests, QC, or approval record;
- write generated files outside the canonical workspace;
- make a paid call without durable reservation and resumable operation identity;
- delete a source, approved artifact, active dependency, or immutable export;
- claim a route/process is implemented without import, wiring, and runtime proof.
