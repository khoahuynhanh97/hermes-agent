# Gate A Worker Context and Runtime Flow

## Purpose

This document explains the existing Hermes runtime around Gate A. It is
required context for implementing the remediation plan. The implementation
plan defines the target contracts; this document defines the behavior that
must survive the refactor.

Read together:

1. `docs/superpowers/specs/2026-08-12-hermes-agent-platform-standardization-design.md`
2. `docs/superpowers/plans/2026-08-13-gate-a-production-wiring-remediation.md`
3. this document.

Do not treat a missing target class or function as an architecture conflict.
The remediation plan intentionally introduces new interfaces. Stop only when
two documents assign contradictory ownership or incompatible public behavior.

## System Position

```text
User / Channel
      |
      v
Authenticated channel ingress
      |
      v
PrincipalContext scope
      |
      v
AIAgent.run_conversation
      |
      v
agent/conversation_loop.py
      |
      v
ToolRegistry.dispatch
      |
      +---------------- native handler
      |
      +---------------- MCP handler
                            |
                            v
                    connected MCP server
```

`agent/conversation_loop.py` is the canonical conversational loop and is not
part of Gate A refactoring. `tools.registry` remains the only tool dispatcher.
Product Intelligence remains an external MCP.

## Current Tool Registration Flow

### Native tools

```text
import tools module
      |
      v
registry.register(name, toolset, schema, handler, ...)
      |
      v
ToolEntry stored in ToolRegistry._tools
      |
      v
model_tools exposes schema to the model
      |
      v
registry.dispatch executes handler
```

Gate A adds an immutable `CapabilityDescriptor` to the same `ToolEntry`. It
does not create another handler registry.

### MCP eager discovery

```text
discover_mcp_tools
      |
      v
register_mcp_servers
      |
      v
connect / initialize MCPServerTask
      |
      v
fetch complete tools list
      |
      v
_register_server_tools
      |
      +-- apply include/exclude
      +-- scan remote descriptions
      +-- convert MCP input schemas
      +-- generate resource/prompt utility schemas
      +-- protect registry ownership
      +-- register handlers
      +-- record MCP provenance
      +-- write schema cache
```

### MCP lazy cache restore

```text
load MCP config
      |
      v
read matching schema-cache entry
      |
      v
_register_from_cache_sync
      |
      +-- restore raw tool schemas
      +-- restore generated utility schemas
      +-- run the same description/security checks
      +-- register lazy handlers
      +-- record lazy server/tool state

first tool call
      |
      v
connect real server and reconcile cached names with live names
```

Lazy handlers must continue routing the first invocation through the existing
lazy-connect mechanism. A candidate refactor must not turn cached handlers into
eager connections.

### MCP dynamic refresh

```text
notifications/tools/list_changed
      |
      v
MCPServerTask._refresh_tools
      |
      v
fetch complete new tools list
      |
      v
collect + validate desired server toolset
      |
      v
atomic replacement of this server's registry entries
      |
      v
update _registered_tool_names and provenance
```

Refresh is a replacement operation, not an append followed by best-effort
cleanup. Validation or commit failure must preserve the complete previous set.

## Target MCP Registration Flow

All three paths converge after collection:

```text
live collector -------------------+
                                   |
cache collector ------------------+--> list[RegistrationCandidate]
                                   |              |
refresh uses live collector -------+              v
                                          validate complete set
                                                   |
                                      accepted + rejected + reasons
                                                   |
                                                   v
                                     one registry batch transaction
                                                   |
                                                   v
                                  provenance/cache/state update after commit
```

The collectors may differ because live MCP objects and cached dictionaries are
different inputs. Candidate validation and registry commit must not differ.

## RegistrationCandidate Contract

```python
@dataclass(frozen=True)
class RegistrationCandidate:
    registry_name: str
    raw_name: str
    origin: str
    schema: dict
    handler: Callable
    check_fn: Callable | None
    descriptor: CapabilityDescriptor
```

Rules:

- `registry_name` is the final provider-safe, server-prefixed wire name.
- `raw_name` is the MCP server's original name or a stable generated-utility
  identifier.
- Raw tools and generated utilities use the same final-name namespace.
- `schema` is model-facing MCP schema only. Do not insert ownership fields such
  as `_internal_toolset_name` into it.
- Ownership belongs to the candidate/descriptor and the registry snapshot.
- `descriptor` is resolved from trusted MCP server provenance/config before
  validation.

## Validation Boundary

`validate_registration_candidates()` is pure. It must not mutate:

- `ToolRegistry`;
- `_mcp_tool_server_names`;
- lazy-server maps;
- schema cache;
- `MCPServerTask._registered_tool_names`.

It receives a complete candidate set and a coherent ownership snapshot. It
must reject:

- every candidate sharing an ambiguous final normalized name;
- a candidate owned by another toolset/server;
- a descriptor whose wire name does not equal the candidate registry name;
- conflicting descriptors for one wire name;
- malformed public schema or missing handler.

Exact duplicate candidates may be deduplicated only when origin, schema,
handler identity, and descriptor are equivalent. Otherwise they are ambiguous.

## Commit Boundary

The registry owns the atomic commit because it owns the mutation lock. The MCP
module must not reach into `registry._lock` or `registry._tools` directly.

The recommended registry interface is behaviorally equivalent to:

```python
def commit_toolset_batch(
    self,
    *,
    toolset: str,
    accepted: tuple[RegistrationCandidate, ...],
    replace_names: frozenset[str] = frozenset(),
) -> tuple[str, ...]:
    """Validate ownership again under the lock and commit all-or-none."""
```

Required semantics:

1. acquire the registry mutation lock;
2. re-check ownership against current state to close discovery races;
3. prepare or snapshot every affected entry;
4. register all accepted candidates with descriptors;
5. for refresh, remove only stale entries owned by the same toolset;
6. on any failure, restore the previous entries and generation;
7. return only names actually committed.

Only after a successful registry commit may `tools.mcp_tool` update provenance,
lazy maps, `_registered_tool_names`, logs, or the schema cache.

Calling `registry.register()` in a loop and appending names unconditionally is
not an atomic batch. Holding the registry's private lock from `mcp_tool.py` is
also not the correct ownership boundary.

## MCP Behaviors That Must Be Preserved

Task 2 is not permission to replace the existing MCP implementation with a
smaller implementation. Preserve:

- stdio, HTTP, OAuth, reconnect, circuit-breaker, and keepalive behavior;
- paginated tools listing;
- include/exclude exact and glob matching;
- description injection scanning on live and cached schemas;
- generated resource and prompt utility tools;
- cross-toolset and cross-server collision protection;
- provider-safe name normalization;
- lazy first-call connection and stale-cache reconciliation;
- schema-cache fingerprinting and write-through;
- MCP provenance maps;
- toolset aliases;
- registry generation and concurrent-reader safety;
- dynamic refresh notification and user-visible change logging;
- handler timeout and availability checks.

When moving code, start from the existing block and extract functions. Do not
reimplement these behaviors from memory.

## Secret Environment Flow

Secret isolation is Gate A Task 2 security behavior and must remain intact
during MCP registration refactoring.

```text
per-server MCP config
      |
      +-- env
      +-- secret_allowlist
              |
              v
validate raw allowlist type and entries
              |
              v
_build_safe_env(user_env, allowed_secret_names)
              |
              v
stdio subprocess
```

`_run_stdio()` must validate the raw allowlist before conversion and pass the
validated set to `_build_safe_env`. The safe environment retains existing safe
baseline variables and `XDG_*`, plus only explicitly allowlisted secrets.
Interpolation references outside the allowlist fail before process creation.

Registration refactoring must not edit this code unless required to preserve a
passing security regression. The following suite is a mandatory checkpoint:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_tool_security.py -q
```

## Principal Flow

```text
trusted channel identity
      |
      v
PrincipalContext(actor, owner, platform, session, roles)
      |
      v
principal_scope
      |
      v
AIAgent uses existing context
      |
      v
ToolRegistry.dispatch reads ToolEntry.descriptor.principal_mode
      |
      +-- session: require principal and overwrite owner argument
      +-- none: do not inject owner
      +-- server: use explicitly configured server identity contract
```

MCP registration must attach descriptors so dispatch never needs to infer
principal policy from the wire name.

## Test Structure

Tests must execute production seams, not relabel helper calls.

### Eager

Call `_register_server_tools()` with a real `MCPServerTask` fixture and a test
registry. Assert validator invocation, committed entries, descriptors,
provenance, and rejected collisions.

### Lazy

Call `_register_from_cache_sync()` with a cache entry in the real cache format.
Assert the same accepted/rejected final names and that handlers remain lazy.

### Refresh

Configure the task fixture so `_advertises_tools()` is true, provide a session
whose paginated `list_tools` is called, and invoke `_refresh_tools()`. Assert:

- the list call occurred;
- validation occurred exactly once;
- successful refresh replaces the complete server-owned set;
- validation and commit failures retain the old set;
- `_registered_tool_names` and provenance change only after commit.

Tests must not use:

- conditional assertions that silently skip when a spy was not called;
- `except Exception: pass`;
- direct mutation of private registry entries to simulate success;
- a fake refresh fixture that returns before advertising tool capability;
- real network, provider, or subprocess calls.

## Required Checkpoints

After each extraction, run both the new tests and existing security/regression
tests. A green new test suite does not permit an existing suite to become red.

```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_registration_paths.py tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_tool_circuit_breaker.py -q
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_canonical_runtime.py tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py -q
.\.venv\Scripts\python.exe -m compileall -q tools hermes
git diff --check
```

Any regression blocks the task. Do not continue to another remediation task.

## Current Worktree Warning

The worktree contains partial Gate A changes and unrelated user files. Do not
reset, checkout, or overwrite entire files. Review `git diff` before editing.
If a partial Task 2 implementation replaced large existing blocks, repair it by
reconciling with the previous behavior and current accepted Gate A changes, not
by discarding unrelated work.

