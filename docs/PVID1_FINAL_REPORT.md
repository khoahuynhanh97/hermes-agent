# PVID1 — Real Video Provider Integration — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **PVID1 IMPLEMENTATION PASS / LIVE ACCEPTANCE BLOCKED (Veo not granted on project)**

---

## 1. PVID1 Status

✅ **PVID1 IMPLEMENTATION PASS / LIVE ACCEPTANCE BLOCKED**

- Vertex Veo adapter implemented behind existing `VideoGenerationPort`
- Async flow (submit → persist operation id → bounded poll) wired into the canonical worker
- 8/8 new tests + 89/89 focused regression passing
- Live attempt: Veo model is **not granted on project `gen-lang-client-0816609628`** (`404 Publisher model not found`)

---

## 2. Provider + Model

**Provider**: Google Cloud Vertex AI (Veo video generation)  
**Model (configured)**: `veo-3.0-preview` (also tried `veo-3.1-preview`, `veo-2.0`, `veo-3.0-lite`)  
**Project**: `gen-lang-client-0816609628`  
**Location**: `us-central1`

All Veo model IDs return `404 Publisher model not found` via `:predict` — the account has not been granted Veo access (preview/allowlist required). This is a project provisioning blocker, not a code issue.

---

## 3. Endpoint / Auth

**Submit**:
```
POST https://us-central1-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.0-preview:generateVideos
```

**Poll**:
```
GET  https://us-central1-aiplatform.googleapis.com/v1/projects/{project}/locations/us-central1/operations/{operation}
```

**Fetch result**:
```
POST .../models/{model}:fetchAndListVideos   body: {"requestId": "<operation id>"}
```

**Auth**: shared ADC helper (`providers/vertex_auth.get_access_token`) — Bearer token from `google.auth.default(scopes=[cloud-platform])`. Same proven auth path as PIMG1.

---

## 4. Async Flow

```
video_generate job
  → worker claim
  → provider.generate()  → POST :generateVideos → operation name
  → persist provider_operation_id in job payload (durable, survives restart)
  → bounded poll loop (worker execution, NOT Hermes):
      provider.check_status() → GET operation
        running → sleep VIDEO_POLL_SECONDS
        done    → :fetchAndListVideos → write .mp4 into workspace → complete
  → timeout → RuntimeError → retryable requeue (next claim resumes from stored operation id)
```

No tight blocking poll inside Hermes; polling happens in the worker/provider (execution layer). Operation id is durable so a fresh worker claim continues safely.

---

## 5. Live Acceptance

Canonical path exercised with real provider config:

```
video_generate job → worker → GoogleVertexVideoProvider → Vertex API
```

Result: `state: failed`
```
vertex http 404: non-JSON response (endpoint/model may not exist)
```

Verified separately via `:predict`:
```
404 Publisher model `projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.0-preview` not found
```

**Exact blocker**: Veo models are not enabled for project `gen-lang-client-0816609628`. Access requires granting/preview allowlist in the GCP project (Vertex AI > Enable Veo / request access). No generated asset was produced because the model is not provisioned.

---

## 6. Generated Asset

None (blocked). When a Veo model is enabled, the worker writes the video to `<workspace>/videos/{request_id}.mp4` and links it via the job result (`output_path`, `provider_operation_id`, `scene_id`). The fake provider path proves asset persistence + workspace containment deterministically.

---

## 7. Files Changed

**Created**:
- `providers/vertex_auth.py` — shared ADC auth + endpoint helpers (deduped from PIMG1)
- `providers/vertex_video_provider.py` — `GoogleVertexVideoProvider` (async submit/poll/download)
- `providers/video_provider_factory.py` — `VIDEO_PROVIDER=fake|google_vertex`
- `scripts/pvid1_live_acceptance.py` — live harness
- `tests/hermes/providers/test_video_provider.py` — 8 tests

**Modified**:
- `hermes/ports/video_generation.py` — added `aspect_ratio` field (default `""`, backward compatible)
- `workers/job_worker.py` — `video_generate` handler (async submit/poll/requeue); handlers now receive `job_id`
- `providers/vertex_image_provider.py` — refactored to shared `vertex_auth`
- `providers/fake_video_provider.py` — FFmpeg-missing fallback writes placeholder (tests run without ffmpeg)
- `.env.example` — documented `VIDEO_PROVIDER` / `VIDEO_MODEL` / poll config

**Unchanged**: `VideoGenerationPort` contract (one additive field), Video Factory domain/application, fake provider for sync tests.

---

## 8. Tests

**8/8 video-provider tests**:
- factory selection (fake vs google_vertex)
- submit async → operation id + aspect ratio 9:16 + duration
- submit with reference image (base64 first-frame)
- submit error normalization (404 Publisher model not found)
- check_status running → no video yet
- check_status done → fetchAndListVideos → persisted mp4 in workspace
- worker sync completion (fake)
- worker async submit→poll→complete (scripted async fake)

**Focused regression**: `89 passed` (13 image + 8 video + K6 8 + K5 11 + K4 22 + K3 11 + Video Factory 13 + duplicate 3).

**Checks**: `py_compile` PASS; `git diff --check` clean.

**Pre-existing failure unchanged**: `test_learning_service.py::test_worker_builds_atomic_lessons_from_source_bound_analysis`.

---

## 9. Remaining Issues

- **Veo not enabled on project** — requires GCP access grant / preview allowlist
- Service-account key lives outside repo (`C:\Users\ninak\.google-creds\...`), must not be committed
- `generateVideos` route returns non-JSON 404 until a Veo model is provisioned

---

## 10. Next Step

PVID1 is implementation-ready. Once Veo is enabled on the project, re-run
`python scripts/pvid1_live_acceptance.py` for live proof.

**Recommend VF-E2E — Real Video Factory End-to-End Acceptance** once a live
video asset exists, to prove the full B1→B10 flow with real image + video
assets. Do not begin it automatically.
