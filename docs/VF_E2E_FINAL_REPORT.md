# VF-E2E — Real Video Factory End-to-End Acceptance — FINAL REPORT

**Date**: 2026-08-07  
**Status**: ✅ **VF-E2E FULL PASS**

---

## 1. Final Project State

```
Project: vfe2e_project
Owner: e2e_owner
DB: D:\work\hermes-agent-data\acceptance\vf-e2e\e2e.db
Workspace: D:\work\hermes-agent-data\acceptance\vf-e2e\workspace
Status: ready_to_publish
final_approval: approved
final_video_asset_id: final_asset_1
```

Fresh-process reconstruction verified (new service+repo instance, durable state only).

---

## 2. Resource Fixture

- Product: blue water bottle (reference = PIMG1 `dbg3.png`, copied into workspace as `product_ref.png`)
- No character
- Creative idea: "Show the blue water bottle on a clean table"
- No sales claims (verified_selling_points empty, restrictions: no sales claims/text)
- Duration: 4s | Aspect: 9:16 | 1 scene
- Owner `e2e_owner`, DB/workspace under `D:\work\hermes-agent-data` (migrated off %TEMP% per instruction)

---

## 3. B1–B10 Result

| Stage | Result |
|-------|--------|
| B1 Resource Pack | LOCKED ✅ (1 product ref) |
| B2 Raw Idea | saved (idea_version 1) ✅ |
| B3 Creative Brief | APPROVED ✅ (HITL) |
| B4 Scene Plan | APPROVED ✅ (HITL), 1 scene, 4s |
| B5 Storyboard | REAL Gemini image generated ✅ |
| B6 Storyboard Approval | APPROVED ✅ (HITL) |
| B7 Video Prompt | persisted ✅ |
| B8 Real Veo Video | generated ✅ |
| B9 Timeline + render | timeline_ready → draft_video_ready ✅ |
| B10 Final Review/Export | approved → export → ready_to_publish ✅ |

---

## 4. HITL Approvals (explicit, not self-approved)

1. **Creative Brief** — HITL authorize ✅
2. **Scene Plan** — HITL authorize ✅
3. **Storyboard** — HITL authorize ✅
4. **Final Review / Export** — HITL authorize ✅

Each gate paused with exact fixture IDs + requested action; approval was granted before continuing.

---

## 5. Real Image Evidence

```
image job state: completed
provider: google_vertex (gemini-2.5-flash-image)
image: workspace/images/vfe2e_frame_1.png
size: 917616 bytes
frame_1 status: FrameGenerationStatus.COMPLETED
frame asset: frame_asset_frame_1
```

Generated once (cost guardrail: no regeneration).

---

## 6. Real Video Evidence

```
video job state: completed
provider: google_vertex (veo-3.1-generate-001)
video: workspace/videos/projectsgen-lang-client-0816609628locati.mp4
size: 603737 bytes
provider_operation_id: projects/gen-lang-client-0816609628/locations/us-central1/
    publishers/google/models/veo-3.1-generate-001/operations/1db9dd90-1684-4361-8818-f5dc233f1997
scene_1 status: VideoGenerationStatus.COMPLETED
scene asset: scene_asset_scene_1
```

Image-to-video from approved storyboard frame; 9:16, 4s, 720p, sampleCount 1.

---

## 7. Timeline / Export Evidence

```
timeline_version: 1 | clips: 1 (source scene_asset_scene_1)
draft_video_asset_id: draft_asset_1
draft mp4: workspace/videos/draft_video.mp4 (302509 bytes)
final mp4: workspace/videos/final_video.mp4 (291559 bytes)
export state: completed (deterministic video.render, no provider call)
```

---

## 8. Files Changed During E2E

**Scripts created** (acceptance fixtures only, under `scripts/`):
- `vfe2e_migrate.py`, `vfe2e_leg1.py`…`vfe2e_leg6.py`, `vfe2e_verify.py`

**Runtime data** (under `D:\work\hermes-agent-data`, not in repo):
- `acceptance/vf-e2e/e2e.db`, `workspace/…`

**No source code changed** — E2E reused existing domain/application/repository/MCP/worker/adapters as-is.

---

## 9. Bugs Found / Fixed

- **Script-level (acceptance harness only, not product code):**
  - `file://` asset URI rejected by containment → used `asset://` scheme
  - `HERMES_VIDEO_FACTORY_WORKSPACE` must be set before service calls → set in scripts
  - async `video_generate` needs `max_attempts` high (Veo takes minutes) → `max_attempts: 200` in fixture payload
  - storyboard save not idempotent across reruns → guard in leg script

**No product-code changes were required** — the canonical flow worked against real providers.

---

## 10. Tests / Checks

- Focused Video Factory + provider + acceptance + K3–K6: **82 passed**
- `py_compile` PASS (all VF-E2E scripts + changed modules)
- `git diff --check` clean
- Pre-existing unrelated failures unchanged (job_repository schema, video_fetcher, database-migration tests — present before E2E, not touched)

---

## 11. Simplicity / Self-Review

| Check | Result |
|-------|--------|
| Added code E2E did not require? | ✅ no — scripts only, no product code |
| Duplicated existing orchestration? | ✅ no — reused service/repo/worker |
| Bypassed Hermes/MCP/application boundaries? | ✅ no — canonical service + durable jobs |
| Bypassed durable jobs? | ✅ no — image/video/render all via JobRepository+worker |
| Self-approved HITL state? | ✅ no — 4 explicit HITL gates |
| Provider/model fallback added? | ✅ no |
| New abstraction removable? | ✅ no new abstractions |

---

## 12. Remaining Blockers

None.

---

## 13. Final Status

```
VIDEO FACTORY V1 — LIVE END-TO-END FULL PASS
```

`ready_to_publish` reached with real Gemini image + real Veo video + deterministic export, all through the canonical B1–B10 flow with durable state, owner scoping, workspace containment, and explicit business HITL at every gate.

No TTS, UI, publishing, or next phase started.
