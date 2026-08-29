"""Offline unit tests for Video Factory domain models and validations."""
from __future__ import annotations

import pytest

from hermes.domain.video_factory import (
    AssetReference, Claim, ClaimStatus, CreativeBrief, FinalApprovalStatus,
    FrameGenerationStatus, FramePrompt, GeneratedScene, ProjectStatus, RawIdea,
    ResourceIdentity, ResourcePack, Scene, ScenePlan, Storyboard,
    StoryboardApprovalStatus, StoryboardFrame, Timeline, TimelineClip,
    TimelineStatus, VideoFactoryProject, VideoGenerationStatus, VideoPrompt,
)


def test_asset_reference_validation():
    ref = AssetReference(asset_id="a1", uri="product.png")
    assert ref.asset_id == "a1"
    assert ref.uri == "product.png"

    with pytest.raises(ValueError, match="required"):
        AssetReference(asset_id="", uri="product.png")


def test_resource_pack_validation():
    asset = AssetReference(asset_id="prod_01", uri="p.png")
    pack = ResourcePack(
        id="rp_1",
        owner_user_id="user_1",
        product_references=(asset,),
        primary_product_asset_id="prod_01",
        product_identity_description="Smart fan",
    )
    assert pack.id == "rp_1"
    assert pack.primary_product_asset_id == "prod_01"

    # Missing primary product asset in references
    with pytest.raises(ValueError, match="primary_product_asset_id must reference"):
        ResourcePack(
            id="rp_1",
            owner_user_id="user_1",
            product_references=(asset,),
            primary_product_asset_id="unknown_asset",
            product_identity_description="Smart fan",
        )


def test_creative_brief_validation():
    brief = CreativeBrief(
        objective="Drive sales",
        target_audience="Commuters",
        core_message="Stay cool anywhere",
        tone="Energetic",
        pace="Fast",
        cta="Shop Now",
        content_blocks=("Problem", "Solution", "CTA"),
        target_duration_seconds=15,
    )
    assert brief.objective == "Drive sales"
    assert brief.target_duration_seconds == 15

    with pytest.raises(ValueError, match="objective is required"):
        CreativeBrief(
            objective="",
            target_audience="Commuters",
            core_message="Stay cool",
            tone="Energetic",
            pace="Fast",
            cta="Shop Now",
            content_blocks=("Problem",),
        )


def test_scene_plan_contiguous_orders():
    s1 = Scene(scene_id="s1", order=1, title="Intro", objective="Hook", content="Show", main_action="Act", duration_seconds=3)
    s2 = Scene(scene_id="s2", order=2, title="Demo", objective="Demo", content="Show", main_action="Act", duration_seconds=5)
    plan = ScenePlan(scenes=(s1, s2))
    assert plan.total_duration_seconds == 8

    # Non-contiguous orders raise error
    s3 = Scene(scene_id="s3", order=5, title="Outro", objective="CTA", content="Show", main_action="Act", duration_seconds=2)
    with pytest.raises(ValueError, match="unique and contiguous"):
        ScenePlan(scenes=(s1, s3))
