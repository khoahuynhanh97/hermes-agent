"""
Acceptance test proving Hermes can orchestrate F2-F5 workflow through application layer.

This test simulates what Hermes would do through MCP by calling the application
service layer that MCP tools invoke. This proves the workflow orchestration works.
"""
import tempfile
from pathlib import Path

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, FinalApprovalStatus, FrameGenerationStatus,
    FramePrompt, GeneratedScene, ProjectStatus, ResourceIdentity, ResourcePack,
    Scene, ScenePlan, Storyboard, StoryboardApprovalStatus, StoryboardFrame,
    Timeline, TimelineClip, TimelineStatus, VideoGenerationStatus, VideoPrompt,
)


def test_hermes_f2_f5_orchestration():
    """
    Prove Hermes can orchestrate F2-F5 through application layer.
    
    This simulates what Hermes would do: coordinate F2-F5 stages using
    the same application service that MCP tools invoke.
    """
    # Setup: Create F1 project at ready_for_storyboard
    db_path = Path(tempfile.mkdtemp()) / "hermes_acceptance.db"
    service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(db_path)))
    
    # F1 setup (direct service for test setup only)
    project = service.create_project("hermes-owner", "hermes-f2-f5-test")
    pack = ResourcePack(
        id="pack1", owner_user_id="hermes-owner",
        product_references=(AssetReference("asset1", "asset://p.jpg"),),
        primary_product_asset_id="asset1",
        product_identity_description="Product",
    )
    project = service.save_resource_pack("hermes-owner", project.id, pack)
    project = service.lock_resource_pack(
        "hermes-owner", project.id,
        ResourceIdentity(description="Locked product identity")
    )
    
    brief = CreativeBrief(
        objective="Show", target_audience="Users", core_message="Message",
        tone="neutral", pace="normal", cta="Act", content_blocks=("test",)
    )
    project = service.save_creative_brief("hermes-owner", project.id, brief)
    project = service.approve_creative_brief("hermes-owner", project.id)
    
    scene_plan = ScenePlan(scenes=(
        Scene(scene_id="s1", order=1, title="Scene 1", objective="O", content="C",
              main_action="Action", duration_seconds=5, start_state="start", end_state="end"),
    ))
    project = service.save_scene_plan("hermes-owner", project.id, scene_plan)
    project = service.approve_scene_plan("hermes-owner", project.id)
    
    assert project.status == ProjectStatus.READY_FOR_STORYBOARD
    
    # Now simulate Hermes orchestration (what MCP tools would invoke)
    owner = "hermes-owner"
    pid = project.id
    
    # F2: Hermes saves storyboard
    storyboard = Storyboard(
        storyboard_id="sb1",
        project_id=pid,
        frames=(
            StoryboardFrame(
                frame_id="f1", scene_id="s1", order=1, label="start",
                purpose="Establish", visual_state="empty", subject_action="none",
                product_state="offscreen", character_state="", context="indoor",
                camera_intention="wide",
                prompt=FramePrompt(positive_prompt="Empty scene, soft lighting"),
                created_at="2026-08-06T13:00:00+00:00"
            ),
        ),
        created_at="2026-08-06T13:00:00+00:00",
        updated_at="2026-08-06T13:00:00+00:00"
    )
    
    project = service.save_storyboard(owner, pid, storyboard)
    assert project.status == ProjectStatus.STORYBOARD_READY
    
    # Hermes updates frame generation status
    project = service.update_frame_generation_status(
        owner, pid, "f1", FrameGenerationStatus.COMPLETED, "img_f1_asset", "job_1"
    )
    
    # Hermes approves storyboard
    project = service.approve_storyboard(owner, pid, "Looks good")
    assert project.status == ProjectStatus.STORYBOARD_APPROVED
    assert project.storyboard.approval_status == StoryboardApprovalStatus.APPROVED
    
    # F3: Hermes saves generated scene with video prompt
    video_prompt = VideoPrompt(
        scene_id="s1", duration_seconds=5, start_visual_state="start",
        end_visual_state="end", subject_action="Action", product_action="visible",
        camera_movement="static", camera_framing="medium",
        environment_motion="none"
    )
    generated_scene = GeneratedScene(
        scene_id="s1",
        video_prompt=video_prompt,
        created_at="2026-08-06T13:10:00+00:00",
        updated_at="2026-08-06T13:10:00+00:00"
    )
    
    project = service.save_generated_scene(owner, pid, generated_scene)
    assert project.status == ProjectStatus.SCENES_GENERATED
    
    # Hermes updates scene generation status
    project = service.update_scene_generation_status(
        owner, pid, "s1", VideoGenerationStatus.COMPLETED, "vid_s1_asset", "job_2", "op_123"
    )
    
    # F4: Hermes saves timeline
    timeline = Timeline(
        timeline_id="tl1", project_id=pid,
        clips=(
            TimelineClip(
                clip_id="clip1", order=1, source_asset_id="vid_s1_asset",
                duration_seconds=5.0
            ),
        ),
        created_at="2026-08-06T13:20:00+00:00",
        updated_at="2026-08-06T13:20:00+00:00"
    )
    
    project = service.save_timeline(owner, pid, timeline)
    assert project.status == ProjectStatus.TIMELINE_READY
    
    # Hermes updates timeline status (simulating render progress)
    project = service.update_timeline_status(owner, pid, TimelineStatus.RENDERING)
    project = service.update_timeline_status(owner, pid, TimelineStatus.COMPLETED)
    
    # Hermes saves draft video
    project = service.save_draft_video(owner, pid, "draft_video_001")
    assert project.status == ProjectStatus.DRAFT_VIDEO_READY
    assert project.draft_video_asset_id == "draft_video_001"
    
    # F5: Hermes approves final video
    project = service.approve_final_video(owner, pid, "Approved for publication")
    assert project.final_approval == FinalApprovalStatus.APPROVED
    
    # Hermes saves final export
    project = service.save_final_export(owner, pid, "final_video_001")
    assert project.status == ProjectStatus.READY_TO_PUBLISH
    assert project.final_video_asset_id == "final_video_001"
    
    # Fresh session: Retrieve project (simulating restart)
    retrieved = service.get_project(owner, pid)
    
    # Verify complete state reconstruction
    assert retrieved.id == pid
    assert retrieved.status == ProjectStatus.READY_TO_PUBLISH
    assert retrieved.storyboard is not None
    assert len(retrieved.generated_scenes) == 1
    assert retrieved.timeline is not None
    assert retrieved.draft_video_asset_id == "draft_video_001"
    assert retrieved.final_video_asset_id == "final_video_001"
    assert retrieved.final_approval == FinalApprovalStatus.APPROVED
    
    print("✅ Hermes F2-F5 orchestration through application layer: PASS")
    print(f"✅ Project {pid} reached ready_to_publish")
