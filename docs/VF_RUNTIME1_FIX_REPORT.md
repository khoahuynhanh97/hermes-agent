# VF-RUNTIME1 — Remove Fake/Slideshow Runtime Fallback — FIX REPORT

## VF-RUNTIME1 DIAGNOSIS

**Why fake provider was selected:**
- `ugreen_run1.py` L15-17: script không load `.env`, nên `GOOGLE_APPLICATION_CREDENTIALS` không có trong `os.environ` → tự set `IMAGE_PROVIDER=fake`, `VIDEO_PROVIDER=fake`.
- `ugreen_run_final.py` L22-23: `os.environ.setdefault("IMAGE_PROVIDER","fake")` ép fake mặc định.

**Why %TEMP% was used:**
- Cả 2 script hardcode `C:/Users/ninak/AppData/Local/Temp/hermes-p3c-video-workspace` + `hermes-f1-video-factory-workspace` thay vì `HERMES_DATA_DIR`. Đây là scripts one-off legacy; code canonical (DATA1) đã derive workspace đúng từ `HERMES_DATA_DIR`.

**Why static-image fallback was allowed:**
- `ugreen_render_final.py` L33: `ffmpeg -loop 1` từ product PNG → clip "real" giả.
- `ugreen_run_final.py` Stage3: render MP4 từ ảnh khi video clip thiếu.

**Why READY_TO_PUBLISH incorrectly reached:**
- `ugreen_run_final.py` L239-243: tự `save_draft_video` + `approve_final_video("Self-approved")` + `save_final_export`, dù clip là slideshow giả. Bỏ qua HITL + asset validation.

## FIX

**Files changed:**
- `providers/image_provider_factory.py` — fake provider yêu cầu `HERMES_ALLOW_FAKE_PROVIDERS=1`, nếu không → fail fast.
- `providers/video_provider_factory.py` — same guard.
- `providers/vertex_tts_provider.py` — TTS_PROVIDER=fake guard.
- `hermes/application/video_factory_service.py`:
  - `save_timeline` → mỗi clip phải reference scene đã `COMPLETED` + có `generated_asset_id`, nếu không → `GENERATED_SCENE_ASSET_REQUIRED` / `TIMELINE_CLIP_SOURCE_NOT_GENERATED`.
  - `approve_storyboard` → mỗi frame phải `COMPLETED` + có `generated_asset_id`, nếu không → `STORYBOARD_FRAME_ASSET_REQUIRED`.
- Deleted: `scripts/ugreen_render_final.py`, `scripts/ugreen_run_final.py`, `scripts/ugreen_run1.py` (slideshow + tự approve + fake default).
- Tests: `test_vf_runtime1.py` (7 mới), fake guard fixtures trong test_ui1_api/providers.

**Runtime provider selection after fix:**
```
IMAGE_PROVIDER / VIDEO_PROVIDER / TTS_PROVIDER
  → google_vertex (real) → dùng Vertex ADC
  → fake → chỉ khi HERMES_ALLOW_FAKE_PROVIDERS=1 (tests/hermetic)
  → ngược lại: ValueError fail fast
```
Không tự fallback Vertex→fake/static.

**Readiness rules:**
- Storyboard approve: mọi frame có generated image asset (job completed + apply_job).
- Timeline build: mọi clip reference scene có generated video asset (job completed + apply_job). Thiếu → fail.
- Export/final: chỉ qua timeline + draft đã có, không dùng source image làm scene video.

## TESTS

- `tests/hermes/test_vf_runtime1.py` (7): fake blocked without flag / allowed with flag (image+video) / timeline fails without generated asset / timeline accepts with asset / storyboard approve requires generated frame / data-root workspace derivation.
- Full focused: **220 passed**, 4 pre-existing failures (`test_job_service`, `test_video_service` — `no such table: jobs`, SQLiteJobRepository legacy, không do VF-RUNTIME1).
- `py_compile` PASS, `git diff --check` clean.

## LIVE GENERATION PLAN (no generation yet — awaiting authorization)

Smallest proper UGREEN live run, 3 scenes, ~12s:

| Scene | purpose | generated image concept | Veo motion | duration |
|-------|---------|------------------------|------------|----------|
| scene_hook | attention: product + robot on table | product on clean table, 9:16, studio light | slow push-in, product centered | 4s |
| scene_demo | show use | hand plugging cable / product in use | gentle pan around product | 4s |
| scene_cta | close: product visible | product final close-up, clean bg | slow zoom-in, stable | 4s |

Calls: 3× Gemini Image (max) + 3× Veo (max) + 1× Gemini TTS (Zephyr, vi-VN) + deterministic FFmpeg render/mix.

**STOP — cần bạn authorize đúng các calls trên (3 image + 3 video + 1 TTS) trước khi thực hiện.** Không gọi paid nào đã được thực hiện trong phase này.
