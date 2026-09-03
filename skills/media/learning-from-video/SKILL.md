---
name: learning-from-video
description: Use when learning knowledge, hooks, or CTA from video.
version: 1.1.0
author: Khoa Huynh (@khoahuynhanh97), Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Video, Learning, Knowledge, CTA, Hooks, Transcripts, Media]
    category: media
    related_skills: [youtube-content, grounded-citations]
---

# Learning From Video Skill

This skill guides the agent in systematically capturing, verifying, analyzing, and distilling technical knowledge or conversion copywriting patterns (hooks and calls-to-action) from online and local video media (TikTok, YouTube, Reels, MP4 files).

It enforces an artifact-first, fail-closed, grounded workflow producing verifiable local evidence before proposing lessons to long-term memory under human review. It does not write creative scripts or auto-approve memory entries.

## When to Use

Use when the user provides a video link or media path and intends to:
- **Learn Knowledge / Workflows / Architecture**: Extract engineering procedures, tool configurations, GitHub repositories, system architectures, or technical lessons → `knowledge` mode.
- **Learn Hooks / CTA / Conversion Patterns**: Deconstruct opening hooks, retention pacing, psychological triggers, and call-to-action structures → `cta` mode.

Skip this skill for casual video summarization (answer directly without artifacts) or when authoring a reusable skill package from documents/chat (use `/learn` instead).

## Prerequisites

- **Terminal & media capabilities**: `terminal` or native media capabilities to download video streams and extract audio.
- **File-system tools**: `write_file`, `read_file` for managing run directories and artifacts.
- **Memory/candidate tools**: `memory` or governed candidate submission for human-in-the-loop (HITL) review.
- Optional: `web_search` as supplemental domain context only — never a substitute for actual video content.

## How to Run

Invoke via slash command or natural language:

```bash
/hoc <url_or_path>              # Alias for knowledge mode
/hoc_kien_thuc <url_or_path>    # Knowledge mode (architecture, workflows, tools)
/hoc_cta <url_or_path>          # CTA mode (hooks, pacing, conversion patterns)
/hoc_CTA <url_or_path>          # Case-insensitive; resolves to hoc_cta

# Slack (within 50-command limit):
/hermes hoc <url_or_path>
/hermes hoc_cta <url_or_path>
```

Natural-language invocations that trigger this skill:
- *"Xem video này và học toàn bộ kiến thức trong đó: `<url>`"* → mode `knowledge`
- *"Phân tích cách video này viết hook và CTA: `<url>`"* → mode `cta`
- *"Học quy trình được hướng dẫn trong video để dùng về sau: `<url>`"* → mode `knowledge`

## Quick Reference

| Artifact | knowledge mode | cta mode |
| :--- | :---: | :---: |
| `video_sample.mp4` | ✓ required | ✓ required |
| `audio.wav` | ✓ if `has_audio: true` | ✓ if `has_audio: true` |
| `exact_transcript.txt` | ✓ required | ✓ required |
| `knowledge_analysis.md` | ✓ required | — |
| `cta_analysis.md` | — | ✓ required |
| `artifact_manifest.json` | ✓ required | ✓ required |
| Memory candidate (HITL) | pending_review | pending_review |

Run directory: `reports/knowledge_capture/<source-slug>-<timestamp>/` (collision-safe; never overwrite).

## Procedure

1. **Determine Mode**: Identify whether the request targets `knowledge` mode (architecture, workflows, tools) or `cta` mode (hooks, pacing, conversion). If ambiguous, default to `knowledge`. Do not execute both modes simultaneously.
2. **Load Normative Contract**: You MUST call:
   `skill_view(name="learning-from-video", file_path="references/procedure-contract.md")`
3. **Execute Contract**: Follow the 8-step contract loaded from that reference file precisely for the chosen mode.
4. **No Fallbacks**: Do not rely on informal summaries or alternative procedures.

## Pitfalls

- **Zero-claim without artifacts**: Never say you watched or learned from a video until `video_sample.mp4` and `exact_transcript.txt` exist on disk.
- **Fail-closed on download error**: If acquisition fails (403, captcha, network), report the real error. Do not fabricate content from web search.
- **Silent video safety**: `audio.wav` is optional when `has_audio: false`; verification must not fail on its absence.
- **No direct memory mutation**: Memory updates require the candidate approval gate. Do not bypass it.

## Verification

- [ ] Run directory is collision-safe: `reports/knowledge_capture/<slug>-<timestamp>/`
- [ ] `video_sample.mp4` exists, is non-empty, SHA-256 recorded
- [ ] `audio.wav` exists and is non-empty (only if `has_audio: true`)
- [ ] `exact_transcript.txt` has timestamps and `[uncertain]` markers
- [ ] Correct analysis file for selected mode exists (`knowledge_analysis.md` or `cta_analysis.md`)
- [ ] `artifact_manifest.json` is valid JSON with all required fields including `has_audio`
- [ ] Memory candidate status is `pending_review` (not auto-approved)
