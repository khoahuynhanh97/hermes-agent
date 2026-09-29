# Gate 2 Candidates: Architecture, Missing Targets & Service Coexistence

This document catalogs items identified during Gate 1 for downstream triage, implementation, or reconciliation in Gate 2.

---

## 1. Taxonomy Breakdown Summary (From `module-inventory.csv`)

- **`ACTIVE`**: 50
- **`INFRASTRUCTURE`**: 5
- **`OPTIONAL`**: 0
- **`MIGRATION`**: 3
- **`UNKNOWN`**: 66
- **`DEAD_CANDIDATE`**: 0
- **`SHADOW_CANDIDATE`**: 0
- **Total Modules Cataloged**: 124

---

## 2. Candidate Inventory

### A. Missing Process Runner Targets (HP-002)
- **Target 1**: `hermes_personal/capabilities/mcp_runner.py` (MISSING_TARGET, referenced in `hermes_personal/runtime/processes.py:153`)
- **Target 2**: `hermes_personal/gateway/platforms/telegram_runner.py` (MISSING_TARGET, referenced in `hermes_personal/runtime/processes.py:193`)
- **Gate 2 Recommendation**: Either implement standalone runner entrypoints under `hermes_personal` or adjust `build_process_topology` defaults so they do not require unmerged scripts.

### B. FastMCP Video Factory Packaging & Registry Binding (`src/hermes/**`)
- **Modules**: `src/hermes/mcp/video_factory/server.py`, `src/hermes/domain/video_factory.py`, `src/hermes/application/video_factory_service.py`, `src/hermes/adapters/sqlite/video_factory_repository.py`, `src/hermes/adapters/google/vertex_video_provider.py`
- **Current Role**: Standalone FastMCP server providing Video Factory wire tools (`create_brief`, `create_scene_plan`, `create_storyboard`, `render`, `export`) tested in `tests/mcp_servers/test_video_factory_server.py`.
- **Packaging Gap**: Excluded from `pyproject.toml` package discovery (`SRC_LAYOUT_PACKAGING_GAP`).
- **Gate 2 Recommendation**: Resolve packaging layout (e.g. standalone MCP server distribution vs explicit `src` package discovery) and wire live tool discovery.

### C. Documentation Synchronization for `WorkflowEngine`
- **Document**: `docs/architecture.md` (lines 140-146)
- **Status**: `DOC_STALE_SOURCE_FIXED`
- **Gate 2 Recommendation**: Update `docs/architecture.md` to reflect that the two aggregate commit and `job_succeeded` consistency defects have been resolved and verified in `tests/hermes_personal/workflows/test_engine.py`.
