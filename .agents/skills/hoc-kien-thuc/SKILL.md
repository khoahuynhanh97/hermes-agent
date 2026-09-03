---
name: hoc-kien-thuc
description: Alias for /hoc — capture grounded knowledge and source artifacts
allowed-capabilities:
  - knowledge.candidate.create
allowed-tools:
  - knowledge_candidate_create
  - knowledge_retrieve
---

# Học Kiến Thức / Grounded Knowledge Capture

Alias for `/hoc`. Executes the 8-step anti-hallucination media knowledge capture procedure:

1. **Acquire Source Media**: Resolve URL and download/copy as `video_sample.mp4`. Fail closed on download errors.
2. **Verify Source Media**: Assert non-empty and decodable; record SHA-256 and duration.
3. **Extract Audio Track (Conditional)**: Extract `audio.wav` if present; set `has_audio` flag.
4. **Transcribe Audio & Visuals (`exact_transcript.txt`)**: Full timestamps, frame inspection for on-screen text, mark uncertainties.
5. **Produce Structured Analysis (`knowledge_analysis.md`)**: Grounded claims, URLs, Mermaid diagrams, procedures.
6. **Generate Manifest (`artifact_manifest.json`)**: Record full metadata and artifact paths.
7. **Propose Governed Candidate (HITL)**: Submit via `knowledge_candidate_create` for operator review.
8. **Verify on Disk & Respond**: Confirm physical artifacts on disk and reply with summary.

