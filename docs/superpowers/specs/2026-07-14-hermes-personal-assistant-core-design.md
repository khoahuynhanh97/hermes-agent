# Hermes Personal Assistant Core Design

## Product Goal

Hermes is a personal AI assistant operated primarily through Telegram. The current product priority is learning from user-provided sources, storing reviewed knowledge, retrieving approved knowledge, and maintaining user-approved personal memory. Video production is explicitly outside the critical path.

## Confirmed Decisions

- Build the new assistant core inside the existing `hermes-agent` repository.
- Keep the current Telegram bot usable while workflows migrate incrementally.
- Use SQLite on laptop 1 as the only transactional source of truth.
- Store the database and artifacts under `D:\HermesData` by default.
- Use Google Drive only for backup, export, and restore.
- Migrate the full knowledge lifecycle: pending, approved, rejected, approval history, source metadata, and available details.
- Keep downloaded media and raw analyses as external artifacts referenced by SQLite.
- Use approval-based personal memory: Hermes may propose durable memory, but only approved memories are reused.
- Support text, ordinary URLs, YouTube/TikTok, documents, images, and audio.
- Use natural Telegram chat as the default interaction and expose only a small command set.
- Search approved knowledge first; search external sources only when local evidence is insufficient.
- Review lessons individually and provide an approve-all action for all lessons from one source.

## Architecture

```text
TelegramAdapter
      |
HermesAssistant
      |
      +-- ChatService
      +-- LearningService
      +-- KnowledgeService
      +-- MemoryService
      +-- ToolService
      |
   JobService
      |
  LLMGateway -> 9Router
      |
 SQLite + local artifacts
```

The new implementation lives in a small `hermes/` Python package. Existing `core/` modules remain compatibility adapters during migration. A workflow must never write to both SQLite and legacy JSON as equal sources of truth. After the SQLite cutover, legacy JSON and Google Drive are read-only migration or export inputs.

## Component Responsibilities

### Telegram Adapter

- Authorize Telegram users.
- Normalize text, URLs, and attachments.
- Send concise HTML responses and action controls.
- Correlate messages with jobs, sources, lessons, and memory proposals.
- Keep old commands as hidden compatibility aliases.
- Contain no provider-specific or learning business logic.

### Hermes Assistant

- Route requests using small deterministic rules: chat, learn, knowledge query, job operation, memory operation, or explicit tool operation.
- Assemble approved knowledge, approved memory, and bounded conversation context.
- Decide whether approved knowledge is sufficient or a live search is needed.
- Remain a single orchestrator; no multi-agent architecture.

### Learning Service

The learning flow is:

```text
normalize -> acquire -> evidence bundle -> source summary -> deep analysis
          -> atomic lesson candidates -> validation -> dedupe -> pending review
```

Summary and reusable lessons are separate outputs. Every pending lesson must reference at least one evidence record. Metadata-only processing may produce a low-confidence summary but must not create a trusted lesson. If source evidence is unavailable, the result is `needs_source`.

### Knowledge Service

- Store source, evidence, lesson, and approval event records.
- Retrieve only approved lessons for normal assistant answers.
- Use SQLite FTS5 before considering semantic/vector retrieval.
- Preserve rejected lessons and history for audit and deduplication.
- Return provenance with every retrieved lesson.
- Keep external search results separate until the user explicitly learns them.

### Memory Service

- Store bounded conversation messages separately from durable memory.
- Durable memory types are preference, personal fact, decision, and task.
- Proposed memory starts as pending and is reused only after approval.
- Forgetting deactivates a memory and records the event.
- Clearing conversation history does not delete approved memory.

### Jobs

- Use one SQLite job table and one local worker.
- Public states are queued, running, completed, failed, and cancelled.
- Persist stage, attempt count, error, input, and result.
- Retry stages with bounded attempts; cancellation is cooperative between stages.
- Do not retain the current manifest queue as a second state machine.

### LLM And 9Router

- Hermes selects task class and required capabilities.
- 9Router handles model/provider/account access and infrastructure fallback.
- The gateway returns text, requested model, actual model when available, usage, duration, and retry count.
- Structured output validation remains in Hermes.
- Learning requests must not silently fall back to a provider or model with unknown capability.
- Direct Gemini vision may remain temporarily behind one explicit adapter until the 9Router multimodal path is verified.

## SQLite Data Model

- `sources`: normalized source identity, type, URL/path, title, hash, confidence, and acquisition state.
- `artifacts`: transcript, image, audio, document text, raw analysis, and report paths with hashes and sizes.
- `evidence`: timestamp, excerpt, image description, or artifact reference supporting a lesson.
- `lessons`: atomic lesson content, type, summary, tags, confidence, status, and reanalysis state.
- `lesson_events`: lifecycle transitions and actor information.
- `messages`: bounded conversation history by owner/chat.
- `memories`: pending/approved/rejected/deactivated durable memory.
- `memory_events`: memory lifecycle history.
- `jobs`: durable queue and stage state.
- `schema_migrations`: database version history.
- `lesson_fts`: FTS5 index containing approved lesson content only.

All owner-scoped reads require `owner_user_id`. Foreign keys are enabled. Writes use transactions and WAL mode. The database must not be placed inside the Google Drive sync directory.

## Telegram UX

The public command set is:

- `/learn`
- `/knowledge`
- `/jobs`
- `/remember`
- `/settings`
- `/help`

Approval, rejection, approve-all, retry, cancel, and reanalysis commands remain available as action commands and button fallbacks. Sending a source naturally creates a learning request. Hermes sends the source summary first, then the deeper analysis and pending lessons. One useful Markdown report may be attached; intermediate worker files are not sent.

## Retrieval Policy

1. Search approved lessons for the owner using FTS5.
2. Rank by lexical relevance, confidence, evidence availability, and source match.
3. Answer with source links when local evidence is sufficient.
4. Search an external source only when local evidence is insufficient or freshness is required.
5. Label live results clearly and never save them automatically.

## Security And Reliability

- Treat all source content as untrusted data.
- Enforce Telegram allowlist checks before any state read or write.
- Limit attachment size, artifact count, extracted text size, and total storage.
- Validate local paths and remote URLs; block private-network fetches except explicitly configured local services.
- Do not log secrets, full sensitive prompts, or raw authorization headers.
- Bind 9Router to localhost or a trusted private network and require an API key.
- Remove silent offline content inference from failed video analysis.
- Back up with SQLite's backup API, not by copying a live WAL database directly.

## Migration And Rollout

1. Add the new database and repository layer without changing production reads.
2. Import all legacy knowledge lifecycle data and verify counts, IDs, statuses, URLs, and detail hashes.
3. Run compatibility tests against both repositories.
4. Enable SQLite as the only runtime knowledge writer.
5. Migrate conversation memory and then jobs.
6. Move Telegram routing to the new assistant orchestrator.
7. Archive the duplicate queue, legacy stores, dead provider paths, and video-production UI only after runtime verification.

## Out Of Scope

- Video generation and batch video production.
- Automatic publishing.
- Vector database.
- Multi-agent orchestration.
- General plugin framework.
- Distributed workers or active-active laptops.
- New GUI work.

## Success Criteria

- Existing approved, pending, and rejected knowledge is present in SQLite with lifecycle history.
- Normal answers retrieve only approved knowledge and include provenance.
- Failed media analysis cannot become a high-confidence lesson.
- Pending lessons and memories require explicit approval.
- Telegram supports natural chat and the compact command set without breaking old command aliases.
- Restarting the bot or worker preserves jobs and data correctly.
- Backup, export, and restore work without Google Drive becoming a live datastore.

