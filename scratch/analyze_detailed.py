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

def analyze_detailed_assembly():
    api_key = get_gemini_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found in configuration.")
        return None
        
    model = get_gemini_model()
    
    frames_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\extracted_frames\VID_20260703_220124_detailed"
    selected_frames = ["frame_0000_t0.00.jpg", "frame_0030_t1.00.jpg", "frame_0060_t2.01.jpg", "frame_0090_t3.01.jpg", "frame_0120_t4.01.jpg"]
    
    parts_to_send = []
    
    print("Preparing key detailed frames...")
    for frame_name in selected_frames:
        frame_path = os.path.join(frames_dir, frame_name)
        if os.path.exists(frame_path):
            base64_data = resize_and_encode_image(frame_path)
            if base64_data:
                parts_to_send.append({
                    "text": f"Detailed Frame: {frame_name}"
                })
                parts_to_send.append({
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": base64_data
                    }
                })

    prompt_text = """
Bạn là một chuyên gia phân tích video sản phẩm và đạo diễn hình ảnh quảng cáo.
Dưới đây là một số hình ảnh chi tiết được trích xuất từ video "VID_20260703_220124.mp4" ghi lại các bộ phận thực tế của sản phẩm.

Người dùng xác nhận sản phẩm chỉ bao gồm chính xác 4 bộ phận chính và 2 con ốc:
1. Thân đỡ điện thoại chính màu đen (Main black phone cradle/clamp with left and right gripping claws).
2. Mũ bảo hiểm mini màu đen (Mini helmet with a white decorative band, white goggles with heartbeat line pattern).
3. Ngàm gắn/Đế nhựa màu trắng hình vuông (White square plastic mounting adapter with a large round socket in the center and small screw holes on the sides).
4. Cần nối/Tay đỡ màu đen (Black plastic curved extension arm/bracket with screw holes on both ends).
5. Hai con ốc đi kèm: Một con ốc màu đen và một con ốc màu trắng.

Nhiệm vụ của bạn:
1. Dựa trên các hình ảnh chi tiết này, hãy xác định chính xác cách lắp ghép của 4 bộ phận này và vai trò của 2 con ốc (ốc đen và ốc trắng).
   - Ví dụ: Đế nhựa màu trắng được gắn vào mặt sau thân đỡ điện thoại bằng ốc nào?
   - Mũ bảo hiểm mini được lắp vào đâu và cố định thế nào?
   - Cần nối màu đen được kết nối như thế nào?
2. Tạo lại kịch bản phân cảnh (Storyboard AI) gồm 6 cảnh, thời lượng 24 giây (mỗi cảnh 4 giây), phong cách TikTok hiện đại để giới thiệu quy trình lắp ghép chính xác này.
   - Bối cảnh: Trên bàn làm việc màu trắng, xung quanh có trang trí phụ kiện màu hồng pastel dễ thương (bình hoa ly hồng, hộp bút thỏ trắng, túi My Melody hồng, chuột không dây màu hồng nhạt) giống ảnh tham khảo.
   - Thao tác: Được thực hiện bởi đôi bàn tay nữ giới thon thả, khéo léo (delicate female hands).
   - Cung cấp prompt sinh ảnh (Image Prompt - EN) và prompt sinh video (Video Prompt - EN) cho từng phân cảnh, mô tả chính xác 4 bộ phận và 2 con ốc này. Prompt phải cực kỳ trực quan, chi tiết kỹ thuật chuyên nghiệp, không dùng từ mơ hồ, định dạng chuẩn 9:16 aspect ratio cho TikTok.

Hãy trả về kết quả dưới định dạng JSON với cấu trúc chính xác sau đây (không bọc trong thẻ markdown, trả về JSON thuần):
{
  "product_analysis": {
    "product_name": "Giá đỡ điện thoại xe máy có mũ bảo hiểm mini",
    "components": [
      "Thân đỡ điện thoại màu đen",
      "Mũ bảo hiểm mini màu đen có kính trắng",
      "Đế gắn nhựa màu trắng hình vuông",
      "Cần nối màu đen dạng cong",
      "Con ốc màu đen",
      "Con ốc màu trắng"
    ],
    "assembly_steps": [
      "Mô tả chính xác bước 1 lắp chi tiết nào...",
      "Mô tả chính xác bước 2...",
      "Mô tả chính xác bước 3...",
      "Mô tả chính xác bước 4..."
    ]
  },
  "title": "Storyboard quảng cáo lắp ghép giá đỡ điện thoại có mũ bảo hiểm mini",
  "concept_summary": "Tóm tắt ý tưởng video AI trên bàn làm việc trắng và phụ kiện hồng...",
  "video_duration": 24,
  "scene_count": 6,
  "hook_options": ["Câu hook 1", "Câu hook 2"],
  "cta_options": ["Câu CTA 1", "Câu CTA 2"],
  "scenes": [
    {
      "scene_number": 1,
      "time_range": "0-4s",
      "scene_purpose": "Mục đích cảnh",
      "visual_description": "Mô tả chi tiết hình ảnh video xuất hiện...",
      "action_description": "Thao tác của tay...",
      "camera_angle": "Góc máy...",
      "camera_movement": "Chuyển động camera...",
      "lighting": "Ánh sáng...",
      "background": "Bàn làm việc màu trắng kèm phụ kiện hồng...",
      "product_focus": "Sản phẩm...",
      "voiceover_line": "Lời bình thuyết minh...",
      "on_screen_text": "Chữ trên màn hình...",
      "image_prompt_en": "Prompt sinh ảnh tiếng Anh chi tiết theo cấu trúc chuẩn...",
      "video_prompt_en": "Prompt sinh video tiếng Anh chi tiết...",
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
    
    print("Calling Gemini API...")
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            print(f"Error HTTP {response.status_code}: {response.text}")
            return None
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        import re
        if text_content.startswith("```"):
            text_content = re.sub(r'^```(json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
            
        storyboard_data = json.loads(text_content)
        return storyboard_data
    except Exception as e:
        print(f"Exception: {e}")
        return None

def save_outputs(storyboard_data, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    
    # Save JSON
    json_path = os.path.join(output_dir, 'storyboard_analysis.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(storyboard_data, f, ensure_ascii=False, indent=4)
        
    # Save Markdown
    md_path = os.path.join(output_dir, 'storyboard_analysis.md')
    
    analysis = storyboard_data.get("product_analysis", {})
    title = storyboard_data.get("title", "Storyboard AI")
    concept = storyboard_data.get("concept_summary", "")
    duration = storyboard_data.get("video_duration", 24)
    scenes_count = storyboard_data.get("scene_count", 6)
    hooks = storyboard_data.get("hook_options", [])
    ctas = storyboard_data.get("cta_options", [])
    
    md_content = f"# Báo cáo Phân tích & Storyboard Video AI: Lắp Ghép Giá Đỡ Điện Thoại Có Mũ Bảo Hiểm Mini\n\n"
    md_content += f"## 1. Phân tích linh kiện thực tế (4 bộ phận & 2 ốc)\n"
    md_content += f"- **Tên sản phẩm xác định**: {analysis.get('product_name', 'Giá đỡ điện thoại xe máy kèm mũ bảo hiểm mini')}\n"
    md_content += "\n### Các bộ phận chi tiết:\n"
    for comp in analysis.get("components", []):
        md_content += f"- {comp}\n"
    
    md_content += "\n### Quy trình lắp ráp chính xác:\n"
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
        f.write("Bối cảnh: Trên bàn làm việc màu trắng, xung quanh trang trí các phụ kiện màu hồng thỏ dễ thương.\n")
        f.write("Thao tác: Sử dụng đôi bàn tay thon thả của nữ giới.\n")
        f.write("Linh kiện: 4 phần chính (thân kẹp đen, mũ bảo hiểm mini đen kính trắng, ngàm nhựa vuông trắng, cần nối đen cong) và 2 con ốc (1 đen, 1 trắng).\n\n")
        for s in scenes:
            num = s.get("scene_number", 1)
            f.write(f"--- CẢNH {num} ({s.get('time_range', '')}) ---\n")
            f.write(f"[IMAGE PROMPT - EN]:\n{s.get('image_prompt_en', '')}\n\n")
            f.write(f"[VIDEO PROMPT - EN]:\n{s.get('video_prompt_en', '')}\n\n")
            f.write(f"[NEGATIVE PROMPT]:\n{s.get('negative_prompt', '')}\n\n")
            f.write("\n")
            
    print(f"Saved outputs to: {output_dir}")

if __name__ == "__main__":
    storyboard = analyze_detailed_assembly()
    if storyboard:
        save_outputs(storyboard, r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may")
        print("Detailed analysis and storyboard generation complete!")
    else:
        print("Failed to generate storyboard.")
