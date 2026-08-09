"""VF-E2E fresh-process reconstruction + final evidence report.

A brand-new process reads the persisted project from durable state only
(no chat/session memory) and prints the complete B1-B10 evidence.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

E2E_ROOT = Path(r"D:\work\hermes-agent-data\acceptance\vf-e2e")
DB_PATH = E2E_ROOT / "e2e.db"
WORKSPACE = E2E_ROOT / "workspace"
OWNER = "e2e_owner"
PROJECT_ID = "vfe2e_project"
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)
os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(DB_PATH)

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database

# Fresh process: new service + repository instance, durable state only
service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))
project = service.get_project(OWNER, PROJECT_ID)

print("=== FRESH-PROCESS RECONSTRUCTION ===")
print("project:", project.id, "| owner:", project.owner_user_id)
print("status:", project.status.value)
print()

print("B1 resource pack:", "LOCKED" if project.resource_pack and project.resource_pack.locked_at else "missing")
print("  product refs:", len(project.resource_pack.product_references) if project.resource_pack else 0)
print("B2 raw idea version:", project.idea_version)
print("B3 brief approval:", project.brief_approval)
print("B4 scene plan approval:", project.scene_plan_approval,
      "| scenes:", len(project.scene_plan.scenes) if project.scene_plan else 0)
print("B5 storyboard version:", project.storyboard.version if project.storyboard else 0,
      "| frames:", len(project.storyboard.frames) if project.storyboard else 0)
if project.storyboard:
    f = project.storyboard.frames[0]
    print("  frame:", f.frame_id, "| status:", str(f.generation_status), "| asset:", f.generated_asset_id)
print("B6 storyboard approval:", project.storyboard.approval_status.value if project.storyboard else "none")
print("B7/B8 generated scenes:", len(project.generated_scenes))
for s in project.generated_scenes:
    print("  scene:", s.scene_id, "| status:", str(s.generation_status), "| asset:", s.generated_asset_id,
          "| op:", s.provider_operation_id)
print("B9 timeline version:", project.timeline.version if project.timeline else 0,
      "| clips:", len(project.timeline.clips) if project.timeline else 0)
print("  draft_video_asset_id:", project.draft_video_asset_id)
print("B10 final_approval:", project.final_approval.value)
print("  final_video_asset_id:", project.final_video_asset_id)
print()

print("=== ASSET FILES ===")
for name in ("images/vfe2e_frame_1.png", "videos/draft_video.mp4", "videos/final_video.mp4"):
    p = WORKSPACE / name
    print(f"{name}: exists={p.exists()} size={p.stat().st_size if p.exists() else 0}")
real_scene = [v for v in (WORKSPACE / "videos").glob("*.mp4") if "draft" not in v.name and "final" not in v.name]
for v in real_scene:
    print(f"real veo video: {v.name} size={v.stat().st_size}")

print()
print("final check:", project.status.value == "ready_to_publish"
      and project.final_approval.value == "approved"
      and project.final_video_asset_id is not None
      and (WORKSPACE / "videos/final_video.mp4").exists()
      and (WORKSPACE / "images/vfe2e_frame_1.png").exists())
