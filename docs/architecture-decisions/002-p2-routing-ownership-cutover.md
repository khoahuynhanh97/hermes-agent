# P2 Routing Ownership Cutover

Status: implemented 2026-08-06

## Target ownership

Natural-language semantic decisions belong to the real Hermes runtime, loaded
skills, and MCP tool schemas. The Product path is:

`Channel -> Hermes reason_combo -> affiliate-product-research skill -> Product MCP -> application/domain/SQLite`

Telegram remains a protocol adapter. It owns command aliases, callback parsing,
session/user identifiers, human approval and response rendering. It does not
identify Product intent, choose a capability, or build a Product plan.

## Caller graph

| Component | Before P2 caller/responsibility | After P2 responsibility | Retirement status |
| --- | --- | --- | --- |
| `core/assistant_runtime.py` | `telegram_bot.py`, `apps/telegram/handlers/assistant.py`, GUI and CLI called `classify()`/`build_plan()`; keyword rules selected Product and other modules | Compatibility plan facade only; all free text is `assistant_core`; Hermes owns semantic routing | `KEEP_TEMPORARY`: legacy CLI/GUI callers remain |
| `core/router.py` | Telegram and `core/job_watcher.py` used command-to-mode aliases; included `/review` protocol alias | Deterministic command/mode protocol routing only; no free-text Product semantics | `STILL_REQUIRED`: active job aliases remain |
| `telegram_bot.py` | Imported runtime and contained an unused Product keyword detector; also owns command handlers and callbacks | Keeps transport, explicit commands, HITL and rendering; Product detector removed | `KEEP_TEMPORARY`: monolithic transport remains |
| `apps/telegram/handlers/assistant.py` | Called a removed `handle_request()` API | Uses compatibility `build_plan()`/formatter; no semantic Product selection | `KEEP_TEMPORARY` |
| `product_research_script` legacy workflow | CLI/application callers and old intent tests | Preserved for compatibility; P2 Product ownership is `skills/affiliate-product-research` + Product MCP | `KEEP_TEMPORARY`: deletion requires P6 migration parity |
| `video_factory`, `knowledge_learner`, `coding_agent`, `tool_builder` | Existing legacy commands/jobs/planners | Preserved; no new P2 MCP or semantic cutover claimed | `STILL_REQUIRED` |

No component is `READY_TO_RETIRE`: each has remaining callers or lacks a
replacement parity proof for its non-Product compatibility surface.

## Product acceptance boundary

The configured external Hermes installation uses model `reason_combo`, the
canonical `affiliate-product-research` skill, and the `hermes_product` MCP
server. The P0 composite server remains registered separately for regression;
P2 does not delete it.
