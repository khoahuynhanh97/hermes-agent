# Hermes Assistant Rollout Plan

Goal: grow the current Hermes repo into a general assistant platform while
keeping the existing video factory stable.

## Sprint 1 - Foundation

### Job 016 - Assistant architecture and CLI foundation

Status: done / foundation added.

Deliverables:

- `docs/hermes-assistant-architecture.md`
- `docs/hermes-assistant-rollout-plan.md`
- `core/assistant_runtime.py`
- `scripts/hermes_assistant_cli.py`
- `docs/tool-manifest-format.md`
- `reports/job_016_hermes_assistant_foundation.md`

Acceptance:

- CLI starts.
- CLI can classify and split a multi-part request.
- No production video factory behavior changes.

### Job 017 - Repo map and source scanner

Status: done / source map added.

Purpose: reduce token cost before coding tasks.

Deliverables:

- `core/repo_map.py`
- `scripts/hermes_repo_map.py`
- `data/repo_maps/hermes_repo_map.json`

Behavior:

- Index files by path, extension, size, key symbols, imports, and recent mtime.
- Ignore runtime outputs, secrets, downloads, cache, `.git`, and large binaries.
- Let coding agent ask for relevant paths before opening full files.

Acceptance:

- Repo map builds without network access.
- It can find likely files for terms like `telegram`, `knowledge`, `job_watcher`,
  `dedup`, and `video_downloader`.

### Job 018 - Coding agent dry-run planner

Status: done / dry-run planner added.

Purpose: turn a coding request into a safe implementation plan.

Deliverables:

- `core/coding_agent.py`
- `scripts/hermes_code_agent.py`

Behavior:

- Input: natural-language coding request.
- Use repo map to select files.
- Read selected files.
- Produce a patch plan, touched files, risks, and verification commands.
- No file writes yet.

Acceptance:

- Given "add Telegram report retry", it proposes focused files and checks.
- Report is written under `reports/`.

## Sprint 2 - Controlled execution

### Job 019 - Patch permission and apply layer

Status: done / permission gate and patch executor added.

Purpose: safely let Hermes edit code.

Deliverables:

- `core/patch_executor.py`
- `core/permission_gate.py`

Behavior:

- Apply unified diffs only under allowed repo roots.
- Block `.env`, sessions, secrets, binaries, `.git`, and generated caches.
- Always write a before/after report.

Acceptance:

- Allowed patch succeeds.
- Blocked patch refuses sensitive paths.

### Job 020 - Verification runner

Status: done / allowlisted verification runner added.

Purpose: make coding changes self-checking.

Deliverables:

- `core/verification_runner.py`

Behavior:

- Run focused commands from plan.
- Capture stdout/stderr to report files.
- Support py_compile, unit scripts, and later frontend/build commands.

Acceptance:

- Can run a syntax check on changed Python files.
- Failure is reported clearly without hiding logs.

## Sprint 3 - Tool builder

### Job 021 - Tool registry and manifest loader

Status: done / manifest registry added.

Purpose: make small Hermes tools reusable.

Deliverables:

- `core/tool_registry.py`
- `tools/manifests/*.json`

Behavior:

- Load tool manifests.
- Validate required fields.
- List runnable tools.

### Job 022 - Tool scaffold/export

Status: done / scaffold and export CLI added.

Purpose: let Hermes create and package new tools.

Deliverables:

- `scripts/hermes_tool.py`
- `core/tool_exporter.py`

Behavior:

- `create`: scaffold a tool folder.
- `run`: run a local tool.
- `export`: zip the tool with manifest and README.

## Sprint 4 - Telegram and GUI integration

### Job 023 - Assistant Telegram bridge

Status: done / assistant planning commands added.

Purpose: route Telegram messages into the assistant runtime.

Behavior:

- Commands:
  - `/assistant <request>`
  - `/code_plan <request>`
  - `/tool_create <name>`
- Coding write actions still require explicit local approval.

### Job 024 - GUI assistant tab

Status: done / dry-run assistant tab added.

Purpose: give a visual control center.

Behavior:

- Show assistant requests, plans, permissions, verification logs, and reports.

## Operating rule

Do not move video factory code during these jobs. First build the assistant layer
around it, then gradually extract modules only when the interfaces are stable.
