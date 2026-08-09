"""VF-E2E Leg 2: approve creative brief, save B4 Scene Plan. Stop at HITL."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

E2E_ROOT = Path(r"C:\Users\ninak\AppData\Local\Temp\opencode\vfe2e")
DB_PATH = E2E_ROOT / "e2e.db"
WORKSPACE = E2E_ROOT / "workspace"
OWNER = "e2e_owner"
PROJECT_ID = "vfe2e_project"
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import Scene, ScenePlan

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

project = service.get_project(OWNER, PROJECT_ID)
if project.brief_approval != "approved":
    project = service.approve_creative_brief(OWNER, PROJECT_ID)
print("brief approval:", project.brief_approval, "status:", project.status.value)

scene = Scene(
    scene_id="scene_1",
    order=1,
    title="Bottle on table",
    objective="Visually present the blue water bottle on a clean table",
    content="Establish shot of the bottle on the table with soft studio lighting",
    main_action="Bottle stands still, camera slowly pans around it",
    duration_seconds=4,
    context="clean table, soft studio lighting",
    camera_intention="slow pan around the bottle",
    start_state="bottle centered on table",
    end_state="bottle centered on table",
    required_resources=("asset_prod_1",),
    status="planned",
)
plan = ScenePlan(scenes=(scene,))
project = service.save_scene_plan(OWNER, PROJECT_ID, plan)
print("scene plan saved, scene_plan_approval:", project.scene_plan_approval, "status:", project.status.value)
print("scene count:", len(project.scene_plan.scenes), "total_duration:", project.scene_plan.total_duration_seconds)
print("PROJECT_ID:", PROJECT_ID)
print("OWNER:", OWNER)
