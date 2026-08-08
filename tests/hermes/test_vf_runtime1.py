"""VF-RUNTIME1 tests: fake-provider protection, generated-asset readiness, data root.

No live/paid calls. All providers mocked or fake-with-flag.
"""
import os
import tempfile
from pathlib import Path

import pytest

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, FrameGenerationStatus, FramePrompt,
    GeneratedScene, ProjectStatus, RawIdea, ResourceIdentity, ResourcePack,
    Scene, ScenePlan, Storyboard, StoryboardFrame, Timeline, TimelineClip,
    VideoGenerationStatus, VideoPrompt,
)


def _base_project(db_path: Path) -> tuple[VideoFactoryService, str, str]:
    svc = VideoFactoryService(SQLiteVideoFactoryRepository(Database(db_path)))
    owner, pid = "owner", "p1"
    svc.create_project(owner, pid)
    svc.save_resource_pack(owner, pid, ResourcePack(
        id="p", owner_user_id=owner,
        product_references=(AssetReference("a1", "asset://products/a1.png"),),
        primary_product_asset_id="a1", product_identity_description="product",
    ))
    svc.lock_resource_pack(owner, pid, ResourceIdentity(description="product"))
    svc.save_raw_idea(owner, pid, RawIdea(text="idea", target_duration_seconds=4))
    svc.save_creative_brief(owner, pid, CreativeBrief(
        objective="o", target_audience="v", core_message="m", tone="t", pace="p",
        cta="", content_blocks=("b",),
    ))
    svc.approve_creative_brief(owner, pid)
    return svc, owner, pid


def test_fake_provider_blocked_without_flag(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.delenv("HERMES_ALLOW_FAKE_PROVIDERS", raising=False)
    from providers.image_provider_factory import get_image_provider
    with pytest.raises(ValueError, match="HERMES_ALLOW_FAKE_PROVIDERS"):
        get_image_provider()


def test_fake_provider_allowed_with_flag(monkeypatch):
    monkeypatch.setenv("IMAGE_PROVIDER", "fake")
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    from providers.image_provider_factory import get_image_provider
    from providers.fake_image_provider import FakeImageGenerationProvider
    assert isinstance(get_image_provider(), FakeImageGenerationProvider)


def test_video_fake_blocked_without_flag(monkeypatch):
    monkeypatch.setenv("VIDEO_PROVIDER", "fake")
    monkeypatch.delenv("HERMES_ALLOW_FAKE_PROVIDERS", raising=False)
    from providers.video_provider_factory import get_video_provider
    with pytest.raises(ValueError, match="HERMES_ALLOW_FAKE_PROVIDERS"):
        get_video_provider()


def test_timeline_fails_without_generated_video_asset(tmp_path):
    svc, owner, pid = _base_project(tmp_path / "t.db")
    svc.save_scene_plan(owner, pid, ScenePlan(scenes=(Scene(
        scene_id="s1", order=1, title="S", objective="o", content="c",
        main_action="a", duration_seconds=4,
    ),)))
    svc.approve_scene_plan(owner, pid)
    # scene exists but has NO generated video asset
    svc.save_generated_scene(owner, pid, GeneratedScene(
        scene_id="s1", video_prompt=VideoPrompt(
            scene_id="s1", duration_seconds=4, start_visual_state="", end_visual_state="",
            subject_action="", product_action="", camera_movement="", camera_framing="",
            environment_motion="",
        ),
    ))
    with pytest.raises(ValueError, match="GENERATED_SCENE_ASSET_REQUIRED"):
        svc.save_timeline(owner, pid, Timeline(
            timeline_id="tl", project_id=pid,
            clips=(TimelineClip(clip_id="c1", order=1, source_asset_id="s1", duration_seconds=4.0),),
        ))


def test_timeline_accepts_generated_video_asset(tmp_path):
    svc, owner, pid = _base_project(tmp_path / "t.db")
    svc.save_scene_plan(owner, pid, ScenePlan(scenes=(Scene(
        scene_id="s1", order=1, title="S", objective="o", content="c",
        main_action="a", duration_seconds=4,
    ),)))
    svc.approve_scene_plan(owner, pid)
    svc.save_generated_scene(owner, pid, GeneratedScene(
        scene_id="s1", video_prompt=VideoPrompt(
            scene_id="s1", duration_seconds=4, start_visual_state="", end_visual_state="",
            subject_action="", product_action="", camera_movement="", camera_framing="",
            environment_motion="",
        ),
    ))
    svc.update_scene_generation_status(owner, pid, "s1", VideoGenerationStatus.COMPLETED, asset_id="vid_s1")
    svc.save_timeline(owner, pid, Timeline(
        timeline_id="tl", project_id=pid,
        clips=(TimelineClip(clip_id="c1", order=1, source_asset_id="s1", duration_seconds=4.0),),
    ))
    project = svc.get_project(owner, pid)
    assert project.status == ProjectStatus.TIMELINE_READY


def test_storyboard_approve_requires_generated_frame(tmp_path):
    svc, owner, pid = _base_project(tmp_path / "t.db")
    svc.save_scene_plan(owner, pid, ScenePlan(scenes=(Scene(
        scene_id="s1", order=1, title="S", objective="o", content="c",
        main_action="a", duration_seconds=4,
    ),)))
    svc.approve_scene_plan(owner, pid)
    # frame with prompt but NO generated asset
    svc.save_storyboard(owner, pid, Storyboard(
        storyboard_id="sb", project_id=pid,
        frames=(StoryboardFrame(
            frame_id="f1", scene_id="s1", order=1, label="l", purpose="p",
            visual_state="", subject_action="", product_state="", character_state="",
            context="", camera_intention="", prompt=FramePrompt(positive_prompt="x"),
        ),),
    ))
    with pytest.raises(ValueError, match="STORYBOARD_FRAME_ASSET_REQUIRED"):
        svc.approve_storyboard(owner, pid)


def test_data_root_workspace_derivation(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HERMES_VIDEO_FACTORY_WORKSPACE", raising=False)
    from hermes.config import get_data_path
    ws = get_data_path("workspaces", "video-factory")
    assert str(ws).startswith(str(tmp_path.resolve()))
    assert ws.parts[-2:] == ("workspaces", "video-factory")
