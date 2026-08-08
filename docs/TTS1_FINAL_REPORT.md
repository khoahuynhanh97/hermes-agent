# TTS1 — Minimal Vertex Gemini TTS — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **TTS1 FULL PASS**

---

## 1. Confirmed Voice / Model

- **Voice**: `Zephyr` (user-confirmed)
- **Model**: `gemini-3.1-flash-tts-preview`
- **Location**: `global` | **Project**: `gen-lang-client-0816609628` | **Language**: `vi-VN`

## 2. Endpoint / Auth

```
POST https://aiplatform.googleapis.com/v1beta1/projects/gen-lang-client-0816609628/locations/global/publishers/google/models/gemini-3.1-flash-tts-preview:generateContent
```
- **Auth**: reuse `providers/vertex_auth.get_access_token()` (ADC) — no second auth path, no credentials in code
- Request shape verified live: `speechConfig.languageCode` + `prebuiltVoiceConfig.voiceName`
- **Note**: model does NOT accept `systemInstruction` (returns 400) → `style_prompt` kept as editable UI field / metadata; provider does not send it (verified).

## 3. WAV Evidence

```
wav: D:\work\hermes-agent-data\acceptance\vf-e2e\workspace\audio\tts1_acceptance.wav
size: 201644 bytes
channels: 1 | rate: 24000 | width: 16-bit | frames: 100800 (~4.2s)
```
PCM → stdlib `wave` → 24kHz/16-bit/mono. Stored under `{HERMES_DATA_DIR}\workspaces\video-factory\audio\`.

## 4. Final MP4 Audio Evidence

```
mp4: D:\work\hermes-agent-data\acceptance\vf-e2e\workspace\videos\final_video_with_voiceover.mp4
size: 277483 bytes
ffprobe video: h264, 720x1280 (9:16)
ffprobe audio: aac, 24000 Hz, 1 channel
```
Mixed via `render_with_audio(video, wav, output)` (`-map 0:v:0 -map 1:a:0 -shortest`).

## 5. Files Changed

- `hermes/ports/text_to_speech.py` (new) — `TextToSpeechPort` + `TTSRequest`/`TTSResult`
- `providers/vertex_tts_provider.py` (new) — `GoogleVertexTTSProvider` (reuses `vertex_auth`)
- `hermes/adapters/local/ffmpeg_capability.py` — added `render_with_audio` (only missing capability)
- `video_factory_api.py` — `POST /tts` (generate) + `POST /tts/mix` (FFmpeg mix)
- `web/src/features/video-factory/VideoFactoryPage.tsx` — Voiceover card (text, style, Generate 1x, audio preview, Render with Voiceover)
- `scripts/tts1_live_acceptance.py` (new) — live harness
- `tests/hermes/test_tts1.py` (new, 7 tests)

## 6. Tests

- **7/7 TTS1 tests**: request mapping, PCM→WAV, WAV passthrough, workspace containment, provider error normalization, FFmpeg mix command, API requires text (no auto-generation)
- **39/39** focused backend regression
- **`npm run build`** PASS | `py_compile` PASS | `git diff --check` clean
- All provider calls mocked in tests — no accidental paid calls

## 7. Simplicity Review

- ✅ one TTS port + one provider (no VoiceManager/AudioManager/fallback)
- ✅ reused `vertex_auth` (no duplicate auth)
- ✅ FFmpeg mix = single minimal method
- ✅ voice = user-confirmed Zephyr, not chosen by code
- ✅ exactly 1 live generation authorized; test fixed to mock HTTP (earlier containment test hit live API once — corrected, noted as the one paid call beyond the authorized single sample)

## 8. Remaining Issue

- `style_prompt` not sent (model rejects systemInstruction). Future: prepend style into text via Hermes reasoning (backend creative logic, not provider).

---

## Final Status

✅ **TTS1 FULL PASS** — real Vietnamese voiceover (Zephyr) generated via Vertex, WAV persisted in data root, mixed into 9:16 MP4 with audio stream verified.

Recommend **`Publishing1 — TikTok Integration`** next. Do not begin automatically.
