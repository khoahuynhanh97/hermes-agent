# Hermes Durable Workflow Approval And Budget Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a durable, restart-safe application plane for workflow state, jobs, business approvals, budgets, retries, and deterministic operator commands.

**Architecture:** Persist each workflow as an optimistic-concurrency aggregate plus append-only events. The engine validates typed commands against a declarative transition graph, commits state/event/outbox atomically, and lets lease-based workers execute bounded jobs. Business approvals are Hermes resources distinct from upstream shell/tool execution approval.

**Tech Stack:** Python 3.10+, SQLite WAL, dataclasses/enums, UTC timestamps, pytest, fake clock, `uv`.

## Global Constraints

- Gates 1-3 must pass before this gate starts.
- Hermes owns workflow, job references, events, approval, and budget truth.
- Workers do not interpret user intent, create plans, alter policy, or cross HITL gates.
- Every command is owner-bound, version-checked, and idempotent.
- State, event, and outbox writes commit in one SQLite transaction.
- Paid, publishing, destructive, identity-sensitive, and HITL actions fail closed.
- Upstream command/tool execution approval remains separate from business workflow approval.
- Tests use temporary stores, fake clocks/workers/providers, and no paid credentials.

---

## File Map

- `hermes_personal/workflows/models.py`: aggregate, commands, events, and transition errors.
- `hermes_personal/workflows/definitions.py`: typed workflow graphs and artifact dependencies.
- `hermes_personal/workflows/repository.py`: SQLite aggregate/event/outbox repository.
- `hermes_personal/workflows/engine.py`: idempotent transition application service.
- `hermes_personal/approvals/models.py`: shared business approval resource.
- `hermes_personal/approvals/service.py`: create/approve/reject/expire/invalidate behavior.
- `hermes_personal/budgets/models.py`: budget envelope and cost ledger.
- `hermes_personal/budgets/service.py`: reserve/record/release and reapproval policy.
- `hermes_personal/jobs/models.py`: durable job and lease records.
- `hermes_personal/jobs/repository.py`: claim/heartbeat/complete/fail/requeue.
- `hermes_personal/jobs/worker.py`: bounded execution loop.
- `hermes_personal/application/operator_service.py`: deterministic `OperatorCommand` dispatch.

### Task 1: Define Workflow Aggregates And Legal Transition Graphs

**Files:**
- Create: `hermes_personal/workflows/models.py`
- Create: `hermes_personal/workflows/definitions.py`
- Create: `hermes_personal/workflows/__init__.py`
- Test: `tests/hermes_personal/workflows/test_definitions.py`

**Interfaces:**
- Consumes: owner ID, workflow type, current state, typed artifact references.
- Produces: `WorkflowDefinition.next_state`, `WorkflowAggregate`, `WorkflowCommand`, and `WorkflowEvent`.

- [ ] **Step 1: Write transition table tests**

```python
PRODUCT_STATES = (
    "ProductInput", "Research", "ResourcePackDraft", "AwaitingProductLock",
    "ProductLocked", "CreativeBriefDraft", "AwaitingBriefApproval",
    "ScenePlanDraft", "AwaitingSceneApproval", "StoryboardDraft",
    "AwaitingStoryboardApproval", "Render", "AwaitingFinalApproval", "Exported",
)

def test_product_video_definition_has_exact_sequence():
    definition = DEFINITIONS["product_to_video"]
    assert definition.ordered_states == PRODUCT_STATES

def test_illegal_transition_is_rejected():
    with pytest.raises(IllegalTransition):
        DEFINITIONS["product_to_video"].validate("ProductInput", "Render")

def test_initial_workflow_definitions_have_explicit_states():
    assert DEFINITIONS["product_research"].ordered_states == (
        "ProductInput", "Research", "ResearchComplete",
    )
    assert DEFINITIONS["knowledge_learning"].ordered_states == (
        "SourceInput", "Extracting", "CandidateDraft", "AwaitingKnowledgeApproval", "Approved",
    )
    assert DEFINITIONS["hook_cta_learning"].ordered_states == (
        "VideoInput", "AnalyzingHookCTA", "HookCTACandidateDraft", "AwaitingHookCTAApproval", "Approved",
    )
    assert DEFINITIONS["video_deconstruction"].ordered_states == (
        "VideoInput", "AnalyzingVideo", "ScenePlanDraft", "AwaitingScenePlanApproval", "Completed",
    )
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/workflows/test_definitions.py -q`

Expected: FAIL on missing workflow package.

- [ ] **Step 3: Implement immutable contracts and definitions**

```python
@dataclass(frozen=True)
class ArtifactRef:
    owner: str
    artifact_id: str
    version: int
    schema_version: str
    digest: str

@dataclass(frozen=True)
class WorkflowAggregate:
    workflow_id: str
    owner_user_id: str
    workflow_type: str
    state: str
    version: int
    artifacts: Mapping[str, ArtifactRef]
    active_job_id: str | None
    active_approval_id: str | None
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class WorkflowCommand:
    command_id: str
    workflow_id: str
    owner_user_id: str
    expected_version: int
    command_type: str
    payload: Mapping[str, Any]
    idempotency_key: str
    occurred_at: datetime
```

Define the five graphs with exactly the state tuples tested above. `Rejected`, `Cancelled`, and `Failed` are terminal exception states reachable only through explicit reject/cancel/permanent-failure commands and are not inserted into the successful `ordered_states` sequence. Each transition declares required artifact slots, produced slots, approval requirement, retryability, timeout seconds, cost effect, and downstream invalidation slots.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/workflows/test_definitions.py -q`

Expected: all graph tests pass.

```powershell
git add -- hermes_personal/workflows tests/hermes_personal/workflows/test_definitions.py
git commit -m "feat: define durable workflow contracts"
```

### Task 2: Persist Aggregate, Event Log, Idempotency, And Outbox Atomically

**Files:**
- Create: `hermes_personal/workflows/repository.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Test: `tests/hermes_personal/workflows/test_repository.py`

**Interfaces:**
- Consumes: expected aggregate version, command ID/idempotency key, events, outbox messages.
- Produces: `WorkflowRepository.commit(expected_version, aggregate, events, outbox) -> CommitResult`.

- [ ] **Step 1: Write concurrency and duplicate tests**

```python
def test_commit_appends_event_and_outbox_in_one_transaction(repository, aggregate_factory):
    aggregate = aggregate_factory(version=0)
    result = repository.commit(-1, aggregate, (event("WorkflowStarted"),), (outbox("job.dispatch"),))
    assert repository.get(aggregate.workflow_id).version == 0
    assert repository.events(aggregate.workflow_id)[0].event_type == "WorkflowStarted"
    assert repository.pending_outbox()[0].topic == "job.dispatch"

def test_stale_version_and_duplicate_command_are_deterministic(repository, aggregate_factory):
    aggregate = aggregate_factory(version=0)
    repository.commit(-1, aggregate, (event("WorkflowStarted", command_id="cmd_1"),), ())
    with pytest.raises(VersionConflict):
        repository.commit(-1, aggregate, (event("Again", command_id="cmd_2"),), ())
    assert repository.command_result("cmd_1").workflow_version == 0
```

- [ ] **Step 2: Verify red and add SQLite tables**

Run: `uv run pytest tests/hermes_personal/workflows/test_repository.py -q`

Expected: FAIL on missing repository.

Create tables for `workflow`, `workflow_event`, `processed_command`, and `workflow_outbox`. Use `BEGIN IMMEDIATE`; update with `WHERE workflow_id=? AND version=?`; require exactly one affected row for existing aggregates. Event sequence is `(workflow_id, sequence)` unique. Command ID and idempotency key are unique per owner. Serialize canonical JSON and UTC ISO-8601 only.

- [ ] **Step 3: Verify rollback behavior**

Inject an outbox insert failure and assert no aggregate/event/command row remains. Run the test file; expected all cases pass.

- [ ] **Step 4: Commit**

```powershell
git add -- hermes_personal/storage/sqlite.py hermes_personal/workflows/repository.py tests/hermes_personal/workflows/test_repository.py
git commit -m "feat: persist workflow state events and outbox"
```

### Task 3: Implement Idempotent Workflow Command Handling

**Files:**
- Create: `hermes_personal/workflows/engine.py`
- Test: `tests/hermes_personal/workflows/test_engine.py`

**Interfaces:**
- Consumes: `WorkflowCommand`, definition registry, repository, approval and budget ports.
- Produces: `WorkflowEngine.handle(command) -> CommandResult`.

- [ ] **Step 1: Write command behavior tests**

Test start, legal advance, illegal advance, stale expected version, duplicate command replay, required artifact mismatch, and downstream artifact invalidation. The duplicate case must return the original `CommandResult` and produce no new event/outbox row.

- [ ] **Step 2: Verify red and implement command handlers**

Run: `uv run pytest tests/hermes_personal/workflows/test_engine.py -q`

Expected: FAIL on missing engine.

Support only typed commands: `start`, `record_artifact`, `request_approval`, `approve`, `reject`, `dispatch_job`, `job_succeeded`, `job_failed`, `retry`, `cancel`, and `expire`. Validate owner/version/idempotency before transition logic. Persist `WorkflowStateChanged` plus domain events and outbox messages in one repository commit.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/workflows/test_engine.py -q`

Expected: all command matrix tests pass.

```powershell
git add -- hermes_personal/workflows/engine.py tests/hermes_personal/workflows/test_engine.py
git commit -m "feat: add idempotent workflow engine"
```

### Task 4: Add Shared Cross-Channel Business Approvals

**Files:**
- Create: `hermes_personal/approvals/models.py`
- Create: `hermes_personal/approvals/repository.py`
- Create: `hermes_personal/approvals/service.py`
- Create: `hermes_personal/approvals/__init__.py`
- Test: `tests/hermes_personal/approvals/test_service.py`

**Interfaces:**
- Consumes: Gate 1 `OperatorCommand`, authenticated owner, workflow artifact refs.
- Produces: `ApprovalRequest` and idempotent `ApprovalService.decide`.

- [ ] **Step 1: Write approval lifecycle tests**

```python
def test_owner_can_approve_from_another_channel(approval_service, approval_factory):
    request = approval_service.create(approval_factory(owner_id="user:42"))
    result = approval_service.decide(operator("approve", request, owner="user:42", channel="web"))
    assert result.status == "approved"

def test_changed_digest_and_stale_version_fail_closed(approval_service, approval_factory):
    request = approval_service.create(approval_factory(digest="sha256:old", version=4))
    approval_service.invalidate_for_artifact(request.workflow_id, "sha256:new", 5)
    with pytest.raises(StaleApproval):
        approval_service.decide(operator("approve", request, expected_version=4))
```

- [ ] **Step 2: Verify red and implement the exact resource**

Run: `uv run pytest tests/hermes_personal/approvals/test_service.py -q`

Expected: FAIL on missing approvals.

```python
@dataclass(frozen=True)
class ApprovalRequest:
    approval_id: str
    owner_id: str
    workflow_id: str
    stage: str
    artifact_refs: tuple[ArtifactRef, ...]
    artifact_digest: str
    expected_version: int
    budget_delta: Money | None
    provider_change: str | None
    status: Literal["pending", "approved", "rejected", "expired", "invalidated"]
    expires_at: datetime
    created_at: datetime
    decided_at: datetime | None
```

Decisions require owner match, pending status, unexpired timestamp, exact expected version/digest, and a unique command ID. Approval emits a workflow command but does not mutate workflow rows directly. Keep this model separate from `hermes_cli.approval_transport.ApprovalRequest`.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/approvals/test_service.py -q`

Expected: all lifecycle tests pass.

```powershell
git add -- hermes_personal/approvals tests/hermes_personal/approvals/test_service.py
git commit -m "feat: add shared business approvals"
```

### Task 5: Enforce Budget Envelopes And Cost Ledger

**Files:**
- Create: `hermes_personal/budgets/models.py`
- Create: `hermes_personal/budgets/repository.py`
- Create: `hermes_personal/budgets/service.py`
- Create: `hermes_personal/budgets/__init__.py`
- Test: `tests/hermes_personal/budgets/test_service.py`

**Interfaces:**
- Consumes: workflow budget cap, provider policy, estimated/actual operation cost, idempotency key.
- Produces: reservations, immutable ledger entries, and `BudgetDecision`.

- [ ] **Step 1: Write envelope tests**

Cover execution within cap, over-cap rejection, provider change requiring approval, new paid operation requiring approval, duplicate actual-cost recording, reservation release, and currency mismatch rejection.

- [ ] **Step 2: Verify red and implement money-safe accounting**

Run: `uv run pytest tests/hermes_personal/budgets/test_service.py -q`

Expected: FAIL on missing budget package.

Define `Money(amount_minor: int, currency: str)`, `BudgetEnvelope(workflow_id, cap, provider_policy, approved_paid_operations, version)`, and append-only `CostEntry`. Never use float. Available amount is `cap - actual - active_reservations`; exceeding it returns `requires_approval` and creates no reservation.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/budgets/test_service.py -q`

Expected: all budget tests pass.

```powershell
git add -- hermes_personal/budgets tests/hermes_personal/budgets/test_service.py
git commit -m "feat: enforce workflow budget envelopes"
```

### Task 6: Add Lease-Based Jobs, Retry, And Restart Recovery

**Files:**
- Create: `hermes_personal/jobs/models.py`
- Create: `hermes_personal/jobs/repository.py`
- Create: `hermes_personal/jobs/worker.py`
- Create: `hermes_personal/jobs/__init__.py`
- Test: `tests/hermes_personal/jobs/test_worker.py`

**Interfaces:**
- Consumes: workflow outbox dispatches and registered deterministic handlers.
- Produces: lease-safe terminal job events returned to the workflow engine.

- [ ] **Step 1: Write worker recovery tests**

Test atomic claim, competing worker exclusion, heartbeat extension, expired lease reclaim, idempotent completion, retryable failure with exponential backoff, permanent failure without retry, and process restart between claim and completion.

- [ ] **Step 2: Verify red and implement job records**

Run: `uv run pytest tests/hermes_personal/jobs/test_worker.py -q`

Expected: FAIL on missing jobs.

Use statuses `pending`, `leased`, `retry_wait`, `succeeded`, `failed`, `cancelled`; store attempt/max_attempts, available_at, lease_owner, lease_expires_at, idempotency_key, input JSON, result/error JSON. Claim with one `UPDATE ... RETURNING` inside `BEGIN IMMEDIATE`. Backoff is `min(base_seconds * 2 ** (attempt - 1), max_seconds)` using an injected clock. Handlers return typed terminal results and cannot write workflow state directly.

- [ ] **Step 3: Verify and commit**

Run: `uv run pytest tests/hermes_personal/jobs/test_worker.py -q`

Expected: all lease/recovery tests pass.

```powershell
git add -- hermes_personal/jobs tests/hermes_personal/jobs/test_worker.py
git commit -m "feat: add durable lease based workers"
```

### Task 7: Wire Deterministic Operator Commands And Event Projection

**Files:**
- Create: `hermes_personal/application/operator_service.py`
- Create: `hermes_personal/application/event_projector.py`
- Create: `hermes_personal/application/__init__.py`
- Test: `tests/hermes_personal/workflows/test_operator_acceptance.py`
- Create: `docs/hermes-personal/workflows.md`

**Interfaces:**
- Consumes: `OperatorCommand`, approval/workflow/job services.
- Produces: authenticated application results and correlated `AgentEvent` records.

- [ ] **Step 1: Add operator acceptance tests**

Test approve/reject/retry/cancel against owner, expected version, idempotency, expired approval, and illegal state. Assert workflow/job/approval/tool correlation IDs are projected without leaking payload secrets.

- [ ] **Step 2: Implement deterministic dispatch**

Dispatch by the six Gate 1 operator command types only. `approve`/`reject` call `ApprovalService`; `retry`/`cancel` call `WorkflowEngine`; `upload` and `form_update` validate typed payload and append artifact/form commands. Unknown commands fail with `unsupported_operator_command`; no LLM is invoked.

- [ ] **Step 3: Run Gate 4 verification**

```powershell
uv run pytest tests/hermes_personal/workflows tests/hermes_personal/approvals tests/hermes_personal/budgets tests/hermes_personal/jobs -q
git diff --check
```

Expected: all suites pass; diff check is empty.

- [ ] **Step 4: Commit acceptance and documentation**

```powershell
git add -- hermes_personal/application tests/hermes_personal/workflows/test_operator_acceptance.py docs/hermes-personal/workflows.md
git commit -m "test: lock durable workflow application plane"
```

## Gate 4 Exit Criteria

- Workflow state/events/outbox survive restart and commit atomically.
- Every command is owner-bound, versioned, and idempotent.
- Shared approval can be decided once from any authenticated owner channel.
- Artifact digest/version changes invalidate stale approval and downstream state.
- Budget cap, provider change, and new paid operation policy fail closed.
- Lease-based workers recover expired work without duplicate terminal effects.
- Operator commands never invoke the LLM; workers never mutate policy or skip gates.
