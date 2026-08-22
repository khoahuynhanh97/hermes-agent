# Hermes Upstream Gateway Rearchitecture Design

**Status:** Design approved in conversation; written-spec review pending

**Date:** 2026-08-22

**Scope:** Hermes conversational ingress, orchestration, capability discovery,
durable workflows, approval, learning, runtime supervision, and the integration
boundaries for Product Intelligence and Video Factory.

## 1. Purpose

Hermes is the single general-purpose AI orchestrator. Telegram, CLI, Web, and
Omni Chat are interaction surfaces, not separate assistants. Every
natural-language request reaches the canonical NousResearch Hermes Agent loop,
which interprets intent, asks risk-based clarification questions, selects
capabilities, and starts or resumes durable workflows.

This design selects a clean target architecture based on the upstream Hermes
Gateway, plugin, skill, and MCP model. It replaces duplicated routing and
compatibility paths in stages. Existing data and working capability modules are
preserved until migration parity and rollback have been verified.

## 2. Relationship To Existing Architecture Authority

This design preserves the bounded-context and data-ownership decisions in
ADR-010. In particular, it does not merge the Hermes, Product Intelligence,
and Video Factory stores.

Where this design conflicts with the migration strategy or target package
layout in the following documents, this design supersedes them after written
approval:

- `docs/superpowers/specs/2026-08-12-hermes-agent-platform-standardization-design.md`
- `docs/hermes-assistant-architecture.md`

ADR-010 remains authoritative for domain ownership. A follow-up ADR must record
the new Gateway-first replacement strategy before implementation cutover.

## 3. Current-State Assessment

The current repository is a self-contained derivative of
`NousResearch/hermes-agent`, not a clean, currently traceable upstream mirror.
It contains the upstream-style `AIAgent`, conversation loop, Gateway, MCP
discovery, memory, session search, skills, and curator foundations, plus custom
Product Intelligence, knowledge, job, and Video Factory modules.

The main gaps are:

- CLI and Telegram free text have begun converging on `AgentTurnRuntime`, but
  not every conversational path uses it.
- Legacy Telegram commands still have direct provider paths.
- Omni Chat still contains keyword routing, simulated progress, and fake asset
  identifiers instead of invoking the canonical agent and workflow state.
- MCP tools are discoverable, but Hermes lacks a stable semantic capability
  layer independent of MCP server and wire-tool names.
- Approval is split by domain and command surface rather than represented as a
  shared typed resource.
- Approved custom knowledge is not reliably assembled into every relevant
  Agent Turn.
- Runtime services do not yet share one readiness and supervision lifecycle.

## 4. Architectural Principles

1. There is one conversational brain: the canonical Hermes `AIAgent` and
   conversation loop.
2. Every natural-language ingress uses one `AgentTurnRequest` boundary.
3. Deterministic operator actions use authenticated application commands and
   do not require LLM reasoning.
4. Hermes reasons and plans; durable workflow state machines execute and
   resume; workers perform bounded deterministic jobs.
5. Capabilities have stable semantic IDs even when their MCP providers or wire
   names change.
6. Each bounded context has one canonical writer. Projections and exports are
   not additional sources of truth.
7. Paid, destructive, publishing, identity-sensitive, and approval-gated
   actions fail closed.
8. Legacy paths are removed only after parity, migration, and rollback checks.

## 5. Target Architecture

```text
Telegram -----+
CLI ----------+
Web Chat -----+--> AgentTurnRequest --> Hermes Gateway
Omni Chat ----+                          |
                                         v
                              Identity + Session Resolver
                                         |
                                         v
                              Agent Turn Orchestration
                              - context assembly
                              - knowledge retrieval
                              - risk clarification
                              - capability planning
                                         |
                                         v
                           AIAgent / conversation_loop
                                         |
                              Capability invocation
                                         |
                                         v
                              Durable Workflow Engine
                              - state and event log
                              - HITL approvals
                              - budget policy
                              - retry and resume
                                         |
                                         v
                         Native tools / Plugins / MCP adapters
                                         |
                                         v
                                Deterministic workers
```

Deterministic interaction follows a separate entry path into the same policy,
workflow, and audit state:

```text
Approve / Reject / Retry / Cancel / Upload / Form Update
                              |
                       OperatorCommand
                              |
                 Auth + Policy + Application API
                              |
                    Durable Workflow Engine
```

No channel owns intent routing, domain state transitions, approval truth, or
provider invocation.

## 6. Logical Components

The boundaries below are logical. The implementation plan must map them onto
the existing `src/hermes` layout without moving upstream code merely for naming
symmetry.

### 6.1 Gateway Adapters

Telegram, CLI, Web Chat, and Omni Chat adapters own transport authentication,
message normalization, streaming/rendering, and channel-local conversation
presentation. They emit `AgentTurnRequest` or `OperatorCommand` and consume
`AgentEvent`.

### 6.2 Agent Turn Orchestration

The orchestration boundary resolves principal and session identity, assembles
relevant memory and approved knowledge, applies clarification policy, exposes
capabilities through progressive tool discovery, invokes `AIAgent`, and
dispatches workflow commands. It contains no provider-specific business logic.

### 6.3 Application And Workflow Plane

Application services validate commands and own workflow transitions. The
durable workflow engine persists state and events before dispatching work. It
supports idempotent command handling, lease-based execution, retries with
backoff, timeouts, compensation where possible, and restart recovery.

### 6.4 Capability Plane

Native tools, plugins, and MCP servers register into a `CapabilityCatalog`.
Domain skills describe when and how Hermes should use capabilities, but do not
perform network, filesystem, provider, approval, or workflow mutations.

### 6.5 Workers

Workers receive validated job commands and emit terminal events. They cannot
interpret user intent, alter approval policy, create a new plan, or cross a
HITL gate.

## 7. Canonical Contracts

### 7.1 AgentTurnRequest

Required fields:

- `turn_id`, `principal_id`, `session_id`, and `channel`;
- user content and typed attachments;
- optional `workflow_id` for explicit resume or handoff;
- locale, timestamp, and idempotency key;
- channel capabilities for streaming and interactive controls.

The authenticated adapter supplies identity fields. Model-generated arguments
cannot select another principal.

### 7.2 OperatorCommand

Required fields:

- `command_id`, `principal_id`, command type, target ID, expected version;
- typed payload, timestamp, and idempotency key;
- authorization context derived from the authenticated channel.

### 7.3 AgentEvent

Events include text deltas, clarification requests, tool activity, workflow
state changes, approval requests, cost updates, artifacts, warnings, and
terminal outcomes. Every event carries the applicable correlation IDs.

### 7.4 CapabilityDescriptor

Each model-visible capability has:

- stable `capability_id` and schema version;
- current native, plugin, or MCP implementation binding;
- owner, trust level, permissions, and data classification;
- side-effect and risk classification;
- cost model, provider policy, and health state;
- approval policy and idempotency requirements;
- allowed skills and workflow transitions.

MCP discovery creates versioned catalog snapshots at startup and on controlled
reload. Full schemas are loaded lazily through Tool Search only when relevant.

## 8. Capability Model

Initial stable capability IDs include:

```text
product.research
product.resource_pack.build
product.resource_pack.lock
video.brief.create
video.scene_plan.create
video.storyboard.create
video.render
video.export
knowledge.candidate.create
knowledge.retrieve
```

`note.create` is a reserved future capability ID and is not registered during
the initial cutover.

The implementation binding may change without changing workflow or skill
contracts. Missing, unhealthy, unauthorized, or schema-incompatible
capabilities are unavailable to the model and produce an actionable error.

The initial first-class workflows are:

1. `product_research`
2. `product_to_video`
3. `knowledge_learning`
4. `hook_cta_learning`
5. `video_deconstruction`

`note_management` is an extension point, not part of the first cutover.

## 9. Product-To-Video Workflow

The canonical state sequence is:

```text
ProductInput
  -> Research
  -> ResourcePackDraft
  -> AwaitingProductLock
  -> ProductLocked
  -> CreativeBriefDraft
  -> AwaitingBriefApproval
  -> ScenePlanDraft
  -> AwaitingSceneApproval
  -> StoryboardDraft
  -> AwaitingStoryboardApproval
  -> Render
  -> AwaitingFinalApproval
  -> Exported
```

Every state defines accepted input versions, produced artifact references,
entry and exit conditions, retryability, timeout behavior, budget impact, and
the next legal transitions. Product Intelligence owns research evidence,
media, resource-pack drafts, and immutable resource locks. Video Factory owns
creative and render artifacts. Hermes owns workflow, approval, budget, and the
binding between those contexts.

Changing an approved artifact creates a new version and invalidates downstream
approval or generated state according to explicit dependency rules.

## 10. Identity, Session, And Handoff

A `GlobalUserIdentity` maps authenticated identities from all four channels.
Memory, preferences, knowledge access, workflows, and approvals are shared by
that global identity. Conversation history remains in a separate
`ConversationSession` per channel.

Cross-channel continuation is explicit through a workflow link, resume command,
or handoff action. Hermes does not silently copy complete Telegram history into
CLI, Web, or Omni Chat context.

## 11. Data Ownership And Single Truth

Single truth means one canonical owner and writer for each entity, not one
physical database.

| Data | Canonical owner |
| --- | --- |
| Identity and channel mapping | Hermes |
| Session and conversational memory | Hermes |
| Knowledge and learning candidates | Hermes Knowledge |
| Workflow state, job references, events, approvals, budgets | Hermes |
| Capability catalog snapshots | Hermes |
| Product evidence, identity, media, resource packs and locks | Product Intelligence |
| Creative brief, scene plan, storyboard, renders and export | Video Factory |
| Markdown, Drive documents and reports | Read/export projections only |

Cross-context references use opaque IDs, schema versions, immutable artifact
versions, and content digests. Absolute filesystem paths are not public
cross-context contracts.

## 12. Learning And Improvement

Hermes improves through versioned memory, approved knowledge, retrieval, and
procedural skills. This design does not claim autonomous model-weight training.

```text
Execution + tool trace + user feedback
                  |
               Evaluator
                  |
       Memory / Knowledge / Skill Candidate
                  |
          Policy + review + approval
                  |
       Versioned store + retrieval index
                  |
          Future Agent Turn context
```

Low-risk preferences may be written automatically to memory. Knowledge and
procedural skills require evidence, evaluation, versioning, and user approval.
Failed workflows and unapproved artifacts are excluded from positive learning.
Every promoted skill supports rollback, and effectiveness is measured using
task outcome, correction rate, approval rate, latency, and cost.

## 13. Clarification, Approval, And Budget Policy

Hermes infers reversible, low-risk defaults and records them. It must ask for
clarification before product or variant ambiguity, externally visible output,
publishing, destructive changes, identity-sensitive changes, paid execution
without authorization, or any defined HITL transition.

An `ApprovalRequest` contains:

```text
approval_id, owner_id, workflow_id, stage,
artifact_refs, artifact_digest, expected_version,
budget_delta, provider_change, status, expires_at
```

Any authenticated channel belonging to the owner may approve or reject the
same request. Processing is idempotent and uses optimistic concurrency. A
changed artifact digest or version invalidates the old approval.

Each paid workflow has an approved `budget_cap`, cost estimate, currency, and
provider policy. Hermes may execute within that envelope. Exceeding the cap,
changing provider, or introducing a new paid operation creates a new approval.

## 14. Runtime Topology

The operator uses one command:

```powershell
hermes start
```

A local supervisor manages separate processes for:

- Hermes Gateway and Agent Runtime;
- FastAPI Application API;
- Telegram adapter;
- durable workflow workers;
- MCP discovery and health monitoring;
- Web UI delivery.

`hermes start` always makes the Web surface available. Development mode runs
its frontend process under the supervisor; production mode serves the verified
static bundle through the Application API.

Startup performs configuration validation, database migrations, workflow
recovery, MCP discovery, capability snapshot creation, and dependency health
checks. Ingress becomes ready only after mandatory dependencies are healthy.
The supervisor restarts failed processes with bounded backoff without changing
durable workflow state.

## 15. Error Handling And Observability

Every operation is correlated through:

```text
principal_id -> session_id -> turn_id -> workflow_id
             -> job_id -> approval_id -> tool_call_id
```

Structured logs and durable events record capability version, provider,
attempt, latency, estimated and actual cost, approval reference, artifact
version, and terminal outcome. Secrets and raw sensitive payloads are redacted.

Transient provider and transport failures retry only when the operation is
idempotent or protected by an idempotency key. Permanent schema, authorization,
budget, or policy failures fail closed and return an actionable event. The Web
and Telegram surfaces render real workflow events; simulated progress and fake
asset IDs are prohibited.

## 16. Upstream And Customization Strategy

The repository must record an `upstream` remote and a pinned upstream base SHA.
Upstream core files are changed only for isolated, tested defects that cannot be
implemented through a public boundary. Project-specific behavior belongs in
Gateway adapters, application services, plugins, skills, MCP integrations, or
anti-corruption adapters.

An upstream compatibility suite covers Agent Turn invocation, Gateway session
routing, MCP discovery, Tool Search, memory retrieval, and skill loading. An
upstream update cannot be merged until this suite and domain contract tests
pass.

## 17. Migration Strategy

The target architecture is clean, but migration is staged rather than a
big-bang replacement:

1. Record the upstream base, architecture inventory, and replacement ADR.
2. Freeze canonical request, event, capability, workflow, approval, and budget
   contracts.
3. Build the new Gateway and Application boundaries beside legacy paths.
4. Introduce capability catalog snapshots and domain adapters.
5. Implement durable workflow state and shared approvals.
6. Cut over CLI and Omni Chat, then Telegram, then Web Chat and operator UI.
7. Run shadow and contract comparisons against legacy behavior.
8. Migrate canonical data with checksums, counts, version validation, and a
   tested rollback path.
9. Observe the new paths before retiring direct provider calls, keyword
   routers, mock progress, and compatibility APIs.

No legacy database, artifact store, or user media is deleted during migration.

## 18. Verification Strategy

### Contract tests

- all four adapters emit equivalent `AgentTurnRequest` semantics;
- operator commands enforce principal, version, and idempotency;
- capability bindings satisfy stable input/output schemas;
- cross-context artifact references verify digest and ownership;
- provider tools cannot cross approval or budget gates.

### Workflow tests

- each legal and illegal state transition;
- restart recovery at every waiting and executing state;
- retry, timeout, duplicate event, compensation, and stale approval behavior;
- Product Intelligence lock to Video Factory binding and invalidation;
- fake providers only, with paid credentials removed.

### End-to-end tests

- equivalent natural-language requests across Telegram, CLI, Web, and Omni Chat;
- ambiguous product requests produce structured clarification;
- product-to-video pauses at every HITL gate and resumes from another channel;
- workflow continues after supervisor restart;
- approved knowledge or skill is retrieved on a later relevant turn;
- MCP outage and provider failure produce actionable recovery behavior.

## 19. Acceptance Criteria

The rearchitecture is accepted only when:

1. No natural-language production path bypasses the canonical Hermes agent.
2. Web and Telegram no longer contain independent semantic routers.
3. Product Intelligence and Video Factory capabilities are visible through the
   catalog and usable through approved domain skills.
4. Product-to-video uses durable state, typed approvals, immutable artifact
   versions, and budget enforcement.
5. Any authenticated owner channel can approve once and observe the same state.
6. Workflows and pending approvals survive process and machine restart.
7. Approved knowledge and skills affect later relevant turns and can be rolled
   back.
8. The one-command supervisor reports readiness and process health.
9. Legacy data remains readable and migration reconciliation has no unexplained
   differences.
10. Compatibility, contract, workflow, security, and end-to-end suites pass
    without live paid-provider calls.

## 20. Out Of Scope

- Autonomous fine-tuning of model weights.
- Combining independent bounded-context databases into one database.
- Letting workers reason about user intent or approvals.
- Routing deterministic gallery, form, filter, or upload interactions through
  an LLM.
- Deleting legacy data during the migration program.
- Implementing `note_management` before orchestration convergence is complete.

## 21. Delivery Decomposition

This is a program-level architecture. The implementation plan must be divided
into independently verifiable delivery gates:

1. Upstream baseline and canonical contracts.
2. Gateway convergence and identity/session model.
3. Capability catalog, MCP governance, and Domain Skills.
4. Durable workflow, approval, and budget plane.
5. Product Intelligence to Video Factory workflow migration.
6. Knowledge retrieval and governed learning.
7. Supervisor, observability, channel cutover, and legacy retirement.

Each gate requires focused tests, migration notes, and rollback criteria before
the next gate starts.
