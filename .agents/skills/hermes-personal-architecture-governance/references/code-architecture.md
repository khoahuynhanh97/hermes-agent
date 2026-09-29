# Code Architecture Rules

These rules apply to `hermes_personal/` and its Product Video integrations. They
refine the canonical documents; they do not override source, tests, or approved
contracts.

## Authority and Ownership

Use the authority order in `docs/README.md`:

1. executable source and migrations;
2. tests;
3. indexed architecture and contract documents;
4. approved plans;
5. historical reports.

Plans and diagrams are intent, not runtime evidence.

| Concern | Canonical owner |
| --- | --- |
| Turn/event/operator wire contracts | `hermes_personal/contracts/` |
| Channel normalization | `hermes_personal/gateway/` |
| Identity and session ownership | `hermes_personal/identity/`, `hermes_personal/sessions/` |
| Canonical agent turn | `hermes_personal/orchestration/` |
| Shared SQLite schema/repositories | `hermes_personal/storage/` |
| Capability discovery/policy/snapshots | `hermes_personal/capabilities/` |
| Durable workflow primitives | `hermes_personal/workflows/` |
| Product Video orchestration/state/jobs/QC | `hermes_personal/product_video/` |
| Product Intelligence adapters | `hermes_personal/integrations/product_intelligence/` |
| Video Factory domain/ports/providers/composition/export | `hermes_personal/integrations/video_factory/` |
| Runtime startup/readiness/supervision | `hermes_personal/runtime/` |
| HTTP/operator/event application surface | `hermes_personal/application/`, `hermes_personal/api/` |

Before adding a file, search these owners and tests for the same responsibility.
An existing owner wins unless an approved refactor explicitly replaces it.

## Dependency Direction

- Contracts and frozen domain values must not import UI, HTTP, CLI, workers,
  provider SDKs, or concrete repositories.
- Orchestration coordinates contracts and ports; it does not own provider wire
  formats, SQL details, filesystem layout, or channel presentation.
- Ports describe required behavior. Concrete provider, SQLite, filesystem, and
  subprocess implementations live at integration/infrastructure edges.
- Gateway, CLI, HTTP, desktop, and web handlers normalize input, invoke one
  application/orchestration path, and render results. They do not duplicate
  business policy or workflow transitions.
- Product Video may use generic workflow/storage primitives, but generic modules
  must not import Product Video implementation details.
- Provider-specific request/response fields, model options, and polling semantics
  stay in provider adapters. Canonical domain objects contain only stable fields.
- Product Video scene rendering has exactly two official provider identities:
  `vertex_ai` for the Vertex AI Veo API and `google_flow` for Playwright Google
  Flow. Local pan/zoom, slideshow, still-image animation, and synthetic video
  adapters are forbidden. Selection happens before the durable claim; recovery
  uses the pinned provider without cross-provider fallback.

Avoid generic dumping grounds such as new `utils.py`, `helpers.py`, or `common.py`.
Name a module after the responsibility it owns.

## Contract and State Rules

- Use one canonical type per boundary. Reuse or extend it rather than adding a
  dictionary-shaped shadow contract.
- Version persisted and external contracts. Reject unsupported versions explicitly.
- Preserve strict message role alternation and the byte-stable conversation prompt.
- Keep the Product Video workflow domain-specific. Do not silently merge it with
  the generic workflow aggregate.
- State transitions, approvals, budget reservations, outbox claims, and provider
  operation IDs must be persisted before an external side effect is treated as
  accepted.
- Replays and retries must return or resume the same logical result; they must not
  create another paid operation or another final artifact version accidentally.

## Move-Only Refactors

For a structural move:

1. Move a coherent ownership cluster, not isolated lines chosen by size.
2. Preserve signatures, exceptions, constants, serialization, and side effects.
3. Keep temporary re-exports at the old import path when callers rely on it.
4. Update internal callers to import from the new owner.
5. Add import-identity tests when compatibility depends on the same object identity.
6. Remove a compatibility re-export only in an explicit breaking-change task.
7. Do not combine a move with behavior, schema, provider, or formatting changes.

## Extension Rules

- Extend existing infrastructure before adding a new manager, registry, workflow,
  state store, path resolver, or model tool.
- New capability should follow the repository Footprint Ladder in `AGENTS.md`.
- Use `config.yaml` for behavior and `.env` only for secrets.
- Do not introduce RabbitMQ, Kafka, Redis, a DLQ, a second database, or a new live
  provider call without an approved architecture decision and recovery design.
- A declared route/process is implemented only when its import target exists, its
  production wiring exists, and a runtime or HTTP smoke test exercises it.

## Verification

Scale checks with the boundary changed:

- contract tests for serialization, validation, and version rejection;
- repository tests against temporary SQLite, including restart/replay behavior;
- workflow tests for legal transitions, stale versions, retries, and all HITL gates;
- adapter tests for provider wire translation without leaking fields into domain;
- runtime tests for routes, processes, startup, and recovery claims;
- import compatibility tests for module moves;
- `uv run ruff check hermes_personal tests/hermes_personal`;
- focused pytest first, then `uv run pytest tests/hermes_personal -q` when feasible.

Prefer invariant tests over snapshots of enum counts, model lists, or incidental
JSON formatting.
