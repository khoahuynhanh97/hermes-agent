---
name: hoc-cta
description: Capture hooks, CTA, and conversion structures from media
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học CTA / Conversion Capture

Executes the 8-step anti-hallucination media conversion capture procedure in `cta` mode:

1. **Acquire Source Media**: Resolve URL and download/copy as `video_sample.mp4`.
2. **Verify Source Media**: Assert non-empty and decodable; record SHA-256 and duration.
3. **Extract Audio Track (Conditional)**: Extract `audio.wav` if present.
4. **Transcribe Audio & Visuals (`exact_transcript.txt`)**: Full timestamps, frame inspection for on-screen text overlays, pacing.
5. **Produce Structured CTA Analysis (`cta_analysis.md`)**:
   - Opening Hook: timestamp and verbatim evidence.
   - Hook Classification (curiosity, problem/solution, benefit, urgency, social proof).
   - Lead-in narrative structure to core value proposition.
   - Pacing, text overlays, visual cues.
   - Primary & secondary CTA placement timestamps and conversion goals.
   - Observed psychological triggers.
   - Abstracted reusable template (no verbatim copyright copying).
6. **Generate Manifest (`artifact_manifest.json`)**: Record full metadata and artifact paths.
7. **Propose Governed Candidate (HITL)**: Submit via `knowledge_candidate_create` for operator review.
8. **Verify on Disk & Respond**: Confirm physical artifacts on disk and reply with summary.

