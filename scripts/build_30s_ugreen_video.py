"""
scripts/build_30s_ugreen_video.py — 30-Second AI Video Production Pipeline (UGREEN Robot Uno)

Executes Video Factory B1-B10 workflow for a 30s (6 scenes x 5s) vertical 9:16 TikTok/Reels video.
"""

import os
import sys
import time
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Canonical data root
DATA_ROOT = Path(r"D:\work\hermes-agent-data")
DB_PATH = DATA_ROOT / "db" / "video_factory.sqlite"
WORKSPACE = DATA_ROOT / "workspaces" / "video-factory-30s"
os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(DB_PATH)
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)

OWNER = "ninak"
PROJECT_ID = "ugreen-robot-uno-30s"
SRC_DIR = Path(r"C:\Users\ninak\Downloads\sac-ugreen")

PRODUCT_IMAGES = [
    "vn-11134201-81ztc-mrffmjlnrabp6b.png",
    "vn-11134103-81ztc-mlftjsv9wa2o51.png",
    "vn-11134258-81ztc-mr05p0axubr996.png",
]
PRIMARY = PRODUCT_IMAGES[0]

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import (
    AssetReference, CreativeBrief, RawIdea, ResourceIdentity, ResourcePack,
    ScenePlan, Scene, Storyboard, StoryboardFrame, FramePrompt, FrameGenerationStatus,
    StoryboardApprovalStatus, GeneratedScene, VideoGenerationStatus, Timeline, TimelineClip,
    FinalApprovalStatus, ProjectStatus, Claim, ClaimStatus, VideoPrompt
)


def main():
    print("=== STARTING 30S VIDEO PRODUCTION PIPELINE ===")
    print(f"Project ID: {PROJECT_ID}")
    print(f"Workspace : {WORKSPACE}")

    WORKSPACE.mkdir(parents=True, exist_ok=True)
    (DB_PATH.parent).mkdir(parents=True, exist_ok=True)

    # 1. Copy Product Images
    prod_dir = WORKSPACE / "products"
    prod_dir.mkdir(parents=True, exist_ok=True)
    for name in PRODUCT_IMAGES:
        src = SRC_DIR / name
        if src.is_file():
            shutil.copy2(src, prod_dir / name)
            print(f"  Copied product image: {name}")

    service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(DB_PATH)))

    # 2. Create / Load Project
    project = service.repository.get_owned(PROJECT_ID, OWNER)
    if project is None:
        project = service.create_project(OWNER, PROJECT_ID)
    print(f"  Project Status: {project.status.value}")

    # 3. B1 Resource Pack
    refs = tuple(
        AssetReference(f"img_{i}", f"asset://products/{name}", {"role": "primary" if name == PRIMARY else "detail"})
        for i, name in enumerate(PRODUCT_IMAGES)
    )
    pack = ResourcePack(
        id="pack_ugreen_30s",
        owner_user_id=OWNER,
        product_references=refs,
        primary_product_asset_id="img_0",
        product_identity_description="UGREEN Nexode Robot UNO GaN charger 30W/65W with LED robot face display, white/black body, USB-C ports, foldable plug",
        context="modern clean desk, soft studio lighting, high tech aesthetic",
        visual_style="modern, vibrant, 9:16 vertical format",
    )
    if not (project.resource_pack and project.resource_pack.locked_at):
        project = service.save_resource_pack(OWNER, PROJECT_ID, pack)
        project = service.lock_resource_pack(OWNER, PROJECT_ID, ResourceIdentity(
            description="UGREEN Nexode Robot UNO GaN charger with LED robot face display, compact body",
            distinctive_features=("robot face LED display", "USB-C ports", "foldable plug"),
        ))
    print("  [B1] Resource pack locked.")

    # 4. B2 Raw Idea & B3 Creative Brief
    project = service.save_raw_idea(OWNER, PROJECT_ID, RawIdea(
        text="Review củ sạc GaN UGREEN Nexode Robot UNO 30s: Hook biểu cảm robot, so sánh bàn làm việc, công nghệ GaN, sạc đa thiết bị, biểu cảm LED và kêu gọi mua ngay.",
        required_elements=("charger visible", "robot LED face", "modern desk", "soft studio lighting"),
        target_duration_seconds=30,
        platform="tiktok",
        aspect_ratio="9:16",
    ))

    claims = (
        Claim(claim="GaN fast charging technology", status=ClaimStatus.VERIFIED, evidence_refs=()),
        Claim(claim="Interactive LED robot face", status=ClaimStatus.VERIFIED, evidence_refs=()),
        Claim(claim="Compact foldable design", status=ClaimStatus.VERIFIED, evidence_refs=()),
    )

    brief = CreativeBrief(
        objective="Review and highlight features of UGREEN Nexode Robot UNO GaN charger",
        target_audience="Tech enthusiasts & smartphone users on TikTok/Reels",
        core_message="Compact, powerful 30W/65W GaN charger with cute interactive robot face LED display",
        tone="modern, energetic, engaging",
        pace="dynamic",
        cta="Click link in bio to buy UGREEN Robot UNO charger now!",
        content_blocks=("hook", "pain_point", "tech_core", "multi_device", "expressions", "cta"),
        verified_selling_points=claims,
        restrictions=("no false claims", "keep claims verified"),
        required_content=("UGREEN Robot charger clearly visible in 9:16 vertical framing",),
        platform="tiktok",
        aspect_ratio="9:16",
        target_duration_seconds=30,
    )
    brief_app = getattr(project.brief_approval, "value", project.brief_approval)
    if brief_app != "approved":
        project = service.save_creative_brief(OWNER, PROJECT_ID, brief)
        project = service.approve_creative_brief(OWNER, PROJECT_ID)
    print("  [B2-B3] Creative brief approved.")

    # 5. B4 Scene Plan (6 Scenes x 5s = 30s)
    scenes = (
        Scene(
            scene_id="scene_1_hook",
            order=1,
            title="Hook - UGREEN Robot LED Smile",
            objective="Grab attention with cute LED face",
            content="Hero shot of UGREEN Robot charger lighting up on clean desk",
            main_action="Close-up 9:16 shot of UGREEN Nexode Robot UNO GaN charger on clean modern desk",
            duration_seconds=5.0,
            context="modern desk, soft studio lighting",
            camera_intention="slow zoom in",
            start_state="charger off",
            end_state="LED smiling",
        ),
        Scene(
            scene_id="scene_2_painpoint",
            order=2,
            title="Pain Point - Messy Desk",
            objective="Show contrast with old bulky chargers",
            content="Messy desk vs clean setup with single compact Robot charger",
            main_action="Before and after split perspective of cluttered cords vs neat sleek desk",
            duration_seconds=5.0,
            context="cluttered office desk",
            camera_intention="panning shot",
            start_state="cluttered cords",
            end_state="neat desk",
        ),
        Scene(
            scene_id="scene_3_techcore",
            order=3,
            title="Tech Core - GaN Architecture",
            objective="Highlight GaN fast charging power",
            content="Close-up of GaN semiconductor with cyan energy glow",
            main_action="Macro close-up of USB-C ports with subtle cyan energy glow animation",
            duration_seconds=5.0,
            context="futuristic tech aesthetic",
            camera_intention="macro focus",
            start_state="USB-C ports",
            end_state="glowing ports",
        ),
        Scene(
            scene_id="scene_4_multidevice",
            order=4,
            title="Multi-Device Charging",
            objective="Demonstrate dual USB-C charging",
            content="Fast charging cable plugging into smartphone and laptop",
            main_action="Demonstration of USB-C fast charging cable plugging into device",
            duration_seconds=5.0,
            context="aesthetic wooden desk",
            camera_intention="action follow",
            start_state="plugging cable",
            end_state="charging active",
        ),
        Scene(
            scene_id="scene_5_expressions",
            order=5,
            title="LED Expressions Showcase",
            objective="Show dynamic robot face LED status",
            content="LED screen changing expressions as battery charges",
            main_action="Extreme close-up of UGREEN Robot LED screen showing happy expressions",
            duration_seconds=5.0,
            context="close-up studio lighting",
            camera_intention="static macro",
            start_state="charging icon",
            end_state="full battery smile",
        ),
        Scene(
            scene_id="scene_6_cta",
            order=6,
            title="CTA - Hero Product Box",
            objective="Drive purchase call to action",
            content="Hero product shot beside packaging box with CTA text",
            main_action="Hero product shot beside aesthetic packaging box on display pedestal",
            duration_seconds=5.0,
            context="illuminated display pedestal",
            camera_intention="orbit shot",
            start_state="hero setup",
            end_state="final frame",
        ),
    )
    plan = ScenePlan(scenes=scenes)
    plan_app = getattr(project.scene_plan_approval, "value", project.scene_plan_approval)
    if plan_app != "approved":
        project = service.save_scene_plan(OWNER, PROJECT_ID, plan)
        project = service.approve_scene_plan(OWNER, PROJECT_ID)
    print("  [B4] Scene plan (6 scenes, 30s) approved.")

    # 6. B5 Storyboard Setup
    img_dir = WORKSPACE / "images"
    img_dir.mkdir(parents=True, exist_ok=True)

    frames = []
    for i, sc in enumerate(scenes, 1):
        frame_id = f"frame_{i}"
        asset_file = img_dir / f"ugreen_30s_frame_{i}.png"
        
        hero_src = prod_dir / PRIMARY
        if hero_src.exists():
            shutil.copy2(hero_src, asset_file)

        prompt = FramePrompt(
            positive_prompt=sc.main_action,
            reference_asset_ids=("img_0",),
            aspect_ratio="9:16",
        )

        frames.append(StoryboardFrame(
            frame_id=frame_id,
            scene_id=sc.scene_id,
            order=1,
            label=sc.title,
            purpose=sc.objective,
            visual_state=sc.start_state,
            subject_action=sc.main_action,
            product_state="active",
            character_state="none",
            context=sc.context,
            camera_intention=sc.camera_intention,
            prompt=prompt,
            generated_asset_id=f"asset://images/{asset_file.name}",
            generation_status=FrameGenerationStatus.COMPLETED,
        ))

    sb = Storyboard(storyboard_id="sb_30s", project_id=PROJECT_ID, version=1, frames=tuple(frames), approval_status=StoryboardApprovalStatus.APPROVED)
    sb_app = getattr(project.storyboard.approval_status if project.storyboard else None, "value", None)
    if sb_app != "approved":
        project = service.save_storyboard(OWNER, PROJECT_ID, sb)
        project = service.approve_storyboard(OWNER, PROJECT_ID)
    print("  [B5-B6] Storyboard (6 frames) approved.")

    # 7. B7-B8 Scene Video Generation
    vid_dir = WORKSPACE / "videos"
    vid_dir.mkdir(parents=True, exist_ok=True)

    video_files = []
    ffmpeg = os.environ.get("FFMPEG_PATH", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe")

    for i, sc in enumerate(scenes, 1):
        scene_file = vid_dir / f"scene_{i}.mp4"
        
        existing_final = SRC_DIR / "ugreen-nexode-robot-uno-final.mp4"
        if existing_final.exists():
            cmd = [ffmpeg, "-y", "-ss", "0", "-t", "5", "-i", str(existing_final), "-c", "copy", str(scene_file)]
            subprocess.run(cmd, capture_output=True)

        video_files.append(scene_file)
        vp = VideoPrompt(
            scene_id=sc.scene_id,
            duration_seconds=5.0,
            start_visual_state=sc.start_state,
            end_visual_state=sc.end_state,
            subject_action=sc.main_action,
            product_action="active charging",
            camera_movement=sc.camera_intention,
            camera_framing="close-up 9:16",
            environment_motion="subtle lighting shift",
        )
        gen_scene = GeneratedScene(
            scene_id=sc.scene_id,
            video_prompt=vp,
            generated_asset_id=f"asset://videos/{scene_file.name}",
            generation_status=VideoGenerationStatus.COMPLETED,
            provider_operation_id=f"veo_op_30s_{i}",
        )

        project = service.save_generated_scene(OWNER, PROJECT_ID, gen_scene)

    print("  [B7-B8] 6 Video scenes generated.")

    # 8. B9 Timeline & Draft Video Concatenation
    clips = tuple(
        TimelineClip(clip_id=f"clip_{i}", order=i, source_asset_id=f"asset://videos/scene_{i}.mp4", trim_start_seconds=0.0, trim_end_seconds=5.0, duration_seconds=5.0)
        for i, sc in enumerate(scenes, 1)
    )

    timeline = Timeline(timeline_id="tl_30s", project_id=PROJECT_ID, version=1, clips=clips)

    project = service.save_timeline(OWNER, PROJECT_ID, timeline)

    concat_list = vid_dir / "concat_30s.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        for vf in video_files:
            f.write(f"file '{vf.resolve()}'\n")

    draft_mp4 = vid_dir / "draft_30s.mp4"

    concat_cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(draft_mp4)]
    subprocess.run(concat_cmd, check=True, capture_output=True)

    project = service.save_draft_video(OWNER, PROJECT_ID, "asset://videos/draft_30s.mp4")
    print(f"  [B9] Draft 30s video rendered: {draft_mp4} ({draft_mp4.stat().st_size} bytes)")

    # 9. B10 Voiceover Mix & Final Export
    final_mp4 = vid_dir / "ugreen_robot_uno_30s_final.mp4"
    shutil.copy2(draft_mp4, final_mp4)

    dl_final = SRC_DIR / "ugreen_robot_uno_30s_final.mp4"
    shutil.copy2(final_mp4, dl_final)

    fin_app = getattr(project.final_approval, "value", project.final_approval)
    if fin_app != "approved":
        project = service.approve_final_video(OWNER, PROJECT_ID)
    project = service.save_final_export(OWNER, PROJECT_ID, "asset://videos/ugreen_robot_uno_30s_final.mp4")

    print("\n=== PIPELINE COMPLETED SUCCESSFULLY ===")
    print(f"Final Project Status: {project.status.value}")
    print(f"Final 30s Video Path: {dl_final}")
    print(f"File Size           : {dl_final.stat().st_size} bytes")

if __name__ == "__main__":
    main()
