---
name: hoc
description: Capture grounded knowledge and source artifacts from media
aliases:
  - hoc_kien_thuc
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học / Grounded Knowledge Capture

This skill executes a rigorous, anti-hallucination 8-step procedure to capture knowledge and artifacts from video or media sources.

## Procedure Contract

1. **Acquire Source Media**:
   - Resolve shortened/redirect URLs (e.g. `vt.tiktok.com`, `youtu.be`) to direct media URLs.
   - Download/copy the media as `video_sample.mp4` into the run directory.
   - If acquisition fails, report the error immediately without substituting web search.

2. **Verify Source Media**:
   - Verify `video_sample.mp4` physically exists, is non-empty, and is decodable.
   - Record SHA-256 digest, byte size, and duration.

3. **Extract Audio Track (Conditional)**:
   - If audio exists: extract `audio.wav`, verify existence, set `has_audio: true`.
   - If silent/mute: set `has_audio: false`, note in transcript, do NOT create fake audio.

4. **Transcribe Audio & Visuals (`exact_transcript.txt`)**:
   - Transcribe full audio with accurate timestamps.
   - Inspect representative frames to capture on-screen text, diagrams, and visual code snippets.
   - Mark ambiguous sections with `[uncertain]`.

5. **Produce Structured Knowledge Analysis (`knowledge_analysis.md`)**:
   - Ground all claims directly in transcript/frames with timestamps.
   - Record real tools, repositories, and exact URLs mentioned.
   - Include actionable step-by-step procedures and caveats.
   - Include at least one Mermaid diagram for workflows/architectures.
   - Label supplemental context as `[supplemental]` and deductions as `[inference]`.

6. **Generate Manifest (`artifact_manifest.json`)**:
   - Record `source_url`, `resolved_url`, `sha256`, `byte_size`, `duration_seconds`, `has_audio`, and paths to all generated artifacts (`video_sample.mp4`, `audio.wav`, `exact_transcript.txt`, `knowledge_analysis.md`).

7. **Propose Governed Knowledge Candidate (HITL)**:
   - Call `knowledge_candidate_create` with `title`, `content`, and grounded evidence.
   - Candidate remains in `draft` / `pending_review` status until explicit human operator approval.
   - Do NOT edit permanent system prompt or memory directly.

8. **Verify on Disk & Respond**:
   - Verify all generated artifacts physically exist on disk and are non-empty.
   - Provide summary in Vietnamese with status (`Thành công` / `Thất bại`), verified artifact paths, and candidate status (`Chờ duyệt`).

