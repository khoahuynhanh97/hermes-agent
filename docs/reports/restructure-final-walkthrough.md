# Walkthrough: Restructure Final Micro-Closure

This document outlines the final micro-closure corrections and verification results for the Hermes Repository Restructure.

---

## Technical Corrections Completed

### 1. Normalized Bundled Resource Cache Path
- The runtime materialization path has been normalized from `HERMES_DATA_DIR/cache/bundled` to `HERMES_DATA_DIR/caches/bundled-resources` in [`src/hermes/runtime/resources.py`](file:///D:/work/hermes-agent/src/hermes/runtime/resources.py).
- Bundled skills are placed under `caches/bundled-resources/skills`.
- Added SHA-256 package content digest tracking (`_compute_package_digest()`) to trigger a re-materialization if the installed wheel changes.
- Safe automatic migration from the old cache path is implemented (`_migrate_old_cache()`) and clears the singular `cache` folder cleanly only if it is completely empty.
- Verified via focused tests in [`tests/hermes/test_runtime_resources.py`](file:///D:/work/hermes-agent/tests/hermes/test_runtime_resources.py).

### 2. Decoupled Graphify from RepoMap
- Graphify query and explain tasks have been completely decoupled from the RepoMap application layers.
- Created a self-contained helper at [`scripts/dev/graphify_graph_client.py`](file:///D:/work/hermes-agent/scripts/dev/graphify_graph_client.py) that reads directly from `caches/graphify-out/graph.json` via JSON node and link traversals.
- The helper does not import `hermes.application.core.repo_map` or any parts of the `hermes` package.
- Updated the PowerShell wrapper [`scripts/dev/graphify.ps1`](file:///D:/work/hermes-agent/scripts/dev/graphify.ps1) to call this decoupled client helper.

### 3. Removed Production Compatibility Code
- Deleted the legacy production-compatibility module `src/hermes/channels/api/compatibility/video_factory_api.py`.
- Replaced it with a test-only fixture adapter at [`tests/fixtures/video_factory_compatibility.py`](file:///D:/work/hermes-agent/tests/fixtures/video_factory_compatibility.py) to keep legacy aiohttp test suites green without dual FastAPI/aiohttp APIs in the production package.
- Updated test files [`tests/hermes/test_publishing1.py`](file:///D:/work/hermes-agent/tests/hermes/test_publishing1.py) and [`tests/hermes/test_tts1.py`](file:///D:/work/hermes-agent/tests/hermes/test_tts1.py) to load `build_routes` from the test fixture.

### 4. Test Dependency Declaration
- Declared `pytest-httpx` inside `[project.optional-dependencies]`'s `dev` list in [`pyproject.toml`](file:///D:/work/hermes-agent/pyproject.toml).
- This ensures it is reproducibly installed during `setup.ps1` setup phase.

### 5. Migration Semantics Integrity
- Preserved honest destination baseline semantics in [`D:\work\hermes-agent-data\migration-manifests\hermes-restructure.json`](file:///D:/work/hermes-agent-data/migration-manifests/hermes-restructure.json).
- The manifest registers `source_snapshot_available = false` and `verification_status = destination_baseline_created`.

---

## Verification Results

### 1. Focused Resource & Collision Tests
- `pytest tests/hermes/test_runtime_resources.py tests/tools/test_skill_collision.py`: **PASSED** (4/4 tests).

### 2. Graphify Active-Source Validation
- Exact Graphify Output Path: `D:\work\hermes-agent-data\caches\graphify-out\graph.json`
- Active production code nodes pointing to legacy paths (e.g. `agent/`, `tools/` at root): **0** nodes (Success).
- Restructured code nodes under `src/hermes/`: **24,916** nodes.
- Wrapper queries (`query` and `explain`) tested and working.

### 3. Backend Route Mapping & Test verification
- aiohttp-based tests using `pytest-httpx`: `test_publishing1.py` and `test_tts1.py` passed cleanly (15/15 tests).
- FastAPI route list verified.

### 4. Compilation & Whitespace checks
- `python -m compileall -q src`: **PASSED** (0 errors).
- `git diff --check`: **PASSED** (0 errors).
