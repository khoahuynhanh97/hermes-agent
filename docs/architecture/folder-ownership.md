# Hermes Repository Folder Ownership Analysis

## Overview
This document establishes the canonical folder ownership, responsibility boundaries, and target migration locations for every top-level directory in `D:\work\hermes-agent`.

---

## Folder Ownership & Classification Table

| Folder | Current Responsibility | Actual Callers | Classification | Final Location | Action | Reason |
|:---|:---|:---|:---|:---|:---|:---|
| `.agents` | Antigravity / Agent custom skills & rules | Antigravity IDE / Agent runtime | tooling-metadata | `.agents/` | keep | Tooling metadata required by agent environment. |
| `.agent_jobs` | Agent background job execution state | Agent runtime job manager | runtime-data | `D:\work\hermes-agent-data\jobs\agent\` | externalize | Runtime job data must live in `HERMES_DATA_DIR`. |
| `.claude` | Claude Code project metadata | Claude CLI | tooling-metadata | `.claude/` | keep | Tooling configuration. |
| `.git` | Git VCS repository | Git VCS | tooling-metadata | `.git/` | keep | Core repository version control. |
| `.superpowers` | Agent workflow superpowers specifications | Antigravity IDE | tooling-metadata | `.superpowers/` | keep | Agent workflow documentation & specs. |
| `.venv` | Canonical Python 3.12 virtual environment | Python runtime, CLI, tests | dependency-installation | `.venv/` | keep | Canonical Python runtime for the platform. |
| `acp_adapter` | Agent Control Protocol JSON-RPC transport | ACP clients, CLI | canonical-source | `src/hermes/channels/acp/` | move | Transport adapter for Agent Control Protocol. |
| `agent` | Conversation loop, TurnRuntime, model tools | Hermes CLI, Telegram, Server | canonical-source | `src/hermes/agent/` | move | Core conversational agent & reasoning engine. |
| `apps` | Application launchers & entry wrappers | Web Studio, Telegram, Workers | application-ui | `apps/` | merge | Canonical home for all UI applications (web, gui, tui, remotion). |
| `assets` | Static brand logos, icons, UI images | Web UI, GUI, documentation | static-resource | `resources/assets/` | move | Static resources must be centralized under `resources/`. |
| `audio` | Sound effect samples & TTS test audio | TTS tools, Sound preview | static-resource | `resources/audio/` | move | Static media assets. |
| `core` | Legacy shared components (jobs, routing, learning) | CLI, Telegram, GUI | canonical-source | `src/hermes/application/` & `src/hermes/domain/` | merge | Distribute into clean domain/application layers. |
| `cron` | Cron scheduling engine & jobs blueprint | Scheduler daemon, CLI | canonical-source | `src/hermes/scheduling/` | move | Dedicated scheduling subsystem. |
| `data` | Local test files & database fixtures | Tests, acceptance scripts | runtime-data | `D:\work\hermes-agent-data\data\` | externalize | Non-static runtime data. |
| `docs` | Architectural documentation, ADRs, specs | Developers, agents | documentation | `docs/` | keep | Central documentation repository. |
| `downloaders` | Video/Audio download adapters (ytdlp, direct) | Media tools, Scraper | canonical-source | `src/hermes/integrations/downloaders/` | move | External service integration. |
| `editor` | Video editing, cutting, subtitle generation | Video Factory, Worker | canonical-source | `src/hermes/video/editor/` | move | Video processing domain subsystem. |
| `gateway` | Channel ingress, session coordinator, telegram | Channels, webhooks | canonical-source | `src/hermes/channels/` | move | Multi-channel gateway subsystem. |
| `graphify-out` | Generated code knowledge graph cache | Graphify tool | generated-cache | `D:\work\hermes-agent-data\caches\graphify\` | externalize | Ephemeral analysis cache. |
| `gui` | Desktop GUI application (CustomTkinter) | `main_gui.py`, desktop users | application-ui | `apps/gui/` | move | Desktop operator application. |
| `hermes` | Domain models, application services, ports, adapters | Core platform | canonical-source | `src/hermes/` | move | Root canonical Hermes package. |
| `hermes_agent.egg-info` | Generated setuptools build metadata | Setuptools build | generated-cache | N/A | delete-generated | Ephemeral packaging artifact. |
| `hermes_cli` | Interactive CLI presentation & commands | Developer terminal | canonical-source | `src/hermes/channels/cli/` | move | Interactive CLI transport channel. |
| `jobs` | Durable worker job state files | Job worker | runtime-data | `D:\work\hermes-agent-data\jobs\workers\` | externalize | Runtime job files. |
| `knowledge_base` | SQLite knowledge database & JSON docs | Knowledge tools | runtime-data | `D:\work\hermes-agent-data\knowledge\database\` | externalize | Persistent user knowledge data. |
| `locales` | I18n translation catalogs | CLI, UI | static-resource | `resources/locales/` | move | Static internationalization strings. |
| `logs` | Runtime execution logs | Application logging | runtime-data | `D:\work\hermes-agent-data\logs\` | externalize | Runtime logs. |
| `mcp_servers` | Video Factory & internal MCP servers | Claude Desktop, Hermes Agent | canonical-source | `src/hermes/mcp/` | move | Hermes MCP servers. |
| `native` | C/C++ extensions (FTS5 CJK SQLite tokenizer) | SQLite adapter | canonical-source | `src/hermes/integrations/native/` | move | Native binary integrations. |
| `node_modules` | Root Node dependencies | Web build (redundant) | dependency-installation | N/A | delete-generated | Redundant root copy; `apps/web` has its own. |
| `obsidian_vault` | User obsidian vault knowledge store | Knowledge sync tool | runtime-data | `D:\work\hermes-agent-data\knowledge\obsidian\` | externalize | User document storage. |
| `plugins` | Dynamic capability plugins (memory, platforms) | Plugin loader | canonical-source | `src/hermes/integrations/plugins/` | move | Extensibility plugins. |
| `projects` | User project workspaces & video media | Video Factory UI | runtime-data | `D:\work\hermes-agent-data\workspaces\projects\` | externalize | User media & project state. |
| `prompt_library` | Prompt templates for video & research | Script generator | static-resource | `resources/prompts/` | move | Static prompt templates. |
| `prompt_output` | Generated prompt text files | Prompt compiler | runtime-data | `D:\work\hermes-agent-data\outputs\prompts\` | externalize | Generated text outputs. |
| `providers` | LLM, TTS, Video model adapters | Agent runtime | canonical-source | `src/hermes/integrations/providers/` | move | Model provider integrations. |
| `remotion_renderer` | Remotion React video rendering bundle | Video Factory export | application-ui | `apps/remotion/` | move | Video rendering frontend app. |
| `runtime_logs` | Structured audit & telemetry logs | Observability engine | runtime-data | `D:\work\hermes-agent-data\logs\runtime\` | externalize | Runtime execution telemetry. |
| `scratch` | Transient developer scratch scripts & tests | Developers | generated-cache | `D:\work\hermes-agent-data\caches\scratch\` | externalize | Ephemeral scratch directory. |
| `scripts` | Ops, dev, acceptance, migration scripts | Operators, CI/CD | operational-script | `scripts/` | keep | Centralized operational scripts. |
| `server` | FastAPI web backend server | Web UI, MCP, REST | canonical-source | `src/hermes/channels/api/` | move | REST API transport channel. |
| `skills` | Hermes skills definitions & manifests | Agent skill guard | static-resource | `resources/skills/` | move | Static skill declarations. |
| `tests` | Automated pytest test suite | CI/CD, developers | test | `tests/` | keep | Canonical test suite. |
| `tools` | Tool registry, native tools, MCP security | Agent runtime | canonical-source | `src/hermes/tools/` | move | Tool registry & execution engine. |
| `tui_gateway` | Terminal UI RPC gateway | TUI frontend | canonical-source | `src/hermes/channels/tui/` | move | TUI channel gateway. |
| `ui-tui` | React/Node based Terminal UI app | Operator terminal | application-ui | `apps/tui/` | move | Terminal UI operator app. |
| `venv` | Duplicate virtual environment | Legacy | dependency-installation | N/A | delete-dead | Duplicate environment; `.venv` is canonical. |
| `web` | React + Vite Operator Console | Web users | application-ui | `apps/web/` | move | Web operator console frontend. |
| `workers` | Background durable job workers | Background runner | canonical-source | `src/hermes/workers/` | move | Background worker daemon. |
| `workspace` | Ephemeral scratch workspace | Agent file operations | runtime-data | `D:\work\hermes-agent-data\workspaces\` | externalize | Ephemeral agent runtime workspace. |
