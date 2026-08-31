# Hermes Personal — Governed Capability Catalog System

## Overview

The **Governed Capability Catalog System** (`hermes_personal.capabilities`) provides stable, policy-evaluated capability management for Hermes Personal Assistant operations across all natural-language ingress channels (Telegram, CLI, Web, Omni).

It decouples stable domain capability declarations (`product.research`, `video.brief.create`, `knowledge.retrieve`, etc.) from dynamic MCP tool implementations, enforcing strict policy controls, immutable snapshot tracking, governed search/lazy schema resolution, and structured error reporting.

---

## Architectural Principles

1. **Sole Brain Architecture**:
   - Upstream `run_agent.AIAgent` remains the sole general-purpose brain for all conversational turns. `HermesTurnService` is a thin facade only; it does not route domain intent or execute tools.
   - Capability catalog rules and domain skills specify permitted capabilities; tools cannot be executed without evaluator authorization.

2. **Stable Manifest & Immutable Bindings**:
   - Capabilities are declared in a fixed manifest (`INITIAL_CAPABILITIES`) containing metadata (display name, description, risk level, cost class, approval policy, allowed skills, allowed workflows).
   - Implementation bindings (`ImplementationBinding`) link stable capability IDs to specific wire tool names (e.g. `mcp__product_intelligence__research_product`).

3. **Immutable Snapshots & Atomic Active Pointer**:
   - Discovered bindings are stored in immutable SQLite snapshots (`capability_snapshot` and `capability_snapshot_binding`).
   - An atomic singleton pointer (`capability_catalog_state`) tracks the active snapshot ID.
   - Snapshot digests use order-independent SHA-256 hashes of capability bindings.

4. **Governed Search & Lazy Schema Resolution**:
   - Tool search (`GovernedCapabilitySearch`) operates over compact metadata search results (capability ID, display name, description, risk, cost class, approval policy), hiding internal wire names and providers.
   - Tool schemas (`describe()`) are resolved lazily only AFTER `CapabilityPolicyEvaluator` confirms authorization.

5. **Structured Machine-Readable Errors**:
   - Policy denials, schema failures, or snapshot errors raise `CapabilityError`, which serializes into machine-readable dict payloads (`code`, `message`, `retryable`, `capability_id`, `actionable_recovery`).
   - Payloads flow directly into canonical `AgentEvent(event_type="failed")` objects across all ingress channels.

---

## Capability Manifest (`INITIAL_CAPABILITIES`)

The catalog maintains exactly **10 stable capability IDs**:

| Capability ID | Risk | Cost | Approval Policy | Owner | Allowed Workflows |
|---|---|---|---|---|---|
| `product.research` | low | free | `none` | `product_intelligence` | `product_research`, `product_to_video` |
| `product.resource_pack.build` | medium | metered | `none` | `product_intelligence` | `product_research`, `product_to_video` |
| `product.resource_pack.lock` | high | free | `hitl:product_lock` | `product_intelligence` | `product_research`, `product_to_video` |
| `video.brief.create` | medium | metered | `precondition:product_locked` | `video_factory` | `product_to_video` |
| `video.scene_plan.create` | medium | metered | `precondition:brief_approved` | `video_factory` | `product_to_video` |
| `video.storyboard.create` | medium | paid | `precondition:scene_approved` | `video_factory` | `product_to_video` |
| `video.render` | high | paid | `hitl:storyboard_and_budget` | `video_factory` | `product_to_video` |
| `video.export` | high | paid | `hitl:final` | `video_factory` | `product_to_video` |
| `knowledge.candidate.create` | medium | free | `review_required` | `learning` | `knowledge_learning` |
| `knowledge.retrieve` | low | free | `approved_only` | `learning` | `product_research`, `product_to_video`, `knowledge_learning` |

> **Note**: `note.create` is intentionally excluded from the stable manifest.

---

## Snapshot & Reload Lifecycle

Operators or background discovery processes use `CapabilityCatalogService.reload()` to refresh tool bindings:

```python
from hermes_personal.capabilities.service import CapabilityCatalogService
from hermes_personal.capabilities.snapshots import CapabilitySnapshotRepository

repo = CapabilitySnapshotRepository(db_connection)
service = CapabilityCatalogService(snapshot_repository=repo, registry=tool_registry)

# Execute controlled reload
new_snapshot = service.reload()
print(f"Activated Snapshot: {new_snapshot.snapshot_id}")
```

### Discovery Validation & Diagnostics
During `reload()`, `CapabilityDiscovery.scan()` validates wire bindings against `DEFAULT_WIRE_BINDING_RULES`:
- If wire tools are missing, diagnostic issues are collected (`tool_not_found`, `check_failed`, `schema_incompatible`, `ambiguous_wire_mapping`, `duplicate_wire_ownership`).
- If discovery is incomplete (fewer than 10 bindings), `reload()` fails closed raising `CapabilityError(code="binding_unavailable")`.

---

## Policy Context & Evaluation

Every request creates a `PolicyRequestContext`:

```python
context = PolicyRequestContext(
    authenticated=True,
    skill_id="hermes-personal-product-research",
    workflow_id="product_research",
    channel_id="cli",
    session_id="ses_01",
    granted_policies=frozenset(["approved_only"]),
    user_confirmed_approval=True,
    budget_available=10.0,
    degraded_mode=False,
)

decision = evaluator.evaluate("product.research", context)
if not decision.allowed:
    raise CapabilityError(code=decision.reason_code, message=decision.message)
```

### Policy Rules Matrix:
1. **Authentication**: Rejects unauthenticated calls (`unauthenticated`).
2. **Skill Identity**: Rejects if capability does not authorize `context.skill_id` (`unauthorized_skill`).
3. **Workflow Identity**: Rejects if capability does not authorize `context.workflow_id` (`unauthorized_workflow`).
4. **Approval & Preconditions**:
   - `user_confirmation`: Requires `user_confirmed_approval=True` (`unmet_approval`).
   - `approved_only`: Requires `"approved_only"` in `context.granted_policies` (`unmet_approval`).
   - `precondition:pack_locked`: Requires `"precondition:pack_locked"` in `context.granted_policies` (`unmet_precondition`).
5. **Paid Budget**: Paid capabilities (`cost_class == "paid"`) require positive `budget_available` (`budget_exceeded`).
6. **Degraded Mode**: In `degraded_mode=True`, paid/high-risk capabilities are blocked (`degraded_service`), while low-risk free capabilities emit a policy warning (`PolicyWarning`).

---

## Governed Skill Definitions

Domain skills are defined under `.agents/skills/`:
- `.agents/skills/hermes-personal-product-research/SKILL.md`
- `.agents/skills/hermes-personal-product-video-production/SKILL.md`
- `.agents/skills/hermes-personal-knowledge-learning/SKILL.md`

Each skill frontmatter declares `allowed-capabilities` and candidate `allowed-tools`. The body asserts the Hermes Orchestrator as sole brain and prohibits silent auto-approval for knowledge modifications.

---

## Canonical Turn Service Integration

`HermesTurnService` (`hermes_personal/orchestration/turn_service.py`) incorporates `CapabilityCatalogService`:

```python
turn_service = HermesTurnService(
    identity_repository=identity_repo,
    session_repository=session_repo,
    event_repository=event_repo,
    transcript_factory=transcript_store,
    agent=upstream_agent,
    catalog_service=catalog_service,
)
```

When capability policy denials or errors occur during turn processing, `HermesTurnService._failed_event` converts `CapabilityError` directly into structured `AgentEvent(event_type="failed")` data:

```json
{
  "event_type": "failed",
  "data": {
    "code": "binding_unavailable",
    "message": "No active catalog snapshot found in repository",
    "retryable": true,
    "capability_id": "",
    "actionable_recovery": "Perform controlled reload() to discover and activate a snapshot"
  }
}
```

---

## Operator Troubleshooting & Reload Guidance

1. **No Active Snapshot Error (`code: binding_unavailable`)**:
   - Cause: Database is fresh or active snapshot state is unpopulated.
   - Remedy: Run `service.reload()` via admin CLI or start script.

2. **Schema Unavailable Error (`code: schema_unavailable`)**:
   - Cause: Wire tool definition missing or unresolvable in tool registry.
   - Remedy: Verify MCP server health and check tool registration.

3. **Unauthorized Skill Error (`code: unauthorized_skill`)**:
   - Cause: The active domain skill is not declared in `CapabilitySpec.allowed_skills`.
   - Remedy: Verify skill frontmatter `allowed-capabilities` and workflow setup.

