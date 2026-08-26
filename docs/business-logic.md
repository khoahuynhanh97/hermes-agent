# Hermes Personal Business Logic

## Canonical routing rules

| Input | Condition | Route | Reject when |
| --- | --- | --- | --- |
| Natural-language message | Authenticated channel identity and valid session | `HermesTurnService` | Unknown identity/session, owner mismatch, channel mismatch |
| Workflow continuation | Session owns active workflow or explicit handoff exists | Same canonical turn service with `workflow_id` | Foreign owner or missing handoff |
| Capability call | Active snapshot resolves ID and policy allows it | Bound implementation | Unknown/unavailable binding or denied policy |
| Operator action | Authenticated owner, supported command, expected version | Command handler/workflow service | Bad target, forbidden owner, version conflict |
| Product-video job | Legal non-HITL state, expected workflow version and input digest | Stage handler | Waiting approval, illegal state, stale version/digest |
| Learning retrieval | Approved and active learning version | Context assembler | Candidate is pending, rejected, rolled back, or foreign |

Channels must not route around `HermesTurnService` for ordinary agent turns.
Channel-specific behavior is limited to authentication, normalization,
capability declaration, event rendering, and platform delivery.

## Turn decision matrix

| Check | Pass | Fail |
| --- | --- | --- |
| Contract schema and non-empty message/attachment | Continue | Validation error |
| `(channel, actor_id)` resolves | Load owner | Authorization failure |
| Session exists and owner/channel match | Continue | Authorization failure |
| Requested workflow is active or handed off | Continue | Authorization failure |
| `(owner, idempotency_key)` is new | Claim execution | See duplicate cases below |
| Same key and same digest is completed/failed | Replay exact committed events | N/A |
| Same key and same digest is running | Return in-progress failure | N/A |
| Same key and different digest | Reject conflict | Never overwrite prior execution |
| Approved learning assembler present | Add approved context | Use canonical history only |
| Agent emits event | Persist, project, then yield | Convert failure to terminal event |

## Capability policy matrix

The capability policy evaluates these gates in order. A denial returns a
structured `CapabilityError` with recovery guidance.

| Gate | Rule |
| --- | --- |
| Authentication | Context must be authenticated when the capability requires a principal |
| Identity | Requested capability ID must match the manifest/binding |
| Skill | Calling skill must be in `allowed_skills` when restricted |
| Workflow | Active workflow must be in `allowed_workflows` when restricted |
| Health | `unavailable` is denied; `degraded` is conditional |
| Schema | Input/output schema versions must match the active binding |
| Approval | Enforce `none`, `review_required`, `approved_only`, `hitl`, or named precondition policy |
| Budget | Metered/paid calls require positive available budget |
| Degraded mode | Only low-risk, free, non-approval work may continue with a warning |

## Operator command rules

Supported command types are `approve`, `reject`, `retry`, `cancel`, `upload`,
and `form_update`. Every command carries:

- authenticated `PrincipalContext`;
- non-empty `target_id`;
- non-negative `expected_version` for optimistic concurrency;
- unique `command_id` and default idempotency key;
- immutable payload mapping.

The generic workflow repository deduplicates `(workflow_id, command_id)`.
Handlers must validate owner and expected version before side effects.

## Product-video decision matrix

| Stage | Legal source state | Required input | Next HITL/state |
| --- | --- | --- | --- |
| Research | `idle` | Product name, keywords, optional PDP URL | `researching` then product-lock preparation |
| Product lock | `researching`/stage-defined state | Resource-pack content | `AwaitingProductLock` |
| Build/brief | approved product lock | `lock_ref` with PI ownership and matching digest | `AwaitingBriefApproval` |
| Scene plan | approved brief | `brief_ref` with VF ownership and matching digest | `AwaitingSceneApproval` |
| Storyboard | approved scene plan | `scene_plan_ref` | `AwaitingStoryboardApproval` |
| Render | approved storyboard | `storyboard_ref` | `AwaitingFinalApproval` |
| Export | approved final render | `render_ref` | `completed` |

No job may dispatch while the workflow is in one of the five `Awaiting*`
states. Approval moves the workflow forward; rejection/revision returns to the
documented revision state.

## Artifact replacement and invalidation

The immutable dependency chain is:

```text
product_lock -> brief -> scene_plan -> storyboard -> render -> export
```

Replacing a node increments the binding version and clears every descendant.
Any pending or approved approval whose payload contains an exact descendant
`artifact_id` is changed to rejected. Matching is recursive and exact; for
example, `artifact-1` must not invalidate `artifact-10`.

Artifact ownership is enforced:

- `lock_ref`: `product_intelligence`;
- brief, scene plan, storyboard, render, export: `video_factory`.

## Budget rules

The product-video handlers currently reserve deterministic stage costs:

| Stage | Units |
| --- | ---: |
| Creative brief | 5 |
| Scene plan | 5 |
| Storyboard | 10 |
| Render | 50 |
| Export | 20 |

Reservation happens before work; success commits the reservation and failure
releases it. The current in-memory engine uses an idempotency key only to avoid a
second commit; it does not deduplicate repeated reservations and is not durable.
These units are internal policy values, not provider prices. Paid-provider
execution requires a durable reservation claim before it is safe for production.

## Governed learning

Task outcomes can propose learning candidates, but candidates are not injected
into future turns until evaluation and explicit approval publish an active
version. Retrieval is owner-scoped. Rollback changes the active version without
deleting evidence or history.

## Explicit non-behaviors

- No silent approval of product locks, creative milestones, final video, or
  learning publication.
- No direct external provider calls from deterministic test clients.
- No substring-based artifact invalidation.
- No cross-owner session or artifact access.
- No assumption that declarative cutover routes are mounted.
