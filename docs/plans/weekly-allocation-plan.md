# Weekly Allocation Plan — Hermes Agent Platform Standardization

**Start Date:** 2026-08-17 (Week 34)
**Program:** Hermes Agent Platform Standardization (ADR-010)
**Total Duration:** 11 weeks (through Week 44)

---

## Week-by-Week Breakdown

### Week 34 (Aug 17–23) — Gate A: Architecture Contract & MCP Security
**Owner:** Platform Team  
**Focus:** Tasks 1–2 from standardization plan; Task 1 from Gate A remediation

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing architecture tests (Task 1, Step 1) |
| Tue | Run RED, publish ADR-010, mark ADR-001 superseded (Task 1, Steps 2–4) |
| Wed | Commit Task 1; begin MCP secret allowlisting (Task 2, Step 3) |
| Thu | Unify normalized registration (Task 2, Step 4); preserve operator disable |
| Fri | Verify GREEN, run MCP regression, commit Task 2 |

**Gate A Remediation Parallel:**
- Task 1: Add explicit policy resolver, write registration coverage tests

**Exit Criteria:** Architecture tests pass; MCP secret scope enforced; ADR-010 published Proposed

---

### Week 35 (Aug 24–30) — Gate A: Capability Metadata & Skill Contracts
**Owner:** Platform Team  
**Focus:** Task 3 (standardization); Tasks 1–2 (Gate A remediation)

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing model/catalog tests (Task 3, Step 1) |
| Tue | Implement immutable descriptors, bind principal at ingress (Steps 3–4) |
| Wed | Enforce canonical skill references (Step 5) |
| Thu | Verify GREEN, scan all bundled skills (Step 6) |
| Fri | Commit Task 3; Gate A remediation Task 1 complete |

**Gate A Remediation Parallel:**
- Task 2: Introduce RegistrationCandidate, validate-once-commit-once pipeline

**Exit Criteria:** All production tools have descriptors; skill validator consumes governed snapshot

---

### Week 36 (Aug 31–Sep 6) — Gate A: Principal Ingress & Skill Validation
**Owner:** Platform Team  
**Focus:** Gate A remediation Tasks 3–4

| Day | Deliverable |
|-----|-------------|
| Mon | Create ingress.py, principal_scope; write adapter-seam tests (Task 3, Steps 1–2) |
| Tue | Bind each channel from trusted source (Step 5); remove identity invention from AIAgent |
| Wed | Verify channel behavior and context cleanup (Step 6) |
| Thu | Skill validator consumes governed snapshot (Task 4, Steps 1–3) |
| Fri | Verify all governed skills; Gate A acceptance (Task 5) |

**Exit Criteria:** Full Gate A verification matrix passes without live providers

---

### Week 37 (Sep 7–13) — Gate B: Video Factory MCP & Durable Job Projection
**Owner:** Media Team  
**Focus:** Tasks 4–5 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Repair Video Factory MCP schema imports, remove duplicates (Task 4, Step 3) |
| Tue | Verify GREEN, run application tests (Task 4, Step 4) |
| Wed | Migrate job-event and generated-asset schemas (Task 5, Step 3) |
| Thu | Append terminal events transactionally; implement GeneratedAsset (Steps 4–5) |
| Fri | Implement idempotent projector; remove browser ownership of apply (Steps 6–7) |

**Exit Criteria:** Video Factory MCP lists unique tools; job completion projects durable assets offline

---

### Week 38 (Sep 14–20) — Gate C: Product Intelligence Contracts
**Owner:** Product Intelligence Team (separate repo)  
**Focus:** Task 6 (standardization) — external dependency

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing contract tests for PI query/draft/lock (Step 1) |
| Tue | Implement public query summaries with admin attestation (Step 3) |
| Wed | Implement durable draft revisions and explicit lock (Step 4) |
| Thu | Repair workspace export semantics (Step 5) |
| Fri | Verify GREEN, backfill fixtures, commit in PI repo (Step 6–7) |

**Blocking:** Hermes Task 7 cannot start until PI lock wire schema is stable

---

### Week 39 (Sep 21–27) — Gate C: Bind PI Locks to Hermes Projects
**Owner:** Platform Team  
**Focus:** Task 7 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Write fail-closed adapter tests (Step 1) |
| Tue | Implement anti-corruption port and adapter (Step 3) |
| Wed | Persist project bindings; migrate ResourcePack → ProductionResourceSet (Step 4) |
| Thu | Verify GREEN and MCP namespace isolation (Step 5) |
| Fri | Commit Task 7 |

**Exit Criteria:** Hermes stores only project bindings to immutable PI locks; no PI internal DB access

---

### Week 40 (Sep 28–Oct 4) — Gate D: FastAPI Operator API Dark Launch
**Owner:** API Team  
**Focus:** Task 8 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing security and composition tests (Step 1) |
| Tue | Build dependency container; bind principal at HTTP ingress (Steps 3–4) |
| Wed | Implement opaque asset streaming (Step 5) |
| Thu | Migrate Video Factory and Product Research routes (Step 6) |
| Fri | Dark-launch FastAPI; smoke verify /health, /api/projects, asset preview (Steps 7–8) |

**Exit Criteria:** FastAPI runs on 127.0.0.1:8000; asset endpoints reject path traversal and cross-owner access

---

### Week 41 (Oct 5–11) — Gate D: Product Research & Media Studio UI
**Owner:** Frontend Team  
**Focus:** Task 9 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing Playwright journeys (Step 1) |
| Tue | Normalize API client; implement Product Research pages (Steps 3–4) |
| Wed | Implement Media Studio asset browsing (Step 5) |
| Thu | Configure Playwright webServer for FastAPI + Vite (Step 6) |
| Fri | Verify GREEN, production build (Step 7); commit Task 9 |

**Exit Criteria:** React displays reference/generated media by opaque asset ID; no filesystem paths exposed

---

### Week 42 (Oct 12–18) — Gate E: Channel Convergence
**Owner:** Platform Team  
**Focus:** Task 10 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Write failing fake-engine parity tests (Step 1) |
| Tue | Implement AgentTurnRequest/Result and AgentTurnRuntime (Step 3) |
| Wed | Migrate CLI and API factories; route Telegram free text (Step 4) |
| Thu | Run GUI turns on worker thread with cancel support (Step 4) |
| Fri | Verify GREEN, channel regressions, compile checks (Step 5); commit Task 10 |

**Exit Criteria:** All free-text surfaces use Agent Turn boundary; AIAgent never invents principal

---

### Week 43 (Oct 19–25) — Gate E: Cutover, Observation, Retirement
**Owner:** Platform Team  
**Focus:** Task 11 (standardization)

| Day | Deliverable |
|-----|-------------|
| Mon | Add failing canonical-entrypoint assertions (Step 1) |
| Tue | Rehearse legacy startup rollback; record evidence (Step 3) |
| Wed | Cut canonical startup to FastAPI (start.ps1, start_web.bat) (Step 3) |
| Thu | Convert legacy servers to explicit compatibility entrypoints (Step 4) |
| Fri | Publish retirement matrix; run full non-paid verification; real read-only smoke (Steps 5–7) |

**Exit Criteria:** FastAPI is only production operator API; legacy paths retired or classified with rollback

---

### Week 44 (Oct 26–Nov 1) — Buffer & ADR Acceptance
**Owner:** All Teams  
**Focus:** Contingency, documentation, ADR-010 Accepted

| Day | Deliverable |
|-----|-------------|
| Mon | Address any rollback issues; complete observation window |
| Tue | Final regression sweep with fake providers |
| Wed | Mark ADR-010 Accepted; record commands/results in migration runbook |
| Thu | Team retrospective; update runbooks |
| Fri | Program closure; celebrate |

---

## Resource Allocation Summary

| Team | Weeks | Primary Gates |
|------|-------|---------------|
| Platform | 34–36, 39, 42–44 | A, C, E |
| Media | 37 | B |
| Product Intelligence | 38 | C (external) |
| API | 40 | D |
| Frontend | 41 | D |

---

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| PI lock schema delays | Medium | High (blocks Task 7) | Weekly sync with PI team; mock contract for Hermes development |
| MCP registration path parity | High | Medium | Gate A remediation Task 2 addresses directly; test all three paths |
| FastAPI parity gaps | Medium | High (blocks cutover) | Dark launch in Week 40; E2E against FastAPI before Week 42 |
| Paid provider calls in CI | Low | Critical | conftest_no_live_providers.py guard; env var enforcement |
| Legacy startup rollback failure | Medium | High | Rehearse rollback in Week 43 before cutover |

---

## Success Metrics (Definition of Done)

- [ ] All 11 standardization tasks complete with commits
- [ ] Gate A verification matrix passes (10 test files)
- [ ] FastAPI is canonical operator API
- [ ] Zero paid provider calls in automated tests
- [ ] Zero absolute filesystem paths served to browser
- [ ] Zero implicit admin/default_owner in production code
- [ ] ADR-010 status: Accepted
- [ ] Retirement matrix published with rollback commands

---

## Tracking

- **Primary Tracker:** GitHub Issues (one per task)
- **Weekly Sync:** Mondays 09:00 UTC
- **Gate Reviews:** End of Weeks 36, 39, 41, 43
- **Plan Location:** `docs/plans/weekly-allocation-plan.md`