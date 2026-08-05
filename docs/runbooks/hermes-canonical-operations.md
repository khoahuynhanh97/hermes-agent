# Hermes Canonical Operations

## Runtime

The general-purpose runtime is NousResearch Hermes. Its non-secret model
configuration is:

`custom -> http://127.0.0.1:20128/v1 -> reason_combo`

9Router owns provider routing and fallback inside the logical combo. Project
code must not select individual reasoning models.

## Canonical capabilities

The repo-local Hermes runtime loads the project-owned MCP servers:

- `hermes_product`
- `hermes_research`
- `hermes_knowledge`
- `hermes_video`
- `hermes_video_factory`

Skills are loaded from `skills/` and remain procedural guidance. Hermes owns
semantic composition; MCP servers own capability boundaries.

## Canonical start

```powershell
cd D:\work\hermes-agent
.\setup.ps1
.\start.ps1
```

Use `.\start.ps1 -UI` to include React. Use
`.\start.ps1 -NoServices --version` for a source/runtime smoke test without
starting backend or workers. Canonical runtime data defaults to the sibling
`D:\work\hermes-agent-data`; `%LOCALAPPDATA%\hermes` contains only Hermes
config and agent state.

## Durable jobs and delivery

### Worker processes

`start.ps1` launches **two** separate worker processes with explicit database
and workspace ownership:

| Worker | DB | Workspace |
|--------|-----|-----------|
| `video` | `hermes-agent-data/db/video.sqlite` | `hermes-agent-data/workspaces/video` |
| `video-factory` | `hermes-agent-data/db/video_factory.sqlite` | `hermes-agent-data/workspaces/video-factory` |

Each worker claims only from its own DB and writes only under its own workspace.
Logs are written separately: `video-worker.*.log` and `video-factory-worker.*.log`.

### Media provider ownership

| Capability | Provider path |
|-----------|---------------|
| Text / reasoning | 9Router `http://127.0.0.1:20128/v1` → `reason_combo` |
| Image generation (storyboard frames) | `IMAGE_PROVIDER` factory → `google_vertex` (Imagen 3) |
| Video generation (scene clips) | `VIDEO_PROVIDER` factory → `google_vertex` (Veo 3.1) |
| TTS voiceover | `TTS_PROVIDER` factory → `google_vertex` (Gemini TTS) |

`.env.example` defaults all three media providers to `fake` so a fresh clone
never makes paid calls. For hermetic demos, add `HERMES_ALLOW_FAKE_PROVIDERS=1`.
For live production, switch each provider to `google_vertex`.

### Paid call gates (HITL required)

Every paid Vertex call goes through an explicit user confirmation gate before
the job is submitted to the durable worker. The gating sequence for Video
Factory is:

1. **Resource identity lock** — user confirms product identity before lock.
2. **Creative Brief approval** — user approves brief before F2 begins.
3. **Scene Plan approval** — user approves plan before storyboard is saved.
4. **Paid Gate A** — one sample image job; user visually inspects before batch.
5. **Paid Gate B** — remaining frame batch; only after Gate A accepted.
6. **Storyboard approval** — user approves all frames before video begins.
7. **Paid Gate C** — one 4-second Veo smoke clip; user accepts before batch.
8. **Paid Gate D** — remaining clip batch; only after Gate C accepted.
9. **Paid Gate E** — one TTS voiceover call with exact text shown to user.
10. **Final Video approval** — user approves draft before final export.

No step may be skipped or auto-advanced.

## Scheduling and approvals

- Semantic recurring work: Hermes native cron.
- Deterministic maintenance: infrastructure/domain scheduler.
- Product and Knowledge approvals: application/domain lifecycle services;
  Telegram and GUI are adapters only.

## Verification

Run the relevant tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Tests isolate the knowledge root in a temporary directory and do not require a
developer-specific mounted drive.

### Focused Video Factory suite

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests/mcp_servers/test_video_factory_server.py `
  tests/hermes/application/test_video_factory_service.py `
  tests/hermes/application/test_video_factory_f2_f5.py `
  tests/hermes/test_tts1.py `
  tests/hermes/test_ui1_api.py `
  tests/workers/test_canonical_job_worker.py `
  tests/providers/test_tts_provider_factory.py `
  -q --basetemp .\.tmp-vf-focused -p no:cacheprovider
```
