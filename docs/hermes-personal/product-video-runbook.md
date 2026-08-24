# Product-To-Video Production Pipeline: Architecture & Operator Runbook

## 1. Overview
The Product Intelligence to Video Factory (PI-to-VF) pipeline orchestrates automated video generation from initial product links (such as TikTok Shop, Amazon, or Shopify PDPs) to finished high-definition export formats.

The pipeline traverses a deterministic **14-state workflow** protected by **5 Human-In-The-Loop (HITL) approval gates**, robust budget controls, and full crash-restart recovery.

---

## 2. 14-State Workflow & 5 HITL Approval Matrix

| Step | Workflow State | State Type | Action / Trigger | Human In The Loop (HITL) Gate |
|---|---|---|---|---|
| 1 | `idle` | Initial | Pipeline initialized via PDP URL | - |
| 2 | `researching` | Automated | Market & PDP research | - |
| 3 | `AwaitingProductLock` | HITL Gate 1 | Pauses for product attributes lock | **Web Portal Approval** |
| 4 | `building_resource_pack` | Automated | Compiles assets & scenes | - |
| 5 | `creating_brief` | Automated | Generates creative brief ($5 budget) | - |
| 6 | `AwaitingBriefApproval` | HITL Gate 2 | Pauses for script & angle approval | **CLI / Chat Approval** |
| 7 | `creating_scene_plan` | Automated | Decomposes script into scenes ($5 budget) | - |
| 8 | `AwaitingSceneApproval` | HITL Gate 3 | Pauses for scene layout review | **Web Portal Approval** |
| 9 | `creating_storyboard` | Automated | Generates storyboard frames ($10 budget) | - |
| 10 | `AwaitingStoryboardApproval` | HITL Gate 4 | Pauses for frame approval | **Telegram Channel Approval** |
| 11 | `rendering` | Automated | GPU video rendering ($50 budget) | - |
| 12 | `AwaitingFinalApproval` | HITL Gate 5 | Pauses for final video review | **Telegram Channel Approval** |
| 13 | `exporting` | Automated | Encoding to MP4 specs ($20 budget) | - |
| 14 | `completed` | Terminal | Artifact delivered (Total cost: $90) | - |

---

## 3. Safety Guarantees & Gate 5 Invariants

1. **Zero Live Network Calls in Tests**:
   - All tests run against deterministic local in-memory providers (`ProductIntelligenceClient` and `VideoFactoryClient`). No paid live LLM/GPU APIs are called during test execution.
2. **Strict HITL Gate Protection**:
   - In any of the 5 `Awaiting*` states, the handler enforces `0 client calls` and `0 budget reserved`, returning `HITL_APPROVAL_REQUIRED` until an explicit human approval command transitions the state.
3. **Optimistic Concurrency & Version Invalidation**:
   - Modifying upstream assets increments the aggregate version. Stale approvals or outdated jobs referencing older versions are rejected immediately with `VERSION_CONFLICT`.
4. **Budget Reservation & Failure Release**:
   - Budgets are reserved prior to any paid GPU/generation calls and committed upon success. If a provider fails, the allocated budget is safely released back to the channel pool.
5. **Durable Crash-Restart Recovery**:
   - Workflow state and command execution history are persisted in SQLite. When workers crash, restart, or failover, pipelines resume exactly from the persisted state without duplicate paid side-effects across all 12 awaiting and executing states.

---

## 4. Verification Path Reconciliation
The current Gate 5 test suites are organized as follows:
- **Product Video E2E & Recovery**: `tests/hermes_personal/product_video/test_product_to_video_e2e.py`, `test_restart_recovery.py`, `test_handlers.py`, `test_job_handlers.py`, `test_capabilities.py`, `test_binding.py`.
- **Legacy Migration & Reconciliation**: `tests/hermes_personal/migration/test_reconciliation.py`.
- **Gate 4 Workflow & Job Engines**: `tests/hermes_personal/workflows/test_workflow_engine.py`, `test_repository.py`, `test_budgets.py`, `test_jobs.py`, `test_approvals.py`, `test_recovery.py`.
- **Capability Catalog & Policy**: `tests/hermes_personal/capabilities/`.

### Complete Verification Command:
```bash
uv run pytest tests/hermes_personal/product_video tests/hermes_personal/migration tests/hermes_personal/workflows tests/hermes_personal/capabilities -q
```
