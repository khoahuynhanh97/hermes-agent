# Hermes Repository Architecture & Structure

## Overview
Hermes is a production agent platform with clear bounded contexts and strict structural boundaries:
- **Source root**: `D:\work\hermes-agent` (Code, manifests, tests, scripts only)
- **Runtime data**: `D:\work\hermes-agent-data` (Databases, logs, media, outputs only)
- **Root Python Policy**: Zero `.py` files at repository root. All Python modules reside in canonical packages.

---

## Canonical Directory Layout (Depth 2)

```text
D:\work\hermes-agent
├── agent/                         # Turn execution, conversation loop & runtime agent
│   ├── conversation_loop.py
│   ├── turn_runtime.py
│   ├── runtime_agent.py
│   ├── model_tools.py
│   └── trajectory_compressor.py
│
├── hermes/                        # Domain, Application Services, Ports & Adapters
│   ├── domain/                    # Entities & Value Objects (ProductResource, etc.)
│   ├── application/               # Application Services (AssetProjection, Workflow, etc.)
│   ├── ports/                     # Repository interfaces
│   ├── adapters/                  # Infrastructure (SQLite, Filesystem)
│   ├── capabilities/              # Capability registry & definitions
│   ├── security/                  # Principals, security boundary & ingress validation
│   ├── runtime/                   # Config, constants, logging, time, utils, bootstrap
│   │   ├── bootstrap.py
│   │   ├── config.py
│   │   ├── constants.py
│   │   ├── logging.py
│   │   ├── time.py
│   │   └── utils.py
│   └── state/                     # State service, schema, search, portability
│       ├── service.py
│       ├── common.py
│       ├── portability.py
│       ├── schema.py
│       └── search.py
│
├── hermes_cli/                    # CLI Transport & Presentation Layer
│   ├── main.py
│   ├── classic_runtime.py
│   └── oneshot.py
│
├── tools/                         # Tool Registry, native tools, MCP security wrapper
│   ├── registry.py
│   ├── mcp_tool.py
│   ├── toolsets.py
│   └── toolset_distributions.py
│
├── mcp_servers/                   # Hermes-owned MCP servers
│   ├── serve.py
│   └── video_factory/
│
├── workers/                       # Durable Execution & Background Processors
│   ├── job_worker.py
│   ├── affiliate_worker.py
│   ├── batch_runner.py
│   └── mini_swe_runner.py
│
├── server/                        # FastAPI Composition Root (Port 8000)
│   ├── app.py
│   ├── dependencies.py
│   ├── routes/
│   └── compatibility/
│       ├── web_studio.py
│       └── video_factory_api.py
│
├── gateway/                       # Channel Integrations & Transport Adapters
│   ├── run.py
│   └── platforms/telegram/
│       ├── bot.py
│       └── notifier.py
│
├── gui/                           # Desktop GUI Modules
│   ├── main.py
│   └── tabs/
│
├── providers/                     # Model Provider Adapters (LLM, Vision, Video, TTS)
├── web/                           # React + Vite Operator Console (Port 3000)
├── skills/                        # Skill Manifests & Declarations
├── scratch/                       # Transient scratch workspace
│
├── tests/                         # Automated Test Suite (100% Deterministic)
│   ├── agent/
│   ├── hermes/
│   ├── tools/
│   ├── workers/
│   ├── server/
│   ├── integration/
│   └── acceptance/
│
├── scripts/                       # Categorized Utility & Acceptance Scripts
│   ├── ops/                       # Operational launchers, doctor, backups, clean
│   │   └── windows/               # Windows bat/vbs launchers & cleaners
│   ├── dev/                       # Diagnostics, profiling, test runners
│   ├── acceptance/                # Deterministic E2E acceptance tests
│   │   └── live/                  # Live Paid/Credential scripts (Vertex, Veo, ElevenLabs)
│   └── migrations/                # Database & Schema migrations
│
├── docs/                          # Architectural documentation & ADRs
│   ├── architecture-decisions/    # ADR-001 through ADR-010
│   ├── architecture/
│   ├── runbooks/
│   ├── reports/
│   └── specs/
│
├── .env.example
├── .gitignore
├── AGENTS.md
├── README.md
├── pyproject.toml
├── requirements.txt
├── requirements-crawl4ai.txt
├── setup.ps1
└── start.ps1
```

---

## Root Allowlist
The root directory is strictly constrained to the following metadata and entry point files:
- `.env`, `.env.example`, `.gitignore`
- `AGENTS.md`, `README.md`
- `pyproject.toml`, `requirements.txt`, `requirements-crawl4ai.txt`
- `setup.ps1`, `start.ps1`

No `.py` files are permitted in the root directory.
