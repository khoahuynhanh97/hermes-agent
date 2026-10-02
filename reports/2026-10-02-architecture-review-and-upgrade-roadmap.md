# Hermes Upstream & hermes_personal Architecture Review (2026-10-02)

## 1. Executive Summary & Health Scorecard

The current system merges a proven, stable Upstream Hermes Core with the highly specialized `hermes_personal` orchestration layer. 

### Health Scorecard (A-F)
- **Architectural Cohesion:** **B** (Strong isolation, but `hermes_personal` wrapper logic adds structural complexity).
- **SQLite Performance & Concurrency:** **A-** (Strong transactional guarantees, but requires careful tuning under high load).
- **Error Resilience:** **B+** (Excellent transactional outbox, but crash-recovery boundary tests need automation).
- **Code Health:** **B** (Refactored handlers improved modularity, but legacy technical debt lingers in core files).
- **UI/UX Modernization:** **D** (Current operator interface is minimal HTML-on-server, urgently needs visual dashboarding).

---

## 2. Top Architectural Bottlenecks & Fixes

1. **God-Object Tendency:** Even after splitting `handlers.py`, `_base.py` remains a significant coupling point.
   - *Fix:* Further decouple the `ProductVideoJobHandlers` class into mixin-style modules based on job category (e.g., `ResearchService`, `CreativeService`).
2. **SQLite Contention:** High-throughput writes to `workflow_outbox` and `turn_event` could trigger `SQLITE_BUSY` in multi-worker scenarios.
   - *Fix:* Ensure WAL mode is enforced, optimize transaction duration, and consider per-table connection pools if load spikes.
3. **Implicit Dependency Injection:** The manual injection of clients/engines in `ProductVideoJobHandlers` is brittle.
   - *Fix:* Formalize a dependency injection container (or use `DependencyInjector` pattern) to manage component lifecycle.

---

## 3. Prioritized Feature Roadmap (Effort vs. Impact)

| Feature | Priority | Effort | Impact | Description |
|:---|:---|:---|:---|:---|
| **Pipeline Kanban Board** | **P0** | High | High | Visual management for the 5 HITL gates. |
| **Provider Fallback Chain** | **P0** | Med | High | Automated provider-failover (e.g., Veo → Kling) for renders. |
| **Integrated TTS + Captions** | **P1** | High | High | Auto-sync voiceover + styled captions for viral reach. |
| **Post-Production Overlay** | **P1** | Med | Med | Brand watermarks, transition effects. |
| **Hybrid Semantic Search** | **P2** | High | Med | Add vector store (ChromaDB) to FTS5 for skill lookup. |

---

## 4. UI/UX Modernization Concept (The "Orchestrator Dashboard")

### Component Breakdown
- **Kanban Board:** State-driven visualization of the 16-state workflow.
- **Scene/Storyboard Editor:** Drag-and-drop grid for previewing keyframes, editing scene prompts, and setting durations.
- **Turn Inspector:** Live-streaming SSE viewer for observing agent turns, tool calls, and background worker status.

### Interaction Flow
1. **Operator view:** Opens Kanban board, sees items in `AWAITING_BRIEF_APPROVAL`.
2. **Action:** Clicks item → opens Side-by-Side viewer (Brief vs. Generated Keyframes).
3. **Decision:** Operator hits "Approve" (triggering `workflow_engine` transition) → item slides to `CREATING_SCENE_PLAN`.

---

## 5. Phase-by-Phase Implementation Plan

### Phase 1: Dashboard Infrastructure (Kanban & Inspector)
- **Goal:** Real-time visibility into the system.
- **Action:** Build basic FastAPI endpoints for Kanban state, turn streaming, and background worker monitoring.
- **Sprint:** Q4/2026 Sprint 1.

### Phase 2: Creative & QC UI
- **Goal:** Enable human control over video generation.
- **Action:** Implement Web-based Keyframe Preview and Storyboard Approval gate interfaces.
- **Sprint:** Q4/2026 Sprint 2-3.

### Phase 3: Multi-model Resilience & Automation
- **Goal:** Increase throughput and pipeline robustness.
- **Action:** Implement automated provider-fallback for failed video renders and integrate TTS/Subtitle services.
- **Sprint:** Q1/2027.

---
**Reviewer:** Principal Software Architect
**Date:** 2026-10-02
