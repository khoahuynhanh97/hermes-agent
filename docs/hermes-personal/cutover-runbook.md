# Hermes Upstream Gateway Cutover and Retirement Runbook

This document defines the operational procedures for the ordered, reversible four-channel cutover and guarded legacy retirement.

## 1. Overview & Principles

- **Single Boundary**: Natural-language ingress across CLI, Omni, Telegram, and Web converges onto one canonical `HermesTurnService`.
- **Zero Loss / Reversible**: Ingress cutover flags can be rolled back instantly per-channel without dropping or mutating durable user data.
- **Semantic Parity**: Parity compares execution categories, capability selections, workflow states, and approval gates rather than fragile prose wordings.
- **Multi-Gate Retirement**: Legacy paths cannot be retired until all 7 mandatory gates pass and historical data stores are confirmed retained.

---

## 2. Ordered Cutover Stages

### Stage 1: CLI and Omni (Direct Local & API Ingress)
1. **Pre-flight Checks**:
   - `uv run pytest tests/hermes_personal/runtime tests/hermes_personal/gateway -q` (100% PASS).
   - Zero unexplained migration diffs in local session stores.
   - Tested rollback commands for `cli` and `omni`.
2. **Cutover Execution**:
   - Set `cutover.channels.cli.enabled = true` and `cutover.channels.omni.enabled = true`.
3. **Observation Window**:
   - Monitor 100 turns; error rate must remain < 0.1%, duplicate effects = 0.

### Stage 2: Telegram Channel Cutover
1. **Pre-flight Checks**:
   - Stage 1 active and healthy.
   - Run semantic parity comparison against shadow Telegram traffic.
   - Webhook & polling health probes report `healthy`.
2. **Cutover Execution**:
   - Set `cutover.channels.telegram.enabled = true`.
3. **Observation Window**:
   - Monitor for 24 hours or 500 interactions; p95 latency delta < 20%.

### Stage 3: Web Chat and Operator UI Cutover
1. **Pre-flight Checks**:
   - Stage 1 and Stage 2 active and healthy.
   - Web frontend built and typechecked (`npm run typecheck && npm run build`).
   - SSE event stream (`/api/events`) and Operator Command API (`/api/operator/command`) verified.
2. **Cutover Execution**:
   - Set `cutover.channels.web.enabled = true`.
3. **Observation Window**:
   - Real-time event stream and approval action verification.

---

## 3. Rollback Procedure

If any error, latency, or semantic discrepancy exceeds configured thresholds during an observation window:
1. Revert the specific channel cutover flag (e.g. `cutover.channels.telegram.enabled = false`).
2. Traffic immediately falls back to shadow / legacy mode.
3. Durable database records, memory files, and generated media are strictly preserved.

---

## 4. Guarded Legacy Retirement Checklist

Before removing or deprecating any legacy entry path or adapter:
- [ ] Gate 1: **Zero Callers**: Static scan and runtime inventory prove zero callers remain.
- [ ] Gate 2: **Semantic Parity**: Shadow comparisons show 100% equivalent outcomes.
- [ ] Gate 3: **Data Migration**: Reconciliation confirms all historical sessions/records migrated.
- [ ] Gate 4: **Rollback Artifact**: Backup and rollback artifacts are tested and accessible.
- [ ] Gate 5: **Test Suite**: Broad test suite passes 100%.
- [ ] Gate 6: **Observation Window**: Production observation period completed with zero incidents.
- [ ] Gate 7: **Release Record**: Release authorization signed off.
- [ ] **Data Retention Confirmed**: Historical databases, sessions, and media assets are permanently retained.
