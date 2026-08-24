# Product-To-Video Production Pipeline: Architecture & Operator Runbook

## 1. Overview
The Product Intelligence to Video Factory (PI-to-VF) pipeline orchestrates automated video generation from initial product links (such as TikTok Shop, Amazon, or Shopify PDPs) to finished high-definition export formats.

The pipeline traverses a deterministic **14-state workflow** protected by **5 Human-In-The-Loop (HITL) approval gates**, robust budget controls, and full crash-restart recovery.

---

## 2. 14-State Workflow & 5 HITL Approval Matrix

| Step | Workflow State | State Type | Action / Trigger | Human In The Loop (HITL) Gate |
|---|---|---|---|---|
| 1 | `idle` | Initial | Pipeline initialized | - |
| 2 | `researching` | Automated | Market & PDP research | - |
| 3 | `AwaitingProductLock` | HITL Gate 1 | Pauses for product attributes lock | **Web Portal Approval** |
| 4 | `building_resource_pack` | Automated | Compiles assets & scenes | - |
| 5 | `creating_brief` | Automated | Generates creative brief | - |
| 6 | `AwaitingBriefApproval` | HITL Gate 2 | Pauses for script & angle approval | **CLI / Chat Approval** |
| 7 | `creating_scene_plan` | Automated | Decomposes script into scenes | - |
| 8 | `AwaitingSceneApproval` | HITL Gate 3 | Pauses for scene layout review | **Web Portal Approval** |
| 9 | `creating_storyboard` | Automated | Generates storyboard frames | - |
| 10 | `AwaitingStoryboardApproval` | HITL Gate 4 | Pauses for frame approval | **Telegram Channel Approval** |
| 11 | `rendering` | Automated | GPU-accelerated video rendering | - |
| 12 | `AwaitingFinalApproval` | HITL Gate 5 | Pauses for final video review | **Telegram Channel Approval** |
| 13 | `exporting` | Automated | Encoding to MP4 / TikTok specs | - |
| 14 | `completed` | Terminal | Artifact delivered | - |

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
   - Workflow state and command execution history are persisted in SQLite. When workers crash, restart, or failover, pipelines resume exactly from the persisted state without duplicate paid side-effects.

---

## 4. Operator Commands & Troubleshooting

### Resuming a Stalled Workflow
```python
from hermes_personal.product_video.handlers import ProductVideoJobHandlers, JobContext
from hermes_personal.workflows.engine import WorkflowEngine

# Load engine and check current state
state, version = engine.get_workflow_state("wf_12345")
print(f"Current State: {state}, Version: {version}")

# Replay job safely with idempotency key
ctx = JobContext(workflow_id="wf_12345", job_id="job_retry", expected_version=version, idempotency_key="idemp_retry_1")
handlers = ProductVideoJobHandlers(workflow_engine=engine)
result = handlers.render_job(ctx, "story_ref_current")
```

### Checking Legacy Data Reconciliation
```bash
uv run pytest tests/hermes_personal/migration/test_reconciliation.py -v
```
