# Runtime Removal & Consolidation Candidates

**Audit Scope**: ARCH-G2 Canonical Ownership Audit  
**Target Profile**: `PERSONAL_HAPPY_PATH_V1`  
**Core Invariant**: `run_agent.AIAgent` is the **only** canonical conversational brain. Upstream CLI, gateway, and TUI remain the primary ingress surfaces.

---

## 1. Overview of Identified Duplication & Packaging Gaps

The audit identified two primary categories requiring consolidation or packaging remediation:
1. **`RUNTIME_DUPLICATE_CANDIDATE`**: Layers in `hermes_personal` that build a parallel turn-service, second gateway, and parallel capability routing abstraction on top of or alongside upstream Hermes.
2. **`PACKAGING_ORPHAN`**: Standalone capability modules under `src/hermes` that are not discovered in `pyproject.toml` package finding, functioning effectively as out-of-band MCP servers rather than core library code.

---

## 2. Detailed Candidate Breakdown

### A. Parallel Conversational Turn Service & Second Gateway

#### 1. `hermes_personal.orchestration.turn_service.HermesTurnService`
- **File**: [`hermes_personal/orchestration/turn_service.py`](file:///d:/work/hermes-upstream-rearchitecture/hermes_personal/orchestration/turn_service.py#L74-L324)
- **Current Role**: Receives `AgentTurnRequest`, verifies policy, creates thread-worker tasks, streams `AgentEvent` objects over async queues.
- **Upstream Overlap**: Upstream `run_agent.AIAgent` ([`run_agent.py`](file:///d:/work/hermes-upstream-rearchitecture/run_agent.py#L1-L250)) already owns multi-turn conversation loops, prompt caching, tool invocation, and streaming callbacks.
- **Production Caller**: Called by `hermes_personal.runtime.gateway_server` (`/api/turn`). Not called by standard upstream CLI (`cli.py`) or messaging gateway (`gateway/run.py`).
- **Classification**: `RUNTIME_DUPLICATE_CANDIDATE`
- **Consolidation Rationale**: A second general turn service adds latency, complex thread-to-async event queues, and violates the "narrow core waist" invariant. Ingress channels should route directly into `AIAgent`.

#### 2. `hermes_personal.orchestration.upstream_agent.UpstreamAIAgentAdapter`
- **File**: [`hermes_personal/orchestration/upstream_agent.py`](file:///d:/work/hermes-upstream-rearchitecture/hermes_personal/orchestration/upstream_agent.py#L46-L100)
- **Current Role**: Spawns a background `Thread` running `AIAgent.run_conversation`, queues text deltas in a bounded `Queue`, and yields `AgentOutput` events.
- **Upstream Overlap**: Direct caller wrapper around `AIAgent`.
- **Production Caller**: `hermes_personal.runtime.gateway_server:create_configured_agent`.
- **Classification**: `RUNTIME_DUPLICATE_CANDIDATE`
- **Consolidation Rationale**: If ingress platforms interact directly with `AIAgent` or standard Hermes gateway sessions, this synthetic queue adapter is redundant.

#### 3. `hermes_personal.runtime.gateway_server` (FastAPI Server)
- **File**: [`hermes_personal/runtime/gateway_server.py`](file:///d:/work/hermes-upstream-rearchitecture/hermes_personal/runtime/gateway_server.py#L1-L426)
- **Current Role**: Exposes FastAPI endpoints (`/api/turn`, `/api/events`, `/healthz`).
- **Upstream Overlap**: Duplicates upstream `gateway/run.py` (which already manages WebSocket / RPC / platform ingress for Telegram, Discord, Slack, etc.) and `mcp_serve.py`. Upstream Telegram adapter exists under `plugins/platforms/telegram/**`.
- **Classification**: `RUNTIME_DUPLICATE_CANDIDATE`
- **Consolidation Rationale**: Upstream Hermes already has gateway platforms and CLI. Adding an extra HTTP turn server is only needed if third-party HTTP clients require `/api/turn`; otherwise, messaging platforms belong in `gateway/platforms/`.

---

### B. Parallel Tool Registry & Policy Engine

#### 4. `hermes_personal.capabilities.service.CapabilityCatalogService` & `policy.CapabilityPolicyEngine`
- **Files**: 
  - [`hermes_personal/capabilities/service.py`](file:///d:/work/hermes-upstream-rearchitecture/hermes_personal/capabilities/service.py)
  - [`hermes_personal/capabilities/policy.py`](file:///d:/work/hermes-upstream-rearchitecture/hermes_personal/capabilities/policy.py)
- **Current Role**: Implements capability discovery, dynamic manifest generation, snapshot pointers, and policy checks.
- **Upstream Overlap**: Upstream `tools/registry.py` ([`tools/registry.py`](file:///d:/work/hermes-upstream-rearchitecture/tools/registry.py)), `model_tools.py`, and `toolsets.py` already manage tool registration, service-gated tools (`check_fn`), and enabled toolset filtering.
- **Classification**: `RUNTIME_DUPLICATE_CANDIDATE`
- **Consolidation Rationale**: Standard model tools and MCP servers connect cleanly through `tools/registry.py` and upstream `mcp_client`. Having a parallel capability catalog creates dual maintenance.

---

### C. Packaging Orphans (Src Layout Gap)

#### 5. `src/hermes` (Video Factory Core & MCP Server)
- **Directory**: [`src/hermes/`](file:///d:/work/hermes-upstream-rearchitecture/src/hermes)
- **Files**:
  - `src/hermes/domain/video_factory.py`
  - `src/hermes/application/video_factory_service.py`
  - `src/hermes/infrastructure/clients/vertex_veo_client.py`
  - `src/hermes/mcp/video_factory/server.py`
- **Packaging Gap**: `pyproject.toml` defines `packages.find.include` without `src/hermes`. Importing `src/hermes` in standard Python without `PYTHONPATH=src;` fails.
- **Runtime Evidence**: Confirmed operational when executed as a standalone subprocess (`uv run python src/hermes/mcp/video_factory/server.py`).
- **Classification**: `PACKAGING_ORPHAN` / `PORT_TO_MCP_EDGE`
- **Consolidation Rationale**: Video Factory is designed as an **edge MCP server** or standalone toolset. It should remain an independent MCP server package or be registered in the MCP catalog, communicating with `AIAgent` via standard stdio JSON-RPC.

---

## 3. Consolidation Matrix Summary

| Module / Component | Classification | Immediate Action | Target Disposition |
| :--- | :--- | :--- | :--- |
| `HermesTurnService` | `RUNTIME_DUPLICATE_CANDIDATE` | Retain for test suite compatibility | Route ingress directly to `run_agent.AIAgent` |
| `UpstreamAIAgentAdapter` | `RUNTIME_DUPLICATE_CANDIDATE` | Retain for test suite compatibility | Stream directly from `AIAgent` callbacks |
| `gateway_server.py` | `RUNTIME_DUPLICATE_CANDIDATE` | Keep as optional HTTP daemon | Consolidate ingress into `gateway/` |
| `CapabilityCatalogService` | `RUNTIME_DUPLICATE_CANDIDATE` | Retain snapshot pointer functionality | Use upstream `tools/registry.py` |
| `src/hermes/**` | `PACKAGING_ORPHAN` | Maintain standalone stdio entry point | Standardize as MCP server tool edge |
