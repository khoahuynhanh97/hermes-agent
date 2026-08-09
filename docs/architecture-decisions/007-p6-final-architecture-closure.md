# P6 Final Architecture Closure

## Canonical path

`User/channel -> Hermes -> 9Router -> reason_combo -> Skill -> MCP -> application/domain -> durable worker/events/delivery`

## Retirement table

| Component | Classification | Remaining callers | Replacement / reason |
|---|---|---|---|
| `mcp_servers/product_poc/` | `RETIRE_NOW` | None; code/test-only before retirement | `hermes_product` parity verified; removed and unregistered |
| `hermes/adapters/router/nine_router_gateway.py` | `RETIRE_NOW` | None; test-only before retirement | Hermes/9Router brain path; removed duplicate adapter |
| `hermes/ports/model_gateway.py`, `hermes/domain/model_request.py` | `RETIRE_NOW` | None after adapter retirement | Dead generic gateway contract; removed with adapter |
| `core/assistant_runtime.py` | `KEEP_COMPATIBILITY` | Telegram, GUI, CLI | Plan-shape facade only; Hermes owns semantics |
| `core/router.py` | `KEEP_CANONICAL` | Telegram, JobWatcher, tests | Deterministic command/mode aliases only |
| `core/ai_router.py` | `KEEP_COMPATIBILITY` | GUI status, JobWatcher status, explicit legacy fallback | No canonical generic routing; rollback/status only |
| `core/llm_gateway.py` | `KEEP_COMPATIBILITY` | Telegram, JobWatcher, HermesLLMGateway | Sends `reason_combo`; legacy fallback is explicit and disabled by default |
| `hermes/llm.py` | `KEEP_CANONICAL` | Affiliate gateways/scripts/Telegram | Typed structured-output wrapper for project services |
| `core/agent_jobs.py` | `KEEP_COMPATIBILITY` | Telegram, GUI, legacy tests | Legacy manifest/.agent_jobs workflows remain active |
| `core/job_watcher.py` | `KEEP_COMPATIBILITY` | Telegram, legacy worker/recovery scripts | Learning/media legacy workflow not fully migrated |
| `scripts/run_job_worker.py` | `KEEP_COMPATIBILITY` | Manual/legacy launcher | Starts the active legacy JobWatcher path |
| `scripts/affiliate_research_worker.py` | `KEEP_CANONICAL` | Manual affiliate queue entrypoint | Uses durable Hermes JobRepository and affiliate handler |
| `affiliate_worker.py` | `MIGRATE_FUTURE_FEATURE` | No repository production caller found | Older direct SQLite affiliate worker; retain until data-plane migration is scoped |
| `hermes/tools/auto_scheduler.py` | `KEEP_COMPATIBILITY` | `auto_crawler`, manual docs | Deterministic affiliate crawl scheduling; Hermes cron owns semantic schedules |
| Telegram `poll_outbox_loop` | `KEEP_COMPATIBILITY` | Telegram startup | Legacy `.agent_jobs` channel delivery; canonical DeliveryConsumer remains for canonical jobs |
| `core/knowledge_store.py` and review adapters | `KEEP_CANONICAL` | MCP/Telegram/GUI/services | Unique persistence and lifecycle compatibility; no duplicate transition owner |
| `tools/video_analyser.py`, `core/video_fetcher.py`, downloader/FFmpeg | `KEEP_CANONICAL` | Video/learning workflows | Specialized vision/audio/local media capabilities |

## Invariants

- No Product POC references remain in the repository.
- No MCP-to-MCP imports exist.
- Canonical workers contain no semantic reasoning or provider routing.
- Generic brain ownership remains external to application/domain code.
- Tests use a temporary knowledge root and do not require `G:\\My Drive`.

## Final known debt

- Legacy GUI direct Gemini workflows remain compatibility paths and require a
  UI-preserving migration before retirement.
- Legacy `.agent_jobs` Telegram delivery and JobWatcher workflows remain until
  their active user flows are migrated to canonical jobs/events.
- Full optional GUI/server test collection still requires existing workspace
  dependencies (`fastapi`) and has an unrelated prompt-studio API mismatch.
