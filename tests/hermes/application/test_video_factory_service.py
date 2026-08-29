"""Offline unit tests for Video Factory application service and SQLite persistence."""
from __future__ import annotations

import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[3] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pytest

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.domain.video_factory import (
    AssetReference, Claim, ClaimStatus, CreativeBrief, ProjectStatus,
    RawIdea, ResourceIdentity, ResourcePack, Scene, ScenePlan,
)


@pytest.fixture
def service(tmp_path):
    repo = SQLiteVideoFactoryRepository(tmp_path / "test_vf.sqlite")
    return VideoFactoryService(repo)


def test_project_lifecycle_f1(service):
    # 1. Create project
    proj = service.create_project("user_a", "proj_01")
    assert proj.id == "proj_01"
    assert proj.status == ProjectStatus.DRAFT

    # 2. Save Resource Pack
    asset = AssetReference(asset_id="a1", uri="asset://product.png")
    pack = ResourcePack(
        id="rp_01",
        owner_user_id="user_a",
        product_references=(asset,),
        primary_product_asset_id="a1",
        product_identity_description="Portable fan",
    )
    proj = service.save_resource_pack("user_a", "proj_01", pack)
    assert proj.status == ProjectStatus.RESOURCE_READY

    # 3. Lock Resource Pack
    identity = ResourceIdentity(description="White portable fan with 5 blades")
    proj = service.lock_resource_pack("user_a", "proj_01", identity)
    assert proj.resource_pack.locked_at is not None

    # 4. Save Raw Idea
    idea = RawIdea(text="Summer commuting portable fan video")
    proj = service.save_raw_idea("user_a", "proj_01", idea)
    assert proj.raw_idea.text == "Summer commuting portable fan video"

    # 5. Save & Approve Creative Brief
    brief = CreativeBrief(
        objective="Convert hot commuters",
        target_audience="Subway riders",
        core_message="Silent portable cooling",
        tone="Direct",
        pace="Brisk",
        cta="Get 20% off today",
        content_blocks=("Hot commute dilemma", "Jisulife silent turbo", "Discount CTA"),
    )
    proj = service.save_creative_brief("user_a", "proj_01", brief)
    assert proj.status == ProjectStatus.BRIEF_READY
    proj = service.approve_creative_brief("user_a", "proj_01")
    assert proj.brief_approval == "approved"

    # 6. Save & Approve Scene Plan
    s1 = Scene(scene_id="s1", order=1, title="Hook", objective="Hook", content="Sweating commuter", main_action="Fanning face", duration_seconds=3)
    s2 = Scene(scene_id="s2", order=2, title="Demo", objective="Demo", content="Turn on fan", main_action="Instant relief", duration_seconds=5)
    plan = ScenePlan(scenes=(s1, s2))
    proj = service.save_scene_plan("user_a", "proj_01", plan)
    assert proj.status == ProjectStatus.SCENE_PLAN_READY
    proj = service.approve_scene_plan("user_a", "proj_01")
    assert proj.status == ProjectStatus.READY_FOR_STORYBOARD

    # 7. Restart persistence check
    reloaded_proj = service.get_project("user_a", "proj_01")
    assert reloaded_proj.status == ProjectStatus.READY_FOR_STORYBOARD
    assert reloaded_proj.creative_brief.objective == "Convert hot commuters"
    assert len(reloaded_proj.scene_plan.scenes) == 2


def test_owner_isolation_raises_not_found(service):
    service.create_project("user_a", "proj_01")
    with pytest.raises(ValueError, match="PROJECT_NOT_FOUND"):
        service.get_project("user_b", "proj_01")
