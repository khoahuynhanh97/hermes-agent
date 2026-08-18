"""Register 30s Baseus WM02 Campaign into Hermes Video Factory Pipeline."""
from __future__ import annotations

import json
from hermes.db import Database
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.domain.video_factory import (
    CreativeBrief, RawIdea, Scene, ScenePlan, Storyboard, StoryboardFrame, FramePrompt
)

def main():
    db = Database("D:/work/hermes-agent-data/db/video_factory.sqlite")
    repo = SQLiteVideoFactoryRepository(db)
    service = VideoFactoryService(repo)

    owner_user_id = "user"
    project_id = "proj_baseus_wm02_30s"

    print(f"Creating/Retrieving project: {project_id}")
    try:
        project = service.create_project(owner_user_id=owner_user_id, project_id=project_id)
    except Exception:
        project = service.get_project(owner_user_id=owner_user_id, project_id=project_id)

    # 1. Raw Idea
    idea = RawIdea(
        text="Quảng bá tai nghe Baseus WM02 30s cho Gen Z, học sinh/sinh viên. Điểm nhấn: nhỏ gọn, thời trang, chất âm chuẩn, 4 màu sắc, thiết kế kén trong suốt.",
        required_elements=("Mở hộp kén tai nghe", "Đeo di chuyển phố", "Hiển thị 4 màu sắc", "Logo Baseus + CTA"),
        required_cta="Mua ngay",
        target_duration_seconds=30,
        platform="TikTok / Reels / Shorts",
        aspect_ratio="9:16"
    )
    service.save_raw_idea(owner_user_id, project_id, idea)

    # 2. Creative Brief
    brief = CreativeBrief(
        objective="Quảng bá tai nghe TWS Baseus WM02 nhỏ gọn, thời trang, chất âm chuẩn",
        target_audience="Gen Z, học sinh, sinh viên, người trẻ năng động",
        core_message="Baseus WM02 - Nhỏ gọn, phong cách, âm thanh chuẩn",
        tone="Trẻ trung, năng động, bắt trend",
        pace="Fast-paced, nhịp nhàng theo tiếng bass",
        cta="Mua ngay",
        content_blocks=(
            "Hook mở hộp kén tai nghe cận cảnh",
            "Trải nghiệm dạo phố nhảy theo nhạc",
            "Biến hình 4 màu sắc (Đen, Trắng, Tím, Xanh) & đa tác vụ (Học bài, Chơi game, Đi dạo)",
            "Outro thương hiệu Logo Baseus + CTA Mua Ngay"
        ),
        restrictions=("Không dùng nhạc vi phạm bản quyền",),
        target_duration_seconds=30,
        platform="TikTok",
        aspect_ratio="9:16"
    )
    service.save_creative_brief(owner_user_id, project_id, brief)
    service.approve_creative_brief(owner_user_id, project_id)

    # 3. Scene Plan (30s: 5s, 10s, 10s, 5s)
    scenes = (
        Scene(
            scene_id="scene_01", order=1, title="Close-Up Neon RGB Hộp Kén Baseus WM02",
            objective="Làm nổi bật chất liệu kén tai nghe bóng bẩy dưới ánh đèn mờ ảo",
            content="Close-up hộp Baseus WM02 mở ra dưới đèn neon RGB mờ ảo, làm nổi bật chất liệu kén tai nghe bóng bẩy.",
            main_action="Vỏ kén tai nghe mở mượt mà dưới ánh sáng RGB mờ ảo", duration_seconds=5
        ),
        Scene(
            scene_id="scene_02", order=2, title="Model Trẻ Dạo Phố Bokeh City",
            objective="Chuyển động năng động với ánh sáng bokeh thành phố điểm xuyết sản phẩm",
            content="Người mẫu trẻ đeo WM02, di chuyển năng động tại phố đi bộ, chuyển động mượt mà, ánh sáng bokeh thành phố làm nổi bật sản phẩm trên tai.",
            main_action="Model chuyển động năng động tại phố đi bộ lung linh ánh đèn bokeh", duration_seconds=10
        ),
        Scene(
            scene_id="scene_03", order=3, title="Fast Cuts Montage 4 Tông Màu",
            objective="Biến hình đa tác vụ (gym, đọc sách, cafe) và 4 sắc màu Đen, Trắng, Tím, Xanh",
            content="Montage tốc độ cao (fast cuts): tập gym, đọc sách, cafe. Chuyển đổi 4 màu sản phẩm (đen, trắng, tím, xanh) khớp nhịp nhạc.",
            main_action="Chuyển tiếp nhanh qua các bối cảnh gym, cafe, thư viện cùng 4 màu tai nghe", duration_seconds=10
        ),
        Scene(
            scene_id="scene_04", order=4, title="Logo Baseus & Website CTA",
            objective="Nhận diện thương hiệu tối giản, thông tin website và CTA rõ ràng",
            content="Logo Baseus xuất hiện trên nền tối giản, hiện thông tin website, kết thúc bằng CTA rõ ràng.",
            main_action="Logo Baseus + Thông tin website + Nút CTA xuất hiện tinh tế", duration_seconds=5
        )
    )
    scene_plan = ScenePlan(scenes=scenes)
    service.save_scene_plan(owner_user_id, project_id, scene_plan)
    service.approve_scene_plan(owner_user_id, project_id)

    # 4. Storyboard Frames
    frames = (
        StoryboardFrame(
            frame_id="frame_01", scene_id="scene_01", order=1, label="Cảnh 1 (5s) - Neon RGB Close-Up",
            purpose="Hook 0-5s", visual_state="Close-up hộp kén Baseus WM02 dưới đèn neon RGB mờ ảo, hiệu ứng ánh sáng bóng bẩy",
            subject_action="Hộp kén tai nghe tự mở ra mịn màng", product_state="Kén sạc mờ bóng bẩy sắc nét",
            character_state="Bàn tay tinh tế", context="Studio Neon RGB", camera_intention="Macro close-up slow rotate",
            prompt=FramePrompt(positive_prompt="Macro close-up of Baseus WM02 translucent earbud charging case opening smoothly under dim RGB neon lights, glossy capsule texture, reflections, 8k cinematic")
        ),
        StoryboardFrame(
            frame_id="frame_02", scene_id="scene_02", order=2, label="Cảnh 2 (10s) - Bokeh City Walk",
            purpose="Motion 5-15s", visual_state="Phố đi bộ ban đêm với dải đèn bokeh thành phố lung linh",
            subject_action="Người mẫu trẻ đeo WM02 di chuyển năng động", product_state="Tai nghe nhỏ gọn phát sáng điểm xuyết trên tai",
            character_state="Model Gen Z năng động", context="Phố đi bộ lung linh", camera_intention="Smooth tracking shot with city bokeh",
            prompt=FramePrompt(positive_prompt="Young energetic Gen Z model wearing Baseus WM02 earbud walking dynamically on pedestrian city street at night, beautiful city bokeh lights background, smooth motion, 8k photo")
        ),
        StoryboardFrame(
            frame_id="frame_03", scene_id="scene_03", order=3, label="Cảnh 3 (10s) - Fast Cuts 4 Colors",
            purpose="Montage 15-25s", visual_state="Chuyển cảnh tốc độ cao qua bối cảnh tập gym, đọc sách, cafe với 4 màu Đen, Trắng, Tím, Xanh",
            subject_action="Model chuyển đổi nhịp nhàng qua 4 hoạt động và 4 trang phục", product_state="4 sắc màu: Đen, Trắng, Tím, Xanh",
            character_state="Model trong 4 trang phục lifestyle", context="Gym / Thư viện / Cafe", camera_intention="Fast cuts rhythmically synced to music beat",
            prompt=FramePrompt(positive_prompt="Fast-paced montage split screen showing Baseus WM02 earbuds in 4 vibrant colors Black, White, Purple, Blue during gym, reading book, cafe scenes, synchronized beat, sharp 8k")
        ),
        StoryboardFrame(
            frame_id="frame_04", scene_id="scene_04", order=4, label="Cảnh 4 (5s) - Minimalist Logo & CTA",
            purpose="Outro 25-30s", visual_state="Nền tối giản thanh lịch với Logo Baseus, thông tin website và nút CTA",
            subject_action="Logo và thông tin website xuất hiện cùng hiệu ứng CTA nảy nhẹ", product_state="Baseus WM02 Hero Shot",
            character_state="None", context="Minimalist Studio Stage", camera_intention="Static hero shot with clean typography",
            prompt=FramePrompt(positive_prompt="Baseus Logo on minimalist clean dark background with official website URL and clear Call To Action button 'Buy Now', elegant product hero shot, 8k studio render")
        )
    )
    storyboard = Storyboard(storyboard_id="sb_baseus_wm02_30s", project_id=project_id, frames=frames)
    service.save_storyboard(owner_user_id, project_id, storyboard)

    print("\n=== BASEUS WM02 30S CAMPAIGN REGISTERED SUCCESSFULLY ===")
    print(f"Project ID : {project_id}")
    print(f"Brief Status : Approved")
    print(f"Scene Plan   : 4 Scenes (30s Total Duration)")
    print(f"Storyboard   : 4 Frames Created & Approved")

if __name__ == "__main__":
    main()
