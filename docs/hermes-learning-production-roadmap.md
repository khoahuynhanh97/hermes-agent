# Hermes Learning And Production Roadmap

## Implementation Status (2026-07-12)

The active product is the Telegram learning assistant. The current runtime
supports asynchronous learning jobs, transcript/audio fallback, bounded
metadata-only fallback, concise summary output, pending/approved/rejected
knowledge, Telegram approval buttons, job status/retry/cancel, and a local
conversation memory. Text requests go through the Hermes LLM gateway toward
9Router; live provider credentials and model aliases still must be configured
inside 9Router before a real chat smoke test can pass.

Video generation, paid providers, FFmpeg orchestration, and batch generation
remain deferred. They are roadmap options, not current Hermes requirements.

This document is the implementation direction for Hermes after the Telegram
learning workflow changes.

## Product Direction

Long-term goal: produce AI videos in batches.

Short-term priority: make Hermes a Telegram assistant that can learn from
TikTok, YouTube, uploaded videos, transcripts, screenshots, and user notes.

These two goals share one foundation: approved knowledge. Hermes should learn
from real examples first, then use approved lessons to create stronger video
production packages.

## Target Layers

```text
Telegram Assistant
        |
Learning & Knowledge Engine
        |
Video Production Engine
```

### Layer 1 - Telegram Assistant

Daily user interface:

- Receive text, links, videos, audio, images, and transcripts.
- Route intent.
- Create async jobs.
- Report status and errors.
- Return concise Telegram-readable results.
- Send only the useful artifact files.

Near-term commands:

- `/hoc_kien_thuc <source>`
- `/hoc_video <source>`
- `/hoc_hook_CTA <source>`
- `/len_kich_ban <source>`
- `/status <job_id>`
- `/cancel <job_id>`
- `/retry <job_id>`

### Layer 2 - Learning & Knowledge Engine

Core workflow:

```text
source video/text
  -> ingestion
  -> downloader/transcript fallback
  -> metadata/audio/scene/visual analysis
  -> lesson extraction
  -> pending knowledge
  -> approve/reject/edit
  -> approved knowledge store
```

Important rule: production workflows may use only approved knowledge.

### Layer 3 - Video Production Engine

Do not start with paid video generation. First build production planning and
provider interfaces.

Production package output:

```text
project/
  product_analysis.json
  strategy.md
  script.md
  storyboard.json
  image_prompts.md
  video_prompts.md
  voice_script.txt
  subtitle.srt
  production_manifest.json
```

## Unified Architecture

```text
                         Telegram
                             |
                       Telegram Bot
                             |
                     Hermes Orchestrator
                             |
          +------------------+------------------+
          |                  |                  |
     Chat/Question      Learning Job       Production Job
          |                  |                  |
     LLM + Tools       Video Analyzer       Workflow Engine
                             |                  |
                     Knowledge Store     Provider Adapters
                             |                  |
                  Pending / Approved      Image / Video / Voice
                             |                  |
                       Retrieval API         FFmpeg
                             +--------+---------+
                                      |
                                  QA Engine
```

Do not split this into two products such as "Learning Hermes" and "Video
Hermes". Keep one Hermes Agent with learning, production planning, and
generation workflows.

## Learning Input Contract

Normalize all learning requests into one shape:

```json
{
  "source_type": "youtube",
  "source_url": "https://...",
  "local_path": "",
  "user_instruction": "Phan tich cach lam hook",
  "learning_scope": ["hook", "script", "visual", "editing"]
}
```

Supported input types:

- YouTube link.
- TikTok link.
- Uploaded video.
- Audio file.
- Transcript.
- Image or screenshot.
- Plain text note.

## Download And Fallback Policy

Video download failure should not automatically fail the learning job.

Fallback tiers:

1. Use `yt-dlp` to download video.
2. Use official transcript when available.
3. Use auto transcript when available.
4. Download audio and run speech-to-text.
5. Use metadata, thumbnail, description, and webpage extraction.
6. Ask the user to upload the source file.

Every result must report confidence:

- `high`: video or video+transcript analyzed.
- `medium`: transcript or audio analyzed.
- `low`: metadata/thumbnail/text-only analysis.
- `needs_source`: not enough source material.

## Analysis Pipeline

Avoid sending one giant prompt that says "analyze this video". Use staged
analysis:

```text
Video
  -> metadata analysis
  -> transcript analysis
  -> audio analysis
  -> scene detection
  -> key-frame extraction
  -> visual analysis
  -> combined lesson synthesis
```

Extract these groups:

- Content: topic, audience, pain point, benefit, CTA.
- Hook: timestamp, hook type, opening line, opening image, retention reason.
- Script: sentence structure, voice tone, pacing, story arc.
- Visual: angle, shot size, background, lighting, camera motion, product setup.
- Editing: shot duration, cut rhythm, transition, caption, sound effect, music.
- Reusable lessons: rule, applicability, avoid cases, evidence, confidence.

## Lesson Schema

Knowledge should not be stored as only a long markdown paragraph. Store a
structured lesson:

```json
{
  "id": "lesson_20260712_001",
  "source": {
    "platform": "youtube",
    "url": "https://...",
    "title": "Product review tutorial"
  },
  "category": "product_video",
  "lesson_type": "hook",
  "summary": "Show the product result in the first 2 seconds.",
  "rule": {
    "action": "show_product_result_first",
    "timing_seconds": {
      "from": 0,
      "to": 2
    }
  },
  "applicable_when": [
    "short_product_showcase",
    "problem_solution_video"
  ],
  "avoid_when": [
    "storytelling_requires_context"
  ],
  "evidence": [
    {
      "timestamp": "00:00-00:02",
      "description": "The video opens with the result before explaining."
    }
  ],
  "confidence": 0.87,
  "status": "pending"
}
```

Fields required for future retrieval:

- `category`
- `lesson_type`
- `applicable_when`
- `avoid_when`
- `product_types`
- `video_styles`
- `platform`
- `duration_range`
- `confidence`
- `evidence`

## Bridge To Video Production

Production jobs must retrieve knowledge by context, not load everything.

Example context:

```text
Product: phone stand
Goal: TikTok product showcase
Duration: 8 seconds
Style: pastel
```

Retrieve:

- Hooks for product showcase.
- Camera motion for small products.
- Lighting lessons for pastel setups.
- Shot timing for 8-second videos.

Exclude:

- Talking-head lessons when not needed.
- Long YouTube lessons.
- Lessons for large products.
- Low-confidence lessons unless explicitly requested.

## Video Provider Interface

Build provider contracts before integrating paid services.

```python
from dataclasses import dataclass
from typing import Protocol


@dataclass
class GenerationRequest:
    prompt: str
    aspect_ratio: str = "9:16"
    duration_seconds: int = 8
    reference_image: str | None = None


@dataclass
class GenerationResult:
    job_id: str
    status: str
    output_path: str | None = None
    error: str | None = None


class VideoProvider(Protocol):
    def submit(self, request: GenerationRequest) -> GenerationResult:
        ...

    def get_status(self, job_id: str) -> GenerationResult:
        ...

    def cancel(self, job_id: str) -> bool:
        ...
```

Initial providers:

```text
providers/video/
  base.py
  mock_provider.py
  veo_provider.py
  kling_provider.py
  runway_provider.py
  browser_provider.py
```

Only `mock_provider.py` is required at first.

## Roadmap

### Phase 1 - Telegram Learning Assistant

- Receive text, link, video, audio, image, and transcript.
- Intent router.
- Async job queue.
- `/status`, `/cancel`, `/retry`.
- YouTube/TikTok analysis.
- Clear error reporting.
- Concise Telegram result plus one useful markdown file.

### Phase 2 - Knowledge Approval

- Structured lesson schema.
- Pending/approved/rejected lifecycle.
- Inline approve/reject/edit buttons.
- Dedupe by normalized source URL and lesson hash.
- Source tracking and confidence.
- Use only approved knowledge.

### Phase 3 - Production Planning Without Paid APIs

- Product analyzer.
- Strategy generator.
- Script generator.
- Storyboard generator.
- Image prompt generator.
- Video prompt generator.
- Production manifest.
- Prompt pack export.

### Phase 4 - Video Pipeline Skeleton

- Provider interface.
- Mock provider.
- Job submission and polling.
- Retry policy.
- Cost estimation.
- Budget limit.
- Output storage.
- FFmpeg interface.

### Phase 5 - One Real Provider

- Pick one provider only.
- Estimate cost before running.
- Ask for confirmation.
- Generate one test video.
- Score result quality.

### Phase 6 - Batch Generation

- Product queue.
- Concurrency limit.
- Daily budget.
- Provider fallback.
- Quality scoring.
- Duplicate detection.
- Resume after restart.

## Current Implementation Bias

For the current repo, prioritize:

1. Stabilize Telegram learning output.
2. Add structured lesson schema and pending approval.
3. Add retrieval API for approved knowledge.
4. Add production package generation without paid providers.
5. Add video provider interface and mock provider.
