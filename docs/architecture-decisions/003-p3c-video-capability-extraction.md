# P3C Video Capability Extraction

## Decision

Expose the existing bounded video capability through a thin `hermes_video` MCP
server and the canonical `video-production` skill. Hermes owns intent
selection; the MCP owns validation and translation to existing application
services. No VideoAgent, planner, router, worker migration, or provider
cleanup is introduced.

## Existing capability inventory

| Component | Classification | P3C use |
| --- | --- | --- |
| `hermes.application.video_service.VideoService` | application service | Enqueue cut/render jobs |
| `hermes.domain.job.Job` / `JobStatus` | domain state | Durable job lifecycle |
| `SQLiteJobRepository` | repository adapter | Persist and owner-scope job payloads |
| `FFmpegCapability` / `DesktopRuntime` | local adapter | Existing execution integration, unchanged |
| `tools.video_analyser.analyze_video` | specialized media capability | Offline inspection only |
| `core.video_fetcher`, `tools.video_downloader` | legacy adapters | Not exposed by P3C |
| `core.job_watcher` and Telegram/GUI handlers | legacy worker/application paths | Preserved; no migration |
| Storyboards, timeline composition, generation, publishing | future capability | Not implemented |

## State and execution

Canonical jobs transition through `queued`, `running`, `succeeded`, `failed`,
or `cancelled`; SQLite leases support worker claiming and recovery. P3C
proves durable enqueue and status retrieval. It does not change the existing
worker plane or claim that `video.cut` and `video.render` are automatically
processed by a migrated worker.

## MCP contract

- `video_analyze`: bounded local path, offline inspection, no paid provider.
- `video_create_job`: bounded `cut` or `render`, validated output path and
  format, durable `VideoService` job creation.
- `video_get_job`: owner-scoped structured status lookup.

All filesystem paths must remain under `HERMES_VIDEO_WORKSPACE`; arbitrary
FFmpeg commands, URLs, provider calls, and publishing are outside the contract.
Media-derived text is untrusted and analysis results are marked
`rights_status: reference_only`.

## Scope boundary

P3C changes only the Video MCP, Video skill, the small payload extension needed
to preserve owner/output metadata, and focused tests/configuration. Product,
Research, Knowledge, Memory, P4 worker/scheduler work, P5 provider cleanup,
and P6 legacy retirement remain unchanged.
