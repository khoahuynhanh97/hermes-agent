# Hermes Personal (`hermes_personal`) Architecture

`hermes_personal` is a bounded domain layer built on top of the upstream Hermes Agent core. It provides channel-neutral turn contracts, durable SQLite-backed orchestration, an AI Product Video Factory, and a Governed Learning system.

---

## 1. Architectural Invariants

1. **Single Brain Invariant:** The upstream `run_agent.AIAgent` remains the sole reasoning and execution engine. `hermes_personal` wraps and orchestrates the turn lifecycle without introducing secondary LLM routers.
2. **Channel-Neutral Wire Contracts:** All ingress channels (Telegram, Web API, Omni) normalize their inputs into [`AgentTurnRequest`](contracts/turn.py) before dispatching to [`HermesTurnService`](orchestration/turn_service.py).
3. **Persist-Before-Yield & Monotonic Cursor:** Turn execution records and domain events (`AgentEvent`) are committed to SQLite before being yielded/streamed to clients, ensuring exact-once replay and durability.
4. **Durable In-Process Workflows (Zero External Broker):** Background task orchestration uses a transactional outbox pattern directly backed by SQLite (`workflow_outbox`) with atomic lease tokens, heartbeat renewals, and exponential backoff.
5. **Human-In-The-Loop (HITL) Governance:** High-value or metered operations (Product Lock, Brief, Scene Plan, Storyboard, Final Video Export, Knowledge Promotion) enforce explicit human approval gates and pre-allocated budget reservations (`BudgetEngine`).

---

## 2. Directory Layout & Module Responsibilities

```
hermes_personal/
├── contracts/          # Immutable domain models & wire contracts (Turn, Events, Operator, Capability)
├── orchestration/      # HermesTurnService, UpstreamAgentAdapter, EventRepository
├── application/        # FastAPI HTTP routes, SSE streams, security middleware (rate limit, size limit)
├── api/                # Application server entrypoint and route mounts
├── gateway/            # Messaging channel normalizers (Telegram / Ingress -> AgentTurnRequest)
├── storage/            # SQLite schema migrations, connection managers, ACID transaction primitives
├── sessions/           # Durable session state and upstream transcript sync
├── workflows/          # 16-state workflow engine, outbox dispatcher, budget ledger, approval service
├── product_video/      # Product-to-Video AI Factory (research packs, scene plans, storyboard, MCP adapters, QC)
├── learning/           # Governed Learning pipeline (/hoc, /hoc-cta, evidence grounding, candidate review)
├── memos/              # Personal quick notes & hashtag tagging engine (/memo)
├── capabilities/       # Capability policy evaluators, catalog snapshots, and access control
├── identity/           # Principal validation and owner isolation
├── runtime/            # Process supervisor, startup coordinator, and readiness health probes
└── cutover/            # Migration tools and legacy session cutover handlers
```

---

## 3. Subsystem Breakdown

### 3.1 Orchestration & Contracts
* **[`contracts/`](contracts/):** Defines Pydantic/dataclass domain contracts:
  * `AgentTurnRequest` / `TurnResponse`: Uniform wire request/response.
  * `AgentEvent`: Standardized streaming events (`token`, `tool_call`, `status_change`, `done`).
  * `OperatorCommand`: Administrative and HITL approval commands.
  * `CapabilityPolicy`: Fine-grained tool execution boundaries.
* **[`orchestration/`](orchestration/):**
  * `HermesTurnService`: Canonical single-entry turn handler. Enforces idempotency via `(owner_user_id, idempotency_key)`.
  * `UpstreamAgentAdapter`: Encapsulates upstream `run_agent.AIAgent`.

### 3.2 Workflow Engine & Transactional Outbox
* **[`workflows/`](workflows/):**
  * `WorkflowEngine`: Manages state machine transitions with atomic SQLite event sourcing.
  * `OutboxDispatcher`: Background worker polling `workflow_outbox` using atomic lease claims (`pending` → `leased`), deadline heartbeats, and exponential retry backoff.
  * `BudgetEngine`: Atomic SQLite budget reservation ledger guaranteeing zero provider calls on budget exhaustion.
  * `ApprovalService`: Manages HITL approval requests and receipts.

### 3.3 Product Video Factory
* **[`product_video/`](product_video/):**
  * `automation/`: Daily product batch discovery and importer.
  * `creative/`: Grounded prompt templates (`ResearchDossier` → `CreativeBriefV2` → `ScriptScenePlanV2` → `StoryboardV2`).
  * `preprocessing/`: Source asset cleaner and normalization.
  * `qc/`: Multimodal Image QC, Keyframe QC, and Video QC rubrics.
  * `mcp_adapters.py`: Bridges outbox handlers to generative AI video tools (Veo, Flow, Kling, Wan).

### 3.4 Governed Learning & Personal Memos
* **[`learning/`](learning/):**
  * Extracts verifiable facts and conversion hooks (`/hoc`, `/hoc-cta`) anchored directly to source media artifacts (`source_artifact`).
  * Stores unapproved insights in `learning_candidate`.
  * Once approved by the human owner, promotes facts to long-term memory or publishes them as reusable skills.
* **[`memos/`](memos/):**
  * Independent fast note-taking system (`/memo`) with SQLite FTS5 search, hashtag indexing, and group categorization.

### 3.5 Runtime & Application API
* **[`application/`](application/) & [`runtime/`](runtime/):**
  * `StartupCoordinator`: Manages deterministic boot ordering (migrations → lease recovery → readiness probes).
  * `Supervisor`: Spawns and supervises Gateway and App API child processes.
  * `middleware.py`: Enforces 10MB payload size limits, token-bucket rate limiting (120 req/min), and CORS policies.

---

## 4. Verification & Testing

To run the full test suite for `hermes_personal`:

```bash
# Run all unit and integration tests
uv run pytest tests/hermes_personal -q

# Run static analysis and linting
uv run ruff check hermes_personal tests/hermes_personal
```
