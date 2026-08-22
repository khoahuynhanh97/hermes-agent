# Hermes Gateway Convergence And Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Telegram, CLI, Web Chat, and Omni Chat through one authenticated Agent Turn boundary backed by global identity, channel-local sessions, explicit workflow handoff, and the upstream `AIAgent` loop.

**Architecture:** Keep upstream Gateway adapters thin. A project-owned `HermesTurnService` resolves identity and session, invokes an `UpstreamAgentPort`, and publishes canonical `AgentEvent` records; deterministic controls continue through `OperatorCommand`. Identity is global per owner, conversation history remains per channel, and cross-channel continuation requires an explicit workflow link.

**Tech Stack:** Python 3.10+, upstream Hermes Gateway/AIAgent, dataclasses, SQLite, pytest, `uv`.

## Global Constraints

- Implement on `codex/hermes-upstream-rearchitecture` in the isolated upstream worktree.
- Preserve upstream package layout; project behavior belongs under `hermes_personal` or a project plugin.
- Do not import Product Intelligence or Video Factory in this gate.
- Do not modify or delete legacy databases, artifacts, media, or runtime data.
- Every natural-language ingress emits `AgentTurnRequest`; deterministic controls emit `OperatorCommand`.
- An authenticated adapter supplies identity; model/tool arguments cannot select another principal.
- Conversation history is channel-local; workflow continuation across channels is explicit.
- Tests use temporary SQLite databases and fake agents; no network or paid provider calls.

---

## File Map

- `hermes_personal/storage/sqlite.py`: connection factory, migrations, and transaction boundary.
- `hermes_personal/identity/models.py`: global identity and channel mapping records.
- `hermes_personal/identity/repository.py`: owner resolution and mapping persistence.
- `hermes_personal/sessions/models.py`: channel-local session and workflow handoff records.
- `hermes_personal/sessions/repository.py`: session creation, lookup, and explicit handoff.
- `hermes_personal/sessions/upstream_transcript.py`: public `SessionStore` transcript adapter.
- `hermes_personal/orchestration/ports.py`: upstream agent and event sink protocols.
- `hermes_personal/orchestration/turn_service.py`: canonical Agent Turn application service.
- `hermes_personal/orchestration/upstream_agent.py`: adapter for `AIAgent.run_conversation`.
- `hermes_personal/gateway/normalizers.py`: transport payload to canonical contracts.
- `hermes_personal/gateway/plugin.py`: plugin registration and shared service wiring.
- `plugins/hermes_personal/__init__.py`: upstream plugin entry point delegating to project wiring.
- `plugins/hermes_personal/plugin.yaml`: discoverable first-party project plugin manifest.
- `tests/hermes_personal/gateway/`: identity, session, orchestration, and channel-equivalence tests.

### Task 1: Persist Global Identity And Authenticated Channel Mappings

**Files:**
- Create: `hermes_personal/storage/sqlite.py`
- Create: `hermes_personal/identity/models.py`
- Create: `hermes_personal/identity/repository.py`
- Create: `hermes_personal/identity/__init__.py`
- Test: `tests/hermes_personal/gateway/test_identity_repository.py`

**Interfaces:**
- Consumes: `ChannelName` from `hermes_personal.contracts`.
- Produces: `IdentityRepository.resolve(channel: ChannelName, external_subject: str) -> GlobalUserIdentity` and `link(owner_user_id: str, channel: ChannelName, external_subject: str) -> ChannelIdentity`.

- [ ] **Step 1: Write the failing identity tests**

```python
def test_same_owner_resolves_across_linked_channels(identity_repository):
    owner = identity_repository.create_owner("Khoa")
    identity_repository.link(owner.owner_user_id, "telegram", "tg:42")
    identity_repository.link(owner.owner_user_id, "web", "oidc:khoa")
    assert identity_repository.resolve("telegram", "tg:42") == owner
    assert identity_repository.resolve("web", "oidc:khoa") == owner

def test_external_subject_cannot_be_reassigned(identity_repository):
    first = identity_repository.create_owner("first")
    second = identity_repository.create_owner("second")
    identity_repository.link(first.owner_user_id, "cli", "local:khoa")
    with pytest.raises(IdentityConflict):
        identity_repository.link(second.owner_user_id, "cli", "local:khoa")
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/gateway/test_identity_repository.py -q`

Expected: FAIL because `IdentityRepository` does not exist.

- [ ] **Step 3: Implement the schema and repository**

Use this schema verbatim in `hermes_personal/storage/sqlite.py`:

```sql
CREATE TABLE IF NOT EXISTS global_user_identity (
  owner_user_id TEXT PRIMARY KEY,
  display_name TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS channel_identity (
  channel TEXT NOT NULL,
  external_subject TEXT NOT NULL,
  owner_user_id TEXT NOT NULL REFERENCES global_user_identity(owner_user_id),
  created_at TEXT NOT NULL,
  PRIMARY KEY (channel, external_subject)
);
CREATE INDEX IF NOT EXISTS channel_identity_owner_idx
  ON channel_identity(owner_user_id, channel);
```

Define immutable records and errors:

```python
@dataclass(frozen=True)
class GlobalUserIdentity:
    owner_user_id: str
    display_name: str
    created_at: datetime

@dataclass(frozen=True)
class ChannelIdentity:
    channel: ChannelName
    external_subject: str
    owner_user_id: str
    created_at: datetime

class UnknownIdentity(LookupError):
    """The authenticated channel subject has no owner mapping."""

class IdentityConflict(ValueError):
    """A channel subject is already linked to a different owner."""
```

`link` must run in one transaction, reject blank subjects, and convert SQLite uniqueness failures into `IdentityConflict`. `resolve` must perform one join and raise `UnknownIdentity`; it must never auto-create an owner from unauthenticated message content.

- [ ] **Step 4: Verify green and commit**

Run: `uv run pytest tests/hermes_personal/gateway/test_identity_repository.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/storage hermes_personal/identity tests/hermes_personal/gateway/test_identity_repository.py
git commit -m "feat: add global channel identity mapping"
```

### Task 2: Persist Channel-Local Sessions And Explicit Workflow Handoffs

**Files:**
- Create: `hermes_personal/sessions/models.py`
- Create: `hermes_personal/sessions/repository.py`
- Create: `hermes_personal/sessions/upstream_transcript.py`
- Create: `hermes_personal/sessions/__init__.py`
- Modify: `hermes_personal/storage/sqlite.py`
- Test: `tests/hermes_personal/gateway/test_session_repository.py`

**Interfaces:**
- Consumes: owner identity, channel, and optional workflow ID.
- Produces: `ConversationSession`, `WorkflowHandoff`, `get_or_create`, `link_workflow`, `resolve_handoff`, and `UpstreamTranscriptAdapter`.

- [ ] **Step 1: Write session isolation and handoff tests**

```python
def test_sessions_are_separate_per_channel(session_repository):
    telegram = session_repository.get_or_create("user:42", "telegram", "chat:1")
    web = session_repository.get_or_create("user:42", "web", "browser:1")
    assert telegram.session_id != web.session_id
    assert telegram.owner_user_id == web.owner_user_id

def test_workflow_is_visible_only_after_explicit_handoff(session_repository):
    source = session_repository.get_or_create("user:42", "telegram", "chat:1")
    target = session_repository.get_or_create("user:42", "cli", "terminal:1")
    session_repository.link_workflow(source.session_id, "wf_7")
    assert session_repository.resolve_handoff(target.session_id, "wf_7") is None
    handoff = session_repository.create_handoff("user:42", "wf_7", source.session_id, target.session_id)
    assert session_repository.resolve_handoff(target.session_id, "wf_7") == handoff
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/gateway/test_session_repository.py -q`

Expected: FAIL on missing session package.

- [ ] **Step 3: Add durable records and invariants**

Add tables `conversation_session(session_id, owner_user_id, channel, external_conversation_id, active_workflow_id, created_at, updated_at, UNIQUE(owner_user_id, channel, external_conversation_id))` and `workflow_handoff(handoff_id, owner_user_id, workflow_id, source_session_id, target_session_id, created_at, UNIQUE(workflow_id, target_session_id))`.

Define:

```python
@dataclass(frozen=True)
class ConversationSession:
    session_id: str
    owner_user_id: str
    channel: ChannelName
    external_conversation_id: str
    active_workflow_id: str | None
    created_at: datetime
    updated_at: datetime

@dataclass(frozen=True)
class WorkflowHandoff:
    handoff_id: str
    owner_user_id: str
    workflow_id: str
    source_session_id: str
    target_session_id: str
    created_at: datetime
```

`create_handoff` must load both sessions in the same transaction and reject owner mismatch. It records only workflow linkage; it does not copy transcripts.

Implement `UpstreamTranscriptAdapter` against the public upstream methods `SessionStore.load_transcript(session_id)` and `SessionStore.append_to_transcript(session_id, message, skip_db=False)`. `history` returns immutable copied message mappings; `append_user_turn` writes one canonical user record; `append_event` writes assistant text/tool/event metadata using the same channel-local `session_id`. Do not read `SessionStore._entries`, `_db`, or any other private field.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/gateway/test_session_repository.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/storage/sqlite.py hermes_personal/sessions tests/hermes_personal/gateway/test_session_repository.py
git commit -m "feat: add channel sessions and workflow handoff"
```

### Task 3: Build The Canonical Agent Turn Service

**Files:**
- Create: `hermes_personal/orchestration/ports.py`
- Create: `hermes_personal/orchestration/turn_service.py`
- Create: `hermes_personal/orchestration/__init__.py`
- Test: `tests/hermes_personal/gateway/test_turn_service.py`

**Interfaces:**
- Consumes: `AgentTurnRequest`, `IdentityRepository`, `SessionRepository`.
- Produces: `HermesTurnService.handle(request: AgentTurnRequest) -> AsyncIterator[AgentEvent]`.

- [ ] **Step 1: Write failing orchestration tests**

```python
@pytest.mark.asyncio
async def test_turn_rejects_principal_session_owner_mismatch(turn_service, request_factory):
    request = request_factory(principal_id="user:other")
    with pytest.raises(AuthorizationError):
        [event async for event in turn_service.handle(request)]

@pytest.mark.asyncio
async def test_turn_streams_monotonic_events_from_one_agent(turn_service, request_factory, fake_agent):
    fake_agent.output = [AgentOutput("text_delta", {"text": "Xin chao"}), AgentOutput("completed", {})]
    events = [event async for event in turn_service.handle(request_factory())]
    assert [event.sequence for event in events] == [0, 1]
    assert fake_agent.calls[0].workflow_id is None
```

- [ ] **Step 2: Verify red**

Run: `uv run pytest tests/hermes_personal/gateway/test_turn_service.py -q`

Expected: FAIL on missing `HermesTurnService`.

- [ ] **Step 3: Implement ports and service**

```python
@dataclass(frozen=True)
class AgentOutput:
    event_type: AgentEventType
    data: Mapping[str, Any]
    workflow_id: str | None = None
    job_id: str | None = None
    approval_id: str | None = None
    tool_call_id: str | None = None

class UpstreamAgentPort(Protocol):
    def run(
        self,
        request: AgentTurnRequest,
        history: tuple[Mapping[str, Any], ...],
    ) -> Iterator[AgentOutput]:
        raise NotImplementedError

class TranscriptPort(Protocol):
    def history(self, session_id: str) -> tuple[Mapping[str, Any], ...]:
        raise NotImplementedError

    def append_user_turn(self, request: AgentTurnRequest) -> None:
        raise NotImplementedError

    def append_event(self, event: AgentEvent) -> None:
        raise NotImplementedError
```

`handle` must validate the stored session owner/channel against the authenticated principal, validate optional workflow linkage, append the user turn before invoking the agent, convert each `AgentOutput` into an `AgentEvent`, persist before yielding, and emit one `failed` event for a caught agent failure. It must not catch `AuthorizationError` or policy errors as successful text.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/gateway/test_turn_service.py -q`

Expected: `2 passed`.

```powershell
git add -- hermes_personal/orchestration tests/hermes_personal/gateway/test_turn_service.py
git commit -m "feat: add canonical hermes turn service"
```

### Task 4: Adapt The Upstream AIAgent Without Forking Its Core

**Files:**
- Create: `hermes_personal/orchestration/upstream_agent.py`
- Test: `tests/hermes_personal/gateway/test_upstream_agent_adapter.py`

**Interfaces:**
- Consumes: upstream `AIAgent.run_conversation(user_message, system_message=None, conversation_history=None, task_id=None, stream_callback=None, persist_user_message=None, persist_user_timestamp=None, persist_user_display_kind=None, persist_user_display_metadata=None, moa_config=None)`.
- Produces: `UpstreamAIAgentAdapter.run(request: AgentTurnRequest, history: tuple[Mapping[str, Any], ...]) -> Iterator[AgentOutput]`.

- [ ] **Step 1: Write an adapter contract test using a spy AIAgent**

```python
def test_adapter_passes_canonical_content_history_and_turn_id(request_factory):
    spy = SpyAIAgent([{"role": "assistant", "content": "ok"}])
    adapter = UpstreamAIAgentAdapter(spy)
    outputs = list(adapter.run(request_factory(content="tao video"), ({"role": "user", "content": "truoc"},)))
    assert spy.call["user_message"] == "tao video"
    assert spy.call["task_id"].startswith("turn_")
    assert outputs[-1].event_type == "completed"
```

- [ ] **Step 2: Verify red, implement, and verify green**

Run: `uv run pytest tests/hermes_personal/gateway/test_upstream_agent_adapter.py -q`

Expected before implementation: FAIL on missing adapter. The adapter must use the public method only, normalize upstream text/tool stream records into `AgentOutput`, preserve tool-call IDs, and never perform keyword intent routing.

Run again; expected: `1 passed`.

- [ ] **Step 3: Run upstream compatibility and commit**

Run: `uv run pytest tests/hermes_personal/test_upstream_compatibility.py tests/hermes_personal/gateway/test_upstream_agent_adapter.py -q`

Expected: exit code `0`.

```powershell
git add -- hermes_personal/orchestration/upstream_agent.py tests/hermes_personal/gateway/test_upstream_agent_adapter.py
git commit -m "feat: adapt upstream ai agent turn loop"
```

### Task 5: Normalize All Four Conversational Ingresses

**Files:**
- Create: `hermes_personal/gateway/normalizers.py`
- Create: `hermes_personal/gateway/plugin.py`
- Create: `hermes_personal/gateway/__init__.py`
- Create: `plugins/hermes_personal/__init__.py`
- Create: `plugins/hermes_personal/plugin.yaml`
- Test: `tests/hermes_personal/gateway/test_channel_equivalence.py`

**Interfaces:**
- Consumes: authenticated channel subject, conversation ID, content, attachments, and channel capabilities.
- Produces: semantically equivalent `AgentTurnRequest` objects and plugin wiring through `PluginContext`.

- [ ] **Step 1: Write the four-channel equivalence test**

```python
@pytest.mark.parametrize("channel", ["telegram", "cli", "web", "omni"])
def test_natural_language_channels_share_one_contract(channel, normalizer_factory):
    request = normalizer_factory(channel).normalize(
        external_subject="subject:khoa",
        external_conversation_id="conversation:7",
        content="Tim san pham cong nghe 200-500k",
        attachments=(),
    )
    assert request.channel == channel
    assert request.content == "Tim san pham cong nghe 200-500k"
    assert request.principal.owner_user_id == "user:khoa"
    assert request.idempotency_key == request.turn_id
```

- [ ] **Step 2: Verify red and implement `ChannelTurnNormalizer`**

Run: `uv run pytest tests/hermes_personal/gateway/test_channel_equivalence.py -q`

Expected: FAIL on missing normalizer.

The normalizer must resolve identity from authenticated transport metadata, call `SessionRepository.get_or_create`, preserve typed attachment references, set channel capabilities explicitly, and accept `workflow_id` only after `resolve_handoff` succeeds for the same owner.

- [ ] **Step 3: Register shared services through a project plugin**

Expose `hermes_personal.gateway.plugin.register(ctx: PluginContext) -> None`. `plugins/hermes_personal/__init__.py` imports and delegates to that function; `plugin.yaml` declares `name: hermes-personal`, `kind: integration`, `version: 1.0.0`, and no provider credentials. Store one `HermesTurnService` in `ctx.state`, register only transport adapters that are absent upstream, and use `ctx.spawn_task` for lifecycle tasks. Do not register a second Telegram semantic router and do not patch `gateway/run.py`.

- [ ] **Step 4: Verify and commit**

Run: `uv run pytest tests/hermes_personal/gateway/test_channel_equivalence.py -q`

Expected: `4 passed`.

```powershell
git add -- hermes_personal/gateway plugins/hermes_personal tests/hermes_personal/gateway/test_channel_equivalence.py
git commit -m "feat: converge conversational channel ingress"
```

### Task 6: Lock Gate 2 Security And End-To-End Behavior

**Files:**
- Create: `tests/hermes_personal/gateway/test_gateway_acceptance.py`
- Create: `tests/hermes_personal/gateway/test_no_semantic_router.py`
- Create: `docs/hermes-personal/gateway.md`

**Interfaces:**
- Consumes: all Gate 2 services.
- Produces: executable acceptance and architecture boundaries for Gate 3.

- [ ] **Step 1: Add acceptance cases**

Test all of these cases with one fake upstream agent: equivalent text reaches the same agent from four channels; channel sessions remain distinct; an explicit handoff resumes `wf_7`; another owner cannot resume it; duplicate turn idempotency returns stored events without a second agent call; streamed event sequences remain monotonic.

- [ ] **Step 2: Add a static routing boundary test**

Parse project adapter modules with `ast` and fail if they contain product/video keyword tables, provider imports, workflow state mutations, or direct Product Intelligence/Video Factory calls. Permit only contracts, identity/session, orchestration, and upstream adapter imports.

- [ ] **Step 3: Run Gate 2 verification**

```powershell
uv run pytest tests/hermes_personal/gateway tests/hermes_personal/contracts tests/hermes_personal/test_upstream_compatibility.py -q
git diff --check
```

Expected: all tests pass and `git diff --check` prints nothing.

- [ ] **Step 4: Commit the acceptance gate**

```powershell
git add -- tests/hermes_personal/gateway docs/hermes-personal/gateway.md
git commit -m "test: lock canonical gateway convergence"
```

## Gate 2 Exit Criteria

- All four natural-language channels create equivalent `AgentTurnRequest` semantics and call one upstream `AIAgent` adapter.
- Global identity is shared; channel conversations and transcripts remain separate.
- Cross-channel workflow continuation requires an authenticated explicit handoff.
- Deterministic controls remain `OperatorCommand` operations.
- Duplicate turns are idempotent and persisted events are replayable.
- No channel contains product/video semantic routing or provider calls.
- Gate 1 compatibility and all Gate 2 tests pass without external services.
