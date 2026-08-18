# HERMES-AGENT - BAO CAO MODULE & TINH NANG

## Tong quan kien truc

Hermes la he thong **tro ly ca nhan + san xuat video content**, kien truc hexagonal (ports & adapters), dang duoc hien dai hoa.

---

## 1. `hermes/` - Core hien dai (44 files)

### Domain Layer (8 models)

| File | Chuc nang |
|------|-----------|
| `results.py` | `Result[T]` - generic success/failure |
| `errors.py` | Error codes (not_found, conflict, invalid_input...) |
| `model_request.py` | 4 tiers: fast, reason, vision, code |
| `prompt_studio.py` | 7-step workflow state machine |
| `job.py` | Job lifecycle (queued->running->succeeded/failed/cancelled) |
| `ingestion.py` | IngestionRequest |
| `knowledge.py` | Knowledge lifecycle + lesson models |
| `project.py` | Project, Workflow, WorkflowStep models |

### Ports (5 interfaces)

| Port | Methods |
|------|---------|
| `ProjectRepository` | create, get, list_active, archive |
| `WorkflowRepository` | get, save |
| `JobRepository` | submit, claim, complete, fail, retry, cancel, get_job, get_jobs_by_status |
| `ModelGateway` | complete |
| `KnowledgeRepository` | save, get, search, list_by_status |

### Application Services (5 services)

| Service | Chuc nang |
|---------|-----------|
| `PromptStudioService` | 7-step workflow: load, save_draft, approve, invalidate, reset |
| `JobService` | submit, claim, complete, fail, retry, cancel, get_job |
| `KnowledgeService` | propose, approve, reject, search |
| `IngestionService` | submit ingestion requests |
| `VideoService` | request_cut, request_render |

### Adapters (4 nhom)

| Adapter | Implement |
|---------|-----------|
| `sqlite/` | Job repository, Project repository, Schema v2 |
| `router/` | 9Router HTTP gateway |
| `telegram/` | Ingestion adapter, Notification adapter |
| `local/` | FFmpeg capability, Desktop runtime |

### Core Modules (12 modules)

| Module | Chuc nang |
|--------|-----------|
| `db.py` | SQLite connection manager + SCHEMA_V1 (12 tables) |
| `knowledge.py` | SQLiteKnowledgeStore: CRUD, FTS5 search, approval workflow, migration |
| `memory.py` | Conversation memory + durable memory (preferences/facts/decisions/tasks) |
| `jobs.py` | SQLite job queue: enqueue, claim, complete, fail, retry, cancel, recover |
| `llm.py` | HermesLLMGateway: typed wrapper for LLM calls |
| `assistant.py` | Bounded context builder from knowledge + memory + conversation |
| `learning.py` | LearningService: persists validated learning results |
| `backup.py` | SQLite backup/restore/verify/export with retention pruning |
| `migration.py` | Legacy knowledge to SQLite migration |
| `config.py` | HermesPaths configuration from env |
| `tools/clone_repo.py` | Git clone utility |
| `tools/prompt_filter/` | Image/video prompt categorization |

---

## 2. `core/` - Legacy Layer (46 files)

### LLM & AI (4 files)

| File | Chuc nang |
|------|-----------|
| `llm_gateway.py` | Primary LLM text gateway via 9Router + fallback chain |
| `ai_router.py` | Multi-provider router: Gemini, Groq, Cerebras, Mistral, OpenRouter, Together, Ollama |
| `router.py` | Telegram command routing map |
| `observability.py` | Logging, alerts, Gemini raw response logs |

### Knowledge & Learning (5 files)

| File | Chuc nang |
|------|-----------|
| `knowledge_store.py` (929 lines) | **Unified Knowledge Store** - single source of truth (JSON backend) |
| `knowledge_base.py` | Legacy knowledge base V1 |
| `learning_review.py` | Human review queue |
| `style_profiler.py` | Style profile extraction from approved knowledge |
| `source_validation.py` | Source URL validation (blocks private/SSRF) |

### Video Production (8 files)

| File | Chuc nang |
|------|-----------|
| `script_generator.py` | TikTok script generation via Gemini (multiple styles) |
| `storyboard_generator.py` | Scene-by-scene storyboard via Gemini |
| `prompt_engine.py` | Convert storyboard -> prompt packs (.md, .txt, .json) |
| `idea_engine.py` | Video idea angle generation via LLM |
| `video_fetcher.py` | Video download (yt-dlp) + transcription (Whisper) |
| `visual_matcher.py` | OpenCV image similarity (histogram + ORB) |
| `clip_library.py` | Clip asset management |
| `keyword_generator.py` | Keyword extraction + translation |

### Job Management (8 files)

| File | Chuc nang |
|------|-----------|
| `agent_jobs.py` (868 lines) | File-based + SQLite job queue |
| `job_watcher.py` (1795 lines) | Daemon - polls jobs and executes them |
| `planner.py` | Task planner + worker prompt generation |
| `task_queue.py` | Manifest-first file queue (pending/running/done/failed) |
| `manifest.py` | Job manifest creation/status |
| `job_dedup.py` | SHA256-based duplicate job detection |
| `artifact_store.py` | Artifact metadata for jobs |
| `status.py` | Manifest progress tracking |

### Coding Agent (6 files)

| File | Chuc nang |
|------|-----------|
| `coding_agent.py` | Dry-run code change planner |
| `repo_map.py` | Lightweight repo map for targeted file reads |
| `patch_executor.py` | Safe unified-diff applicator with permission gate |
| `permission_gate.py` | Path-based permission checks (blocks secrets) |
| `verification_runner.py` | Runs allowlisted verification commands |
| `repository_search.py` | GitHub repo search via API |

### Assistant & Memory (4 files)

| File | Chuc nang |
|------|-----------|
| `assistant_runtime.py` | Request classification + execution planning |
| `conversation_memory.py` | Per-user conversation memory |
| `pending_store.py` | Persistence for pending video links/files |
| `telegram_auth.py` | Telegram user authorization |

---

## 3. `server/` - FastAPI Web API (5 files)

| Route | Method | Chuc nang |
|-------|--------|-----------|
| `/api/projects` | GET/POST/DELETE | Project CRUD |
| `/api/jobs` | POST | Submit job |
| `/api/jobs/{id}` | GET | Get job details |
| `/api/prompt-studio/{id}` | GET/POST | Workflow: draft, approve, invalidate |
| `/api/events` | GET (SSE) | Server-Sent Events |
| `/health` | GET | Health check |

---

## 4. `web/` - React Frontend (7 components)

| Component | Chuc nang |
|-----------|-----------|
| `ProjectSelector` | Project list + creation |
| `PromptStudioPage` | 7-step workflow UI |
| `JobsPage` | Job management |
| `KnowledgePage` | Knowledge CRUD |
| `AIAnalysisPage` | AI creative studio (4 modes, 4 tiers) |
| `SettingsPage` | Configuration |
| `Layout` | Sidebar navigation |

---

## 5. `web_studio.py` - Legacy Web UI (1535 lines)

Single-file aiohttp web server with embedded HTML/CSS/JS. 3 modules:

- **Module 1**: Prompt Studio (7 subtabs) - san pham -> phan tich -> kich ban -> storyboard -> prompt anh -> prompt video -> ket qua
- **Module 2**: Cat gep video (8 subtabs) - san pham -> tim nguyen lieu -> cat clip -> cat thu cong -> kho clip -> dung video -> ket qua -> content recycler
- **Module 3**: AI phan tich & sang tao (8 subtabs) -> hoc & duyet -> y tuong -> kich ban -> giong doc -> storyboard -> cong viec AI -> assistant -> cai dat

**10 REST API endpoints**: projects, clips, generate-audio, render-video, knowledge/queue, knowledge/approve

---

## 6. `telegram_bot.py` (2242 lines)

**Command routing**: `/hoc_kien_thuc`, `/hoc_video`, `/hoc_hook_cta`, `/len_kich_ban`, `/review`, `/htmlvideo`, `/de_xuat_nang_cap`, `/approve`, `/reject`, `/merge`, `/approve_force`, `/knowledge`, `/assistant`, `/code_plan`, `/status`, `/retry`, `/cancel`

**Tinh nang chinh**:
- Knowledge learning pipeline (video -> analysis -> proposal -> approval)
- Memory management (propose -> approve/reject/deactivate)
- Job creation & monitoring
- Inline keyboard callbacks
- Duplicate detection khi approve knowledge
- File handling (video/image/document)

---

## 7. Workers (5 files)

| Worker | Chuc nang |
|--------|-----------|
| `base_worker.py` | Base contract - manual prompt execution |
| `codex_worker.py` | Codex agent worker |
| `antigravity_worker.py` | Antigravity review worker |
| `ai_studio_worker.py` | AI Studio pipeline |
| `html_video_worker.py` | HTML/CSS video page renderer |

---

## 8. GUI Desktop (18 files + 10 tabs)

**Stack**: CustomTkinter

| Tab | Chuc nang |
|-----|-----------|
| Settings | API keys, paths, model config |
| Learn & Review | Knowledge review queue |
| Idea Engine | Video idea generation |
| Script Generator | TikTok script (multiple styles) |
| Audio Generator | TTS audio (Edge-TTS + ElevenLabs) |
| Storyboard | Scene breakdown + prompt export |
| Agent Jobs | Job monitoring |
| Assistant | AI chat |
| Content Recycler | Content remixing |
| Prompt Studio | 7-step workflow |

---

## 9. Providers & Tools

| Nhom | So luong | Chuc nang |
|------|----------|-----------|
| Video Download | 2 (yt-dlp, direct) | Tai video tu URLs |
| Media Search | 6 (Pexels, Pixabay, Social, Shopee, Custom Scraper, AI Video) | Tim nguyen lieu |
| Tools | 10 (TTS, video analysis, script, publisher, BGM...) | Xu ly media |
| Editor | 7 (cut, trim, subtitle, compose...) | Chinh sua video |
| Platforms | 6 (TikTok, YouTube, Douyin, Xiaohongshu, 1688, Taobao, Shopee) | Ho tro nen tang |

---

## 10. Tests (42 files)

| Area | Tests |
|------|-------|
| Domain | 2 (ModelRequest, Results) |
| Adapters | 3 (9Router, project repository, Telegram ingestion) |
| Application | 4 (job, knowledge, prompt studio, video) |
| Server | 1 (Projects API) |
| hermes/ | 14 (db, backup, knowledge, memory, LLM, etc.) |
| core/ | 3 (asset pipeline, content source, script generator) |
| GUI | 6 (content recycler, navigation, prompt studio) |
| Contract | 1 (legacy baseline) |

---

## Tong quan

| Metric | Count |
|--------|-------|
| Python files | ~200+ |
| Classes | ~80+ |
| Functions | ~400+ |
| Tests | 42 files |
| API endpoints | 10 (web_studio) + 6 (FastAPI) |
| LLM providers | 7 |
| AI video providers | 6 |
| DB tables | 12 + FTS5 |
| GUI tabs | 10 |
| Workers | 5 |
| Telegram commands | ~20+ |

---

## File Reference

| File | Created | Last Updated |
|------|---------|--------------|
| `HERMES_MODULE_REPORT.md` | 2026-07-28 | 2026-07-28 |
