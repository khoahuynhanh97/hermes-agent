# Phase Report — UI apply_job wiring + fresh-project acceptance

**Status**: ✅ PASS

## Implemented
- `video_factory_api.py` — new `POST /api/vf/projects/{id}/jobs/{job_id}/apply`: maps a completed durable job result into Video Factory domain state
  - `image_generate` → `update_frame_generation_status` (frame by request_id)
  - `video_generate` → `update_scene_generation_status` (+ provider_operation_id)
  - `video.render` → no domain mapping (file already in workspace)
  - Idempotent; 404 if job/frame missing; 409 if not completed
- UI poll: after job completed → call `apply_job` → single project refetch (previously jobs completed but domain frame/scene status never updated, which blocked a fresh UI user)

## Why (gap)
In the earlier E2E, frame/scene status was updated by direct service calls in scripts. The UI/API flow had no path to apply a completed worker job back into domain state, so a fresh user could not advance past Storyboard/Video. This closes that gap.

## Live acceptance
None (no paid calls). Proven by a hermetic fresh-project API acceptance test with fake providers + canonical worker + apply_job.

## Files changed
- `video_factory_api.py`
- `web/src/features/video-factory/VideoFactoryPage.tsx`
- `tests/hermes/test_ui1_api.py` (new `test_fresh_project_full_flow_via_api`)

## Tests
- **56/56** focused (UI1 API incl. fresh-project full flow → ready_to_publish; Publishing1; TTS1; data-root; providers; Video Factory)
- `npm run build` PASS | `py_compile` PASS | `git diff --check` clean

## Simplicity review
- ✅ no new class/layer — one API handler + one UI call, reuses existing service
- ✅ no source-of-truth duplication (domain still authoritative)
- ✅ tests mock providers, no paid calls

## Remaining blocker
- TikTok live publish: external app credentials + OAuth (user-provisioned) — unchanged.

## Next evidence-backed step
Fresh-project UI/API acceptance now proven. Publishing1 live remains the only external-resource gate.
