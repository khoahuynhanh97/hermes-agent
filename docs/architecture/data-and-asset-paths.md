# Data and Asset Paths Policy

This document governs asset ownership, storage layout, reference preservation, and frontend media access requirements for the Hermes Agent Platform.

---

## Asset Ownership and Linking Policy

### 1. Product Intelligence Original Assets
- **Ownership**: Product Intelligence owns all raw source assets (e.g. downloaded manufacturer product images, evidence captures, `ResearchSnapshot`, and `ResourcePack`).
- **Policy**: Hermes **must not** copy, duplicate, or rename these original files into the Hermes workspace.
- **Reference Binding**: Hermes only stores persistent metadata references (`asset_id`, `product_id`, `snapshot_id`, `sha256`, `mime_type`, and `source_uri` or local path references) inside the SQLite databases and Resource Pack structures.

### 2. Hermes Generated Assets
- **Ownership**: Hermes owns all synthesized media outputs (storyboard frame images, scene video clips, narration voiceover files, mixed final draft, and export ad videos).
- **Policy**: All generated assets must reside within their respective project workspaces inside `HERMES_DATA_DIR/workspaces/projects/<project-id>/`. No generated media should reside in the code repository or workspace root.

### 3. Frontend Asset Access
- **No Direct Filesystem Expose**: The backend APIs must **never** expose absolute local filesystem paths (e.g., `D:\folder\file.jpg` or `file://` URLs) to the frontend.
- **Asset Access URL**: The frontend accesses resources via standard asset API content paths, such as:
  `/api/assets/<asset-id>/content`
- **Operator Actions**: Interactive API calls (like `open-file` and `open-folder`) are strictly backend operator triggers that use local commands and do not return absolute paths in API responses.

---

## Asset Mapping Registry

| Asset Type | Owner | Physical Storage | Persisted Reference | Frontend Access |
| :--- | :--- | :--- | :--- | :--- |
| **Original Product Image** | Product Intelligence | External Storage (e.g., Product Intelligence cache) | `asset_id`, `sha256`, `source_uri` | `/api/assets/<asset-id>/content` |
| **Evidence Snapshot** | Product Intelligence | External Storage (e.g. `ResearchSnapshot` folder) | `snapshot_id`, `product_id`, `path_reference` | `/api/assets/<asset-id>/content` |
| **Resource Pack Lock** | Product Intelligence | DB / Resource Metadata | `resource_pack_lock_id`, `reference_uri` | Not Exposed |
| **Storyboard Frame Image** | Hermes Video Factory | `HERMES_DATA_DIR/workspaces/projects/<project-id>/generated/images/` | `frame_id`, `asset_id` (e.g. `frame_asset_frame_1`) | `/api/assets/<asset-id>/content` |
| **Scene Video Clip** | Hermes Video Factory | `HERMES_DATA_DIR/workspaces/projects/<project-id>/generated/videos/` | `scene_id`, `asset_id` (e.g. `scene_asset_scene_1`) | `/api/assets/<asset-id>/content` |
| **Narration Audio WAV** | Hermes Video Factory | `HERMES_DATA_DIR/workspaces/projects/<project-id>/generated/audio/` | `audio_track_asset_id` (e.g. `voiceover_Zephyr`) | `/api/assets/<asset-id>/content` |
| **Final Export Video** | Hermes Video Factory | `HERMES_DATA_DIR/workspaces/projects/<project-id>/exports/` | `final_video_asset_id`, `output_path` | `/api/assets/<asset-id>/content` or via streaming router |
| **Storyboard Data** | Hermes Video Factory | `HERMES_DATA_DIR/workspaces/projects/<project-id>/storyboards/` | JSON metadata reference | `/api/vf/projects/<project-id>` details |
