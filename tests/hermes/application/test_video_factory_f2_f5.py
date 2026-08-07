"""Simple F2-F5 workflow test to verify end-to-end architecture."""
import tempfile
from pathlib import Path

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, FinalApprovalStatus, FrameGenerationStatus,
    FramePrompt, GeneratedScene, ProjectStatus, RawIdea, ResourceIdentity,
    ResourcePack, Scene, ScenePlan, Storyboard, StoryboardApprovalStatus,
    StoryboardFrame, Timeline, TimelineClip, TimelineStatus,
    VideoGenerationStatus, VideoPrompt,
)


def test_f2_f5_complete_workflow():
    """Test complete Video Factory workflow from ready_for_storyboard to ready_to_publish."""
    db_path = Path(tempfile.mkdtemp()) / "test_vf.db"
    service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(db_path)))
    
    # F1: Setup approved scene plan
    project = service.create_project("owner-a", "test-f2-f5")
    
    pack = ResourcePack(
        id="pack1",
        owner_user_id="owner-a",
        product_references=(AssetReference("asset1", "asset://product1.jpg"),),
        primary_product_asset_id="asset1",
        product_identity_description="Blue water bottle",
    )
    project = service.save_resource_pack("owner-a", project.id, pack)
    project = service.lock_resource_pack(
        "owner-a", project.id,
        ResourceIdentity(description="Blue water bottle with white logo")
    )
    
    idea = RawIdea(text="Show product benefits", target_duration_seconds=10)
    project = service.save_raw_idea("owner-a", project.id, idea)
    
    brief = CreativeBrief(
        objective="Show product",
        target_audience="Users",
        core_message="Great product",
        tone="friendly",
        pace="moderate",
        cta="Buy now",
        content_blocks=("intro", "demo"),
    )
    project = service.save_creative_brief("owner-a", project.id, brief)
    project = service.approve_creative_brief("owner-a", project.id)
    
    scene_plan = ScenePlan(scenes=(
        Scene(
            scene_id="scene1",
            order=1,
            title="Intro",
            objective="Introduce",
            content="Show product",
            main_action="Display",
            duration_seconds=5,
            start_state="empty",
            end_state="product visible",
        ),
        Scene(
            scene_id="scene2",
            order=2,
            title="Demo",
            objective="Demonstrate",
            content="Use product",
            main_action="Pour water",
            duration_seconds=5,
            start_state="product visible",
            end_state="action complete",
        ),
    ))
    project = service.save_scene_plan("owner-a", project.id, scene_plan)
    project = service.approve_scene_plan("owner-a", project.id)
    assert project.status == ProjectStatus.READY_FOR_STORYBOARD
    
    # F2: Storyboard
    storyboard = Storyboard(
        storyboard_id="sb1",
        project_id=project.id,
        frames=(
            StoryboardFrame(
                frame_id="frame1",
                scene_id="scene1",
                order=1,
                label="start",
                purpose="Establish scene",
                visual_state="empty table",
                subject_action="none",
                product_state="offscreen",
                character_state="",
                context="indoor",
                camera_intention="wide",
                prompt=FramePrompt(positive_prompt="Empty table, soft lighting"),
            ),
            StoryboardFrame(
                frame_id="frame2",
                scene_id="scene1",
                order=2,
                label="product appears",
                purpose="Show product",
                visual_state="product on table",
                subject_action="none",
                product_state="centered",
                character_state="",
                context="indoor",
                camera_intention="closeup",
                prompt=FramePrompt(positive_prompt="Blue water bottle on table"),
            ),
            StoryboardFrame(
                frame_id="frame3",
                scene_id="scene2",
                order=1,
                label="hand reaches",
                purpose="Begin action",
                visual_state="hand approaching",
                subject_action="reaching",
                product_state="centered",
                character_state="",
                context="indoor",
                camera_intention="medium",
                prompt=FramePrompt(positive_prompt="Hand reaching for bottle"),
            ),
        ),
        created_at="2026-08-06T10:00:00+00:00",
        updated_at="2026-08-06T10:00:00+00:00",
    )
    
    project = service.save_storyboard("owner-a", project.id, storyboard)
    assert project.status == ProjectStatus.STORYBOARD_READY
    assert len(project.storyboard.frames) == 3
    
    # Simulate frame generation
    for frame in project.storyboard.frames:
        project = service.update_frame_generation_status(
            "owner-a", project.id, frame.frame_id,
            FrameGenerationStatus.COMPLETED,
            asset_id=f"img_{frame.frame_id}",
            job_id=f"job_{frame.frame_id}"
        )
    
    project = service.approve_storyboard("owner-a", project.id, "Looks good")
    assert project.status == ProjectStatus.STORYBOARD_APPROVED
    assert project.storyboard.approval_status == StoryboardApprovalStatus.APPROVED
    
    # F3: Video generation
    for scene in scene_plan.scenes:
        video_prompt = VideoPrompt(
            scene_id=scene.scene_id,
            duration_seconds=scene.duration_seconds,
            start_visual_state=scene.start_state,
            end_visual_state=scene.end_state,
            subject_action=scene.main_action,
            product_action="visible",
            camera_movement="static",
            camera_framing="medium",
            environment_motion="none",
        )
        generated_scene = GeneratedScene(
            scene_id=scene.scene_id,
            video_prompt=video_prompt,
            created_at="2026-08-06T10:10:00+00:00",
            updated_at="2026-08-06T10:10:00+00:00",
        )
        project = service.save_generated_scene("owner-a", project.id, generated_scene)
    
    assert project.status == ProjectStatus.SCENES_GENERATED
    
    # Simulate video generation completion
    for scene in project.generated_scenes:
        project = service.update_scene_generation_status(
            "owner-a", project.id, scene.scene_id,
            VideoGenerationStatus.COMPLETED,
            asset_id=f"vid_{scene.scene_id}",
            job_id=f"vjob_{scene.scene_id}"
        )
    
    # F4: Timeline
    timeline = Timeline(
        timeline_id="tl1",
        project_id=project.id,
        clips=(
            TimelineClip(
                clip_id="clip1",
                order=1,
                source_asset_id="vid_scene1",
                duration_seconds=5.0,
            ),
            TimelineClip(
                clip_id="clip2",
                order=2,
                source_asset_id="vid_scene2",
                duration_seconds=5.0,
            ),
        ),
        created_at="2026-08-06T10:20:00+00:00",
        updated_at="2026-08-06T10:20:00+00:00",
    )
    
    project = service.save_timeline("owner-a", project.id, timeline)
    assert project.status == ProjectStatus.TIMELINE_READY
    
    project = service.update_timeline_status("owner-a", project.id, TimelineStatus.RENDERING)
    project = service.update_timeline_status("owner-a", project.id, TimelineStatus.COMPLETED)
    
    project = service.save_draft_video("owner-a", project.id, "draft_video_001")
    assert project.status == ProjectStatus.DRAFT_VIDEO_READY
    assert project.draft_video_asset_id == "draft_video_001"
    
    # F5: Final review and export
    project = service.approve_final_video("owner-a", project.id, "Approved for export")
    assert project.final_approval == FinalApprovalStatus.APPROVED
    
    project = service.save_final_export("owner-a", project.id, "final_video_001")
    assert project.status == ProjectStatus.READY_TO_PUBLISH
    assert project.final_video_asset_id == "final_video_001"
    
    # Verify we can retrieve complete project
    retrieved = service.get_project("owner-a", project.id)
    assert retrieved.id == project.id
    assert retrieved.status == ProjectStatus.READY_TO_PUBLISH
    assert retrieved.storyboard is not None
    assert len(retrieved.generated_scenes) == 2
    assert retrieved.timeline is not None
    assert retrieved.draft_video_asset_id == "draft_video_001"
    assert retrieved.final_video_asset_id == "final_video_001"
    assert retrieved.final_approval == FinalApprovalStatus.APPROVED


def test_storyboard_frame_rejection():
    """Test frame rejection and regeneration workflow."""
    db_path = Path(tempfile.mkdtemp()) / "test_reject.db"
    service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(db_path)))
    
    project = service.create_project("owner-b", "test-reject")
    
    # Quick F1 setup
    pack = ResourcePack(
        id="pack1",
        owner_user_id="owner-b",
        product_references=(AssetReference("asset1", "asset://p.jpg"),),
        primary_product_asset_id="asset1",
        product_identity_description="Product",
    )
    project = service.save_resource_pack("owner-b", project.id, pack)
    project = service.lock_resource_pack("owner-b", project.id, ResourceIdentity(description="P"))
    
    brief = CreativeBrief(
        objective="Test", target_audience="Users", core_message="Msg",
        tone="neutral", pace="normal", cta="Act", content_blocks=("test",)
    )
    project = service.save_creative_brief("owner-b", project.id, brief)
    project = service.approve_creative_brief("owner-b", project.id)
    
    scene_plan = ScenePlan(scenes=(
        Scene(scene_id="s1", order=1, title="T", objective="O", content="C",
              main_action="A", duration_seconds=3),
    ))
    project = service.save_scene_plan("owner-b", project.id, scene_plan)
    project = service.approve_scene_plan("owner-b", project.id)
    
    # Create storyboard
    storyboard = Storyboard(
        storyboard_id="sb1",
        project_id=project.id,
        frames=(
            StoryboardFrame(
                frame_id="f1", scene_id="s1", order=1, label="test",
                purpose="test", visual_state="v", subject_action="a",
                product_state="p", character_state="", context="c",
                camera_intention="i",
                prompt=FramePrompt(positive_prompt="test frame"),
            ),
        ),
        created_at="2026-08-06T10:00:00+00:00",
        updated_at="2026-08-06T10:00:00+00:00",
    )
    project = service.save_storyboard("owner-b", project.id, storyboard)
    
    # Generate frame
    project = service.update_frame_generation_status(
        "owner-b", project.id, "f1",
        FrameGenerationStatus.COMPLETED, asset_id="img_f1"
    )
    
    # Reject frame
    project = service.reject_storyboard_frame(
        "owner-b", project.id, "f1", "Product identity not matching"
    )
    
    frame = project.storyboard.frames[0]
    assert frame.generation_status == FrameGenerationStatus.REJECTED
    assert "identity not matching" in frame.review_notes
    assert frame.version >= 2


def _make_service_at_storyboard_ready(db_path: Path) -> tuple["VideoFactoryService", str, str]:
    """Helper: returns (service, owner_user_id, project_id) at STORYBOARD_READY with one frame."""
    service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(db_path)))
    project = service.create_project("owner-g", "gate-test")
    pack = ResourcePack(
        id="pack1", owner_user_id="owner-g",
        product_references=(AssetReference("a1", "asset://p.jpg"),),
        primary_product_asset_id="a1",
        product_identity_description="Product",
    )
    project = service.save_resource_pack("owner-g", project.id, pack)
    project = service.lock_resource_pack("owner-g", project.id, ResourceIdentity(description="P"))
    brief = CreativeBrief(
        objective="O", target_audience="U", core_message="M",
        tone="neutral", pace="normal", cta="C", content_blocks=("x",)
    )
    project = service.save_creative_brief("owner-g", project.id, brief)
    project = service.approve_creative_brief("owner-g", project.id)
    scene_plan = ScenePlan(scenes=(
        Scene(scene_id="s1", order=1, title="T", objective="O", content="C",
              main_action="A", duration_seconds=4, start_state="start", end_state="end"),
    ))
    project = service.save_scene_plan("owner-g", project.id, scene_plan)
    project = service.approve_scene_plan("owner-g", project.id)
    storyboard = Storyboard(
        storyboard_id="sb1", project_id=project.id,
        frames=(StoryboardFrame(
            frame_id="f1", scene_id="s1", order=1, label="l",
            purpose="p", visual_state="v", subject_action="a",
            product_state="p", character_state="", context="c",
            camera_intention="i",
            prompt=FramePrompt(positive_prompt="frame"),
        ),),
        created_at="2026-08-06T10:00:00+00:00",
        updated_at="2026-08-06T10:00:00+00:00",
    )
    project = service.save_storyboard("owner-g", project.id, storyboard)
    return service, "owner-g", project.id


def test_image_jobs_allowed_before_storyboard_approval():
    """Image frame generation is permitted before storyboard approval."""
    db_path = Path(tempfile.mkdtemp()) / "gate_image.db"
    service, owner, pid = _make_service_at_storyboard_ready(db_path)
    # Updating frame generation status is the pre-approval image path
    project = service.update_frame_generation_status(
        owner, pid, "f1", FrameGenerationStatus.COMPLETED, asset_id="img_f1"
    )
    assert project.storyboard.frames[0].generated_asset_id == "img_f1"


def test_video_job_rejected_before_storyboard_approval():
    """save_generated_scene must raise STORYBOARD_APPROVAL_REQUIRED when not yet approved."""
    import pytest
    db_path = Path(tempfile.mkdtemp()) / "gate_video.db"
    service, owner, pid = _make_service_at_storyboard_ready(db_path)
    video_prompt = VideoPrompt(
        scene_id="s1", duration_seconds=4,
        start_visual_state="start", end_visual_state="end",
        subject_action="A", product_action="visible",
        camera_movement="static", camera_framing="medium", environment_motion="none",
    )
    generated_scene = GeneratedScene(scene_id="s1", video_prompt=video_prompt)
    with pytest.raises(ValueError, match="STORYBOARD_APPROVAL_REQUIRED"):
        service.save_generated_scene(owner, pid, generated_scene)


def test_tts_guard_rejected_before_storyboard_approval():
    """require_storyboard_approved must raise STORYBOARD_APPROVAL_REQUIRED when pending."""
    import pytest
    db_path = Path(tempfile.mkdtemp()) / "gate_tts.db"
    service, owner, pid = _make_service_at_storyboard_ready(db_path)
    with pytest.raises(ValueError, match="STORYBOARD_APPROVAL_REQUIRED"):
        service.require_storyboard_approved(owner, pid)


def test_tts_guard_passes_after_storyboard_approval():
    """require_storyboard_approved returns project after storyboard is approved."""
    db_path = Path(tempfile.mkdtemp()) / "gate_tts_ok.db"
    service, owner, pid = _make_service_at_storyboard_ready(db_path)
    # Complete the frame so approve_storyboard passes
    service.update_frame_generation_status(owner, pid, "f1", FrameGenerationStatus.COMPLETED, asset_id="img_f1")
    service.approve_storyboard(owner, pid, "ok")
    project = service.require_storyboard_approved(owner, pid)
    assert project.storyboard.approval_status == StoryboardApprovalStatus.APPROVED
