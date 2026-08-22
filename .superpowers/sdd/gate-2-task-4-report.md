# Gate 2 Task 4 Report

## Status

DONE_WITH_CONCERNS

## RED

Command:

```powershell
uv run pytest tests/hermes_personal/gateway/test_upstream_agent_adapter.py -q
```

Observed after the test fixture collection issue was corrected: 6 failures,
each caused by `ModuleNotFoundError` for
`hermes_personal.orchestration.upstream_agent`. This established the missing
adapter boundary before production code was added.

## GREEN

Focused adapter verification:

```text
8 passed in 0.39s
```

Compatibility and service verification:

```text
26 passed in 2.46s
```

Ruff:

```text
All checks passed!
```

## Output

- Added `UpstreamAIAgentAdapter`, exported from `hermes_personal.orchestration`.
- It calls only public `AIAgent.run_conversation` with canonical message,
  list-copied history, turn ID, stream callback, and persisted user message.
- A worker and queue expose callback text deltas through a synchronous iterator
  before the upstream synchronous call returns; `None` creates no text event.
- It emits new structured tool-call/tool-result activities with the original
  `tool_call_id`, avoids re-emitting final text already streamed, validates the
  canonical result, and emits exactly one `completed` or `failed` terminal.
- Upstream exceptions are re-raised for `HermesTurnService`; workflow IDs are
  emitted only when an upstream `workflow_id` exactly matches the request.
- The adapter contains no keyword/static routing symbols.

## SHA

Implementation commit: `b2760dcc9d39e9424b670d53a9e987831049ba3a`

## Concerns

The upstream call is synchronous and has no cancellation handle in its public
surface. The adapter uses a daemon worker so it can stream callback deltas, but
cannot forcibly stop an already-running upstream call when its iterator consumer
is cancelled. This preserves the no-upstream-core-change constraint; lifecycle
interruption remains upstream-owned.
