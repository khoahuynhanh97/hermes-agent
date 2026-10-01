# Hermes Project — Simple Current-State Audit

**Date:** 2026-10-01  
**Target:** Hermes Agent Repository (Upstream Agent + `hermes_personal` Rearchitecture Layer)  
**Output Path:** `reports/2026-10-01-hermes-simple-audit.md`

---

## 1. Main Features

Hermes provides a dual-layer AI agent system: a **general-purpose autonomous AI agent core** (upstream Hermes) and a **governed personal agent & media factory layer** (`hermes_personal`).

### 1.1 Multi-Platform Conversational Agent Core (Upstream)
* **What it does:** Runs an LLM agent loop with prompt caching, dynamic tool execution (terminal, file operations, web browsing, Python code execution), session management, and subagent delegation across 20+ messaging platforms (Telegram, Discord, Slack, WhatsApp, Signal, Matrix, Webhooks, etc.), a React Ink TUI (`hermes --tui`), and an interactive CLI (`hermes`).
* **Problem it solves:** Eliminates platform lock-in, providing a unified AI assistant accessible from any chat platform, terminal, or desktop interface.
* **Status:** Complete & production-hardened upstream.

### 1.2 Unified Wire Contract & Turn Service (`hermes_personal`)
* **What it does:** Normalizes heterogeneous platform inputs into a canonical wire contract (`AgentTurnRequest`) processed by `HermesTurnService`, yielding standardized real-time streamed and persisted events (`AgentEvent`).
* **Problem it solves:** Prevents fragmented agent brains across different ingress channels (Telegram, Web API, Omni) by funneling all requests through one single-turn orchestration layer.
* **Status:** Complete (MVP_DONE); backed by SQLite durable event persistence.

### 1.3 Product Intelligence → AI Video Factory (`hermes_personal/product_video`)
* **What it does:** End-to-end media production pipeline: automated product research → resource pack creation → candidate generation → scene planning & storyboard layout → multi-model AI video generation (Kling, Wan, Hunyuan, Minimax, Google Flow) → automated Quality Control (QC scoring/validation) → final export packaging.
* **Problem it solves:** Automates high-volume, repeatable commercial product video production while enforcing mandatory Human-In-The-Loop (HITL) approval gates at critical production milestones (Product Lock, Brief, Scene Plan, Storyboard, Final Export).
* **Status:** Core workflows and deterministic/MCP adapters complete (MVP_DONE); live paid provider automation (e.g., Google Flow page automation) partially verified.

### 1.4 Governed Learning & Knowledge Base (`hermes_personal/learning`)
* **What it does:** Captures grounded knowledge, source artifacts, and conversion structures (`/hoc`, `/hoc-cta`) into a candidate store. Candidates undergo evaluation and HITL approval before being promoted into durable knowledge memories or published as skills.
* **Problem it solves:** Prevents AI hallucination and ungrounded memory drift by requiring strict source grounding and explicit owner review before updating agent behavior or skills.
* **Status:** Complete (MVP_DONE).

### 1.5 Personal Memos (`hermes_personal/memos`)
* **What it does:** Fast note-taking and lookup system (`/memo`) organizing quick thoughts using group categories and hashtags (`#tag`), kept strictly separate from the formal Knowledge Base.
* **Problem it solves:** Allows instant, lightweight note capture without polluting the structured knowledge retrieval engine.
* **Status:** Complete (MVP_DONE).

### 1.6 Durable Workflow Engine & Outbox Dispatcher (`hermes_personal/workflows`)
* **What it does:** In-process asynchronous task orchestrator and durable transactional outbox backed by SQLite. Features task leasing, heartbeat renewal, exponential backoff retries, poison message quarantine, and cost/budget authorization guards (`BudgetEngine`).
* **Problem it solves:** Guarantees reliable asynchronous execution and at-least-once delivery without requiring heavyweight external message brokers (such as RabbitMQ, Kafka, or Redis).
* **Status:** Complete (MVP_DONE).

### 1.7 Runtime Supervisor & Ingress APIs (`hermes_personal/runtime`, `hermes_personal/api`)
* **What it does:** Provides a single unified startup process (`hermes start`), FastAPI application endpoints (`/api/turn`, `/api/omni/turn`, `/api/events/replay`, `/api/operator/command`), health/readiness probes, and child process lifecycle management.
* **Problem it solves:** Simplifies deployment, operations, and monitoring on single-machine environments (including native Windows).
* **Status:** Complete (MVP_DONE).

---

## 2. Main Modules

The repository is structured into distinct, modular subsystems:

```
hermes-agent/
├── agent/ + run_agent.py          # Core upstream LLM agent loop & provider adapters
├── gateway/                       # Upstream multi-platform messaging adapters
├── tools/ + toolsets.py           # Auto-discovered tool execution backends
├── plugins/                       # Memory, context engine, model provider plugins
├── cron/                          # Scheduler and periodic job runner
├── hermes_personal/               # Bounded rearchitecture overlay
│   ├── contracts/                 # Canonical schemas (Turn, Events, Operator, Capability)
│   ├── orchestration/             # HermesTurnService & UpstreamAgentAdapter
│   ├── application/ & api/        # FastAPI HTTP endpoints, SSE streaming, middleware
│   ├── gateway/                   # Ingress normalizers (Telegram / Chat to TurnRequest)
│   ├── storage/ & sessions/       # SQLite repositories & session management
│   ├── workflows/                 # WorkflowEngine, OutboxDispatcher, BudgetEngine
│   ├── product_video/ & product/  # Product Video Factory & Intelligence pipeline
│   ├── learning/                  # Governed Learning, candidate evaluation & promotion
│   ├── memos/                     # Personal Quick Memos & tag indexing
│   ├── capabilities/ & identity/  # Policy evaluator, owner isolation & budgets
│   └── runtime/                   # Process supervisor, readiness probes, startup
```

### Module Responsibilities & Connections

1. **Upstream Agent Core (`run_agent.py`, `agent/`, `tools/`)**
   * *Responsibility:* Executes LLM provider calls, maintains prompt-cached conversation context, dynamically evaluates tool calling, and drives tools across local/virtual environments.
   * *Connections:* Wrapped by `hermes_personal/orchestration/upstream_agent.py` as an execution engine.

2. **Personal Contracts (`hermes_personal/contracts/`)**
   * *Responsibility:* Defines immutable domain models: `AgentTurnRequest`, `AgentEvent`, `OperatorCommand`, `CapabilityPolicy`, and `Principal`.
   * *Connections:* Serves as the central interface contract used by API, Orchestration, Gateway, Workflows, and Video Factory.

3. **Orchestration (`hermes_personal/orchestration/`)**
   * *Responsibility:* Houses `HermesTurnService`, the single entry point for turns. Coordinates context injection (memos, knowledge), invokes the upstream agent adapter, and commits events to the database.
   * *Connections:* Receives requests from `application/` and `gateway/`; emits to `storage/` and `workflows/`.

4. **Application & HTTP API (`hermes_personal/application/`, `hermes_personal/api/`)**
   * *Responsibility:* Implements FastAPI HTTP routes (`/api/turn`, `/api/events/replay`, `/api/operator/command`), rate-limiting, request size guards (10MB), and SSE event streaming.
   * *Connections:* Translates external HTTP calls into `AgentTurnRequest` / `OperatorCommand` and queries `EventRepository`.

5. **Storage & Sessions (`hermes_personal/storage/`, `hermes_personal/sessions/`)**
   * *Responsibility:* Manages durable SQLite databases (`hermes_personal.db`), schema migrations, session tracking, and monotonic event cursor ordering.
   * *Connections:* Injected into all services requiring persistent state.

6. **Workflows & Outbox (`hermes_personal/workflows/`)**
   * *Responsibility:* State machine for long-running workflows, job lease recovery, policy-based cost reservations (`BudgetEngine`), and transactional outbox message dispatch.
   * *Connections:* Dispatches jobs for `product_video/`; publishes domain events via `orchestration/`.

7. **Product Video Factory (`hermes_personal/product_video/`, `hermes_personal/product/`)**
   * *Responsibility:* Drives the automated video production pipeline (research packs, scene plans, storyboard generation, MCP video generation tools, QC validation, and final export).
   * *Connections:* Runs as handlers on top of `workflows/`; connects to external rendering providers via MCP or local tools.

8. **Governed Learning & Memos (`hermes_personal/learning/`, `hermes_personal/memos/`)**
   * *Responsibility:* Handles grounded knowledge acquisition (`/hoc`), candidate review/promotion, and personal memo tagging (`/memo`).
   * *Connections:* Injected by `HermesTurnService` during turn context construction.

9. **Runtime & Supervisor (`hermes_personal/runtime/`)**
   * *Responsibility:* Coordinates boot sequence (`StartupCoordinator`), readiness probes, child subprocess monitoring (`Supervisor`), and graceful shutdowns.
   * *Connections:* Spawns and monitors the Gateway Server and FastAPI App server.

---

## 3. Main Workflows

### 3.1 Conversational Turn Workflow (User Input → Processing → Response)

```text
[User (Web / Telegram / Ingress)]
               │
               ▼
[Normalizer / Ingress Adapter]
   - Validates authentication & rate limit
   - Converts payload to canonical `AgentTurnRequest`
               │
               ▼
[HermesTurnService]
   - Loads session context & monotonic event sequence
   - Injects relevant memos & approved knowledge
   - Evaluates capability policies & budgets
               │
               ▼
[Upstream AIAgent Adapter]
   - Resolves prompt & cached context
   - Runs LLM inference loop
   - Executes authorized tools (terminal, browser, MCP, etc.)
               │
               ▼
[Event Publisher & SQLite Store]
   - Emits structured `AgentEvent` stream
   - Persists turn record to `EventRepository`
               │
               ▼
[Response to User / SSE Stream / Chat Ingress]
```

---

### 3.2 Product Video Factory Workflow (Research → Video → QC → Export)

```text
1. Product Research & Resource Pack
   - Ingest product URL / media / specs
   - Extract claims, features, target audience, visual assets
   - Generate Resource Pack (Status: `ready_to_lock`)
   - 🔒 [HITL Gate: Product Lock Approval]

2. Creative Planning (Scene Plan & Storyboard)
   - Generate creative brief and scene breakdown
   - 🔒 [HITL Gate: Scene Plan Approval]
   - Generate prompt templates & storyboard visual frames
   - 🔒 [HITL Gate: Storyboard Approval]

3. Video Generation & Worker Dispatch
   - Reserve capability budget in `BudgetEngine`
   - Dispatch generation jobs via SQLite Outbox (`pending` → `leased`)
   - Call generation backends via MCP adapters (Kling / Wan / Hunyuan / Minimax / Flow)
   - Checkpoint job IDs, poll status with deadline enforcement

4. Automated Quality Control (QC)
   - Evaluate video clips against QC rules (duration, resolution, audio sync, artifacting)
   - Generate QC scorecard (Pass / Conditional / Fail)

5. Final Export & Delivery
   - 🔒 [HITL Gate: Final Owner Approval]
   - Assemble final video manifest, metadata, and assets
   - Export packaged deliverable
```

---

### 3.3 Governed Knowledge & Learning Workflow (Input → Evaluation → Promotion)

```text
[User / Agent Media Observation]
               │
               ▼
[Knowledge Ingestion: `/hoc` or `/hoc-cta`]
   - Extracts structured facts, assertions, or conversion patterns
   - Anchors assertions directly to source artifacts (video clip, URL, transcript)
               │
               ▼
[Candidate Store (SQLite)]
   - Stored in pending candidate state (`status: candidate`)
   - Validates groundedness and source integrity
               │
               ▼
[Human-In-The-Loop (HITL) Review]
   - Owner inspects grounded candidate & diff
   - Approve / Edit / Reject
               │
               ▼
[Promotion & Publishing]
   - Approved candidates promoted to durable Knowledge Memory
   - Optionally published as reusable agent Skill (`SKILL.md`)
               │
               ▼
[Runtime Retrieval]
   - Injected into subsequent relevant turns by `HermesTurnService`
```

---

## 4. Overall Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Ingress Layer                                  │
│   Web UI / Dashboard   │   Telegram / Chat Platforms   │   CLI / TUI        │
│   (FastAPI Endpoints)  │   (Gateway Normalizers)       │   (Direct Ingress) │
└───────────────────────┬───────────────────────────────┬─────────────────────┘
                        │                               │
                        ▼                               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Core Orchestration Layer                           │
│                          (hermes_personal/orchestration)                    │
│                                                                             │
│                            HermesTurnService                                │
│          ┌─────────────────────────┴─────────────────────────┐              │
│          ▼                                                   ▼              │
│  [UpstreamAgentAdapter]                              [Policy & Budget Guard]│
│          │                                                   │              │
│          ▼                                                   ▼              │
│   AIAgent (LLM Loop) ───► Tools / MCP Adapters ◄──── Outbox Dispatcher      │
└──────────┬───────────────────────────────────────────────────┬──────────────┘
           │                                                   │
           ▼                                                   ▼
┌──────────────────────────────────────┐   ┌──────────────────────────────────┐
│           Feature Modules            │   │      Workflow & Job Engine       │
│  • Personal Memos (/memo)            │   │  • Workflow State Machine        │
│  • Governed Learning (/hoc)          │   │  • Transactional Outbox          │
│  • Product Video Factory             │   │  • Lease Management & Backoff    │
│    (Research → Scene → Video → QC)   │   │  • HITL Approval Gates           │
└──────────────────┬───────────────────┘   └──────────────────┬───────────────┘
                   │                                          │
                   ▼                                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Persistence & External Providers                        │
│                                                                             │
│   SQLite Database (hermes_personal.db)                                      │
│   • Sessions, Events & Turns    • Workflows & Outbox Jobs                   │
│   • Budget Reservations         • Memos & Knowledge Base                    │
│                                                                             │
│   External / Edge Providers                                                 │
│   • LLM Providers (OpenRouter, Anthropic, OpenAI, GMI)                      │
│   • Video AI MCPs (Kling, Wan, Minimax, Hunyuan, Google Flow)               │
│   • Local Filesystem (Artifacts, Video Clips, Manifests)                    │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Current State Summary

### 5.1 What Hermes Currently Does
Hermes functions as an extensible personal AI agent combined with an automated media production factory. It accepts commands across multiple chat platforms, CLI, and Web APIs, processes conversational turns with unified prompt-caching and tool execution, manages tagged personal memos, captures source-grounded knowledge with human oversight, and drives a structured, multi-stage AI video creation pipeline with strict HITL approval gates.

### 5.2 Main Modules
* **`agent/` & `run_agent.py`:** Core upstream LLM execution loop and tool framework.
* **`hermes_personal/contracts/` & `orchestration/`:** Channel-neutral `AgentTurnRequest` / `AgentEvent` contracts and `HermesTurnService`.
* **`hermes_personal/application/` & `api/`:** FastAPI web server, SSE streams, middleware guards, and operator endpoints.
* **`hermes_personal/workflows/`:** SQLite-backed workflow state machine, transactional outbox, budget guards, and worker lease manager.
* **`hermes_personal/product_video/`:** Product research pack builder, scene/storyboard planner, AI video generation adapters, and QC evaluator.
* **`hermes_personal/learning/` & `memos/`:** Grounded knowledge capture (`/hoc`) and quick memo tagging (`/memo`).
* **`hermes_personal/storage/` & `runtime/`:** SQLite repositories, process supervisor, and startup lifecycle coordinator.

### 5.3 Main Workflows
1. **Conversational Turn:** Ingress Normalizer → `HermesTurnService` → Capability Guard → `AIAgent` → Tool Execution → SQLite Event Commit → Streamed Output.
2. **Product Video Factory:** Product Ingestion → Research Pack (HITL Lock) → Scene/Storyboard Plan (HITL Lock) → Outbox Job Dispatch → AI Video Generation → QC Scoring → Final Export (HITL Lock).
3. **Governed Learning:** Media Ingestion (`/hoc`) → Grounded Candidate Extraction → Owner Review/Approval → Promotion to Knowledge Memory / Published Skill.

### 5.4 Parts That Appear Complete
* **Core Turn Pipeline:** `HermesTurnService`, `UpstreamAgentAdapter`, and SQLite event streaming.
* **Durable Persistence:** Full SQLite transactional persistence for events, turn sequences, outbox messages, workflows, budgets, and memos.
* **Outbox Safety & Delivery:** Worker leasing, monotonic retries, lease renewal, and poison message quarantine.
* **Governed Learning & Memos:** Candidate generation, source artifact anchoring, HITL approval flows, and `#tag` memo queries.
* **Product Video Architecture:** Spec-compliant state machine, MCP adapter contracts, deterministic fakes, QC scorecarding, and export schemas.
* **Runtime & Operational Safety:** Rate-limiting middleware, request body size limits (10MB), supervisor child process readiness probes, and graceful shutdowns.
* **Test Suite:** Comprehensive test coverage across all `hermes_personal` modules (1100+ passing tests).

### 5.5 Parts That Appear Incomplete or Unclear
* **Live Paid Video Provider Execution at Scale:** While MCP adapters and deterministic simulation contracts are complete, live browser-automated video generation (e.g. Google Flow via Playwright) has single-clip verification but has not undergone high-volume automated paid production runs.
* **Distributed Scaling Architecture:** The system is explicitly built for single-machine SQLite durability. Distributed message brokers (RabbitMQ, Kafka, Redis) and distributed multi-worker pools are deferred and intentionally omitted from the current design.
* **Multi-Process Optional Runners:** In the local development topology, optional background runners (`mcp_runner`, `worker`, `telegram_runner`) are disabled by default in favor of the unified in-process supervisor, leaving standalone daemon deployments as an optional operational setup.
