# Hermes Assistant Architecture

Hermes Assistant is the umbrella system. Hermes TikTok / video factory is one
application inside it, not the whole product.

## Product shape

Hermes Assistant should support three first-class capabilities:

1. Video factory
   - Crawl or receive video sources.
   - Analyze product / hook / CTA / scene structure.
   - Produce scripts, prompts, storyboard, voiceover, workflow files, and reports.

2. Knowledge learner
   - Receive Telegram messages, files, reports, and links.
   - Extract reusable lessons.
   - Send proposals to review queue.
   - Only approved knowledge enters the durable knowledge base.

3. Coding agent
   - Run as a terminal assistant similar to a lightweight Codex / Claude Code flow.
   - Inspect source code, create plans, apply patches after approval, run checks, and write reports.
   - Use repo maps and small focused context to reduce model cost.

The fourth supporting capability is tool building:

4. Tool builder
   - Create small reusable local tools.
   - Each tool has a manifest, runner, permissions, output contract, and export/deploy path.

## Layers

```text
Hermes Assistant
  Interfaces
    CLI / terminal chat
    Telegram bot
    GUI
    Future local web API

  Assistant Core
    Intent router
    Planner
    Task coordinator
    Permission gate
    Provider router
    Report writer

  Memory and Knowledge
    UnifiedKnowledgeStore
    Review queue
    Approved lessons
    Repo map / code graph
    Prompt and tool templates

  Tool System
    Tool registry
    Tool manifest
    Tool runner
    Tool exporter
    Local deploy adapter

  Apps
    video_factory
    knowledge_learner
    coding_agent
    tool_builder
```

## Current repo mapping

| Capability | Existing files | Status |
| --- | --- | --- |
| Provider router | `core/ai_router.py` | Exists |
| Job queue | `core/agent_jobs.py`, `core/task_queue.py` | Exists |
| Video factory | `telegram_bot.py`, `core/job_watcher.py`, `tools/video_downloader.py` | Exists |
| Knowledge learner | `core/knowledge_store.py`, `core/learning_review.py`, `knowledge_base/` | Exists |
| Assistant runtime | `core/assistant_runtime.py` | Added as foundation |
| Assistant CLI | `scripts/hermes_assistant_cli.py` | Added as foundation |
| Coding executor | Future `core/coding_agent.py` | Not implemented yet |
| Tool registry | Future `core/tool_registry.py` | Not implemented yet |

## Permission model

Hermes Assistant should never jump directly from chat to arbitrary shell writes.
Use this staged model:

1. Read-only plan
   - Inspect files.
   - Classify intent.
   - Produce plan and risk notes.

2. Approved patch
   - Apply a small patch only after the user asks for implementation.
   - Keep changes scoped to named files.

3. Verification
   - Run syntax checks or focused tests.
   - Write a report.

4. Automation
   - Only promote repeated, stable flows into tools or workers.

## Provider strategy

Use a low-cost provider router:

- Local first when available: Ollama / LM Studio.
- Free or low-cost API when acceptable: OpenRouter, Groq, Cerebras, Mistral.
- Paid or high-quality model only for hard planning, review, or recovery.

Coding tasks should use repo maps and narrow file reads before model calls.

## Coding agent target workflow

```text
User request
  -> classify as coding_agent
  -> scan relevant files
  -> write implementation plan
  -> ask/apply patch
  -> run focused verification
  -> write report
```

Initial commands:

```cmd
cd /d C:\Work\Code\Hermes_download\hermes-agent
set PYTHONUTF8=1
python scripts\hermes_assistant_cli.py -i
```

Single request:

```cmd
python scripts\hermes_assistant_cli.py --message "fix duplicate Telegram report handling"
```
