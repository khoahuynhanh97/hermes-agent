# TTS1A — Fix Gemini TTS Style Prompt Mapping — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **TTS1A PASS**

---

## Fix

`GoogleVertexTTSProvider` no longer sends `systemInstruction` (which the model rejects with 400). It now combines `style_prompt` + voiceover text into a single `contents.text` via `_build_text`.

## Exact contents mapping

```text
style_prompt non-empty:
  "<STYLE PROMPT>\n\nSay the following:\n<VOICEOVER TEXT>"

style_prompt empty:
  "Say the following:\n<VOICEOVER TEXT>"
```

Final payload `contents`:

```json
{"contents": [{"role": "user", "parts": [{"text": "<mapped text>"]}]}
```

No `systemInstruction`. No creative defaults in provider. `style_prompt` stays editable UI/request data.

## Verified

- Provider: `gemini-3.1-flash-tts-preview` | voice `Zephyr` | `vi-VN` | `global` | auth reuse `vertex_auth`
- WAV/FFmpeg/UI flow unchanged

## Tests

- **9/9 TTS1A tests** (updated):
  - style prompt appears in `contents`
  - voiceover text appears unchanged
  - no `systemInstruction` in payload
  - empty style → minimal instruction only, no default style
  - `_build_text` exact strings (with/without style)
  - + existing PCM→WAV, passthrough, containment, error, FFmpeg mix, API text-required
- **38/38** focused regression | `py_compile` PASS | `git diff --check` clean
- Frontend untouched (no rebuild needed)

## Live-call guard

Autouse fixture in `test_tts1.py` blocks `requests.post` + `get_access_token` by default; any test that would accidentally reach Vertex fails fast. No live provider call during tests.

## Simplicity

- No new file/class (one method added to existing provider)
- No new provider, no auth change, no UI redesign, no publishing

---

**TTS1A PASS.** Not starting Publishing1.
