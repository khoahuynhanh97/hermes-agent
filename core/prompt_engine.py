import os
import sys
import json
import re

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def generate_prompts_from_storyboard(storyboard_data, product_name="", output_dir=""):
    """
    Từ storyboard_data (dict), tạo ra 3 loại output:
    1. File .md tổng hợp để review
    2. File .txt riêng lẻ theo từng scene để copy vào AI tools
    3. File .json để app đọc lại, sửa, quản lý version

    Trả về dict:
    {
        "md_path": "...",
        "txt_paths": ["P01_prompt.txt", ...],
        "json_path": "...",
        "prompts_count": N
    }
    """
    if not output_dir:
        return {"error": "Cần chỉ định output_dir"}

    prompts_dir = os.path.join(output_dir, "prompts")
    os.makedirs(prompts_dir, exist_ok=True)

    scenes = storyboard_data.get("scenes", [])
    title = storyboard_data.get("title", "Storyboard")
    concept = storyboard_data.get("concept_summary", "")
    hook_options = storyboard_data.get("hook_options", [])
    cta_options = storyboard_data.get("cta_options", [])
    video_duration = storyboard_data.get("video_duration", 0)
    scene_count = storyboard_data.get("scene_count", len(scenes))

    # --- 1. Build .json output ---
    prompts_json = {
        "product_name": product_name,
        "storyboard_title": title,
        "concept_summary": concept,
        "video_duration": video_duration,
        "scene_count": scene_count,
        "hook_options": hook_options,
        "cta_options": cta_options,
        "prompts": []
    }

    for scene in scenes:
        sn = scene.get("scene_number", 0)
        pad = str(sn).zfill(2)
        prompt_entry = {
            "prompt_id": f"P{pad}",
            "scene_number": sn,
            "time_range": scene.get("time_range", ""),
            "scene_purpose": scene.get("scene_purpose", ""),
            "video_prompt_vi": scene.get("video_prompt_vi", ""),
            "video_prompt_en": scene.get("video_prompt_en", ""),
            "image_prompt_vi": scene.get("image_prompt_vi", ""),
            "image_prompt_en": scene.get("image_prompt_en", ""),
            "negative_prompt": scene.get("negative_prompt", "no watermark, no logo, no distorted hands, no deformed product, no text artifacts, extra fingers, bad anatomy"),
            "camera_angle": scene.get("camera_angle", ""),
            "camera_movement": scene.get("camera_movement", ""),
            "lighting": scene.get("lighting", ""),
            "background": scene.get("background", ""),
            "action_description": scene.get("action_description", ""),
            "voiceover_line": scene.get("voiceover_line", ""),
            "on_screen_text": scene.get("on_screen_text", ""),
            "capcut_notes": scene.get("capcut_notes", ""),
        }
        prompts_json["prompts"].append(prompt_entry)

    json_path = os.path.join(prompts_dir, "prompts.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(prompts_json, f, ensure_ascii=False, indent=4)

    # --- 2. Build individual .txt files per scene ---
    txt_paths = []
    for p in prompts_json["prompts"]:
        pid = p["prompt_id"]
        purpose = p["scene_purpose"]
        time_range = p["time_range"]
        vp_en = p["video_prompt_en"]
        vp_vi = p["video_prompt_vi"]
        neg = p["negative_prompt"]
        cam = p["camera_angle"]
        light = p["lighting"]
        action = p["action_description"]
        bg = p["background"]

        content = f"""# {pid} — {purpose}
# Time: {time_range} | Format: 9:16 vertical

== VIDEO PROMPT (English — Copy to Veo / Kling / Runway / Seedance) ==

{vp_en}

Camera: {cam}
Lighting: {light}
Action: {action}
Background: {bg}

Negative Prompt: {neg}

== VIDEO PROMPT (Vietnamese) ==
{vp_vi}

"""
        txt_file = os.path.join(prompts_dir, f"{pid}_prompt.txt")
        with open(txt_file, "w", encoding="utf-8") as f:
            f.write(content)
        txt_paths.append(txt_file)

    # --- 3. Build .md summary file ---
    md_lines = [
        f"# 🎬 Prompts Pack: {title}\n",
        f"> **Sản phẩm:** {product_name}  \n",
        f"> **Video Duration:** {video_duration}s | **Scenes:** {scene_count}\n\n",
        f"## 💡 Concept\n{concept}\n\n",
    ]

    if hook_options:
        md_lines.append("## 🎣 Hook Options\n")
        for i, h in enumerate(hook_options, 1):
            md_lines.append(f"{i}. {h}\n")
        md_lines.append("\n")

    if cta_options:
        md_lines.append("## 📢 CTA Options\n")
        for i, c in enumerate(cta_options, 1):
            md_lines.append(f"{i}. {c}\n")
        md_lines.append("\n")

    md_lines.append("---\n\n")

    for p in prompts_json["prompts"]:
        pid = p["prompt_id"]
        sn = p["scene_number"]
        purpose = p["scene_purpose"]
        time_range = p["time_range"]

        md_lines.append(f"## {pid} — Scene {sn}: {purpose}\n")
        md_lines.append(f"**Time:** {time_range}  \n")
        md_lines.append(f"**Camera:** {p['camera_angle']}  \n")
        md_lines.append(f"**Light:** {p['lighting']}  \n")
        md_lines.append(f"**Action:** {p['action_description']}  \n\n")

        if p["video_prompt_en"]:
            md_lines.append("**🎬 Video Prompt (EN):**\n")
            md_lines.append(f"```\n{p['video_prompt_en']}\n```\n\n")

        if p["video_prompt_vi"]:
            md_lines.append("**📝 Video Prompt (VI):**\n")
            md_lines.append(f"> {p['video_prompt_vi']}\n\n")

        if p["negative_prompt"]:
            md_lines.append(f"**❌ Negative:** `{p['negative_prompt']}`\n\n")

        if p["voiceover_line"]:
            md_lines.append(f"**🎙️ Voiceover:** {p['voiceover_line']}\n\n")

        if p["on_screen_text"]:
            md_lines.append(f"**📺 On-screen text:** {p['on_screen_text']}\n\n")

        if p["capcut_notes"]:
            md_lines.append(f"**✂️ CapCut notes:** {p['capcut_notes']}\n\n")

        md_lines.append("---\n\n")

    # Full prompt sets at the end
    full_en_set = storyboard_data.get("full_video_prompt_set_en", "")
    full_vi_set = storyboard_data.get("full_video_prompt_set_vi", "")

    if full_en_set:
        md_lines.append("## 📋 Full Video Prompt Set (English)\n")
        md_lines.append(f"```\n{full_en_set}\n```\n\n")

    if full_vi_set:
        md_lines.append("## 📋 Full Video Prompt Set (Vietnamese)\n")
        md_lines.append(f"```\n{full_vi_set}\n```\n\n")

    md_path = os.path.join(prompts_dir, "prompts_pack.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.writelines(md_lines)

    return {
        "md_path": md_path,
        "txt_paths": txt_paths,
        "json_path": json_path,
        "prompts_count": len(txt_paths),
        "prompts_dir": prompts_dir,
    }


def load_prompts(prompts_dir):
    """Tải prompts.json từ thư mục prompts trong project."""
    path = os.path.join(prompts_dir, "prompts", "prompts.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
