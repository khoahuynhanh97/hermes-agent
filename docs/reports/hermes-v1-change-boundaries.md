# Hermes Product-to-Video Workflow V1 Change Boundaries

## Analysis
Hermes workflow V1 requires integration of:
- Product Intelligence MCP client
- ResourcePackLock binding
- Video Factory project management
- Durable jobs for asset generation
- Frontend (Product Research UI, Video Factory UI)

## Existing Implementation Reused
- Existing `src/hermes` structure for backend.
- Existing `apps/web` for frontend.
- Existing Durable Job framework.
- Existing Asset API.

## Missing Wiring Implemented
- Orchestration service in application layer to bridge PI MCP and Video Factory.
- Frontend API endpoints for workflow state.
- Asset loading via `/api/assets/<asset-id>/content`.

## Files Expected to Change
- `src/hermes/application/workflow.py` (New: orchestration)
- `apps/web/src/pages/product-research.tsx` (Update)
- `apps/web/src/pages/video-factory.tsx` (Update)
- `src/hermes/api/assets.py` (Update: secure loading)

## Suggested Future Commit Boundaries
1. Backend orchestration & Durable job integration.
2. Product Research UI & Asset API secure loading.
3. Video Factory UI & Simulation jobs.
