import os
import json

def save_storyboard_outputs(storyboard_data, output_dir):
    """
    Saves the structured storyboard data into output_dir.
    Files written: storyboard.json, storyboard.md, image_prompts.txt, video_prompts.txt.
    """
    os.makedirs(output_dir, exist_ok=True)
    
    # 1. Save JSON
    json_path = os.path.join(output_dir, 'storyboard.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(storyboard_data, f, ensure_ascii=False, indent=4)
        
    # 2. Format and Save Markdown
    md_path = os.path.join(output_dir, 'storyboard.md')
    
    title = storyboard_data.get("title", "Storyboard AI")
    concept = storyboard_data.get("concept_summary", "")
    duration = storyboard_data.get("video_duration", 24)
    scenes_count = storyboard_data.get("scene_count", 6)
    
    hooks = storyboard_data.get("hook_options", [])
    ctas = storyboard_data.get("cta_options", [])
    
    md_content = f"# Storyboard AI: {title}\n\n"
    md_content += f"## Tổng quan ý tưởng\n{concept}\n"
    md_content += f"- **Thời lượng**: {duration} giây\n"
    md_content += f"- **Số phân cảnh**: {scenes_count} cảnh\n\n"
    
    md_content += "## Hook đề xuất\n"
    for idx, h in enumerate(hooks):
        md_content += f"{idx + 1}. {h}\n"
    md_content += "\n"
    
    md_content += "## CTA đề xuất\n"
    for idx, c in enumerate(ctas):
        md_content += f"{idx + 1}. {c}\n"
    md_content += "\n"
    
    md_content += "## Phân cảnh chi tiết\n\n"
    
    scenes = storyboard_data.get("scenes", [])
    for s in scenes:
        num = s.get("scene_number", 1)
        trange = s.get("time_range", "0s")
        purpose = s.get("scene_purpose", "")
        
        md_content += f"### Scene {num} | {trange} | {purpose}\n\n"
        md_content += f"* **Mô tả hình ảnh**: {s.get('visual_description', '')}\n"
        md_content += f"* **Hành động**: {s.get('action_description', '')}\n"
        md_content += f"* **Góc máy**: {s.get('camera_angle', '')}\n"
        md_content += f"* **Chuyển động camera**: {s.get('camera_movement', '')}\n"
        md_content += f"* **Ánh sáng**: {s.get('lighting', '')}\n"
        md_content += f"* **Background**: {s.get('background', '')}\n"
        md_content += f"* **Tiêu điểm sản phẩm**: {s.get('product_focus', '')}\n"
        md_content += f"* **Lời đọc (Voice)**: {s.get('voiceover_line', '')}\n"
        md_content += f"* **Chữ trên màn hình (Text)**: {s.get('on_screen_text', '')}\n"
        md_content += f"* **Prompt ảnh VI**: {s.get('image_prompt_vi', '')}\n"
        md_content += f"* **Prompt ảnh EN**: {s.get('image_prompt_en', '')}\n"
        md_content += f"* **Prompt video VI**: {s.get('video_prompt_vi', '')}\n"
        md_content += f"* **Prompt video EN**: {s.get('video_prompt_en', '')}\n"
        md_content += f"* **Negative prompt**: {s.get('negative_prompt', '')}\n\n"
        
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)
        
    # 3. Format and Save Image Prompts List
    img_path = os.path.join(output_dir, 'image_prompts.txt')
    img_content = "=== BỘ PROMPT HÌNH ẢNH (IMAGE PROMPTS) ===\n\n"
    for s in scenes:
        num = s.get("scene_number", 1)
        img_content += f"=== CẢNH {num} ===\n"
        img_content += f"[TIẾNG ANH - KHUYÊN DÙNG]:\n{s.get('image_prompt_en', '')}\n\n"
        img_content += f"[TIẾNG VIỆT]:\n{s.get('image_prompt_vi', '')}\n"
        img_content += f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n"
        
    with open(img_path, 'w', encoding='utf-8') as f:
        f.write(img_content)
        
    # 4. Format and Save Video Prompts List
    vid_path = os.path.join(output_dir, 'video_prompts.txt')
    vid_content = "=== BỘ PROMPT VIDEO (VIDEO PROMPTS) ===\n\n"
    for s in scenes:
        num = s.get("scene_number", 1)
        vid_content += f"=== CẢNH {num} ===\n"
        vid_content += f"[TIẾNG ANH - KHUYÊN DÙNG]:\n{s.get('video_prompt_en', '')}\n\n"
        vid_content += f"[TIẾNG VIỆT]:\n{s.get('video_prompt_vi', '')}\n"
        vid_content += f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n"
        
    with open(vid_path, 'w', encoding='utf-8') as f:
        f.write(vid_content)
        
    return {
        "json_path": json_path,
        "markdown_path": md_path,
        "image_prompts_path": img_path,
        "video_prompts_path": vid_path
    }
