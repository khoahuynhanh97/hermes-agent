# Happy Path Gap Matrix

**Audit Scope**: ARCH-G2 Canonical Ownership Audit  
**Target Flow**: Product Intelligence $\rightarrow$ Video Factory $\rightarrow$ Knowledge Base Happy Path  
**Baseline Revision**: `b193b1d07e`

---

## 1. Capability Gap Summary

| Subsystem | Area | Current Status | Identified Gap | Severity | Required Remediation |
| :--- | :--- | :--- | :--- | :---: | :--- |
| **Video Factory** | MCP Registration | Verified via stdio subprocess | `AIAgent` configuration does not auto-mount `src/hermes/mcp/video_factory/server.py` in default `config.yaml` | **MEDIUM** | Add stdio MCP server entry to default `config.yaml` / MCP catalog |
| **Video Factory** | Provider Integration | Task 5 Google Vertex Veo Proven (`d4eeafc5bd`) | Live provider is implemented and proven; requires service-gated credentials in configuration. | **LOW** | Document credential setup in `docs/` |
| **Video Factory** | Packaging Layout | `src/hermes` layout | `src/hermes` is not in `pyproject.toml` package finding | **LOW** | Run as stdio MCP subprocess (clean decoupling) or add package inclusion |
| **Knowledge Base** | Agent Skill Bridge | Governed learning module tested | `AIAgent` requires governed skill `hermes-personal-knowledge-learning` active in `skills/` | **LOW** | Ensure skill is linked in default active skills directory |
| **HITL Approvals** | Interactive Resumption | Handled in domain tests | CLI/Telegram interactive approval buttons need direct callback mapping to active workflow IDs | **MEDIUM** | Connect Telegram inline keyboard approval callback to Outbox/Workflow engine |
| **Durable Outbox** | Async Job Recovery | SQLite outbox implemented | Outbox worker needs to run in background ticker for long-running poll recovery on restart | **LOW** | Wire outbox ticker into `hermes start` supervisor |

---

## 2. Detailed Gap Analysis

### Gap 1: MCP Server Auto-Configuration
- **Description**: FastMCP servers (`src/hermes/mcp/video_factory/server.py` and `Product-Intelligence/product_scout/mcp_server.py`) run as standalone stdio processes. `AIAgent` uses `mcp_client` to connect to configured servers.
- **Current Behavior**: Subprocesses can be launched manually or tested over `stdio_client`, but standard `~/.hermes/config.yaml` lacks the pre-configured stdio command block.
- **Fix**: Provide canonical MCP client configuration in `~/.hermes/config.yaml`:
  ```yaml
  mcp_servers:
    video_factory:
      command: "uv"
      args: ["run", "--directory", ".", "python", "src/hermes/mcp/video_factory/server.py"]
      env:
        PYTHONPATH: "src;"
    product_intelligence:
      command: "uv"
      args: ["run", "--directory", "../Personal/Product-Intelligence", "python", "product_scout/mcp_server.py"]
  ```

### Gap 2: Telegram HITL Button Callback to Workflow Engine
- **Description**: When `AIAgent` or a skill creates a pending approval (e.g. Creative Brief review), the Telegram platform adapter (`plugins/platforms/telegram**`) renders inline buttons.
- **Current Behavior**: Approval callbacks update message state; must durably unblock the waiting workflow step in `hermes_personal.workflows.engine`.
- **Fix**: Ensure `handle_callback_query` in Telegram platform dispatches approval events to `SQLiteDurableOutbox`.

---

## 3. Verification & Compliance
- **Offline Safety**: All gaps can be remediated and verified using temporary SQLite databases and mock MCP stdio responses.
- **No Core Breakage**: None of the required remediations require modifying `run_agent.AIAgent` conversational internals.
