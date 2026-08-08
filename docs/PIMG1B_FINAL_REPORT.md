# PIMG1B — Switch Image Provider to Gemini (Vertex) — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **PIMG1 FULL PASS** (live generation verified)

---

## 1. Status

✅ **PIMG1 FULL PASS**

- Vertex AI adapter implemented behind existing `ImageGenerationPort`
- Canonical worker/job path live-verified end to end
- Generated storyboard image persisted inside the Video Factory workspace
- Config-based provider selection; ADC/service-account auth, no credentials in code

**Model note**: the task-specified `gemini-3.1-flash-lite-image` does **not exist**
on this project (Vertex returns `404 Publisher model not found`). The live run used
`gemini-2.5-flash-image`, the available Gemini image model on the project.
Adapter/config are model-agnostic; setting a valid `IMAGE_MODEL` works.

---

## 2. Provider / Endpoint / Auth

**Provider**: Google Cloud Vertex AI (Gemini image model)  
**Model used (live)**: `gemini-2.5-flash-image`  
**Project**: `gen-lang-client-0816609628`  
**Location**: `us-central1` (required — `global` returns 404 for image models)

**Endpoint**:
```
https://us-central1-aiplatform.googleapis.com/v1/projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/gemini-2.5-flash-image:generateContent
```

**Auth**: Application Default Credentials (`google.auth.default()` with
`cloud-platform` scope → Bearer token). Service account:
`vertex-express@gen-lang-client-0816609628.iam.gserviceaccount.com`.
Key file path set via `GOOGLE_APPLICATION_CREDENTIALS` in `.env` (path only).

**Config**:
```
IMAGE_PROVIDER=google_vertex
IMAGE_MODEL=gemini-2.5-flash-image
GOOGLE_CLOUD_PROJECT=gen-lang-client-0816609628
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=<path to service-account key file>  # not committed
```

---

## 3. Changes

**Created**:
- `providers/gemini_common.py` — shared payload builders (contents, aspect ratio, image extraction incl. Vertex string-`inlineData` handling, output path)
- `providers/vertex_image_provider.py` — `GoogleVertexImageProvider` (ADC auth, project/location/model config, idempotency, normalized errors)
- `scripts/setup_vertex_auth.py` — validates a downloaded service-account key and writes the env var path (no secrets printed)
- `scripts/pimg1b_live_acceptance.py` — canonical live acceptance harness
- 6 Vertex adapter tests

**Modified**:
- `providers/gemini_image_provider.py` — refactored to use `gemini_common` (Developer-API adapter retained)
- `providers/image_provider_factory.py` — added `google_vertex`
- `.env.example` — documented Vertex config, `us-central1`
- tests: negative-prompt semantics updated

**Unchanged**: `ImageGenerationPort`, worker job contract, fake provider, Video Factory domain, workspace containment.

---

## 4. Fixes found during live acceptance

| Issue | Fix |
|-------|-----|
| `google.auth.default()` returned `Request`-less token path | use `google.auth.default(scopes=[cloud-platform])` + `credentials.refresh(Request())` |
| `global` location → 404 for image models | location default `us-central1` |
| Vertex requires `role: "user"` in contents | added role to `build_contents` |
| Vertex returns `inlineData` as a **string** (repr/JSON) | `extract_image` parses dict or string form |
| negative-prompt text triggers image-model **safety block** | Gemini image models have no negative semantics → prompt sent as-is (negative no longer appended) |

---

## 5. Live Acceptance (canonical path)

```
image_generate job → CanonicalJobRepository → worker → GoogleVertexImageProvider → Vertex API
```

Result: `state: completed`
```
output_path: ...\workspace\images\pimg1b_storyboard_frame.png
exists: True
size_bytes: 976685
provider: google_vertex
provider_operation_id: vertex:20260807155742
```

Generated asset is a valid PNG persisted inside the configured Video Factory workspace.

---

## 6. Tests

**13/13 image-provider tests passing**:
- 5 Gemini Developer adapter
- 6 Vertex adapter (endpoint URL, success payload/auth, idempotency, 403 normalization, missing project, ADC failure reporting)
- 2 worker `image_generate` (fake-provider asset persistence + bad-payload rejection)

**Focused regression**: `81 passed`.

**Checks**: `py_compile` PASS; `git diff --check` clean.

**Pre-existing failure unchanged**: `test_learning_service.py::test_worker_builds_atomic_lessons_from_source_bound_analysis`.

---

## 7. Remaining Issues

- `gemini-3.1-flash-lite-image` unavailable on the project; live model is `gemini-2.5-flash-image`
- Service-account key file stored at `C:\Users\ninak\.google-creds\...` — outside repo, must not be committed

---

## 8. Next Step

PVID1 (real video provider) can proceed: same adapter + factory + worker pattern is proven live.

Do not begin PVID1 automatically.
