# ADR-001: Hermes Agent Migration Audit (2026-08-05)

**Status:** Proposed
**Date:** 2026-08-05
**Scope:** `D:\work\hermes-agent`

## Context

Repo này không wrap Hermes Agent (NousResearch). Tự build Telegram assistant cho TikTok Video Factory use case. Audit (theo prompt 2026-08-05) kiểm tra các tính năng custom trùng với native Hermes Agent built-in.

## Decision

Repo tiếp tục độc lập với Hermes Agent. Không migrate. Lý do:

1. **Scope khác nhau.** Repo này là TikTok Video Factory production tool. Hermes Agent (NousResearch) là general-purpose CLI agent.
2. **Features cần thiết không có ở Hermes Agent built-in.** Affiliate pipeline (Shopee CSV, Crawl4AI, Telegram review), Vietnamese knowledge learning, storyboard generation — đều custom.
3. **Migrating = high-risk rewrite.** Repo có 100+ files, ~10K LOC, 39+40 skills, 5 docs plans đã execute. Migration toàn bộ costs hơn lợi ích.

## Trạng thái tính năng trùng Hermes Agent (sau audit)

| Hermes Agent (NousResearch) built-in | Repo hiện tại | Trạng thái |
|---|---|---|
| Multi-platform gateway (Telegram, Discord, Slack, WhatsApp, Signal) | `telegram_bot.py` only | Custom, không multi-platform |
| Built-in cron scheduler | Polling worker loops | Custom polling, không dùng cron |
| `approvals.mode` HITL | `handle_callback` inline buttons | Custom, không dùng built-in |
| Autonomous skill creation | Static skills only | Chưa có |
| Reasoning loop / agent | Deterministic keyword routing | Custom (xem `core/assistant_runtime.py:classify`) |
| LLM provider (OpenAI, Anthropic, OpenRouter) | `core/llm_gateway.py` (custom) | Custom |
| Knowledge graph (Honcho) | `hermes/knowledge.py` (FTS5 SQLite) | Custom |
| FTS5 session search | Native FTS5 (`hermes/knowledge.py`) | Custom |
| `agentskills.io` skill standard | Compatible | OK |

## Từ chối đề xuất (prompt gốc)

### Đề xuất 1: Xóa `telegram_gateway.py` vì trùng Hermes Agent built-in
- **Từ chối.** Repo KHÔNG có `telegram_gateway.py`. Toàn bộ logic ở `telegram_bot.py`. Xem Plan 2026-08-04 task 5.

### Đề xuất 2: Xóa `link_router.py` vì deterministic if/else
- **Từ chối.** Repo KHÔNG có `link_router.py`. Có `core/assistant_runtime.py:classify` và `telegram_bot.py:is_product_research_script_request` — cả hai keyword-based. Acceptable cho scope TikTok factory. Migration to skill-based routing = P3.2 (high risk).

### Đề xuất 3: Xóa `skill_auto_learner.py` vì trùng native skill creation
- **Từ chối.** Repo KHÔNG có `skill_auto_learner.py`. Auto skill creation = priority thấp vì 40 static skills đã cover use cases.

### Đề xuất 4: Xóa `crawl4ai` vì trùng `mcp-fetch`
- **Từ chối.** Repo KHÔNG dùng MCP. `crawl4ai_fetcher.py` + `static_fetcher.py` bổ sung nhau (static first, crawl4ai fallback cho JS). Cần cả hai.

### Đề xuất 5: Dùng Hermes built-in approval + cron
- **Từ chối cho high-priority build.** Custom polling + custom HITL đã mature và test. Migration = P3.1 + P3.3. Có thể cân nhắc nếu adopt Hermes Agent (P3.3).

### Đề xuất 6: Xóa `data/skills/graphify` (trùng MCP)
- **Từ chối.** Repo KHÔNG có `data/skills/graphify`. graphify skill ở `.agents/skills/graphify/` (upstream copy, tôi cài ở turn trước). DB node meta `graphify-out/GRAPH_REPORT.md` để lưu audit facts.

### Đề xuất 7: graphify = Knowledge Base
- **Từ chối.** KB native = `hermes/knowledge.py` (FTS5). graphify dùng cho code mapping, không thay thế KB.

## Refactor Plan (chi tiết ở audit report)

| Priority | Action | Risk | Effort |
|---|---|---|---|
| P1.1 | Doc `data/skills/` không tồn tại | 0 | 5 min |
| P1.2 | Remove `telegram_bot.md` | 0 | 1 min |
| P1.3 | Doc graphify usage | 0 | 10 min |
| P2.1 | Remove root `affiliate_worker.py` | Medium | 30 min |
| P2.2 | Remove `telegram_notifier.py` | Medium | 15 min |
| P2.3 | Consolidate `core/llm_gateway.py` + `hermes/llm.py` | High | 2 hrs |
| P3.1 | Merge worker loops | High | 4 hrs |
| P3.2 | Skill-based routing (markdown) | High | 1 day |
| P3.3 | Migrate to Hermes Agent (NousResearch) | Very high | 1 week |

## Consequences

### Positive
- Không tốn effort migrate. Repo tiếp tục evolve độc lập.
- 40 skills + 5 docs plans + 432 tests = foundation mature.
- Knowledge graph (graphify) add-on cho code analysis, không thay thế.

### Negative
- Repo không "nhanh lên" khi Hermes Agent có updates.
- Phải tự maintain cron, approval, multi-platform.
- Có thể duplicate effort nếu sau này muốn expand scope.

### Risks
- Nếu user reassign = migrate to Hermes Agent, cost cao.
- Custom code diverges từ upstream Hermes Agent → maintenance burden.

## References

- `graphify-out/GRAPH_REPORT.md` § Audit Notes (2026-08-05)
- `docs/superpowers/plans/2026-08-04-product-research-script-supervisor.md`
- `docs/hermes-assistant-architecture.md`
- `docs/affiliate-product-research-user-guide.md`
- `docs/status/hermes-current-feature-report.md`
