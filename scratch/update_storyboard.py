import os
import json

def update_storyboard(json_path, output_dir):
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 1. Update concept summary
    data["concept_summary"] = (
        "Video AI động, tập trung vào sản phẩm, mô phỏng quá trình lắp ghép dễ dàng và giới thiệu các tính năng "
        "độc đáo (chống nắng, chống mưa, chống rung) của giá đỡ điện thoại xe máy có mũ che nắng. Sản phẩm được "
        "lắp ráp trên một mặt bàn làm việc màu trắng, xung quanh trang trí các phụ kiện dễ thương màu hồng phấn "
        "(như hộp bút thỏ trắng, túi đựng mỹ phẩm Melody màu hồng, chuột máy tính màu hồng, hoa tươi cắm bình xanh). "
        "Các thao tác lắp ráp được thực hiện bởi đôi bàn tay nữ giới thon thả, tạo cảm giác thân thiện, tỉ mỉ."
    )

    # 2. Update scenes
    for scene in data.get("scenes", []):
        num = scene.get("scene_number")
        
        # Modify background description
        if num in [1, 2, 3]:
            scene["background"] = (
                "Mặt bàn làm việc màu trắng sạch sẽ, trang trí các phụ kiện màu hồng dễ thương: "
                "bên trái có bình hoa nhỏ màu xanh pastel cắm hoa ly hồng phấn và hộp cắm bút thỏ thỏ trắng tai hồng; "
                "bên phải có túi đựng mỹ phẩm trong suốt viền hồng hình My Melody và chuột không dây màu hồng nhạt."
            )
            scene["lighting"] = "Ánh sáng tự nhiên dịu nhẹ, tươi sáng, tạo không khí ấm áp, dễ chịu."

        # Update descriptions and prompts for specific scenes
        if num == 1:
            scene["visual_description"] = (
                "Các bộ phận tháo rời của giá đỡ điện thoại được xếp gọn gàng trên mặt bàn làm việc màu trắng. "
                "Xung quanh là bình hoa ly màu hồng, hộp bút thỏ trắng dễ thương, túi đựng mỹ phẩm My Melody màu hồng "
                "và chuột máy tính màu hồng phấn."
            )
            scene["image_prompt_en"] = (
                "Overhead flat lay shot of disassembled black motorcycle phone holder components (main holder body, "
                "mini helmet sunshade, mounting arm, connectors, screws) neatly arranged on a clean white desk surface. "
                "In the background, cute pink office accessories are visible: a small blue vase with pink lilies, "
                "a white bunny-shaped pen holder, a pink My Melody makeup pouch, and a cute pink computer mouse. "
                "Bright, natural, aesthetic soft morning lighting, high-end lifestyle product photography, 8k resolution, cinematic."
            )
            scene["video_prompt_en"] = (
                "Dynamic flat lay video showing disassembled components of a black motorcycle phone holder (sunshade, "
                "extension arm, bracket) neatly arranged on a clean white desk. Next to them are cute pink desk accessories: "
                "a bunny pen holder, pink flowers in a pastel blue vase, a pink mouse, and a pink pouch. The camera slowly "
                "pans and rotates overhead, capturing the clean, aesthetic layout. Soft bright natural lighting, lifestyle vlog style, 4K."
            )

        elif num == 2:
            scene["visual_description"] = (
                "Cận cảnh đôi bàn tay nữ giới thon thả lắp ngàm gắn mũ màu trắng vào mặt sau thân đỡ điện thoại, "
                "sau đó ấn khớp gắn mũ che nắng màu đen vào vị trí trên mặt bàn làm việc màu trắng, xung quanh có các phụ kiện màu hồng."
            )
            scene["action_description"] = (
                "Đôi bàn tay nữ giới thao tác nhanh nhẹn và khéo léo: lắp ngàm trắng, vặn núm đen và gắn mũ che nắng vào chốt."
            )
            scene["image_prompt_en"] = (
                "Close-up shot of delicate female hands assembling a black motorcycle phone holder on a clean white desk. "
                "She is attaching a white plastic bracket to the back of the holder and securing it with a black screw knob, "
                "then snapping a mini black helmet sunshade onto it. In the soft-focused background, cute pink desk accessories "
                "(bunny holder, pink mouse) are visible. Aesthetic soft lighting, clean and pastel atmosphere, detailed skin texture, 8k."
            )
            scene["video_prompt_en"] = (
                "Close-up video of delicate female hands assembling a motorcycle phone holder. She attaches a white bracket "
                "to the holder, twists a black knob, and snaps a mini black helmet-shaped sunshade onto it. The camera slowly "
                "zooms in on her precise hand movements. The background features a white desk decorated with cute pink office "
                "accessories. Aesthetic pastel vibe, soft bright lighting, sharp focus, 4K."
            )

        elif num == 3:
            scene["visual_description"] = (
                "Cận cảnh đôi bàn tay nữ giới lắp ráp khớp nối chữ L màu trắng và cần nối tay đỡ màu đen vào mặt sau thân đỡ, "
                "siết chặt bằng đai ốc lục giác màu trắng trên nền bàn làm việc màu trắng trang nhã."
            )
            scene["action_description"] = (
                "Bàn tay nữ tháo lắp khớp nối, cần đỡ và vặn đai ốc lục giác trắng một cách dễ dàng."
            )
            scene["image_prompt_en"] = (
                "Close-up shot of elegant female hands installing the mounting arm of a motorcycle phone holder. "
                "She connects a white L-shaped adapter to the back, attaches a black extension arm, and secures it by "
                "screwing a white hexagonal cap. The scene is set on a white desk with cute pink accessories in the blurred background. "
                "Soft bright natural lighting, shallow depth of field, high-end commercial aesthetic, clean and cozy, 8k."
            )
            scene["video_prompt_en"] = (
                "Close-up video of elegant female hands connecting the mounting arm to the phone holder. She attaches "
                "the white L-shaped connector, slots in the black extension arm, and tightly screws the white hexagonal cap. "
                "Camera tracks the mechanical connection details smoothly. The background is a clean white desk with pastel pink decorations. "
                "Fast-paced, satisfying assembly clicks, soft natural light, 4K."
            )

        elif num == 4:
            scene["visual_description"] = (
                "Giá đỡ điện thoại hoàn chỉnh (có mũ che nắng) được gắn chắc chắn lên ghi đông xe máy. Đôi bàn tay nữ giới đặt "
                "điện thoại vào kẹp và kéo dây silicon bảo hộ màu đen chằng quanh 4 góc."
            )
            scene["action_description"] = (
                "Bàn tay nữ kẹp điện thoại và gắn dây đai silicon bảo vệ chắc chắn."
            )
            scene["image_prompt_en"] = (
                "Medium close-up shot of delicate female hands securing a modern smartphone inside a motorcycle phone holder "
                "with a mini helmet sunshade, already mounted on a motorcycle handlebar. She is stretching a black rubber "
                "silicone strap over the four corners of the phone. Urban street background, soft daytime lighting, "
                "professional look, sharp focus on the phone and hands."
            )
            scene["video_prompt_en"] = (
                "Medium shot video of delicate female hands placing a smartphone into the motorcycle phone holder with "
                "the mini helmet sunshade, then stretching a black rubber strap over the corners to secure it. The camera "
                "pans slightly, showing the mount on a clean, modern motorcycle. Bright daylight, real-world demonstration, 4K."
            )

        elif num == 6:
            scene["action_description"] = (
                "Sản phẩm xoay tròn 3D trên nền bàn làm việc màu trắng đầy phụ kiện hồng dễ thương. "
                "Đôi bàn tay nữ xuất hiện tinh tế ở cuối cảnh chỉ vào nút Mua Ngay."
            )
            scene["image_prompt_en"] = (
                "Studio shot of a fully assembled motorcycle phone holder with mini helmet sunshade rotating on a white reflective desk. "
                "In the background, cute pink desk decor is visible. A clean, manicured female hand points gently towards an overlay "
                "text: 'Mua Ngay!'. Bright commercial lighting, premium aesthetic, pastel tones, 8k."
            )
            scene["video_prompt_en"] = (
                "Dynamic 3D product animation of the motorcycle phone holder rotating on a white desk with pink desk accessories "
                "in the background. Features like 'Chống Nắng', 'Chống Mưa', 'Chống Rung' slide in as cute pink-themed text overlays. "
                "A manicured female hand appears at the end, pointing to a 'Mua Ngay!' call-to-action button. Soft cinematic lighting, "
                "aesthetic transitions, 4K."
            )

    # 3. Save updated outputs
    # Let's import save_storyboard_outputs style formatting
    # We will write the updated markdown, txt, and json files.
    # Write json
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
    
    md_content = f"# Báo cáo Phân tích & Storyboard Video AI: Lắp Ghép Giá Đỡ Điện Thoại Có Mũ Che Nắng\n\n"
    md_content += f"## 1. Phân tích sản phẩm tự quay\n"
    md_content += f"- **Tên sản phẩm xác định**: {analysis.get('product_name', 'Giá đỡ điện thoại xe máy kèm mũ che nắng')}\n"
    md_content += "\n### Các bộ phận chi tiết:\n"
    for comp in analysis.get("components", []):
        md_content += f"- {comp}\n"
    md_content += "\n### Các bước lắp ghép ghi nhận trong video:\n"
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
        
    # Write txt prompts
    prompts_path = os.path.join(output_dir, 'ai_prompts.txt')
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write("=== TẬP HỢP PROMPT PHỤC VỤ VỊ TRÍ TẠO ẢNH / VIDEO AI ===\n\n")
        f.write("Bối cảnh: Trên bàn làm việc màu trắng, xung quanh trang trí các phụ kiện màu hồng dễ thương.\n")
        f.write("Thao tác: Sử dụng đôi bàn tay thon thả của nữ giới.\n\n")
        for s in scenes:
            num = s.get("scene_number", 1)
            f.write(f"--- CẢNH {num} ({s.get('time_range', '')}) ---\n")
            f.write(f"[IMAGE PROMPT - EN]:\n{s.get('image_prompt_en', '')}\n\n")
            f.write(f"[VIDEO PROMPT - EN]:\n{s.get('video_prompt_en', '')}\n\n")
            f.write(f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n")
            f.write("\n")

    print("Successfully updated storyboard files!")

if __name__ == "__main__":
    json_path = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\storyboard_analysis.json"
    output_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may"
    update_storyboard(json_path, output_dir)
