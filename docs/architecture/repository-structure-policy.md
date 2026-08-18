# Hermes Repository Structure Policy

This document defines the canonical directory structure, ownership boundaries, and storage policies for the Hermes Agent Platform to prevent cluttering of the repository root.

---

## Directory Ownership & Boundaries

### 1. Code & Applications
- **`src/hermes/`**: Primary production Python source code. All production modules must reside under this directory. No python files or modules are permitted in the root folder.
- **`apps/`**: Deployable user interface applications (e.g. React frontend in `apps/web` or TUI in `apps/tui`). This directory is not a Python source root.
- **`tests/`**: Automated tests (unit, integration, and contract tests) and their test-only fixtures (e.g., `tests/fixtures/`). Tests must never be mixed with production code.
- **`scripts/`**: Operational, development, migration, and acceptance scripts.
  - `scripts/dev/`: Scripts helper for developer workflow.
  - `scripts/ops/`: Operations launchers and scripts.
  - `scripts/migrations/`: Database or config migrations.
  - `scripts/policies/`: Structural policies.

### 2. Resources & Documentation
- **`docs/`**: Documentation artifacts.
  - `docs/architecture-decisions/` (ADR): Architectural Decision Records.
  - `docs/runbooks/`: Operational guidelines and setup walkthroughs.
  - `docs/reports/`: Final reports, summaries, and walkthroughs.
- **`resources/`**: Static development or design resources (e.g., logos, assets) that are only required during development and do not need to be imported from the installed wheel.
- **`src/hermes/bundled/`**: Runtime resources packaged directly inside the distribution wheel. These include bundled skills, prompts, and localization files that the application materialize at runtime.

### 3. Runtime Data
- **`HERMES_DATA_DIR`**: Root for all mutable runtime data. Under no circumstances should mutable data, database files, workspaces, generated videos/audios, caches, or logs be created inside the repository root.

---

## Structural Asset Distinctions

To ensure strict path governance, the platform distinguishes between the following types of assets:

| Asset Type | Description | Allowed Location |
| :--- | :--- | :--- |
| **Source Code** | Production code modules and scripts. | `src/hermes/`, `tests/`, `scripts/` |
| **Bundled Resource** | Static skills/prompts packaged in wheel. | `src/hermes/bundled/` |
| **Application Static Asset** | Frontend UI elements, icons, components. | `apps/web/` / `apps/tui/` |
| **User Data** | Projects, profiles, configurations. | `HERMES_DATA_DIR/db/` |
| **Generated Asset** | Video Factory generated MP4, WAV, images. | `HERMES_DATA_DIR/workspaces/projects/<id>/generated/` |
| **Runtime Cache** | Temp directories, graphify graphs, pytest cache. | `HERMES_DATA_DIR/caches/` |
| **Temporary Artifact** | Scratch scripts, short-lived logs, temp media. | `HERMES_DATA_DIR/caches/scratch/` |
| **Test Fixture** | Mocks, static test data, test-only databases. | `tests/fixtures/` |
| **Documentation Artifact** | ADRs, runbooks, report walkthroughs. | `docs/` |

---

## Product Intelligence Boundaries
Product Intelligence data (original downloaded product images, snapshot data, evidence, and resource packs) remains owned by the external source. 

- Hermes does **not** copy or rename these files into the repository.
- Hermes only persists references (`asset_id`, `product_id`, `snapshot_id`, `sha256`, `mime_type`, and `source_uri` or local path references) within its database and resource models.

---

## Enforcement & Policy Rules
1. **No Production Code at Root**: Creation of `.py` files in the repository root is strictly forbidden.
2. **No Data in Repository**: Runtime databases (`*.sqlite`, `*.db`), logs (`*.log`), generated outputs (`*.mp4`, `*.wav`), or caches (`.pytest_cache`, `graphify-out/`) must not be written inside the repository root.
3. **No Traversals**: All path parameters must reject `..` segments and validate safe containment under the `HERMES_DATA_DIR` boundary.
