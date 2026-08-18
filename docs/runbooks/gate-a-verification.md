# Gate A Verification Runbook

This document records the verification evidence, test execution results, and security invariants for **Gate A (Platform Standardization & Security Governance)** remediation.

---

## Security Invariants Proved

1. **Explicit Capability Metadata at Registration**:
   - Every model-visible production tool possesses an immutable `CapabilityDescriptor` assigned at registration time.
   - Dispatch reads `entry.descriptor` directly and fails closed (`missing_descriptor`) if a registered entry lacks a descriptor.
   - Capability policy is resolved via exact tool name / toolset policy inventory (`CapabilityPolicyResolver`), never by substring matching or runtime name inference.

2. **Unified Candidate Registration Pipeline for MCP**:
   - Eager discovery (`_register_server_tools`), lazy cache restore (`_register_from_cache_sync`), and server refresh (`MCPServerTask._refresh_tools`) all emit `RegistrationCandidate` objects with final prefixed `registry_name`.
   - `validate_registration_candidates` is a pure function that checks schema validity, handler callability, exact duplicate deduplication (`raw_name`, `registry_name`, `origin`, `schema`, `handler is first.handler`, `descriptor`), descriptor wire_name/toolset alignment, and ownership snapshot collisions.
   - `commit_toolset_batch` under `registry._lock` performs all-or-none atomic commits of tools, checks, aliases, and single `_generation` increment.

3. **Fail-Closed Secret Allowlists**:
   - Absent or `None` `secret_allowlist` configuration defaults to an empty set (`set()`), rejecting any interpolated `${VAR}` or `${env:VAR}` fail-closed with `SecretScopeError`.
   - `_build_safe_env` supports `${VAR}`, `${env:VAR}`, hyphens, and dots via `_ENV_VAR_PATTERN` and `_env_ref_name`. Unallowlisted secret-source variables are blocked from passing to subprocesses.

4. **Principal Ingress & Channel Binding**:
   - Channel adapters (CLI, oneshot, gateway, API server, Telegram, GUI) create authenticated `PrincipalContext` instances at channel boundaries and bind them using `principal_scope()`.
   - `AIAgent.run_conversation()` consumes existing context from `current_principal` and never invents identity.
   - Session-scoped tool dispatch injects `owner_user_id` from `principal.owner_user_id` and overwrites model-supplied spoofed parameters.

5. **Governed Skill Contracts**:
   - `validate_bundled_skill_tools` validates all bundled skills against a coherent `CapabilityCatalog` snapshot.
   - Every governed tool-using skill declares `allowed-tools` and `requires_tools`; documentation-only skills declare `documentation_only: true`.

---

## Test Execution Results

### 1. Focused Gate A Verification Matrix (79 tests)
```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_platform_architecture_contract.py tests\tools\test_mcp_tool_security.py tests\tools\test_mcp_registration_paths.py tests\tools\test_capability_registration.py tests\hermes\test_canonical_runtime.py tests\hermes\test_capability_catalog.py tests\hermes\test_principal_ingress.py tests\hermes\test_channel_principal_integration.py tests\tools\test_skill_contracts.py -q
```
**Result**: `79 passed in 14.34s`

### 2. Regression & Circuit Breaker Suite (15 tests)
```powershell
.\.venv\Scripts\python.exe -m pytest tests\tools\test_mcp_tool_circuit_breaker.py tests\hermes\test_telegram_authorization.py tests\hermes\test_telegram_product_research_routing.py tests\workers\test_canonical_job_worker.py tests\hermes\test_product_intelligence_integration.py -q
```
**Result**: `15 passed in 5.60s`

### 3. Production Code Compilation
```powershell
.\.venv\Scripts\python.exe -m compileall -q agent core gateway gui hermes hermes_cli mcp_servers providers server tools workers
```
**Result**: `Pass (exit code 0)`

### 4. Git Diff Check
```powershell
git diff --check
```
**Result**: `Pass (exit code 0)`

### 5. Known Recorded Baseline (2 tests)
```powershell
.\.venv\Scripts\python.exe -m pytest tests\hermes\test_p2_routing_ownership.py -q
```
**Result**: `2 failed` (Expected routing ownership baseline failures reserved for Task 10 / Gate E channel convergence).
