# Executive Summary: Runtime Truth Audit (Gate 0 & Gate 1 Rework)

**Audit Scope**: Gate 0 (Preservation & Baseline) & Gate 1 (Runtime Truth, Topology & Inventory Audit)  
**Repository Root**: `D:/work/hermes-upstream-rearchitecture`  
**Current Branch**: `codex/hermes-upstream-rearchitecture`  
**Revision (HEAD)**: `b193b1d07e800d7109e77f5ae5f61fa66f2fb454`  
**Date (UTC)**: 2026-08-29 19:05:48 UTC  
**Decision**: **COMPLETE** (All 8 rework tasks verified and proven)

---

## 1. Key Audit Findings & Corrections

1. **Working-Tree Preservation**: All 17 pre-audit modified and untracked files match their original `preservation_manifest_start.json` SHA-256 digests byte-for-byte.
2. **Real CLI Call Path**: `hermes start` traced step-by-step from `pyproject.toml:373` $\rightarrow$ `hermes_cli/main.py:12418` $\rightarrow$ `PluginManager` $\rightarrow$ `hermes_personal/runtime/plugin.py:11` $\rightarrow$ `setup_start_parser` / `handle_start` $\rightarrow$ `StartupCoordinator` $\rightarrow$ `build_process_topology` $\rightarrow$ `Supervisor`.
3. **Route Inventory**: Reconciled mounted routes from actual source (`/api/turn`, `/api/omni/turn`, `/api/events`, `/api/events/replay`, `/api/operator/command`, `/api/artifacts/{artifact_id}`, `/health/live`, `/health/ready`, `/healthz`). No nonexistent `/api/v1/...` routes exist in source.
4. **Per-Module Evidence & Source Provenance**: Eliminated all directory prefix heuristics. Added `source_provenance` column derived dynamically via Git (`TRACKED_HEAD`, `TRACKED_MODIFIED`, `WORKTREE_UNTRACKED`). `/hoc` capability files explicitly identified as worktree-only / uncommitted.
5. **Config Layers Clarified**: Clearly separated `RuntimeConfig` dataclass defaults (`enable_mcp: True`, `enable_telegram: True`) from `runtime-config.local.yaml.example` (`enable_mcp: False`, `enable_telegram: False`) and explicit operator config.
6. **`src/hermes` Re-Audited**: Accurately documented `SRC_LAYOUT_PACKAGING_GAP`. Classified `src/hermes` modules as `UNKNOWN` (TESTED). `MCPVideoFactoryAdapter` consumes compatible wire-tool names from a registry; binding to this specific server requires separate discovery/runner wiring.
7. **WorkflowEngine Contradiction Reconciled**: Identified as `DOC_STALE_SOURCE_FIXED` (source in `hermes_personal/workflows/engine.py` and `tests/hermes_personal/workflows/test_engine.py` proves both architectural defects resolved).
8. **100% Semantic & Path Citation Validation**: Programmatically validated all file paths and semantic constraints across all deliverables with zero nonexistent citations.

---

## 2. Taxonomy Breakdown (124 Cataloged Files)

| Classification | Count | Description |
| :--- | :---: | :--- |
| **`ACTIVE`** | **50** | Verified active production callers in `hermes start` turn path, supervisor, or upstream CLI/gateway closure. |
| **`INFRASTRUCTURE`** | **5** | Storage connection helpers, middleware, observability data structures, package init files with active exports. |
| **`OPTIONAL`** | **0** | Gated modules with exact configuration gates. |
| **`MIGRATION`** | **3** | Cutover parity and retirement validation modules (`hermes_personal/cutover/`). |
| **`UNKNOWN`** | **66** | Modules with no verified active callers in `hermes start` production closure (including `src/hermes/**` due to packaging gap). |
| **`DEAD_CANDIDATE`** | **0** | (Missing runner targets `mcp_runner.py` and `telegram_runner.py` recorded as `MISSING_TARGET` under HP-002). |
| **`SHADOW_CANDIDATE`** | **0** | Zero (no module proven to shadow an active canonical duplicate). |
