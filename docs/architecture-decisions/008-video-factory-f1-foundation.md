# ADR 008: Video Factory F1 Foundation

## Decision

F1 uses a separate `mcp_servers/video_factory/` capability boundary. The existing `mcp_servers/video/` boundary remains responsible for offline media inspection and durable cut/render jobs. Video Factory is a structured creative workflow and has a distinct application service and repository contract.

F1 persists one owner-scoped `video_factory_projects` aggregate through the existing SQLite `Database` migration chain (schema 10). B1 Resource Pack, B2 Raw Idea, B3 Creative Brief, and B4 Scene Plan are structured domain objects serialized into named aggregate columns with independent versions, approvals, timestamps, and status.

Hermes remains the only creative reasoning owner. MCP handlers parse transport data and delegate to `VideoFactoryService`; the service validates workflow and ownership but never calls an LLM. Local asset URIs are contained by `HERMES_VIDEO_FACTORY_WORKSPACE`; remote references are metadata only and no media blobs are stored.

F1 requires explicit Resource Pack identity locking, Creative Brief approval, and Scene Plan approval. The final state is `ready_for_storyboard`. Storyboard, image/video generation, timeline composition, and publishing remain future capabilities.

## Consequences

- The creative workflow cannot silently approve its own output.
- Product/Research/Knowledge MCPs remain composable by Hermes and do not call one another.
- The aggregate is pragmatic for F1 while keeping a stable contract for future storyboard linkage.
