# ADR-010: General-Purpose Agent Platform Standardization

**Status:** Accepted

**Date:** 2026-08-12

**Scope:** `D:\work\hermes-agent` and the public MCP boundary of `D:\work\Personal\Product-Intelligence`

## Context

Hermes Personal is standardizing as a secure, general-purpose AI Agent Orchestrator. Hermes owns conversational reasoning, tool selection, context management, retries, and human interaction. It does not absorb the internal business logic or data stores of independently owned capability modules.

This document establishes the architecture authority for Hermes Agent platform standardization.

## Decisions

### 1. Hermes is the Conversational Orchestrator
- `agent/conversation_loop.py` (`run_conversation`) is the canonical execution loop.
- `run_agent.AIAgent` is its compatibility facade.
- Channels (CLI, Web, Gateway, Telegram, GUI) converge on a channel-neutral Agent Turn boundary above `AIAgent`.

### 2. Channels are Transport & UI Adapters
- Channels own authentication, rendering, streaming, and UI threading.
- Channels dispatch turns to the Agent Turn boundary or call Operator APIs directly.

### 3. Capability Bounded Contexts
- Hermes-owned application modules, external MCP servers, and workers retain independent domain ownership.
- Hermes does not import Product Intelligence Python packages (`product_scout`, `media`).
- Database merging across Hermes, Product Intelligence, and Video Factory is prohibited.

### 4. Product Intelligence is External Resource Intelligence
- Product Intelligence owns open-web discovery, evidence, product/variant resolution, product media storage, research snapshots, resource pack drafts, and immutable resource locks.
- Hermes stores only a `ProjectResourceBinding` referencing immutable Product Intelligence locks by ID and manifest digest.

### 5. Video Factory Consumes Production Resource Bindings
- Product Intelligence resource locks and Video Factory input resources are separate bounded contexts.
- An anti-corruption adapter in Hermes verifies Product Intelligence locks and converts them to Video Factory input sets (`ProductionResourceSet`).

### 6. Workers operate under Application Services
- Workers execute background job items from `JobRepository` and project terminal events idempotently into application states.
- Browser polling never owns job-to-domain projection transactions.

### 7. FastAPI is the Canonical Operator API Root
- `server/app.py` is the single Web composition root.
- Legacy `web_studio.py` is retained as a compatibility adapter during strangler migration.

## Data Ownership Summary

| Domain | Owner |
|---|---|
| Sessions, memory, turn state | Hermes Agent Runtime |
| Product evidence, identity, listings, media, resource locks | Product Intelligence |
| Project-to-Resource Lock Binding | Hermes Application Layer |
| Affiliate commission, score, shortlist, content package | Affiliate Product |
| Video Factory creative brief through render export | Video Factory |
| Job execution, leases, terminal events | Hermes Durable Job Plane |

## References

- [`docs/superpowers/specs/2026-08-12-hermes-agent-platform-standardization-design.md`](file:///d:/work/hermes-agent/docs/superpowers/specs/2026-08-12-hermes-agent-platform-standardization-design.md)
- [`docs/architecture-decisions/007-p6-final-architecture-closure.md`](file:///d:/work/hermes-agent/docs/architecture-decisions/007-p6-final-architecture-closure.md)
- [`docs/architecture-decisions/009-canonical-source-runtime.md`](file:///d:/work/hermes-agent/docs/architecture-decisions/009-canonical-source-runtime.md)
