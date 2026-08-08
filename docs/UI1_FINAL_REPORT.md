# UI1 — Minimal Video Factory Workflow UI — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **UI1 FULL PASS**

---

## 1. Existing Stack Reused

- **Frontend**: React 18 + Vite + TanStack React Query + react-router (already in `web/`)
- **Backend**: aiohttp (`web_studio.py`, port 8000) — added a thin `video_factory_api.py` module with `build_routes()`, wired into the existing app
- **Domain/backend**: reused `VideoFactoryService` + `SQLiteVideoFactoryRepository` + canonical `CanonicalJobRepository`/worker — zero new orchestration layer
- **No new framework, no new MCP, no UI state machine duplicating domain**

---

## 2. UI Structure

Single workspace page at `/video-factory`:

```
Video Factory
  owner selector | open project | create project
  1 Resources | 2 Idea | 3 Brief | 4 Scenes | 5 Storyboard | 6 Video | 7 Timeline | 8 Export
```

- Cards per stage, simple forms, product image base64 upload, image/video preview, draft/final `<video>` and frame `<img>` via `/media/...`
- Job status line (Queued/Generating/Completed/Failed + normalized error) with 3s polling of OUR backend (`/api/vf/jobs/{id}`)

---

## 3. B1–B10 Coverage

| Stage | UI action → backend |
|-------|--------------------|
| B1 Resources | `POST /resources` (identity, context, style, product image upload) → save + lock Resource Pack |
| B2 Idea | `POST /idea` (text, duration, platform, ratio) |
| B3 Brief | `POST /brief` + `Approve Creative Brief` (explicit HITL button) |
| B4 Scenes | `POST /scenes` + `Approve Scene Plan` (explicit HITL) |
| B5 Storyboard | `POST /storyboard` + `Generate Image (1x)` → `POST /storyboard/generate` enqueues image_generate job |
| B6 Storyboard | `Approve Storyboard` (explicit HITL) |
| B7/B8 Video | `POST /video` saves VideoPrompt + enqueues `video_generate` job |
| B9 Timeline | `POST /timeline` + `POST /timeline/render` (deterministic draft) |
| B10 Export | `Approve Final` (explicit HITL) + `Export Final` |

Frontend never calls Vertex/Gemini/Veo directly — always `UI → backend → service → durable job → worker → provider`.

---

## 4. HITL UX

Four explicit approval buttons, never hidden inside a "Continue":
- `Approve Creative Brief`
- `Approve Scene Plan`
- `Approve Storyboard`
- `Approve Final`

Approval requires prior stage (domain enforces, e.g. video requires storyboard approved; export requires final approval). No auto-approve anywhere.

---

## 5. Image/Video Job UX

- `Generate Image (1x)` and `Generate Video (1x)` are explicit one-click actions
- Backend enqueues exactly one durable job per click (`image_generate` / `video_generate`)
- UI polls `/api/vf/jobs/{id}` at 3s intervals; shows Queued/Generating/Completed/Failed + normalized provider error
- No auto-generation on load, no auto-regenerate, no model switching, no auto-retry

---

## 6. Runtime Data

All generated data under `HERMES_DATA_DIR` (default `D:\work\hermes-agent-data`):
- DB: `{root}/db/video_factory.sqlite`
- Workspace: `{root}/workspaces/video-factory`
- Media served read-only via `/media/{path}` with workspace containment check (traversal → 403/404)
- `asset://` semantics preserved; uploads written into workspace `products/`
- Nothing written into the Git repo (verified: no `.png/.mp4` in `git status`)

---

## 7. Files Changed

**Backend**
- `video_factory_api.py` (new) — 19 aiohttp routes, thin, calls service/jobs only
- `web_studio.py` — `from video_factory_api import build_routes; app.add_routes(build_routes())`

**Domain/port (small extension for UI list)**
- `hermes/ports/video_factory_repository.py` — added `list_owned`
- `hermes/adapters/sqlite/video_factory_repository.py` — implemented `list_owned`

**Frontend**
- `web/src/features/video-factory/VideoFactoryPage.tsx` (new)
- `web/src/app.tsx` — added `/video-factory` route

**Tests**
- `tests/hermes/test_ui1_api.py` (new, 5 tests)

---

## 8. Tests

**UI1 backend API (5/5)** via aiohttp test client (no paid generation):
- create + get project
- full B1→B10 wiring incl. brief/scene/storyboard approvals + video job enqueue
- final export rejected without approval (domain guard)
- media workspace containment (traversal blocked)
- list projects

**Frontend build**: `npm run build` (tsc + vite) PASS.

**Focused regression**: `41 passed` (UI1 API 5 + data-root 6 + providers 21 + Video Factory service/domain/acceptance 9).

**Checks**: `py_compile` PASS; `git diff --check` clean.

---

## 9. Simplicity Review

| Check | Result |
|-------|--------|
| Frontend duplicated domain logic? | ✅ no — UI calls backend, domain stays source of truth |
| Unnecessary framework/layer? | ✅ none added (reused React + aiohttp) |
| Features outside UI1? | ✅ none (no auth, no analytics, no drag-drop, no WebSocket, no publishing) |
| UI understandable without docs? | ✅ single page, numbered stage cards |
| Paid ops always explicit? | ✅ 1-click buttons; no auto generation |
| Runtime asset in source repo? | ✅ none |
| More screens than needed? | ✅ one workspace page only |
| Removable component/helper? | ✅ all minimal |

---

## 10. Missing Features (only useful next-iteration items)

- Product image upload UX (currently paste-base64; a file picker would be nicer)
- Auto-refresh project card when job completes (currently one refresh after job settles)
- Video prompt auto-derived from storyboard frame (currently manual text)

---

## 11. Recommended Next Step

**UI2 — usability polish** (file picker for product image, clearer stage navigation, job-state refresh) — OR **Publishing1 TikTok integration** once publishing scope is approved.

Do not begin the next phase automatically.

---

## 12. Final Status

✅ **UI1 FULL PASS** — minimal workflow UI over the existing canonical Video Factory backend, all four HITL gates explicit, all paid generation explicit, runtime data under `HERMES_DATA_DIR`, no business logic duplicated in the frontend.
