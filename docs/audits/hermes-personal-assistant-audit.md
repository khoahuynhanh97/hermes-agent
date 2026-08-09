# Hermes Personal Assistant Audit

> Historical baseline audit. Implementation status after the first execution:
> Telegram job operations, 9Router gateway wiring, approved knowledge
> lifecycle, source fallbacks, authorization, and bounded conversation memory
> are now present. As of 2026-07-13, local 9Router live chat is verified with
> `kr/glm-5` and `kr/qwen3-coder-next`, OpenCode is configured through
> `nine-router`, and the Telegram bot plus job worker have been restarted
> against the verified model configuration.

Audit date: 2026-07-12

Scope: repository audit only. No production source code was changed for this audit.

## Executive verdict

**Overall: PARTIAL**

Hermes already has enough working pieces for a small personal assistant: a Telegram bot, a local file-backed job worker, video/transcript ingestion, a multi-provider router, a local knowledge store, and approval-related code. The pieces are not yet connected into one reliable assistant runtime.

The primary learning lifecycle is now present: `/hoc_kien_thuc` analyzes a source, returns a concise summary plus `summary_analysis.md`, creates a pending knowledge entry, and exposes Telegram approval actions. Remaining gaps are broader input normalization, generic tool execution, and optional multimodal/provider migration.

The current safe architecture is a small provider-neutral text gateway in front of Telegram and learning calls, with 9Router as primary and the legacy local provider router as a controlled fallback. Optional video/provider modules remain outside this migration.

## Status summary

| Area | Status | Evidence and verdict |
| --- | --- | --- |
| Telegram bot entry point | COMPLETE | `telegram_bot.py` starts polling and registers chat, learning, file/video, and planning handlers. |
| Telegram authorization | COMPLETE | A global allowlist guard uses `TELEGRAM_ALLOWED_USER_IDS` with private-owner fallback; unauthorized updates are stopped. |
| General chat/QA | COMPLETE | Text requests use the LLM gateway, short per-user conversation memory, approved knowledge context, and bounded live GitHub search for repository requests. |
| Input normalization | PARTIAL | Links, Telegram video/document attachments, captions, and text are handled through separate helper paths; there is no common typed input contract. Images and audio are not first-class Telegram handlers. |
| Long-running learning jobs | PARTIAL | File-backed jobs and one worker exist, but transcript extraction runs synchronously while creating the Telegram job. |
| Required job states | PARTIAL | The public job view exposes queued/running/completed/failed/cancelled while legacy file names remain for compatibility. |
| Job retry | COMPLETE | Bounded worker retry/DLQ and Telegram `/retry` are implemented and tested. |
| Job status/cancel | COMPLETE | Telegram `/status`, `/cancel`, and `/retry` are registered with owner checks. |
| Video download fallback | PARTIAL | Video download, subtitle extraction, audio download, Whisper fallback, and circuit breaking exist. Metadata/page-only analysis and a user upload continuation are not integrated as a job state. |
| Prompt-injection handling | PARTIAL | Transcript context explicitly treats source text as untrusted, but this policy is not centralized for documents, URLs, images, or all model calls. |
| Knowledge lifecycle model | COMPLETE | `UnifiedKnowledgeStore` supports pending, approved, rejected, timestamps, source URL dedupe, and atomic index writes with backup recovery. |
| Telegram learning-to-pending flow | COMPLETE | Knowledge jobs create pending entries after deep extraction and deliver summary plus one Markdown artifact. |
| Approved-only retrieval | COMPLETE | `get_approved_entries()` and script knowledge injection use only approved entries; the existing test passes. |
| Approval history | COMPLETE | Approval/rejection transitions retain actor, mode, timestamps, and rejection reason. |
| Telegram inline approval | COMPLETE | Outbox delivery sends Approve/Reject buttons and callbacks enforce ownership. |
| Tool registry | PARTIAL | Manifest loading, input validation, shell-free generated-tool execution, and bounded timeout now exist through `scripts/hermes_tool.py run`; Telegram confirmation/integration remains deferred. |
| Assistant orchestrator | PARTIAL | Telegram has a practical routing layer; `HermesAssistantRuntime` remains a planning helper rather than a mandatory central orchestrator. |
| LLM abstraction | PARTIAL | `core/llm_gateway.py` centralizes Telegram/worker text calls; optional video/production modules still have direct provider calls by design. |
| Task-based routing | PARTIAL | Rule-based aliases route chat, learning, analysis, structured extraction, and code; capability metadata for vision/tool calls remains deferred. |
| 9Router integration | COMPLETE FOR TEXT | Gateway uses environment-driven OpenAI-compatible 9Router calls with health/model probes, timeout, retry, logging, and controlled fallback. |
| 9Router endpoint compatibility | COMPLETE | Historical audit found port `20128` closed; latest verification on 2026-07-13 confirms `/api/health`, `/v1/models`, and non-streaming `/v1/chat/completions` work locally. |
| Automated test suite | PARTIAL | Fifteen focused standalone scripts cover gateway, jobs, learning fallback, approval, security, repository search, and delivery; pytest is not installed. |
| Full source compilation | CONFLICTING | Compilation fails on an existing unmatched `)` in `gui/app_staged.py:4527`. Runtime-critical files used by the bot had previously compiled, but the repository as a whole does not. |
| Secret handling | PARTIAL | `.env` is ignored and `.env.example` is tracked. Real local credentials exist in `.env`; logs and exception text still require careful redaction. |

## Current architecture map

```text
Telegram update
  -> telegram_bot.py
     -> direct chat commands -> LLM gateway / ask_local_ollama()
     -> learning commands -> build_video_job()
        -> AgentJobManager -> .agent_jobs/inbox/*.json
        -> synchronous fetch_transcript()

scripts/run_job_worker.py
  -> JobWorker.process_next_job()
     -> video download / transcript / video analysis
     -> core.llm_gateway.complete() for text analysis and extraction
     -> project artifacts + .agent_jobs/outbox/*.done.json

telegram_bot.py poll_outbox_loop()
  -> concise message + selected artifact files
  -> archive delivered job

Knowledge paths
  -> UnifiedKnowledgeStore (unified_index.json + entries/*.json)
  -> LearningReviewStore (legacy review compatibility)
  -> UnifiedKnowledgeStore (pending/approved/rejected source of truth)
  -> Telegram outbox approval callbacks update UnifiedKnowledgeStore
```

There are two job implementations:

- `AgentJobManager` uses `.agent_jobs/{inbox,processing,outbox,failed}` and drives the Telegram learning runtime.
- `TaskQueue` uses `jobs/{pending,running,done,failed}` and is partially surfaced through `AgentJobManager`.

For a personal assistant, one implementation should eventually become canonical. This does not need to be solved in Phase 1.

## Telegram learning runtime trace

1. `telegram_bot.py` receives `/hoc_kien_thuc`, `/hoc_video`, `/hoc_hook_CTA`, `/len_kich_ban`, a supported video link, or an uploaded video/document.
2. Link/file context is stored in `PendingStore` by chat ID.
3. `create_video_job_command()` resolves the source and calls `build_video_job()`.
4. `build_video_job()` writes a job through `AgentJobManager`. For knowledge learning it requests `learn_knowledge`, `analyze_video`, and `write_summary_analysis`.
5. Before returning to Telegram, `build_video_job()` calls `fetch_transcript()` synchronously. That helper attempts local transcription, auto-subtitles, then audio plus Whisper where available.
6. `scripts/run_job_worker.py` polls the inbox. `JobWorker` moves a job to processing and downloads/analyzes the source.
7. Video analysis uses `tools/video_analyser.py`, which directly uploads media to Gemini. Transcript-only analysis uses `core.ai_router.chat()`.
8. The knowledge branch performs a second structured extraction, writes `proposal_meta.json` and `summary_analysis.md`, and stores the lesson as pending.
9. The bot polls the outbox, sends a concise summary and only `summary_analysis.md` for knowledge jobs, then exposes Approve/Reject callbacks.
10. Approved lessons can be retrieved by chat; technology/repository detail fields are included in matching and context output.

Important behavior:

- Download failure does not immediately end the attempt when a transcript exists.
- With neither media nor transcript, the worker raises a controlled error rather than inventing content.
- Confidence is currently `high` for video and `medium` for transcript, but no `low` or `needs_source` result is persisted as a structured learning outcome.
- Transcript content is explicitly wrapped as untrusted reference data.

## Knowledge lifecycle trace

### Working lifecycle primitives

`UnifiedKnowledgeStore` provides:

- pending creation through `add_entry()`;
- URL normalization and obvious source-URL dedupe;
- approve and reject transitions;
- approved-only listing and prompt context generation;
- atomic index replacement and backup recovery;
- separate detail JSON files.

### Existing review-file bridge

`LearningReviewStore` provides a markdown review queue. On approve, it parses proposal metadata, creates or locates a unified entry, marks it approved, and moves the proposal file. On reject, it marks an existing matching entry rejected when possible and moves the file.

This bridge has three weaknesses:

- approval creates a pending entry and immediately approves it rather than preserving a clean pending record from analysis time;
- actor names are hardcoded as `gui_user`, including when called from Telegram;
- lifecycle transitions are not stored as an append-only history.

### Current break

The knowledge-learning worker returns at `core/job_watcher.py:534`. The proposal creation code later in the function belongs to the separate hook/CTA branch. Consequently, the main knowledge command does not reach either `LearningReviewStore.create_proposal()` or `UnifiedKnowledgeStore.add_entry()`.

## Direct model dependency map

| Location | Dependency | Use | Issue |
| --- | --- | --- | --- |
| `telegram_bot.py` | `google.generativeai` | Chat, story, code review, tech answers | Business logic calls Gemini directly. |
| `tools/video_analyser.py` | `google.generativeai` file API | Upload and analyze video/audio | Provider-specific multimodal path; deprecated SDK warning. |
| `core/ai_router.py` | Raw Gemini REST, OpenAI-compatible REST, Ollama REST | Text routing/fallback | Useful foundation, but endpoints/models are hardcoded and fallback capability checks are incomplete. |
| `core/job_watcher.py` | `core.ai_router.chat()` | Analysis, structured extraction, scripts/prompts | Closest existing consumer to the target gateway. |
| `core/idea_engine.py` | Raw Gemini REST | Idea generation | Direct provider dependency. |
| `core/keyword_generator.py` | Raw Gemini REST | Multiple keyword/product extraction calls | Direct provider dependency and duplicated HTTP handling. |
| `core/project_creator.py` | Raw Gemini REST | Project/product analysis | Direct provider dependency. |
| `core/script_generator.py` | Raw Gemini REST | Script generation | Direct provider dependency; also consumes approved knowledge. |
| `core/storyboard_generator.py` | Raw Gemini REST | Storyboard generation | Direct provider dependency. |
| `gui/app.py` | Raw Gemini REST plus `core.ai_router` | GUI generation/settings | Duplicates provider logic outside the router. |
| `gui/app_staged.py` | Raw Gemini REST plus `core.ai_router` | Staged duplicate GUI | Duplicate implementation and currently has a syntax error. |
| `gui/prompt_compiler_tab.py` | Raw OpenRouter, Gemini, Groq, Ollama REST | Prompt compilation | Reimplements routing and hardcodes a Gemini model. |

No direct Anthropic or OpenAI SDK integration was found in production code. No 9Router base URL or client was found.

## What already works

- Telegram polling, text replies, supported video-link intent prompts, video/document intake, and job result delivery.
- File-backed job persistence with processing, completion, failure, bounded retries, DLQ behavior, and basic restart visibility.
- Video download duration limit and download circuit breaker.
- Subtitle and audio/Whisper transcript fallback where dependencies and source access allow it.
- Controlled failure when no usable media/transcript exists.
- Structured JSON extraction validation and fallback metadata.
- A local unified knowledge index with source dedupe and approved-only retrieval.
- Standalone tests for worker JSON hardening, knowledge-store safety, reliability behavior, and approved-only script injection.
- `.env` exclusion from Git and a tracked `.env.example`.

## Current unnecessary complexity

1. Two overlapping job queues and two status vocabularies.
2. A review-file lifecycle beside a unified JSON lifecycle, with only partial synchronization.
3. `gui/app.py` and the large duplicate `gui/app_staged.py`; the latter currently does not compile.
4. Provider routing duplicated across `core.ai_router`, Telegram, GUI tabs, and generation modules.
5. `HermesAssistantRuntime` describes a broad modular assistant but only produces dry plans; it is not the live orchestrator.
6. Video-factory modules dominate the repository and README even though the desired product is a personal assistant.
7. Tool manifests imply a registry, but there is no production tool execution contract yet.

These should be reduced incrementally. None justify a repository rewrite.

## Security findings

| Finding | Status | Recommended treatment |
| --- | --- | --- |
| Telegram user authorization absent | MISSING | Add a small `TELEGRAM_ALLOWED_USER_IDS` allowlist guard before expanding capabilities. |
| Arbitrary shell execution from Telegram | PARTIAL | Existing coding/verification permission helpers are separate from Telegram; do not expose them until an explicit allowlist and confirmation path exist. |
| External URL validation/SSRF protection | MISSING | Validate schemes, reject localhost/private network targets for generic URL inspection, and constrain downloader-supported hosts. |
| File size/type limits | PARTIAL | Video duration is limited, but attachment/download byte limits and MIME validation are not consistently enforced. |
| Path traversal | PARTIAL | Many paths are resolved, but review queue callback names are joined directly and need basename/containment validation. |
| Prompt injection | PARTIAL | Transcript handling is defensive; the same untrusted-source boundary is not consistently applied elsewhere. |
| Secret logging | PARTIAL | `.env` is ignored. Gateway logging must redact authorization headers, query credentials, and full prompts. |
| Retry/storage bounds | PARTIAL | Worker retries are bounded and pending state expires; storage retention is not generally bounded. |

## Regression risks

- Changing `core.ai_router.py` in place could break the worker, GUI settings, and prompt compiler assumptions at once.
- Moving transcript extraction into the worker changes when users see job acceptance and how failures are reported.
- Reconnecting knowledge creation can accidentally approve low-confidence or fallback output unless pending is the only initial state.
- The review queue contains legacy markdown formats; migration or parsing changes need fixture tests.
- Existing mojibake in source text and Windows console encoding can hide behavior and test failures.
- A broad compile/test command currently fails for reasons outside the Telegram runtime, so Phase 1 needs targeted tests plus an explicit known-failure note.

## Minimal target architecture

```text
Telegram adapter
  -> HermesAssistant (one orchestrator)
     -> chat workflow
     -> learning workflow
     -> explicit tool calls
     -> approved knowledge retrieval
     -> LLMGateway
        -> 9Router OpenAI-compatible adapter
        -> controlled Gemini adapter (temporary fallback)

Local persistence
  -> existing AgentJobManager initially
  -> UnifiedKnowledgeStore
  -> per-application conversation/job state
```

Boundaries:

- Telegram only normalizes updates, authorizes users, correlates jobs, and renders responses/buttons.
- One practical assistant object chooses chat, learning, or tool execution.
- Learning owns extraction, analysis, pending lesson creation, and confidence.
- The knowledge store remains local and returns approved entries only.
- The LLM gateway owns model access, timeout/retry/error mapping, capability checks, and redacted telemetry.
- 9Router owns provider connectivity and any fallback behavior verified in its real implementation. It stores no Hermes state.

## Incremental implementation plan

### Phase 1A: smallest safe LLM change

1. Add a small `core/llm/` package containing configuration, request/result models, errors, a gateway, and provider adapters.
2. Preserve current behavior with a Gemini text adapter and an OpenAI-compatible adapter; do not migrate video upload yet.
3. Route only `core/job_watcher.py` text calls through the gateway.
4. Add unit tests using mocked HTTP responses for config, timeout, provider error mapping, structured output, and capability mismatch.
5. Leave `core.ai_router.chat()` as a compatibility wrapper until consumers migrate.

Why this scope: the worker already uses one abstraction point and is easy to mock. Migrating Telegram, GUI, all generators, and video upload together would create unnecessary regression risk.

### Phase 1B: Telegram security before more tools

Add a shared user allowlist guard and tests. This is operationally higher priority than adding new commands or tools.

### Phase 2: verified 9Router adapter

Probe the running service, confirm `/v1/models` and `/v1/chat/completions`, authentication, response shape, model aliases, streaming expectations, error responses, and any router-provided fallback metadata. Then configure the OpenAI-compatible adapter with environment variables.

### Phase 3: repair learning lifecycle

Create structured pending lessons from the knowledge branch, persist confidence/source/evidence, send Approve/Reject buttons, register callback handlers, and verify approved-only retrieval. Do this after model access is testable so lifecycle tests do not require live AI calls.

### Later

Add `/status`, `/cancel`, and `/retry`; normalize inputs; move blocking transcript work fully into the worker; migrate remaining direct model consumers one module at a time. Do not build a production engine or shared package yet.

## Top three implementation tasks

1. Introduce and test the minimal LLM gateway, adopting it only in `core/job_watcher.py` first.
2. Add Telegram authorization with `TELEGRAM_ALLOWED_USER_IDS` before exposing more assistant/tool behavior.
3. Restore the learning pending/approve/reject path and register real Telegram inline callbacks.

## Latest verification performed

| Command | Result |
| --- | --- |
| `GET http://127.0.0.1:20128/api/health` | Passed: `{"ok": true}`. |
| `GET http://127.0.0.1:20128/v1/models` | Passed: returned Kiro/Codex/Gemini model catalog including `kr/glm-5` and `kr/qwen3-coder-next`. |
| `POST /v1/chat/completions` with `kr/qwen3-coder-next` | Passed: returned `OK`. |
| `opencode models nine-router` | Passed: listed `nine-router/kr/qwen3-coder-next`, `nine-router/kr/glm-5`, `nine-router/kr/claude-sonnet-4.5`, `nine-router/cx/gpt-5.4-mini`. |
| `opencode run "Reply OK only" -m nine-router/kr/qwen3-coder-next` | Passed: returned `OK`. |
| `.venv\Scripts\python.exe scripts\test_llm_gateway.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_learning_fallback.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_learning_job_metadata.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_approved_knowledge_retrieval.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_telegram_attachments.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_telegram_learning_delivery.py` | Passed: local outbox delivery sends summary text, only `summary_analysis.md`, and Approve/Reject callbacks for the pending knowledge entry; approval callback moves the entry to approved. |
| `.venv\Scripts\python.exe scripts\test_job_operations.py` | Passed. |
| `.venv\Scripts\python.exe scripts\test_telegram_security_and_knowledge.py` | Passed. |
| `.venv\Scripts\python.exe -m py_compile ...` on runtime-critical files | Passed. |
| `git diff --check` | Passed; only CRLF warnings were reported. |
| Process check for `telegram_bot.py` and `scripts\run_job_worker.py` | Passed: one bot process and one worker process are running. |

## Historical verification from original audit

| Command | Result |
| --- | --- |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe -m pytest -q` | Failed: `pytest` is not installed. |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe -m compileall -q -x "\\.venv|\\scratch|\\projects|\\jobs|\\knowledge_base" .` | Failed: existing syntax error in `gui/app_staged.py:4527`. |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe scripts\test_worker_json_and_transcript.py` | Passed all 6 checks. |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe scripts\test_knowledge_store_safety.py` | Passed all 5 checks. |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe scripts\test_reliability_integration.py` | Passed. |
| `$env:PYTHONUTF8="1"; .venv\Scripts\python.exe scripts\test_script_generator_knowledge_injection.py` | Passed all 3 checks. |
| `Test-NetConnection 127.0.0.1 -Port 20128` | `TcpTestSucceeded=False`. |
| HTTP GET `/`, `/health`, `/v1/models` on `127.0.0.1:20128` | All failed to connect. |

The standalone scripts required `PYTHONUTF8=1` on this Windows console. Without it, the knowledge safety script fails while printing emoji before tests execute.

## Current continuation update (2026-07-13)

- Learning now performs a deeper synthesis before creating a pending lesson.
- Technology lessons can store repositories, AI tools/skills, search keywords, and Hermes usage guidance.
- Local `.txt`, `.md`, `.json`, `.csv`, `.srt`, and `.vtt` attachments are read as bounded, untrusted text sources for learning.
- Approved knowledge retrieval searches those detail fields and returns repository candidates to chat.
- Telegram chat and `/tim_repo` can query the bounded public GitHub repository endpoint. Live results are reference data only and are not auto-approved knowledge.
- Generated local tools can be listed and run from the CLI with manifest input validation, path containment, shell-free execution, and a bounded timeout.
- `scripts/test_repository_search.py` and `scripts/test_tech_repo_knowledge.py` pass.
- The full focused suite now contains 17 passing scripts.
- The bot and job worker were restarted after this change and both are running.
- Telegram Bot API `getMe` succeeds for `Khoa1bot`; local 9Router health and a live gateway `Reply with OK only` smoke test also succeed.

## Remaining unverified or deferred areas

- 9Router vision, tool-call, JSON-mode, context-limit metadata, and server-side fallback semantics beyond basic non-streaming chat.
- Live Telegram end-to-end behavior from a fresh user message after the latest restart.
- Live YouTube/TikTok download reliability for current platform behavior and cookies.
- Gemini video upload behavior and size limits under the configured account.
- Whisper installation/model availability; it is imported lazily and not listed in `requirements.txt`.
- Generic website, image, audio, and document learning flows.
- Safe tool execution from Telegram; the current registry only loads manifests.
- Storage retention and cleanup for project outputs, downloads, knowledge artifacts, and archived jobs.
