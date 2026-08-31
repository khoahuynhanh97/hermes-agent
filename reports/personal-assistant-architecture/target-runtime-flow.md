# Target Runtime Flow

**Architecture Profile**: `PERSONAL_HAPPY_PATH_V1`  
**Core Invariant**: Single Canonical Brain (`run_agent.AIAgent`), Edge Capabilities (Knowledge Base, Video Factory), Durable Outbox for async job recovery.

---

## 1. Unified Architecture Topology

```mermaid
flowchart TD
    subgraph Ingress["Ingress Surfaces (Canonical)"]
        CLI["Hermes CLI (cli.py)"]
        TG["Telegram Gateway (plugins/platforms/telegram/**)"]
        TUI["TUI / Desktop (ui-tui / Electron)"]
    end

    subgraph Core["Canonical Brain (Narrow Waist)"]
        Agent["AIAgent (run_agent.py)"]
        PromptCache[("Prompt Cache (Byte-Stable System Prompt)")]
        SessionStore[("SQLite SessionDB (hermes_state.py)")]
    end

    subgraph EdgeCaps["Edge Capabilities & Tools"]
        KB_Skill["Knowledge Base Skill (hermes-personal-knowledge-learning)"]
        KB_Repo[("SQLite Learning DB (hermes_personal/learning)")]
        
        VF_Skill["Video Factory Skill (hermes-personal-product-video-production)"]
        VF_MCP["Video Factory FastMCP Server (src/hermes/mcp/video_factory/server.py)"]
        PI_MCP["Product Intelligence MCP Server (product_scout/mcp_server.py)"]
        
        VertexVeo["Google Vertex AI Veo (predictLongRunning)"]
    end

    subgraph Durable["Durable State & HITL"]
        Workflows[("SQLite Durable Outbox & Jobs (hermes_personal/workflows)")]
        HITL["Operator Approval Gate (CLI / TG Buttons)"]
    end

    CLI --> Agent
    TG --> Agent
    TUI --> Agent

    Agent <--> PromptCache
    Agent <--> SessionStore

    Agent -- "1. Skill Instruction" --> KB_Skill
    KB_Skill <--> KB_Repo
    KB_Skill -- "Candidate Promotion" --> HITL

    Agent -- "2. Skill Instruction" --> VF_Skill
    VF_Skill -- "Stdio MCP JSON-RPC" --> VF_MCP
    VF_Skill -- "Stdio MCP JSON-RPC" --> PI_MCP

    VF_MCP <--> Workflows
    VF_MCP -- "5-Gate Approvals" --> HITL
    VF_MCP -- "Async Render" --> VertexVeo
```

---

## 2. End-to-End Turn Execution Flow

### Step 1: User Ingress
1. User sends message via **Telegram Bot** or **Interactive CLI** (`"Tạo video quảng cáo cho sản phẩm X"`).
2. The channel adapter normalizes the message into the standard conversation turn format.
3. The turn is dispatched directly to `run_agent.AIAgent.run_conversation()`.

### Step 2: Canonical Brain & Skill Activation
1. `AIAgent` checks active conversation history and stable system prompt (preserving byte-exact prompt cache).
2. Agent reads matching skill: [`hermes-personal-product-video-production`](file:///d:/work/hermes-upstream-rearchitecture/.agents/skills/hermes-personal-product-video-production/SKILL.md).
3. Skill instructs Agent on the 5-Gate HITL procedure and required MCP tool calls.

### Step 3: Edge MCP Tool Execution
1. **Gate 1 (Product Research & Lock)**:
   - Agent calls PI MCP: `research_product` $
ightarrow$ `build_resource_pack` $
ightarrow$ `lock_resource_pack`.
   - Result: Locked Resource Pack ID (e.g. `rp_vf_live_01`).
2. **Gate 2 (Creative Brief)**:
   - Agent calls VF MCP: `create_brief(product_id=...)`.
   - Operator approves Brief via interactive approval.
3. **Gate 3 (Scene Plan)**:
   - Agent calls VF MCP: `create_scene_plan(scenes=[...])`.
   - Operator approves Scene Plan.
4. **Gate 4 (Storyboard)**:
   - Agent calls VF MCP: `create_storyboard(frames=[...])`.
   - Storyboard assets generated and approved.
5. **Gate 5 (Render & Deterministic Export)**:
   - Agent calls VF MCP: `render(storyboard_result=...)`.
   - VF submits asynchronous job to Vertex AI Veo (`predictLongRunning`).
   - Job is tracked durably in SQLite Outbox / Jobs table (`hermes_personal/workflows`).
   - Polling checks completion $
ightarrow$ decodes inline Base64 video $
ightarrow$ saves local MP4 artifact.
   - Agent calls `export` $
ightarrow$ final MP4 delivered to Operator.

### Step 4: Governed Learning (Knowledge Base)
1. If Operator provides corrections or preferences during the turn:
   - Candidate is recorded in SQLite Learning DB (`hermes_personal/learning`).
   - Candidate remains in `PENDING` status until explicit Operator promotion.
   - Once approved, skill publisher updates local SKILL docs without breaking core prompt caches.

---

## 3. Architectural Invariants Preserved

1. **Sacred Prompt Caching**: No mid-turn tool injection, dynamic prompt restructuring, or synthetic role duplication.
2. **Narrow Core Waist**: Zero video rendering or knowledge database logic inside `run_agent.py`; capability lives entirely in MCP servers, skills, and plugins.
3. **Durable Single-Machine Safety**: SQLite transactions protect state against process crashes; render jobs survive restart.
4. **Zero Live Bypass**: All paid actions require explicit Operator HITL gate approvals.
