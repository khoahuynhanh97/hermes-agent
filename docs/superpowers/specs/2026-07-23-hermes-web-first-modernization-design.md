# Hermes Web-first Modernization Design

## Mục tiêu

Hiện đại hóa Hermes thành một hệ thống cho một quản trị viên, trong đó Web là nơi vận hành chính. Desktop chỉ cung cấp năng lực local, Telegram chỉ nhận dữ liệu và gửi thông báo, còn tất cả workflow dùng chung một application layer và một nguồn trạng thái SQLite.

## Quyết định đã chốt

- Web có quyền tạo, sửa, duyệt, chạy lại và theo dõi toàn bộ workflow.
- Desktop chỉ chạy tác vụ cần máy local: chọn file, FFmpeg, render, cắt ghép và kiểm tra môi trường.
- Telegram nhận link, ảnh, video, tài liệu và lệnh ngắn; tạo ingestion request; gửi tiến độ, lỗi và kết quả.
- Hermes phục vụ một quản trị viên trong giai đoạn này; không xây multi-user, phân quyền tổ chức hay cloud tenancy.
- SQLite là nguồn dữ liệu vận hành chính. Filesystem giữ asset, artifact và export, với bản ghi SQLite tham chiếu đến chúng.
- 9Router là cổng duy nhất cho các model trả lời. Hermes gửi tier `fast`, `reason`, `vision` hoặc `code`; 9Router chọn provider/model cụ thể và fallback trong tier.
- Các provider không phải LLM, như download, crawl, search, AI-video và FFmpeg, vẫn là adapter công cụ riêng.
- Di trú theo Strangler Migration: adapter tương thích giữ luồng cũ chạy được cho đến khi workflow mới thay thế nó.

## Ngôn ngữ miền

| Thuật ngữ | Nghĩa chuẩn |
| --- | --- |
| Project | Không gian làm việc của một sản phẩm/campaign, sở hữu workflow, asset và artifact. |
| Workflow | Chuỗi bước có trạng thái, ví dụ Prompt Studio 7 bước hoặc dựng video. |
| Step | Một bước trong workflow; có draft, approval state, input và output. |
| Artifact | File kết quả có phiên bản, được lưu filesystem và đăng ký trong SQLite. |
| Job | Đơn vị thực thi bất đồng bộ có trạng thái, log, retry policy và artifact. |
| Ingestion | Nhận nguồn từ Web hoặc Telegram rồi chuẩn hóa thành dữ liệu domain/job. |
| Knowledge proposal | Tri thức chưa được duyệt; chỉ trở thành approved knowledge sau approval. |
| Capability tier | Nhu cầu model: `fast`, `reason`, `vision`, `code`; không phải tên model/provider. |
| Local capability | Tác vụ chỉ máy local làm được: FFmpeg, filesystem, render hoặc chọn file. |

## Kiến trúc đích

```text
Web Admin (React/TypeScript)
Desktop Local Runtime
Telegram Ingestion + Notification
CLI / Local Worker
             │
             ▼
       Hermes Application
 projects | prompt_studio | video | knowledge | jobs | assets
             │
     ┌───────┼────────┬───────────┐
     ▼       ▼        ▼           ▼
SQLite   Model Gateway Job Runtime Storage
           │             │          │
        9Router      FFmpeg      filesystem
                       tools       backup/export
```

### Application modules

Each module exposes a small interface and hides storage, UI and provider details.

| Module | Interface responsibility | Implementation responsibility |
| --- | --- | --- |
| `projects` | Create, load, archive and describe projects. | SQLite records, project directories and metadata migration. |
| `prompt_studio` | Read/update step draft, approve step, regenerate step, reset/load project workflow. | Seven-step state, validation, artifact generation and invalidation. |
| `video` | Register assets, request local operations, inspect render outputs. | FFmpeg adapters, cutters, editor and local worker dispatch. |
| `knowledge` | Ingest source, propose, approve, reject and search knowledge. | SQLite knowledge records, legacy Markdown migration and indexes. |
| `jobs` | Submit, claim, retry, cancel and observe jobs. | SQLite queue, worker lease, logs, artifact references and recovery. |
| `model_gateway` | Complete a typed request by capability tier. | 9Router HTTP client, capability map, timeouts, errors and observability. |
| `notifications` | Publish progress/result notifications. | Telegram sender and Web event stream adapters. |

## Interface rules

- UI, Telegram and CLI may call application modules only. They must not import `requests`, provider SDKs, FFmpeg helpers, `sqlite3`, job-folder paths or legacy JSON stores.
- Application modules depend on repository and adapter interfaces, not concrete HTTP/filesystem implementations.
- Only the Model Gateway knows the 9Router base URL, API key, model aliases and response format.
- Only Job Runtime writes execution status transitions. Domain modules request jobs; they do not mutate a worker folder directly.
- Only repositories translate domain objects to SQLite rows or legacy migration records.
- All mutations return a domain result with stable error codes; interfaces map them to HTTP/Telegram/Desktop presentation.

## Persistence and migration

SQLite becomes source of truth through the existing `hermes/` package. The schema is extended for projects, workflows, workflow steps, jobs, job events, artifacts, assets and ingestion requests.

Migration order:

1. Create tables and repositories without changing existing reads.
2. Add dual-write adapters for new mutations.
3. Backfill legacy project metadata, JSON state and knowledge entries into SQLite.
4. Compare counts, identifiers and checksums; produce a migration report.
5. Switch reads module-by-module to SQLite.
6. Freeze legacy writes, retain read/export compatibility for one release cycle.

No migration deletes legacy data. Backups use SQLite backup plus filesystem manifest export.

## Model Gateway and 9Router

`model_gateway` accepts a request containing capability tier, messages, optional structured-output schema, timeout and correlation ID. It resolves tier aliases such as `fast`, `reason`, `vision`, `code` through 9Router configuration. It returns normalized content, model metadata, retry count and safe errors.

`core/llm_gateway.py` is the initial migration adapter. Direct use of `core/ai_router.py`, direct OpenRouter calls and direct Gemini calls are removed only after every caller has moved to the new gateway. AI-video providers are not part of this replacement because they are task adapters, not conversational/model-answer providers.

## Interfaces

### Web Admin

The Web Admin is a React/TypeScript single-page application served by a FastAPI backend. It owns project selection, Prompt Studio, video job control, knowledge review, settings, job logs and artifact viewing. It reads current state through REST endpoints and live job updates through Server-Sent Events.

### Desktop Local Runtime

Desktop becomes a thin local runtime client. It registers local capabilities, submits local jobs, displays job status and opens native file selectors. It does not own workflow state or duplicate Web screens.

### Telegram

Telegram converts approved user messages/files into `IngestionRequest` records and publishes notifications from `notifications`. It does not perform full workflow approvals or direct model/provider calls.

### CLI and workers

CLI uses the same application interfaces for administration, diagnostics and scripts. Workers claim jobs using a lease and execute only registered job handlers.

## Delivery phases

1. Foundation: package layout, typed domain results, SQLite repositories, 9Router gateway contract, job runtime contract, migration observability.
2. Web platform: FastAPI API, authentication for one local administrator, React shell, project/job/event views.
3. Prompt Studio: migrate seven-step workflow and artifacts to application module and Web UI.
4. Knowledge and Telegram: ingestion pipeline, proposal/review workflow and notifications.
5. Video and Desktop: local capability registration, video job handlers and thin Desktop runtime.
6. Legacy retirement: remove duplicated UI/business logic, freeze legacy stores and update runbooks.

## Testing strategy

- Domain/application modules: deterministic unit tests with in-memory or temporary SQLite repositories.
- Repositories: SQLite integration tests including transaction, migration and rollback behavior.
- Model Gateway: contract tests with fake 9Router HTTP responses; no live paid-provider tests in CI.
- Jobs: integration tests for submit, lease, completion, retry, cancellation and recovery.
- Web: API tests plus Playwright journeys for project creation, Prompt Studio approval/invalidation and knowledge review.
- Telegram/Desktop: adapter contract tests with fakes; a small manual smoke checklist for native integrations.
- Migration: fixture-based before/after reports and idempotency tests.

## Out of scope

- Multi-user teams, role-based access control, public tenant isolation and billing.
- Cloud PostgreSQL and distributed worker orchestration.
- Automatic public exposure of 9Router.
- Replacing AI-video provider protocols beyond moving their invocation behind job handlers.
- Deleting legacy files during the initial modernization release.

## Acceptance criteria

- Web can operate all project, Prompt Studio, knowledge and job workflow actions without desktop-only state.
- Telegram can create ingestion requests and receive notifications without calling model/provider code directly.
- All LLM responses use the Model Gateway and 9Router tier aliases.
- SQLite can reconstruct project, workflow, job and artifact state after restart.
- Desktop can execute registered local jobs without owning domain state.
- Each migration phase is independently deployable, reversible at the adapter level and covered by focused tests.
