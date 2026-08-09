# P5 LLM Ownership and Provider Normalization

## Decision

Generic semantic reasoning is owned by the configured Hermes brain:

`Hermes -> custom OpenAI-compatible provider -> 9Router (http://127.0.0.1:20128/v1) -> reason_combo`

The application sends the logical name `reason_combo` only. The models inside
that combo and their fallback order remain 9Router configuration and are not
duplicated in project code.

## Evidence-backed inventory

| Call site | Purpose | Classification | Current provider | Canonical owner | Action |
|---|---|---|---|---|---|
| `hermes/llm.py` | Typed text and structured output for Product/Research | `GENERIC_REASONING` | `core.llm_gateway` to 9Router | Hermes brain / `reason_combo` | Keep typed wrapper; preserve JSON validation |
| `hermes/adapters/model/affiliate_analysis_gateway.py` | Structured research analysis | `GENERIC_REASONING` | HermesLLMGateway | Hermes brain / `reason_combo` | No provider coupling |
| `hermes/adapters/model/affiliate_content_gateway.py` | Structured content package | `GENERIC_REASONING` | HermesLLMGateway | Hermes brain / `reason_combo` | No provider coupling |
| `core/llm_gateway.py` | Legacy text callers and compatibility boundary | `GENERIC_REASONING` plus compatibility | 9Router; optional explicit legacy fallback | Hermes brain / `reason_combo` | Normalize all text tasks to one logical combo; remove app fallback models |
| `core/ai_router.py` | Provider status UI and explicit legacy fallback | `LEGACY_UNUSED` for generic production inference | Direct Gemini/OpenAI-compatible/Ollama providers | None for canonical brain | Keep temporary for status/rollback; no new callers |
| `core/job_watcher.py` | Existing learning/script worker and provider status | `LEGACY_UNUSED` for text path | Text via `core.llm_gateway`; status via `ai_router` | Hermes brain for text | Migrate/retire with legacy worker plan; outside P5 broad cleanup |
| `tools/video_analyser.py` | Source-bound video/image analysis | `SPECIALIZED_VISION` | Gemini Vision or local OpenCV fallback | Vision/media capability | Preserve separate adapter and offline behavior |
| `core/video_fetcher.py` | Speech transcription | `SPECIALIZED_AUDIO` | local `faster-whisper` | STT capability | Preserve |
| `core/*_generator.py`, GUI Gemini REST | Older GUI/script generation paths | `GENERIC_REASONING` | Direct Gemini | Hermes brain / `reason_combo` | Active legacy callers; parity migration is a follow-up, not broad P5 cleanup |
| `core` video cut/render workers | Deterministic media execution | `SPECIALIZED_VIDEO_GENERATION` | local FFmpeg/execution, not an LLM | Video execution capability | Preserve; no speculative provider added |

## Normalization

`core/llm_gateway.py` remains a compatibility adapter because legacy callers
still exist. It now sends exactly one candidate model, `reason_combo`, and does
not reproduce 9Router fallback logic. `LLM_PROVIDER=legacy` remains an explicit
rollback path only and is disabled by default.

Specialized vision and audio paths are not routed through the generic brain.
No image-generation, video-generation, embedding, or new generic router was
introduced by P5.
