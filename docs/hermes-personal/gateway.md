# Hermes Personal Gateway

The Hermes Personal gateway is a convergence boundary for conversational ingress. It normalizes authenticated Telegram, CLI, web, and omni envelopes into one `AgentTurnRequest` contract and sends every natural-language turn to `HermesTurnService`. The service calls one `UpstreamAIAgentAdapter`, backed by the public upstream `AIAgent` API. Channel adapters do not choose product, video, provider, or workflow implementations.

## Identity And Sessions

`IdentityRepository` maps each authenticated `(channel, external_subject)` to a global `owner_user_id`. Normalizers never create or infer identity mappings. `HermesTurnService` resolves the subject again and verifies that the request owner, session owner, and session channel all match before claiming or executing a turn.

Conversation sessions are channel-local. The same global owner therefore has distinct Telegram, CLI, web, and omni `session_id` values and separate transcripts. A turn reads only its session transcript and appends only to that transcript.

## Workflow Handoff

A workflow may continue in its active session. Cross-channel continuation additionally requires an explicit `workflow_handoff` from a source session to the target session, and both sessions must have the authenticated owner. A missing handoff, a different workflow, or an owner mismatch fails authorization before an execution claim or agent call.

The gateway only authorizes a supplied workflow ID. It does not mutate workflow state or select a workflow from message keywords.

## Idempotency And Event Replay

Every turn has an authenticated idempotency key. `EventRepository` atomically claims `(owner_user_id, idempotency_key)` in SQLite after identity, session, and workflow validation. The claim stores the first turn ID, session ID, status, and a SHA-256 digest of canonical request semantics. Retry-specific `turn_id`, `occurred_at`, and the key itself are excluded from the digest; message, principal, session, channel, attachments, workflow, locale, capabilities, history, and toolset semantics remain covered.

Claim outcomes are fail closed:

- A new key on an idle session creates one `in_progress` execution.
- A new key while another turn is in progress for the SAME session raises `TurnInProgress` (yielding a canonical `TURN_IN_PROGRESS` failed event on HTTP streaming) and does NOT invoke the agent.
- The same key and digest while running raises `TurnInProgress` and does not call the agent.
- The same key with a different digest raises `IdempotencyConflict` and does not touch transcript or agent state.
- The same key and digest after `completed` or `failed` reconstructs stored events and replays them without appending another user turn or invoking the agent.

Each event is serialized in SQLite under `(turn_id, sequence)` with a unique `event_id`. Live execution writes the event to the replay store and transcript before yielding it. A `completed` or `failed` event marks the execution terminal before it is yielded. Replay is ordered by sequence and preserves the original event ID, canonical turn ID, timestamp, correlations, payload, and terminal type. Reconstructed event payloads are recursively immutable. Closing and reopening SQLite is part of the replay contract; there is no in-memory idempotency fallback.

## Session-Scoped Agent Pool Lifecycle

The configured provider mode uses `SessionScopedAgentPool` in `hermes_personal/runtime/gateway_server.py`:

- **Instantiation**: `AIAgent` instances are created on-demand per `(owner_id, session_id)` when the first turn arrives.
- **Cache-Safe Isolation**: Subsequent turns for the same `(owner_id, session_id)` reuse the exact same `AIAgent` instance, preserving prompt prefix caching while ensuring distinct sessions never share mutable agent state.
- **Shutdown Disposal**: Upon Gateway shutdown, the lifespan/shutdown handler invokes `SessionScopedAgentPool.close()`, which closes all pooled agent instances and cleans up resources.
- **Production Limitation**: The in-memory pool retains active session instances for the duration of the Gateway process lifetime without an LRU eviction/idle session retirement policy. In large multi-user production deployments, an explicit bounded eviction strategy should be added.

## Deterministic Controls

Natural-language normalizers produce only `AgentTurnRequest`. Approve, reject, retry, cancel, upload, and form updates remain explicit `OperatorCommand` operations with their own target/version/idempotency contract. Conversational text that happens to contain words such as "approve" is still a natural-language turn and is never converted into an operator action by a channel normalizer.

## One Brain And Cutover Scope

`HermesTurnService` plus the upstream `AIAgent` remain the sole general-purpose brain. Ingress packages are limited to contracts, identity/session resolution, orchestration binding, and the upstream adapter. An AST acceptance boundary scans the exact project adapter packages and rejects semantic routing tables, provider or Product Intelligence/Video Factory imports, workflow mutation, and direct domain calls.

This gate registers the project service and locks its behavior, but production Telegram, CLI, web, and omni route cutover is deferred. Existing upstream routes are not replaced by Gate 2 Task 6; cutover must occur in the later routing gate with its own rollout and rollback checks.
