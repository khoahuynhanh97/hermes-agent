# Video Factory F1 Runbook

Set `HERMES_VIDEO_FACTORY_DB_PATH` to an isolated SQLite file and `HERMES_VIDEO_FACTORY_WORKSPACE` to the allowed local asset root. Start the capability with:

```powershell
python -m mcp_servers.video_factory.server
```

The F1 sequence is `video_project_create`, `resource_pack_save`, `resource_pack_lock`, `raw_idea_save`, `creative_brief_save`, `creative_brief_approve`, `scene_plan_save`, and `scene_plan_approve`. Use `resource_pack_unlock` for an explicit identity revision. Read operations use `video_project_get`, `resource_pack_get`, `creative_brief_get`, and `scene_plan_get`.

The workflow stops at `ready_for_storyboard`. Do not use F1 as a request for storyboard frames, image generation, video generation, timeline composition, or publishing.
