# Learning From Video — Procedure Contract

This is the **single normative source** for the 8-step artifact capture procedure.
Both `agent/knowledge_capture_prompt.py` (prompt engine) and `SKILL.md` (natural-language routing) reference this file. Any modification to this contract must be reflected in both consumers.

---

## Step 1 — Acquire Source Media

1. Resolve any shortened or redirect URL (e.g. `vt.tiktok.com`, `youtu.be`) to the final direct media URL.
2. Download the source video and save as `video_sample.mp4` inside the run directory using available terminal media commands or browser capabilities. For a local source, copy it under that name. Record the final resolved URL separately.
3. **If acquisition fails** (403, captcha, network error, DRM block), stop immediately and report the real error. Do NOT substitute web search results for the video content.

## Step 2 — Verify Source Media

1. Verify `video_sample.mp4` physically exists, is non-empty, and is decodable.
2. Record: SHA-256 digest, byte size, duration in seconds.

## Step 3 — Extract Audio Track (Conditional)

1. If the video contains an audio stream: extract the complete audio as `audio.wav` at full video duration using available media tools. Verify the file exists, is non-empty, and is decodable. Set `has_audio: true`.
2. If the video has NO audio (silent/mute video): set `has_audio: false` in the manifest, note absence of audio in `exact_transcript.txt`, and do NOT create a fake audio file. Verification must NOT fail solely due to the absence of `audio.wav` when `has_audio` is `false`.

## Step 4 — Transcribe Audio & Visuals (`exact_transcript.txt`)

1. Transcribe the full audio from start to finish with accurate timestamps.
2. Inspect representative/key frames to capture on-screen text, code snippets, and visual-only teaching that speech transcription misses.
3. Place `[uncertain]` markers where speech or text recognition is ambiguous.
4. File header must contain: source URL/path, resolved media URL, SHA-256 digest, transcription method, language.

## Step 5 — Produce Structured Analysis

**Mode A — `knowledge_analysis.md`**:
- Claims grounded directly in transcript/frames with timestamps.
- Real tools, repositories, and exact URLs mentioned in the video.
- Step-by-step actionable procedures.
- Cautions, edge cases, and applicability to Hermes.
- At least one Mermaid diagram when visualizing architecture or sequences.
- Supplemental web context explicitly labelled `supplemental`.
- Inferences labelled `inference`.

**Mode B — `cta_analysis.md`**:
- Opening Hook: timestamp and brief verbatim evidence.
- Hook Classification (curiosity, problem/solution, benefit, urgency, social proof, etc.).
- Lead-in narrative structure from hook to core value proposition.
- Pacing, text overlays, and visual cues.
- Primary and secondary CTA: placement timestamp and conversion goal.
- Observed psychological triggers.
- Reusable abstracted template (no verbatim copyright copying).
- Subjective deductions labelled `inference`.

## Step 6 — Generate Manifest (`artifact_manifest.json`)

Required fields:
```json
{
  "source_url": "<input_url_or_path>",
  "resolved_url": "<final_media_url>",
  "sha256": "<hash>",
  "byte_size": 1234567,
  "duration_seconds": 98,
  "has_audio": true,
  "transcription_method": "<transcription_method_or_service>",
  "artifacts": {
    "video_sample": "<absolute_path>",
    "audio_sample": "<absolute_path or 'not_applicable'>",
    "transcript": "<absolute_path>",
    "analysis": "<absolute_path>"
  },
  "memory_candidate_status": "pending_review"
}
```

## Step 7 — Propose Governed Memory Candidate (HITL)

1. Format a distilled summary entry.
2. Submit to governed memory candidate queue for human review.
3. **Strict rules**:
   - Do NOT auto-approve the candidate.
   - Do NOT edit `MEMORY.md` directly.
   - Record status as `pending_review` until a human approves.

## Step 8 — Verify on Disk & Respond

1. Check that every expected artifact physically exists and is non-empty before sending the final answer.
   - `audio.wav` is checked **only** when `has_audio` is `true`.
   - Do NOT claim success when verification fails.
2. Final reply in the user's language (default Vietnamese):
   - Status: `Thành công` / `Một phần` / `Thất bại`.
   - Absolute paths of verified artifact files.
   - Memory candidate status (`Chờ duyệt` / `pending_review`).
   - Disclosures of uncertainties, inferences, and any supplemental web sources used.

---

## Anti-Hallucination Rules (for both consumers)

- Never claim video was watched/learned from unless Step 2 and Step 4 artifacts exist on disk.
- Web search is `supplemental` evidence only — never proof that the video was processed.
- Do not import facts from a vendor website as though the video said them.
