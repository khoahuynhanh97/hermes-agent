import os
import json

def rewrite_storyboard_prompts(json_path, output_dir):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Re-define components to strictly match the 4 items and 2 screws
    data["product_analysis"]["components"] = [
        "Thân đỡ điện thoại màu đen (chữ nhật, có kẹp hai bên)",
        "Mũ bảo hiểm mini màu đen (có kính trắng vẽ hình điện tâm đồ)",
        "Đế gắn nhựa màu trắng hình vuông (có lỗ tròn to ở giữa)",
        "Cần nối màu đen dạng cong (có hoa văn vân sọc nổi dọc thân cần)",
        "Một con ốc màu đen",
        "Một con ốc màu trắng"
    ]

    # Re-define assembly steps to strictly match these parts
    data["product_analysis"]["assembly_steps"] = [
        "Bước 1: Đặt đế gắn nhựa màu trắng hình vuông (có lỗ tròn to ở giữa) khớp vào mặt dưới/mặt trong của chiếc mũ bảo hiểm mini màu đen.",
        "Bước 2: Sử dụng con ốc màu trắng để vặn và siết chặt, cố định đế gắn nhựa màu trắng vào mũ bảo hiểm mini.",
        "Bước 3: Lồng cần nối màu đen dạng cong vào đế gắn nhựa màu trắng thông qua lỗ khớp tròn, sử dụng con ốc màu đen để vặn siết cố định cần nối vào cụm mũ và đế nhựa.",
        "Bước 4: Gắn thân đỡ điện thoại màu đen vào phần chốt khóa phía trước mặt của cụm để hoàn thiện giá đỡ giá kẹp điện thoại."
    ]

    # Update prompts for each scene
    for scene in data.get("scenes", []):
        num = scene.get("scene_number")
        
        if num == 1:
            scene["visual_description"] = (
                "Các bộ phận tháo rời của giá đỡ điện thoại được xếp gọn gàng trên mặt bàn làm việc màu trắng. "
                "Gồm có: 1 thân đỡ điện thoại kẹp đen, 1 chiếc mũ bảo hiểm mini đen có kính trắng điện tâm đồ, "
                "1 đế gắn nhựa vuông màu trắng có lỗ tròn lớn ở giữa, 1 cần nối cong màu đen có vân nổi dọc thân, "
                "1 con ốc đen và 1 con ốc trắng. Xung quanh là các đồ trang trí màu hồng thỏ dễ thương."
            )
            scene["image_prompt_en"] = (
                "Overhead flat lay shot, top-down view of a white desk with soft natural lighting. On the desk are exactly "
                "six items arranged neatly: a black rectangular phone cradle with side clamps, a mini black toy helmet with "
                "a white decorative band and white goggles featuring a heartbeat line pattern, a white square plastic mounting plate "
                "with a large circular socket in the center and small screw holes on the corners, a black curved plastic extension arm "
                "with a textured ribbed pattern along its body, one simple black screw, and one simple white screw. The background is "
                "softly blurred with cute pink office desk accessories: a bunny pen holder, a pink makeup pouch, a pink mouse, and a lily flower vase. "
                "No extra or invented components. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "A slow zoom-in overhead flat lay video on a white desk with soft natural lighting. On the desk are exactly "
                "six items arranged neatly: a black rectangular phone cradle with side clamps, a mini black toy helmet with "
                "a white decorative band and white goggles featuring a heartbeat line pattern, a white square plastic mounting plate "
                "with a large circular socket in the center and small screw holes on the corners, a black curved plastic extension arm "
                "with a textured ribbed pattern along its body, one simple black screw, and one simple white screw. Delicate female hands "
                "gently arrange the items to create a clean layout. The background features cute pink office desk accessories softly blurred. "
                "No extra or invented components. 9:16 aspect ratio."
            )

        elif num == 2:
            scene["visual_description"] = (
                "Cận cảnh đôi bàn tay nữ thon thả đặt đế gắn nhựa màu trắng hình vuông khớp vào mặt trong của chiếc mũ bảo hiểm mini màu đen, "
                "sau đó luồn con ốc màu trắng qua lỗ ren để liên kết hai bộ phận này lại với nhau."
            )
            scene["image_prompt_en"] = (
                "Close-up shot of delicate female hands assembling the components on a white desk. Her left hand holds the mini black toy helmet "
                "upside down, while her right hand aligns the white square plastic mounting plate with the large circular socket into the helmet's interior, "
                "threading the single white screw through to connect them. Blurred pink bunny decor and pink pouch in the background. "
                "Strictly showing only these parts. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "Close-up video of delicate female hands. The left hand holds the mini black toy helmet upside down, while the right hand aligns "
                "the white square plastic mounting plate (with the large circular socket) into the helmet's interior and threads the single white screw "
                "through to connect them. Smooth movements. Background shows a white desk with cute pink accessories softly blurred. 9:16 aspect ratio."
            )

        elif num == 3:
            scene["visual_description"] = (
                "Cận cảnh đôi bàn tay nữ thon thả lắp cần nối màu đen dạng cong vào phần chốt tròn của đế gắn nhựa màu trắng, "
                "sau đó đưa con ốc màu đen vào và vặn chặt để cố định cần nối."
            )
            scene["image_prompt_en"] = (
                "Close-up shot of delicate female hands connecting the black curved plastic extension arm (with textured ribbed pattern) "
                "into the circular socket of the white square plastic mounting plate that is attached to the mini black helmet. She inserts "
                "the single black screw through the connection point and tightens it. White desk surface with blurred cute pink accessories. "
                "Strictly showing only these parts. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "Close-up video of delicate female hands connecting the black curved plastic extension arm (with textured ribbed pattern) "
                "into the circular socket of the white square plastic mounting plate attached to the mini black helmet. She inserts "
                "the single black screw through the hole and tightens it. Camera tracks the tightening motion smoothly. 9:16 aspect ratio."
            )

        elif num == 4:
            scene["visual_description"] = (
                "Cận cảnh đôi bàn tay nữ thon thả gắn thân đỡ điện thoại chính màu đen vào phần chốt ở mặt trước của cụm đế gắn nhựa màu trắng, "
                "tạo thành bộ giá kẹp hoàn chỉnh có mũ bảo hiểm bảo vệ phía trên."
            )
            scene["image_prompt_en"] = (
                "Close-up shot of delicate female hands attaching the black rectangular phone cradle with side clamps onto the mounting chasis "
                "at the front of the white square plastic mounting plate, completing the assembly with the mini black helmet sitting on top. "
                "White desk background with blurred cute pink accessories. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "Close-up video of delicate female hands snapping the black rectangular phone cradle with side clamps onto the mounting chasis "
                "of the white square plastic mounting plate, completing the assembly with the mini black helmet sitting on top. The camera focus "
                "remains on the snap connection. White desk background. 9:16 aspect ratio."
            )

        elif num == 5:
            scene["background"] = "Đường phố đô thị năng động hoặc gara xe máy hiện đại, mờ nhẹ."
            scene["image_prompt_en"] = (
                "POV shot from a motorcycle rider. The fully assembled phone holder is securely mounted on the handlebar. It consists only of "
                "the black rectangular phone cradle, the mini black helmet with the heartbeat visor sitting on top, the white square mounting base, "
                "and the black curved extension arm. A smartphone is clamped securely in the holder. Bright sunlight, outdoor background. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "POV video from a motorcycle rider looking at the assembled phone holder mounted on the handlebar. The holder consists only of "
                "the black rectangular phone cradle, the mini black helmet with the heartbeat visor on top, the white square mounting base, "
                "and the black curved extension arm. The rider rides smoothly down the street. Camera simulates riding movement. 9:16 aspect ratio."
            )

        elif num == 6:
            scene["image_prompt_en"] = (
                "Wide shot of the fully assembled phone holder (black phone cradle, mini black helmet on top, white square mounting plate, "
                "black curved extension arm) holding a smartphone, standing on a clean white desk. Delicate female hands gently adjust the phone. "
                "Cute pink accessories (bunny pen holder, pink mouse, flower vase) are neatly arranged around it. Clean, bright studio lighting. 9:16 aspect ratio."
            )
            scene["video_prompt_en"] = (
                "A slow rotating orbit shot around the fully assembled phone holder (black phone cradle, mini black helmet, white square mounting plate, "
                "black curved arm) holding a smartphone on a clean white desk. Cute pink accessories are neatly arranged around it. Delicate female hands "
                "point to the product. Smooth and professional commercial video style. 9:16 aspect ratio."
            )

    # Save JSON
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
        
    # Format and save markdown
    md_path = os.path.join(output_dir, 'storyboard_analysis.md')
    analysis = data.get("product_analysis", {})
    title = data.get("title", "Storyboard AI")
    concept = data.get("concept_summary", "")
    duration = data.get("video_duration", 24)
    scenes_count = data.get("scene_count", 6)
    hooks = data.get("hook_options", [])
    ctas = data.get("cta_options", [])
    
    md_content = f"# Báo cáo Phân tích & Storyboard Video AI: Lắp Ghép Giá Đỡ Điện Thoại Có Mũ Bảo Hiểm Mini (Chi Tiết Chuẩn Linh Kiện)\n\n"
    md_content += f"## 1. Phân tích linh kiện thực tế (4 bộ phận & 2 ốc)\n"
    md_content += f"- **Tên sản phẩm**: {analysis.get('product_name', 'Giá đỡ điện thoại xe máy kèm mũ bảo hiểm mini')}\n"
    md_content += "\n### Các bộ phận chi tiết:\n"
    for comp in analysis.get("components", []):
        md_content += f"- {comp}\n"
    md_content += "\n### Quy trình lắp ráp chi tiết:\n"
    for idx, step in enumerate(analysis.get("assembly_steps", [])):
        md_content += f"{idx + 1}. {step}\n"
    md_content += "\n---\n\n"
    
    md_content += f"## 2. Kịch bản Storyboard Video AI (3D/Animation)\n"
    md_content += f"> **Ý tưởng chủ đạo**: {concept}\n\n"
    md_content += f"- **Thời lượng**: {duration} giây\n"
    md_content += f"- **Số phân cảnh**: {scenes_count} cảnh (Mỗi cảnh 4 giây)\n\n"
    
    md_content += "### Hook đề xuất\n"
    for h in hooks:
        md_content += f"- *\"{h}\"*\n"
    md_content += "\n"
    md_content += "### CTA đề xuất\n"
    for c in ctas:
        md_content += f"- *\"{c}\"*\n"
    md_content += "\n"
    
    md_content += "## Phân cảnh chi tiết\n\n"
    
    scenes = data.get("scenes", [])
    for s in scenes:
        num = s.get("scene_number", 1)
        trange = s.get("time_range", "0-4s")
        purpose = s.get("scene_purpose", "")
        
        md_content += f"### Phân cảnh {num} ({trange}) - [Mục đích: {purpose}]\n"
        md_content += f"- **Hình ảnh hiển thị (Visual)**: {s.get('visual_description', '')}\n"
        md_content += f"- **Thao tác hành động**: {s.get('action_description', '')}\n"
        md_content += f"- **Góc máy & Chuyển động**: {s.get('camera_angle', '')} | {s.get('camera_movement', '')}\n"
        md_content += f"- **Ánh sáng & Bối cảnh**: {s.get('lighting', '')} | {s.get('background', '')}\n"
        md_content += f"- **Điểm nhấn sản phẩm (Product Focus)**: {s.get('product_focus', '')}\n"
        md_content += f"- **Lời đọc thuyết minh (Voiceover)**: **{s.get('voiceover_line', '')}**\n"
        md_content += f"- **Chữ trên màn hình (Text)**: *\"{s.get('on_screen_text', '')}\"*\n\n"
        
        md_content += f"> **Prompt tạo ảnh (Image Prompt - EN)**:\n"
        md_content += f"> ```\n{s.get('image_prompt_en', '')}\n```\n\n"
        
        md_content += f"> **Prompt tạo video (Video Prompt - EN)**:\n"
        md_content += f"> ```\n{s.get('video_prompt_en', '')}\n```\n\n"
        
        md_content += f"> **Negative Prompt**:\n"
        md_content += f"> ```\n{s.get('negative_prompt', '')}\n```\n\n"
        md_content += "---\n\n"
        
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    # Save prompts file
    prompts_path = os.path.join(output_dir, 'ai_prompts.txt')
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write("=== TẬP HỢP PROMPT PHỤC VỤ VỊ TRÍ TẠO ẢNH / VIDEO AI (CẬP NHẬT THEO ĐÚNG LINH KIỆN HÌNH ẢNH) ===\n\n")
        f.write("Bối cảnh: Trên bàn làm việc màu trắng, xung quanh trang trí các phụ kiện màu hồng thỏ dễ thương.\n")
        f.write("Thao tác: Sử dụng đôi bàn tay thon thả của nữ giới.\n")
        f.write("Linh kiện: 4 phần chính (thân kẹp đen, mũ bảo hiểm mini đen kính trắng vẽ điện tâm đồ, ngàm nhựa vuông trắng, cần nối đen cong có vân dọc) và 2 con ốc (1 đen, 1 trắng).\n\n")
        for s in scenes:
            num = s.get("scene_number", 1)
            f.write(f"--- CẢNH {num} ({s.get('time_range', '')}) ---\n")
            f.write(f"[IMAGE PROMPT - EN]:\n{s.get('image_prompt_en', '')}\n\n")
            f.write(f"[VIDEO PROMPT - EN]:\n{s.get('video_prompt_en', '')}\n\n")
            f.write(f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n")
            f.write("\n")
            
    print("Prompts successfully rewritten!")

if __name__ == "__main__":
    json_path = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\storyboard_analysis.json"
    output_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may"
    rewrite_storyboard_prompts(json_path, output_dir)
