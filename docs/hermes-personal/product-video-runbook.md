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

---

## 5. Single-Machine Operator Runbook & Execution

### Minimum Configuration & Prerequisites
- Environment setting: `HERMES_HOME` pointing to runtime directory (default `~/.hermes`).
- SQLite storage: persistent database at `$env:HERMES_HOME/hermes.db`.
- Default budget policy: initialized via `init_default_engine(BudgetPolicy(max_total=1000, per_channel={"video_factory": 500, "product_intelligence": 500}))`.

### Starting the Pipeline Producer & Worker
1. **User Entry Point (`POST /api/operator/command`)**:
   ```bash
   curl -X POST http://127.0.0.1:8642/api/operator/command \
     -H "Authorization: Bearer $HERMES_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "owner_id": "local-owner",
       "command_type": "start_workflow",
       "target_id": "wf_prod_01",
       "expected_version": 0,
       "payload": {
         "product_name": "TikTok Wireless Earbuds",
         "keywords": ["bluetooth", "anc"],
         "pdp_url": "https://shop.tiktok.com/view/product/17294829104"
       }
     }'
   ```
2. **Durable Worker Process**:
   ```powershell
   # Explicit fake mode for offline verification
   $env:HERMES_PROVIDER_MODE = "fake"
   uv run python -m hermes_personal.workflows.worker --db-path ~/.hermes/hermes.db --poll-interval 1.0
   ```
   The `durable_worker` process automatically binds `job.dispatch` topic handlers to `ProductVideoJobHandlers` via `create_product_video_topic_handlers`.

### Operator Approval, Status Inspection & Progression
- **Check Workflow Status & Artifacts**:
  ```bash
  curl http://127.0.0.1:8642/api/artifacts/{artifact_id}?owner_id=local-owner
  ```
- **Data Progression Chain & HITL Approvals**:
  - `start_workflow` -> `product_video.research` -> HITL `AwaitingProductLock`
  - `approve` `AwaitingProductLock` -> `product_video.resource_pack` -> `product_video.lock` -> `product_video.creative_brief` -> HITL `AwaitingBriefApproval`
  - `approve` `AwaitingBriefApproval` -> `product_video.scene_plan` -> HITL `AwaitingSceneApproval`
  - `approve` `AwaitingSceneApproval` -> `product_video.storyboard` -> HITL `AwaitingStoryboardApproval`
  - `approve` `AwaitingStoryboardApproval` -> `product_video.render` -> HITL `AwaitingFinalApproval`
  - `approve` `AwaitingFinalApproval` -> `product_video.export` -> `COMPLETED`
- **Operator HITL Approval & Workflow Progression (`POST /api/operator/command`)**:
  ```bash
  curl -X POST http://127.0.0.1:8642/api/operator/command \
    -H "Authorization: Bearer $HERMES_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "owner_id": "local-owner",
      "command_type": "approve",
      "target_id": "req_approval_id_or_wf_id",
      "expected_version": 1
    }'
  ```
  `approve` validates approval request state, verifies `expected_version`, marks request `APPROVED`, validates state transition via `transition()`, enqueues the next outbox job, and commits atomically in SQLite.

### MCP Tool & Live Provider Resolution Matrix

| Workflow Stage | Job Name | Live Adapter | Dispatched MCP / Local Wire Tool | Fallback / Behavior in `provider_mode="configured"` |
|---|---|---|---|---|
| 1. Market Research | `product_video.research` | `MCPProductIntelligenceAdapter` | `mcp__product_intelligence__research_product` / `product_intelligence_research` / `web_search` | Fails closed with `MISSING_PROVIDER_CONFIG` |
| 2. Resource Pack Draft | `product_video.resource_pack` | `MCPProductIntelligenceAdapter` | `mcp__product_intelligence__build_resource_pack` / `product_intelligence_build_resource_pack` | Uses deterministic build if tool unmapped |
| 3. Lock Resource Pack | `product_video.lock` | `MCPProductIntelligenceAdapter` | `mcp__product_intelligence__lock_resource_pack` / `product_intelligence_lock_resource_pack` | Uses deterministic lock if tool unmapped |
| 4. Creative Brief | `product_video.creative_brief` | `MCPVideoFactoryAdapter` | `mcp__video_factory__create_brief` / `video_factory_create_brief` | Fails closed with `MISSING_PROVIDER_CONFIG` |
| 5. Scene Plan | `product_video.scene_plan` | `MCPVideoFactoryAdapter` | `mcp__video_factory__create_scene_plan` / `video_factory_create_scene_plan` | Fails closed with `MISSING_PROVIDER_CONFIG` |
| 6. Storyboard | `product_video.storyboard` | `MCPVideoFactoryAdapter` | `mcp__video_factory__create_storyboard` / `video_factory_create_storyboard` | Fails closed with `MISSING_PROVIDER_CONFIG` |
| 7. GPU Render | `product_video.render` | `MCPVideoFactoryAdapter` | `mcp__video_factory__render` / `video_factory_render` / `video_generate` | Polls `mcp__video_factory__get_job_status` if async; fails closed if unconfigured |
| 8. MP4 Export | `product_video.export` | `MCPVideoFactoryAdapter` | `mcp__video_factory__export` / `video_factory_export` | Fails closed with `MISSING_PROVIDER_CONFIG` |

---

### Sample Configuration (`config.yaml`) & Secrets

In `~/.hermes/config.yaml` (behavioral settings only; no secrets):
```yaml
# ~/.hermes/config.yaml
mcp_servers:
  product_intelligence:
    command: "python"
    args: ["-m", "mcp_servers.product_intelligence"]
    env:
      API_ENDPOINT: "https://api.product-intel.local/v1"
  video_factory:
    command: "python"
    args: ["-m", "mcp_servers.video_factory"]
    env:
      GPU_ENDPOINT: "https://gpu-render.local/v1"

# Provider mode for background worker: 'configured' (live MCP) or 'fake' (offline test)
provider_mode: "configured"
```

In `~/.hermes/.env` (credentials only):
```bash
# Secrets are loaded into environment variables; never checked into git
HERMES_API_KEY=hermes_operator_secret_token_here
VIDEO_FACTORY_API_KEY=vf_live_secret_key_here
PRODUCT_INTELLIGENCE_API_KEY=pi_live_secret_key_here
```

---

### Verification Tiers & Readiness Status

1. **Offline Verified (100% Passing)**:
   - Full 9-stage data progression, 5 HITL gates, optimistic concurrency (`expected_version`), atomic SQLite transactions, and outbox claim/lease/retry/quarantine mechanisms.
   - Tested and verified with 84 targeted tests and 609 personal package tests without calling paid external APIs.

2. **Live Wired but Unverified**:
   - `MCPProductIntelligenceAdapter` and `MCPVideoFactoryAdapter` dynamically probe `ToolRegistry` for registered tools, map payloads, handle async job polling, and forward product/resource pack IDs across all stages.
   - Fails closed with explicit, actionable error message if required MCP tools are missing in `configured` mode.

3. **Live Verified**:
   - Requires user to launch live MCP servers with external credentials and run a complete real-world video generation.

---

### Starting the Live Worker

```powershell
# Run durable background worker in live configured mode
uv run python -m hermes_personal.workflows.worker --db-path ~/.hermes/hermes.db --poll-interval 1.0 --provider-mode configured
```
