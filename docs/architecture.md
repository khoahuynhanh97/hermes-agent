# Hermes Personal Architecture

## Scope

This document describes the implemented `hermes_personal` bounded context. It
does not replace the upstream Hermes architecture in `run_agent.py`, `gateway/`,
or `hermes_cli/`. The central rule is that upstream `AIAgent` remains the sole
general-purpose reasoning engine.

## Architectural invariants

1. Every channel is normalized into `AgentTurnRequest`.
2. Every general conversation enters `HermesTurnService` and invokes the public
   upstream `AIAgent.run_conversation` API through `UpstreamAIAgentAdapter`.
3. Channels may render events differently, but business behavior does not live
   in a channel adapter.
4. Identity and session ownership are validated before inference or workflow
   continuation.
5. Events are committed before they are yielded to callers.
6. Workflow state, command deduplication, outbox records, approvals, budgets,
   and governed learning use explicit durable contracts.
7. Product-video milestones require human approval and immutable artifact refs.

## Bounded contexts

| Context | Responsibility | Primary source |
| --- | --- | --- |
| Contracts | Channel-neutral principals, turns, commands, events, capabilities | `hermes_personal/contracts/` |
| Gateway | Authentication envelope normalization and channel capabilities | `hermes_personal/gateway/` |
| Identity and sessions | External identity mapping, owner isolation, explicit cross-channel handoff | `hermes_personal/identity/`, `hermes_personal/sessions/` |
| Orchestration | Canonical agent turn and upstream adapter | `hermes_personal/orchestration/` |
| Storage | SQLite schema and repositories | `hermes_personal/storage/` |
| Capabilities | Snapshot catalog, policy, MCP discovery, governed search | `hermes_personal/capabilities/` |
| Workflows | Durable aggregate, events, commands, outbox, approval, budget, jobs | `hermes_personal/workflows/` |
| Product video | Product Intelligence to Video Factory state and artifact chain | `hermes_personal/product_video/` |
| Learning | Candidate, evidence, evaluation, publication, retrieval, rollback | `hermes_personal/learning/` |
| Runtime | Startup sequencing, readiness, process topology, supervision | `hermes_personal/runtime/` |
| Application | Health, event streaming/replay, operator commands, artifact metadata | `hermes_personal/application/` |

## System view

```mermaid
flowchart LR
    T[Telegram] --> N[ChannelTurnNormalizer]
    C[CLI] --> N
    W[Web] --> N
    O[Omni] --> N
    N --> I[IdentityRepository]
    N --> S[SessionRepository]
    N --> TS[HermesTurnService]
    TS --> ER[(SQLite EventRepository)]
    TS --> LR[Approved Learning Retrieval]
    TS --> UA[UpstreamAIAgentAdapter]
    UA --> AI[Upstream AIAgent]
    AI --> UA
    UA --> TS
    TS --> EV[AgentEvent stream]
    EV --> T
    EV --> C
    EV --> W
    EV --> O
    TS --> WF[Durable Workflows]
    WF --> AP[Approvals and Budgets]
    WF --> PV[Product Video]
    PV --> AR[Versioned Artifact Refs]
```

## Canonical agent-turn sequence

```mermaid
sequenceDiagram
    participant Ch as Channel adapter
    participant N as ChannelTurnNormalizer
    participant IS as Identity/Session stores
    participant T as HermesTurnService
    participant E as EventRepository
    participant A as UpstreamAIAgentAdapter
    participant U as AIAgent

    Ch->>N: authenticated envelope
    N->>IS: resolve identity and local session
    IS-->>N: owner_user_id and session_id
    N-->>Ch: AgentTurnRequest
    Ch->>T: stream_turn(request)
    T->>IS: validate owner, channel, session, handoff
    T->>E: claim(owner, idempotency_key, digest)
    alt completed duplicate
        E-->>T: committed AgentEvents
        T-->>Ch: exact replay
    else new request
        T->>A: run(request, history, approved context)
        A->>U: run_conversation(...)
        U-->>A: text/tool stream
        A-->>T: AgentEvents
        T->>E: append event before delivery
        T-->>Ch: committed event
        T->>E: mark terminal
    end
```

## Trigger mechanisms

| Trigger | Entry contract | Dispatch behavior |
| --- | --- | --- |
| Natural-language turn | `AgentTurnRequest` | Canonical `HermesTurnService` path |
| Operator action | `OperatorCommand` | Authenticated command handler with expected version |
| Workflow command | Command dictionary with `command_id`, `workflow_id`, `type`, `args` | `WorkflowEngine` and atomic repository commit |
| Background stage | `JobSpec` / product-video `JobContext` | In-process `JobDispatcher` thread |
| Startup | `StartupCoordinator.prepare()` | Strict ordered readiness gate |
| Recovery | persisted workflows and outbox | `WorkflowRecoveryService` |

## Startup and readiness

```mermaid
flowchart TD
    A[Config validation] --> B[Database migration]
    B --> C[Expired lease recovery]
    C --> D[Workflow and approval recovery]
    D --> E[MCP discovery]
    E --> F[Capability snapshot activation]
    F --> G[Mandatory dependency probes]
    G --> H[Ingress ready]
```

`StartupCoordinator` accepts dependency callbacks. A step with no callback is a
completed no-op, so a successful unit-level startup report alone is not proof
that migrations, discovery, recovery, or external probes ran. Production wiring
must inject each mandatory callback. The current CLI executes this coordinator
before spawning children, while `Supervisor` does not run the declared process
probes; therefore the present sequence is not an end-to-end readiness proof.

## Workflow state models

There are two separate state abstractions. Do not merge them implicitly.

### Generic durable workflow

The generic `WorkflowEngine` accepts commands, checks duplicate `command_id`,
commits events and aggregate versions, and applies its own compact state model.
The current implementation has two known consistency defects: it commits the
pre-transition cached aggregate before validating/applying the transition, and
`job_succeeded` maps to `job_dispatched` while the allowed-state table expects a
target named `job_succeeded`. A successful command can therefore be rejected,
and restart recovery can observe a stale aggregate. Do not use this engine for
production state transitions until both defects and their recovery tests are
fixed.

```mermaid
stateDiagram-v2
    [*] --> initial
    initial --> started: start
    started --> approval_requested: request_approval
    approval_requested --> approved: approve
    approval_requested --> cancelled: reject/cancel
    approved --> job_dispatched: dispatch_job
    job_dispatched --> job_failed: job_failed
    job_dispatched --> job_succeeded: intended job_succeeded target
    job_failed --> job_retried: retry
    job_retried --> job_failed: job_failed
    job_retried --> job_succeeded: intended job_succeeded target
    started --> expired: expire
    approved --> cancelled: cancel
```

### Product-video workflow

The product-video state machine is domain-specific and has five mandatory HITL
waiting states.

```mermaid
stateDiagram-v2
    [*] --> idle
    idle --> researching
    researching --> AwaitingProductLock
    AwaitingProductLock --> building_resource_pack: approve product lock
    building_resource_pack --> creating_brief
    creating_brief --> AwaitingBriefApproval
    AwaitingBriefApproval --> creating_scene_plan: approve brief
    AwaitingBriefApproval --> AwaitingProductLock: replace product
    creating_scene_plan --> AwaitingSceneApproval
    AwaitingSceneApproval --> creating_storyboard: approve scene plan
    AwaitingSceneApproval --> creating_scene_plan: revise
    creating_storyboard --> AwaitingStoryboardApproval
    AwaitingStoryboardApproval --> rendering: approve storyboard
    AwaitingStoryboardApproval --> creating_storyboard: revise
    rendering --> AwaitingFinalApproval
    AwaitingFinalApproval --> exporting: approve final
    AwaitingFinalApproval --> rendering: rerender
    exporting --> completed
```

## Design versus runtime evidence

The master design and gate plans under `docs/superpowers/` define the target
program. Runtime claims require all of the following:

- an importable implementation,
- a production wiring path,
- focused automated tests,
- and, for user-facing processes, a real startup or HTTP smoke test.

The cutover inventory and process topology are declarative validators. Their
presence does not prove that all declared routes or child modules are mounted.
See [Infrastructure](infrastructure.md#known-runtime-gaps).
