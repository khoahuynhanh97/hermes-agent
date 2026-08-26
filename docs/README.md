# Hermes Personal Documentation

This directory is the canonical documentation entry point for the
`hermes_personal` rearchitecture. The repository also contains upstream Hermes
documentation; that material remains authoritative for the legacy CLI, gateway,
tools, skills, and provider integrations unless a document below explicitly
narrows the scope to `hermes_personal`.

## Authority order

When documents disagree, use this order:

1. Executable source and database migrations under `hermes_personal/`.
2. Tests under `tests/hermes_personal/`.
3. The contracts and operational documents in this index.
4. The approved design and gate plans under `docs/superpowers/`.
5. Historical reports and migration notes.

Plans describe intent and acceptance criteria. They are not evidence that a
runtime surface is implemented. Implementation status must be confirmed from
source and tests.

## Core documents

| Document | Purpose |
| --- | --- |
| [Architecture](architecture.md) | Bounded contexts, turn path, startup, and state machines |
| [Infrastructure](infrastructure.md) | Processes, SQLite, filesystem, workers, and deployment gaps |
| [Security and auth](security-and-auth.md) | Identity, owner isolation, secrets, policy, and known auth limitations |
| [Business logic](business-logic.md) | Routing and decision matrices, HITL rules, capability policy |
| [Data contracts](data-contracts.md) | Canonical request, event, command, artifact, and capability schemas |
| [Data mapping](data-mapping.md) | External input to canonical and persistence mappings |
| [Integrations](integrations-spec.md) | Implemented HTTP API and internal integration contracts |
| [Error handling](error-handling.md) | Error taxonomy, retry ownership, recovery, and no-DLQ policy |
| [Idempotency](idempotency-strategy.md) | Turn, workflow, budget, and product-video deduplication rules |
| [Known gaps](known-gaps.md) | Source-audited blockers, risks, and closure evidence |

## Specialized runbooks

- [Gateway details](hermes-personal/gateway.md)
- [Capability catalog](hermes-personal/capabilities.md)
- [Governed learning](hermes-personal/learning.md)
- [Operations](hermes-personal/operations.md)
- [Workflow implementation notes](hermes-personal/workflows.md)
- [Product-video migration](hermes-personal/product-video-migration.md)
- [Product-video runbook](hermes-personal/product-video-runbook.md)
- [Cutover runbook](hermes-personal/cutover-runbook.md)

## Current implementation boundary

The implemented core uses a single upstream `AIAgent` through
`HermesTurnService`, SQLite persistence, local filesystem artifacts, in-process
job threads, and a subprocess supervisor abstraction. RabbitMQ, Kafka, Redis,
and a dead-letter queue are not part of the current implementation.

The core `hermes start` topology is runnable: Gateway, App API, durable SQLite
event replay, and the development Web UI have real startup/readiness/shutdown
smoke coverage. The standalone MCP discovery, durable-worker, and Telegram
runner commands remain optional gaps and must be disabled in the local profile.
See [Operations](hermes-personal/operations.md) for the exact command and
[Known gaps](known-gaps.md) for the remaining production boundary.
