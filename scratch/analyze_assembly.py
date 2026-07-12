import os
import sys
import json
import base64
import cv2
import requests

# Load config from env
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

def get_gemini_api_key():
    return getattr(config, "GEMINI_API_KEY", "")

def get_gemini_model():
    return getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")

def resize_and_encode_image(image_path, max_dim=512):
    """Resizes image for API upload and returns base64 string."""
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None
        h, w = img.shape[:2]
        if max(h, w) > max_dim:
            scale = max_dim / max(h, w)
            img = cv2.resize(img, (int(w * scale), int(h * scale)))
            
        _, buffer = cv2.imencode('.jpg', img, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        print(f"Error encoding image {image_path}: {e}")
        return None

def analyze_videos_with_gemini(video_dir, metadata_path):
    api_key = get_gemini_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found in configuration.")
        return None
        
    model = get_gemini_model()
    
    with open(metadata_path, 'r', encoding='utf-8') as f:
        metadata = json.load(f)
        
    parts_to_send = []
    
    # Select key frames from each video to give Gemini a complete picture
    print("Selecting and preparing key frames for AI analysis...")
    for video_name, info in metadata.items():
        frames = info.get("extracted_frames", [])
        if not frames:
            continue
            
        # Strategy to select key frames
        # For short videos (<10s): 1 key frame (middle)
        # For medium videos: 2 key frames (near start and near end)
        # For long videos: 3-4 key frames
        num_frames = len(frames)
        if num_frames == 3:
            selected_indices = [1]  # middle frame
        elif num_frames == 6:
            selected_indices = [1, 4]  # second and fifth
        elif num_frames >= 10:
            selected_indices = [1, 4, 7, 9]  # spread out
        else:
            selected_indices = [0]
            
        print(f"Video {video_name}: selecting frame indices {selected_indices} out of {num_frames} extracted frames")
        
        for idx in selected_indices:
            if idx < len(frames):
                frame_info = frames[idx]
                local_path = frame_info["local_path"]
                base64_data = resize_and_encode_image(local_path)
                if base64_data:
                    parts_to_send.append({
                        "text": f"Video: {video_name}, Frame timestamp: {frame_info['timestamp_sec']}s"
                    })
                    parts_to_send.append({
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64_data
                        }
                    })

    if not parts_to_send:
        print("No frames successfully encoded.")
        return None

    # Add the text prompt at the beginning
    prompt_text = """
Bạn là một chuyên gia phân tích video sản phẩm và đạo diễn hình ảnh quảng cáo.
Dưới đây là một số hình ảnh được trích xuất từ các video tự quay ghi lại quá trình trên tay, giới thiệu chi tiết và lắp ghép một thiết bị: "Giá đỡ điện thoại xe máy có mũ che nắng (mini umbrella/sunshade)".

Hãy thực hiện phân tích các hình ảnh này và thực hiện các nhiệm vụ sau:
1. Xác định và liệt kê các thành phần/chi tiết của bộ giá đỡ điện thoại xe máy có mũ che nắng xuất hiện trong các ảnh (ví dụ: ngàm gắn ghi đông/chân gương, thân đỡ điện thoại, tấm che nắng hình mũ/ô bảo vệ, khớp xoay, ốc vít, v.v.).
2. Mô tả lại các bước lắp ghép sản phẩm dựa trên thứ tự các video và hình ảnh (từ lúc tháo hộp/các bộ phận rời rạc, lắp ghép ngàm, gắn mũ che nắng, đến khi lắp hoàn chỉnh lên xe máy và kẹp điện thoại vào).
3. Tạo ra một kịch bản phân cảnh (Storyboard AI) chi tiết gồm 6 cảnh để dựng một video AI lắp ghép 3D/Animation cực kỳ chuyên nghiệp và đẹp mắt dựa trên tư liệu thực tế này.
   - Video AI này mô phỏng quá trình lắp ghép và giới thiệu các tính năng độc đáo (chống nắng, chống mưa cho điện thoại, chống rung).
   - Thời lượng: 24 giây (6 cảnh, mỗi cảnh 4 giây).
   - Phong cách: TikTok Reels/Shorts hiện đại, nhịp điệu nhanh, bắt mắt, tập trung vào sản phẩm (Product-focused), ánh sáng studio chuyên nghiệp hoặc ngoại cảnh đường phố năng động.
   - Với mỗi phân cảnh, cung cấp:
     + Tên phân cảnh & mục đích.
     + Mô tả trực quan (Visual description).
     + Chuyển động và góc máy (Camera angle & movement).
     + Lời đọc thuyết minh tiếng Việt (Voiceover).
     + Chữ hiển thị trên màn hình (On-screen text).
     + Prompt tạo hình ảnh (Image Prompt - EN) chi tiết để sinh ảnh AI (như Midjourney, Flux, SD).
     + Prompt tạo video (Video Prompt - EN) chi tiết để sinh video AI (như Luma, Runway Gen-3, Sora).
     + Negative prompt để tránh lỗi.

Hãy trả về kết quả dưới định dạng JSON với cấu trúc chính xác sau đây (không bọc trong thẻ markdown, trả về JSON thuần):
{
  "product_analysis": {
    "product_name": "Tên sản phẩm",
    "components": ["Chi tiết 1", "Chi tiết 2", ...],
    "assembly_steps": ["Bước 1", "Bước 2", ...]
  },
  "title": "Storyboard quảng cáo lắp ghép giá đỡ điện thoại có mũ che nắng",
  "concept_summary": "Tóm tắt ý tưởng chủ đạo của video AI...",
  "video_duration": 24,
  "scene_count": 6,
  "hook_options": ["Câu hook giật tít 1", "Câu hook giật tít 2"],
  "cta_options": ["Câu kêu gọi hành động 1", "Câu kêu gọi hành động 2"],
  "scenes": [
    {
      "scene_number": 1,
      "time_range": "0-4s",
      "scene_purpose": "Mục đích cảnh",
      "visual_description": "Mô tả chi tiết hình ảnh video AI xuất hiện...",
      "action_description": "Thao tác/chuyển động của sản phẩm hoặc tay...",
      "camera_angle": "Góc máy...",
      "camera_movement": "Chuyển động camera...",
      "lighting": "Ánh sáng...",
      "background": "Bối cảnh...",
      "product_focus": "Điểm nhấn sản phẩm...",
      "voiceover_line": "Lời bình thuyết minh tiếng Việt...",
      "on_screen_text": "Chữ chạy trên màn hình...",
      "image_prompt_en": "Prompt sinh ảnh tiếng Anh chi tiết theo cấu trúc: [Camera Angle/Shot Type] + [Subject & Action] + [Environment/Background] + [Lighting/Mood] + [Aesthetic/Style] + [Technical parameters]",
      "video_prompt_en": "Prompt sinh video tiếng Anh chi tiết chứa các từ khóa chuyển động và góc quay chuyên nghiệp...",
      "negative_prompt": "Các từ khóa loại trừ lỗi..."
    }
  ]
}
"""

    parts_to_send.insert(0, {"text": prompt_text})
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": parts_to_send
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    print(f"Sending request to Gemini API ({model})... This might take a few moments.")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=120)
        if response.status_code != 200:
            print(f"Error Gemini API (HTTP {response.status_code}): {response.text}")
            return None
            
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Parse JSON
        import re
        if text_content.startswith("```"):
            text_content = re.sub(r'^```(json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
            
        storyboard_data = json.loads(text_content)
        return storyboard_data
    except Exception as e:
        print(f"Exception during Gemini call: {e}")
        # Try a backup parsing if text was returned but failed json.loads
        try:
            print("Raw response text preview:")
            print(text_content[:500])
        except:
            pass
        return None

def save_outputs(storyboard_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # Save raw JSON
    json_path = os.path.join(output_dir, 'storyboard_analysis.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(storyboard_data, f, ensure_ascii=False, indent=4)
        
    # Save human-readable markdown
    md_path = os.path.join(output_dir, 'storyboard_analysis.md')
    
    analysis = storyboard_data.get("product_analysis", {})
    title = storyboard_data.get("title", "Storyboard AI")
    concept = storyboard_data.get("concept_summary", "")
    duration = storyboard_data.get("video_duration", 24)
    scenes_count = storyboard_data.get("scene_count", 6)
    hooks = storyboard_data.get("hook_options", [])
    ctas = storyboard_data.get("cta_options", [])
    
    md_content = f"# Báo cáo Phân tích & Storyboard Video AI: Lắp Ghép Giá Đỡ Điện Thoại Có Mũ Che Nắng\n\n"
    
    # Product analysis section
    md_content += f"## 1. Phân tích sản phẩm tự quay\n"
    md_content += f"- **Tên sản phẩm xác định**: {analysis.get('product_name', 'Giá đỡ điện thoại xe máy kèm mũ che nắng')}\n"
    md_content += "\n### Các bộ phận chi tiết:\n"
    for comp in analysis.get("components", []):
        md_content += f"- {comp}\n"
    
    md_content += "\n### Các bước lắp ghép ghi nhận trong video:\n"
    for idx, step in enumerate(analysis.get("assembly_steps", [])):
        md_content += f"{idx + 1}. {step}\n"
    md_content += "\n---\n\n"
    
    # Storyboard section
    md_content += f"## 2. Kịch bản Storyboard Video AI (3D/Animation)\n"
    md_content += f"> **Ý tưởng chủ đạo**: {concept}\n\n"
    md_content += f"- **Thời lượng**: {duration} giây\n"
    md_content += f"- **Số phân cảnh**: {scenes_count} cảnh (Mỗi cảnh 4 giây)\n\n"
    
    md_content += "### Hook đề xuất (Mở đầu cuốn hút)\n"
    for h in hooks:
        md_content += f"- *\"{h}\"*\n"
    md_content += "\n"
    
    md_content += "### CTA đề xuất (Kêu gọi hành động)\n"
    for c in ctas:
        md_content += f"- *\"{c}\"*\n"
    md_content += "\n"
    
    md_content += "## Phân cảnh chi tiết\n\n"
    
    scenes = storyboard_data.get("scenes", [])
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
        f.write("=== TẬP HỢP PROMPT PHỤC VỤ VỊ TRÍ TẠO ẢNH / VIDEO AI ===\n\n")
        for s in scenes:
            num = s.get("scene_number", 1)
            f.write(f"--- CẢNH {num} ({s.get('time_range', '')}) ---\n")
            f.write(f"[IMAGE PROMPT - EN]:\n{s.get('image_prompt_en', '')}\n\n")
            f.write(f"[VIDEO PROMPT - EN]:\n{s.get('video_prompt_en', '')}\n\n")
            f.write(f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n")
            f.write("\n")
            
    print(f"Saved outputs to directory: {output_dir}")
    print(f"  - JSON: {json_path}")
    print(f"  - Markdown: {md_path}")
    print(f"  - Prompts: {prompts_path}")
    
    return json_path, md_path, prompts_path

if __name__ == "__main__":
    video_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may"
    metadata_path = os.path.join(video_dir, "extracted_frames", "metadata.json")
    output_dir = video_dir
    
    if not os.path.exists(metadata_path):
        print(f"Metadata file not found at {metadata_path}. Run extract_frames.py first.")
        sys.exit(1)
        
    storyboard = analyze_videos_with_gemini(video_dir, metadata_path)
    if storyboard:
        save_outputs(storyboard, output_dir)
        print("Analysis and storyboard generation complete!")
    else:
        print("Failed to generate storyboard.")
