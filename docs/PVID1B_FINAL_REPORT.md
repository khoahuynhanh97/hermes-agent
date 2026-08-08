# PVID1B — Correct Vertex Veo Integration — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **PVID1 FULL PASS**

---

## 1. Confirmed Provider / Model / Region

- **Provider**: `google_vertex`
- **Model**: `veo-3.1-generate-001` (exact, no `-preview`)
- **Region**: `us-central1`
- **Project**: `gen-lang-client-0816609628`

---

## 2. Exact Endpoints

**Submit**:
```
POST https://us-central1-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001:predictLongRunning
```

**Poll**:
```
POST https://us-central1-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001:fetchPredictOperation
body: {"operationName": "<FULL_OPERATION_NAME>"}
```

Obsolete paths removed: `:generateVideos`, `GET /operations/{id}`, `:fetchAndListVideos`, `vertex_operation_endpoint`.

---

## 3. Auth Path

`providers/vertex_auth.get_access_token()` — ADC, scope `https://www.googleapis.com/auth/cloud-platform`. Reused PIMG1 path. Service account `vertex-express@gen-lang-client-0816609628.iam.gserviceaccount.com`. No credentials in code.

---

## 4. Request Parameters Actually Used

```json
{
  "instances": [{
    "prompt": "A single blue water bottle on a clean table, the camera slowly pans around it, soft studio lighting",
    "image": { "bytesBase64Encoded": "<dbg3.png base64>", "mimeType": "image/png" }
  }],
  "parameters": {
    "aspectRatio": "9:16",
    "durationSeconds": 4,
    "resolution": "720p",
    "sampleCount": 1
  }
}
```

No GCS, no storageUri, no multiple samples, no fallback.

---

## 5. Async Flow (per worker design)

```
video_generate job
→ worker claim 1: predictLongRunning → persist FULL operationName → retryable requeue
→ worker claim 2..N: fetchPredictOperation
    → running: retryable requeue (later claim resumes)
    → done: decode bytesBase64Encoded → write <workspace>/videos/<id>.mp4 → job completed
```

One step per claim. Poll cadence lives in the driver (`time.sleep(15)` between claims), NOT inside worker execution and NOT in Hermes.

---

## 6. Live Acceptance Result

```
state: completed
output_path: C:\Users\ninak\AppData\Local\Temp\tmpxcxsdhfa\workspace\videos\projectsgen-lang-client-0816609628locati.mp4
exists: True
size_bytes: 762520
provider: google_vertex
provider_operation_id: projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-generate-001/operations/21d56807-c28e-4e04-aa16-d8288637e233
scene_id: scene_1
```

- `state = completed` ✅
- file exists, 762520 bytes, valid MP4 ✅
- path within Video Factory workspace ✅
- `provider_operation_id` = full operation name ✅
- `scene_id` preserved ✅

---

## 7. Files Changed

**Modified**:
- `providers/vertex_video_provider.py` — correct contract (`predictLongRunning` / `fetchPredictOperation`), inline base64 → workspace MP4, GCS-URI fallback as error (no GCS subsystem), `mime_for()` instead of hardcoded PNG
- `workers/job_worker.py` — `video_generate` single-shot: submit→persist op→requeue, or fetch once→running requeue/done complete
- `providers/vertex_auth.py` — removed unused `vertex_operation_endpoint`
- `scripts/pvid1b_live_acceptance.py` — live harness (driver-level poll cadence, `max_attempts: 200`)

**Tests updated** (no duplicate suite): `tests/hermes/providers/test_video_provider.py`

**Unchanged**: `VideoGenerationPort`, `video_provider_factory`, fake provider, Video Factory domain/application.

---

## 8. Tests

**21/21 provider tests passing** (13 image + 8 video). Covered: `predictLongRunning` endpoint, request body, PNG→base64, operationName persistence, `fetchPredictOperation`, running state, completed base64→workspace MP4, provider error normalization, worker resume (2 claims), workspace containment.

**89/89 focused regression passing**. `py_compile` PASS. `git diff --check` clean.

---

## 9. Self-Review Findings

### code-review-self checklist

| Check | Result |
|-------|--------|
| Correctness (live output verified) | ✅ 762KB MP4 |
| Edge cases: empty op name, non-200, no video bytes, gcsUri-only, timeout | ✅ normalized in adapter |
| Error normalization (JSON + non-JSON) | ✅ |
| Security: no secrets, ADC only, workspace containment | ✅ |
| DRY: reused `vertex_auth`, `gemini_common.mime_for`, existing worker | ✅ |
| Dead code removed (`vertex_operation_endpoint`) | ✅ |
| Hardcoded assumptions: PNG mime fixed via `mime_for()` | ✅ fixed this pass |

### intended-vs-implemented

| Intended (task claim) | Implemented (evidence) |
|-----------------------|-------------------------|
| submit `:predictLongRunning` | `vertex_model_endpoint(..., "predictLongRunning")` ✅ |
| persist FULL operationName | worker `update_payload(... provider_operation_id=<full>)` ✅ |
| poll `:fetchPredictOperation` `{"operationName": full}` | `check_status` POST body ✅ |
| NOT `generateVideos`/GET-op/fetchAndListVideos | grep: zero stale refs ✅ |
| inline base64 → `<workspace>/videos/` | `_download_result` writes to `self.output_dir` = `workspace/videos` ✅ |
| gcsUri only as fallback error, no GCS subsystem | ✅ |
| no tight poll in Hermes | single-step per claim; driver cadence ✅ |
| reuse ADC auth | `from providers.vertex_auth import get_access_token` ✅ |
| no model fallback | factory only fake/google_vertex; no fallback list ✅ |
| worker resume after restart/requeue | async test: 2 claims resume from persisted op ✅ |
| workspace containment | reference via `_contained_file`; output under `workspace/videos` ✅ |

No mismatches that cross a trust/cost/data boundary.

---

## 10. Simplicity Assessment

- One adapter, direct REST (requests), no SDK
- Reused port/factory/worker/auth
- No new manager/coordinator/polling-engine
- No GCS abstraction, no fallback routing, no multi-sample
- Small focused test edits (8 video tests), not a duplicate suite

---

## 11. Remaining Blocker

None. Live generation passed.

Note: `veo-3.1-generate-001` image_to_video supports durations `4/6/8` seconds (`5` returns an API validation error); `4` was used as specified.

---

## 12. Next Step

**Recommend VF-E2E — Real Video Factory End-to-End Acceptance** (B1→B10 with real image + video assets). Do not begin automatically.
