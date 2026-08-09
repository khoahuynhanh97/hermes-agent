# Video Factory V1 Architecture

**Status**: IMPLEMENTED  
**Version**: F1-F5 Complete  
**Last Updated**: 2026-08-06

## Overview

Video Factory V1 implements the complete creative production lifecycle from resource collection through final export, reaching `ready_to_publish` status. The system is designed for Hermes-driven creative workflows with durable job execution for expensive generation operations.

## System Architecture

```
User / Channel
      ↓
Hermes (reason_combo via 9Router)
      ↓
Video Factory Skill
      ↓
Video Factory MCP (capability boundary)
      ↓
VideoFactoryService (application)
      ↓
VideoFactoryProject (domain)
      ↓
SQLiteVideoFactoryRepository (persistence)
```

For expensive/long-running execution:

```
Application
      ↓
Canonical JobRepository
      ↓
Worker
      ↓
Specialized Provider (Image/Video Generation)
      ↓
Job result
      ↓
Events (when needed)
      ↓
Delivery (when needed)
```

## Project Lifecycle States

```
draft
  ↓
resource_ready (B1 Resource Pack)
  ↓
brief_ready (B3 Creative Brief approved)
  ↓
scene_plan_ready (B4 Scene Plan saved)
  ↓
ready_for_storyboard (B4 Scene Plan approved)
  ↓
storyboard_ready (B5 Storyboard saved)
  ↓
storyboard_approved (B6 Storyboard approved)
  ↓
scenes_generated (B8 Scene videos generated)
  ↓
timeline_ready (B9 Timeline saved)
  ↓
draft_video_ready (B9 Draft video rendered)
  ↓
ready_to_publish (B10 Final export approved)
```

## Workflow Phases

### F1: Foundation (B1-B4)

**B1: Resource Pack**
- Collect product/character reference assets
- Lock identity before downstream planning
- Validate workspace containment

**B2: Raw Idea**
- Store user's creative intent as editable text
- Capture optional constraints (duration, platform, CTA)

**B3: Creative Brief**
- Hermes proposes claims with Product/Research/Knowledge evidence
- Support verified, user-provided-unverified, unsupported, restricted statuses
- Require explicit business approval

**B4: Scene Plan**
- Break brief into ordered scenes
- Define visual states, actions, camera intention
- Calculate total duration
- Require explicit business approval

### F2: Storyboard Generation (B5-B6)

**B5: Frame Planning & Generation**
- Hermes plans 2-5 frames per scene based on complexity
- Build frame prompts incorporating locked identity, brief, visual context
- Persist frame plan BEFORE expensive image generation
- Submit image generation jobs (not inline)
- Track generation status per frame: planned → generating → completed/failed/rejected

**B6: Storyboard Review**
- Business reviews complete storyboard
- Support frame rejection and regeneration
- Explicit approval required before F3

**Image Generation Architecture**:
```
Hermes decides frame prompts
  ↓
Application creates image generation job
  ↓
Canonical JobRepository persists job
  ↓
Worker claims job
  ↓
ImageGenerationPort (boundary)
  ↓
Provider adapter (FakeImageProvider or real provider)
  ↓
Generated asset stored in workspace
  ↓
Job marked complete with asset_id
  ↓
Application updates frame status
```

### F3: Video Generation (B7-B8)

**B7: Video Prompt Builder**
- Per-scene video prompts reference approved storyboard frames
- Incorporate start/end visual states from Scene Plan
- Include identity constraints, motion, camera movement

**B8: Video Generation**
- Submit video generation jobs per scene
- Support async provider operations with operation_id tracking
- Status: pending → generating → completed/failed/rejected
- Safe restart/continuation after process failure

**Video Generation Architecture**:
```
Hermes decides video prompts
  ↓
Application creates video generation job
  ↓
Canonical JobRepository persists job
  ↓
Worker claims job
  ↓
VideoGenerationPort (boundary)
  ↓
Provider adapter (FakeVideoProvider or real provider)
  ↓
Provider returns operation_id for async generation
  ↓
Worker polls/waits for completion
  ↓
Generated video stored in workspace
  ↓
Job marked complete with asset_id
  ↓
Application updates scene status
```

### F4: Timeline Composition (B9)

**B9: Timeline & Render**
- Create timeline from generated scene videos in Scene Plan order
- Support optional voiceover/music assets
- Submit deterministic render job to Video MCP
- Render uses bounded FFmpeg operations (no arbitrary commands)
- Timeline status: draft → rendering → completed/failed
- Save draft_video_asset_id after successful render

**Timeline Render Architecture**:
```
Hermes decides timeline composition
  ↓
Application creates render job via Video MCP
  ↓
Canonical JobRepository persists job
  ↓
Worker claims job
  ↓
Deterministic FFmpeg execution (bounded parameters)
  ↓
Draft video stored in workspace
  ↓
Job marked complete with asset_id
  ↓
Application saves draft_video_asset_id
```

### F5: Final Review & Export (B10)

**B10: Final Review**
- Business reviews draft video
- Support approval or revision request
- Revision routes back to appropriate stage (storyboard/video/timeline)

**Final Export**
- After approval, create final export (typically MP4)
- Use deterministic Video MCP render job
- Save final_video_asset_id
- Project reaches `ready_to_publish`

**Social publishing (TikTok/YouTube/Facebook) is NOT implemented in V1.**

## Domain Model

### Core Entities

**VideoFactoryProject**: Root aggregate
- Owner-scoped
- Tracks all workflow artifacts
- Version counters for each artifact type
- Single source of truth for project state

**ResourcePack** (F1)
- Product/character references
- Locked identities (immutable after lock)
- Visual style, context

**RawIdea** (F1)
- User's creative intent
- Optional constraints

**CreativeBrief** (F1)
- Objective, audience, message, tone, pace, CTA
- Verified selling points (Claims with evidence)
- Restrictions

**ScenePlan** (F1)
- Ordered scenes
- Visual states, actions, duration
- Required resources

**Storyboard** (F2)
- Ordered frames per scene
- Frame prompts
- Generation status per frame
- Approval status

**StoryboardFrame** (F2)
- Visual state, actions, product/character state
- Frame prompt (positive, negative, constraints, composition, camera, lighting)
- Generated asset reference
- Review notes

**GeneratedScene** (F3)
- Video prompt
- Generation status
- Generated asset reference
- Provider operation tracking

**Timeline** (F4)
- Ordered clips referencing scene videos
- Optional audio tracks
- Render status

**TimelineClip** (F4)
- Source asset reference
- Trim/duration
- Transition
- Audio metadata

### Value Objects

**AssetReference**: Stable asset identity + URI + metadata  
**ResourceIdentity**: Locked product/character identity description  
**Claim**: Claim text + status + evidence refs + restriction reason  
**FramePrompt**: Structured image generation parameters  
**VideoPrompt**: Structured video generation parameters

### Enums

**ProjectStatus**: draft → resource_ready → ... → ready_to_publish  
**ClaimStatus**: verified | user_provided_unverified | unsupported | restricted  
**FrameGenerationStatus**: planned | generating | completed | failed | rejected  
**StoryboardApprovalStatus**: pending | approved | revision_required  
**VideoGenerationStatus**: pending | generating | completed | failed | rejected  
**TimelineStatus**: draft | rendering | completed | failed  
**FinalApprovalStatus**: pending | approved | revision_required

## Persistence (schema_v11)

**video_factory_projects table**:
- All F1-F5 JSON columns (resource_pack_json, storyboard_json, generated_scenes_json, timeline_json, etc.)
- Version counters (resource_version, storyboard_version, video_generation_version, timeline_version)
- Status, approvals, asset references
- Owner isolation via UNIQUE(owner_user_id, id)

**video_factory_generated_assets table**:
- Track all generated assets (frame images, scene videos, draft video, final video)
- Provider metadata, generation params
- Local path within workspace

## MCP Tools

### F1 (existing)
- `video_project_create`, `video_project_get`
- `resource_pack_save`, `resource_pack_get`, `resource_pack_lock`, `resource_pack_unlock`
- `raw_idea_save`
- `creative_brief_save`, `creative_brief_get`, `creative_brief_approve`
- `scene_plan_save`, `scene_plan_get`, `scene_plan_approve`

### F2: Storyboard
- `storyboard_save`
- `storyboard_update_frame_status`
- `storyboard_approve`
- `storyboard_reject_frame`

### F3: Video Generation
- `video_scene_save`
- `video_scene_update_status`

### F4: Timeline
- `timeline_save`
- `timeline_update_status`
- `timeline_save_draft_video`

### F5: Final Review
- `final_approve`
- `final_request_revision`
- `final_save_export`

## Provider Architecture

### Image Generation

**Port**: `ImageGenerationPort` (hermes/ports/image_generation.py)
- `generate(request: ImageGenerationRequest) -> ImageGenerationResult`
- `check_status(operation_id) -> ImageGenerationResult`

**Fake Provider**: `FakeImageGenerationProvider` (providers/fake_image_provider.py)
- Generates minimal 1x1 PNG placeholders
- Immediate completion
- For tests and architecture acceptance

**Real Provider Integration** (when credentials available):
- Provider-specific adapter implements ImageGenerationPort
- Configuration via environment variables (not hardcoded in application)
- Example: IMAGE_PROVIDER=<provider>, IMAGE_MODEL=<model>

### Video Generation

**Port**: `VideoGenerationPort` (hermes/ports/video_generation.py)
- `generate(request: VideoGenerationRequest) -> VideoGenerationResult`
- `check_status(operation_id) -> VideoGenerationResult`

**Fake Provider**: `FakeVideoGenerationProvider` (providers/fake_video_provider.py)
- Uses FFmpeg to create minimal color test videos
- Deterministic, safe for tests
- For tests and architecture acceptance

**Real Provider Integration** (when credentials available):
- Provider-specific adapter implements VideoGenerationPort
- Configuration via environment variables
- Example: VIDEO_PROVIDER=<provider>, VIDEO_MODEL=<model>
- Support async operations with operation_id persistence

### Video Rendering (Deterministic)

Uses existing **Video MCP** (`mcp_servers/video/`) for deterministic media operations:
- `video_create_job`: cut/render with bounded parameters
- `video_get_job`: job status
- `video_analyze`: offline inspection

No arbitrary FFmpeg commands from LLM output.

## Job Types

### Conceptual Job Types
- `frame_image_generate`: Generate storyboard frame image
- `scene_video_generate`: Generate scene video
- `timeline_render`: Render timeline to draft video
- `final_export`: Export final video

Jobs use canonical JobRepository with durable state, retry, cancellation, and recovery.

## Versioning & Invalidation

### Version Tracking
Each artifact type has a version counter:
- `resource_version`, `idea_version`, `brief_version`, `scene_version`
- `storyboard_version`, `video_generation_version`, `timeline_version`

Versions increment on save.

### Downstream Invalidation Rules

**Resource Pack identity changes** → storyboard/video outputs may become stale  
**Creative Brief changes** → Scene Plan and downstream may require revision  
**Scene Plan changes** → Storyboard and later stages become stale  
**Storyboard changes** → generated video scenes may become stale  
**Video scene changes** → timeline/final export becomes stale  
**Timeline changes** → final approval/export becomes stale

Implementation: Changing upstream artifact does NOT auto-delete downstream artifacts. Status transitions and approval states guide workflow. Superseded artifacts remain inspectable.

## Security & Isolation

### Owner Isolation
Every operation requires `owner_user_id`. Cross-owner access is rejected.

### Workspace Containment
All local asset URIs validated against `HERMES_VIDEO_FACTORY_WORKSPACE`. Path traversal prevented.

### Secrets
Never persist or expose provider API keys, credentials, or secrets in project state, logs, or responses.

### Provider Payload
Provider adapters validate and bound all provider-specific parameters. No arbitrary code execution.

## Business HITL (Human-in-the-Loop)

### Approval Gates
- **Creative Brief Approval**: Business decision on claims and messaging
- **Scene Plan Approval**: Business decision on structure and pacing
- **Storyboard Approval**: Business decision on visual direction
- **Final Video Approval**: Business decision on complete output

Hermes may recommend approval but must NOT silently approve on behalf of the user.

For automated tests, use explicit test-domain authorization.

## Cost Safety

### Idempotency
Image/video generation jobs use stable `request_id` to prevent duplicate paid calls on retry.

### Bounded Retries
Jobs have `max_attempts`. Hermes does not create unbounded generation loops.

### Explicit Generation
Frame/scene generation is explicit, not automatic. Hermes reasons before invoking expensive operations.

## Restart Safety

### Durable State
All significant workflow state persisted in SQLite. Fresh Hermes process can reconstruct project without prior chat context.

### Job Continuation
Long-running jobs (especially async video generation) survive process restart via:
- Job state in canonical JobRepository
- Provider operation_id persistence
- Worker recovery of expired leases

## Testing Strategy

### Unit Tests
- Domain validation (scene order, claim requirements, etc.)
- Application service lifecycle transitions

### Integration Tests
- F1-F5 complete workflow with fake providers
- Frame rejection and regeneration
- Owner isolation
- Workspace containment

### Acceptance Tests
- Real Hermes with reason_combo
- Enabled MCPs: product, research, knowledge, video, video_factory
- Temporary test project/owner/database/workspace
- Fake providers for architecture acceptance
- Live provider acceptance (when credentials available)

## Configuration

### Environment Variables

**Database**:
- `HERMES_VIDEO_FACTORY_DB_PATH`: Project database location
- `HERMES_VIDEO_DB_PATH`: Video jobs database location

**Workspace**:
- `HERMES_VIDEO_FACTORY_WORKSPACE`: Root for local asset containment

**Providers** (when real providers configured):
- `IMAGE_PROVIDER`, `IMAGE_MODEL`
- `VIDEO_PROVIDER`, `VIDEO_MODEL`
- Provider-specific API keys and endpoints

## Skills

**video-production** (skills/video-production/SKILL.md) v2.0.0:
- Teaches Hermes the F1-F5 procedure
- Explains approval gates
- Describes available MCP tools
- Clarifies boundaries (Hermes = creative decision, MCP = capability, Worker = execution)

## Current Limitations

### Not Implemented in V1
- Social platform publishing (TikTok, YouTube, Facebook APIs)
- Automatic caption/subtitle generation
- Music discovery/licensing marketplace
- Advanced analytics/campaign management
- Large GUI/dashboard
- Computer-vision identity scoring

### Provider Integration
- Fake providers work deterministically for architecture acceptance
- Real image/video providers require external credentials
- Provider selection is configuration, not application-level fallback logic

### TTS/Voiceover
- Timeline supports optional imported voiceover assets
- TTS provider integration is future extension point
- No built-in voice generation in V1

## Deferred Features

- Campaign scheduling
- A/B testing of creative variants
- Automatic thumbnail generation
- Multi-language support
- Brand guidelines enforcement
- Collaborative review workflows

## Architecture Principles Confirmed

✅ Hermes = sole general-purpose creative brain  
✅ 9Router = generic reasoning gateway  
✅ reason_combo = logical reasoning model  
✅ Skill = procedure (not state)  
✅ MCP = capability boundary (not orchestrator)  
✅ Application/Domain = workflow rules and state  
✅ JobRepository = durable execution queue  
✅ Worker = deterministic execution (no reasoning)  
✅ Database = durable source of truth  
✅ HITL = explicit business authorization  
✅ Image/Video providers = specialized capabilities (not generic brain)  
✅ No MCP-to-MCP orchestration  
✅ No new general-purpose Agents besides Hermes

## Files Structure

```
hermes/
  domain/
    video_factory.py (F1-F5 domain model)
    job.py (job domain model)
  application/
    video_factory_service.py (F1-F5 application logic)
    video_service.py (deterministic media operations)
  ports/
    video_factory_repository.py (persistence port)
    job_repository.py (job port)
    image_generation.py (image provider port)
    video_generation.py (video provider port)
  adapters/
    sqlite/
      video_factory_repository.py (F1-F5 persistence)
      canonical_job_repository.py (job persistence)
      schema_v10.py (F1 schema)
      schema_v11.py (F2-F5 schema extension)
  jobs.py (canonical job repository)
  db.py (database initialization, migrations)

mcp_servers/
  video_factory/
    server.py (F1-F5 MCP tools)
  video/
    server.py (deterministic media MCP tools)

providers/
  fake_image_provider.py (test image generation)
  fake_video_provider.py (test video generation)
  ai_video_provider.py (existing video provider reference)

skills/
  video-production/
    SKILL.md (v2.0.0 F1-F5 procedure)

workers/
  job_worker.py (canonical worker)

tests/
  hermes/
    domain/
      test_video_factory.py (domain validation)
    application/
      test_video_factory_service.py (F1 tests)
      test_video_factory_f2_f5.py (F2-F5 integration tests)
```

## Definition of Done

Video Factory V1 is **COMPLETE** when:

✅ F1-F5 domain model defined  
✅ Application service implements all lifecycle operations  
✅ Repository persists F1-F5 state with schema v11  
✅ MCP server exposes F1-F5 tools  
✅ Skill documents F1-F5 procedure  
✅ Image generation port and fake adapter exist  
✅ Video generation port and fake adapter exist  
✅ Deterministic Video MCP handles render/export  
✅ Durable jobs support image/video/render operations  
✅ Owner isolation enforced across B1-B10  
✅ Workspace containment validated  
✅ Upstream invalidation semantics clear  
✅ Business approval gates require explicit authorization  
✅ F1-F5 integration tests pass with fake providers  
✅ Fresh process can reconstruct complete project from durable state  
✅ Project can reach `ready_to_publish` status  
✅ No social publishing API added  
✅ Architecture principles confirmed  

## Next Steps (Post-V1)

1. **Real Provider Integration**: Wire real image/video generation providers when credentials available
2. **Worker Handlers**: Implement specialized job handlers for frame_image_generate, scene_video_generate
3. **TTS Integration**: Add voiceover generation capability
4. **Social Publishing**: Implement platform-specific upload APIs
5. **Analytics**: Track generation costs, success rates, user engagement
6. **Advanced Workflows**: Multi-variant testing, iterative refinement, collaborative review
