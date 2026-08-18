"""UGREEN live run - Leg 2: approve brief + B4 scene plan. Stop at Scene Plan HITL."""
import os, sys
from pathlib import Path
ROOT = Path(r"D:\work\hermes-agent"); sys.path.insert(0, str(ROOT))
os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = r"D:\work\hermes-agent-data\db\video_factory.sqlite"
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = r"D:\work\hermes-agent-data\workspaces\video-factory"
OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import Scene, ScenePlan

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(os.environ["HERMES_VIDEO_FACTORY_DB_PATH"]))))
project = service.get_project(OWNER, PROJECT_ID)
if project.brief_approval != "approved":
    project = service.approve_creative_brief(OWNER, PROJECT_ID)
print("brief:", project.brief_approval, "status:", project.status.value)

plan = ScenePlan(scenes=(
    Scene(
        scene_id="scene_hook", order=1, title="Hero: Robot Face", objective="Product hero on a clean desk",
        content="UGREEN Nexode Robot UNO charger standing on a clean desk, robot face visible",
        main_action="charger stands still, camera pushes in slowly",
        duration_seconds=4,
        context="clean desk, soft studio lighting",
        camera_intention="slow cinematic push-in",
        start_state="charger centered on desk",
        end_state="charger centered, closer",
        required_resources=("ugreen_img_0",),
    ),
    Scene(
        scene_id="scene_demo", order=2, title="Demo: In Use", objective="Show charger in use / connected",
        content="USB-C cable connecting to the charger, phone nearby, natural use",
        main_action="cable plugged in gently, camera pans",
        duration_seconds=4,
        context="clean desk, soft lighting",
        camera_intention="gentle camera movement",
        start_state="cable near charger",
        end_state="cable connected",
        required_resources=("ugreen_img_0", "ugreen_img_1"),
    ),
    Scene(
        scene_id="scene_cta", order=3, title="Close-up: Beauty Shot", objective="Final product close-up",
        content="Clean close-up of the UGREEN charger, soft light, final beauty shot",
        main_action="stable slow zoom, charger centered",
        duration_seconds=4,
        context="clean desk, soft studio lighting",
        camera_intention="stable slow zoom",
        start_state="charger mid-close",
        end_state="charger close-up",
        required_resources=("ugreen_img_0",),
    ),
))
project = service.save_scene_plan(OWNER, PROJECT_ID, plan)
print("scene plan saved, approval:", project.scene_plan_approval, "status:", project.status.value, "total:", project.scene_plan.total_duration_seconds, "s")
print("PROJECT_ID:", PROJECT_ID)
