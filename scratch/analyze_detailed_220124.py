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

def analyze_220124_assembly():
    api_key = get_gemini_api_key()
    if not api_key:
        print("Error: GEMINI_API_KEY not found in configuration.")
        return None
        
    model = get_gemini_model()
    
    frames_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\extracted_frames\VID_20260703_220124_detailed"
    # Select all 14 frames to get full details of this short assembly sequence
    selected_frames = sorted(os.listdir(frames_dir))
    
    parts_to_send = []
    
    print(f"Preparing all {len(selected_frames)} detailed frames for VID_20260703_220124...")
    for frame_name in selected_frames:
        frame_path = os.path.join(frames_dir, frame_name)
        if os.path.exists(frame_path) and frame_name.endswith('.jpg'):
            base64_data = resize_and_encode_image(frame_path)
            if base64_data:
                parts_to_send.append({
                    "text": f"Frame: {frame_name}"
                })
                parts_to_send.append({
                    "inlineData": {
                        "mimeType": "image/jpeg",
                        "data": base64_data
                    }
                })

    prompt_text = """
Bạn là một chuyên gia phân tích video sản phẩm và đạo diễn hình ảnh quảng cáo.
Dưới đây là chuỗi toàn bộ hình ảnh phân cảnh chi tiết được trích xuất từ video "VID_20260703_220124.mp4". 

Hãy thực hiện nhiệm vụ sau:
1. Phân tích chuỗi hình ảnh này để mô tả chính xác quy trình lắp ráp sản phẩm xảy ra trong video "VID_20260703_220124.mp4".
   - Bàn tay đang lắp chi tiết nào vào chi tiết nào?
   - Con ốc nào đang được vặn vào đâu?
   - Xác định xem đây là công đoạn nào của quá trình lắp ráp giá đỡ điện thoại.
2. Thiết kế lại kịch bản phân cảnh (Storyboard AI) gồm 6 cảnh, tổng thời lượng 24 giây (mỗi cảnh 4 giây), phong cách TikTok hiện đại để giới thiệu quy trình lắp ghép cụ thể này.
   - Bối cảnh: Trên bàn làm việc màu trắng, xung quanh có trang trí phụ kiện màu hồng pastel dễ thương (bình hoa ly hồng, hộp bút thỏ trắng, túi My Melody hồng, chuột không dây màu hồng nhạt) giống ảnh tham khảo.
   - Thao tác: Được thực hiện bởi đôi bàn tay nữ giới thon thả, khéo léo (delicate female hands).
   - Cung cấp prompt sinh ảnh (Image Prompt - EN) và prompt sinh video (Video Prompt - EN) cho từng phân cảnh, mô tả chính xác chuyển động và các bộ phận được lắp ghép. Prompt phải cực kỳ trực quan, chi tiết kỹ thuật chuyên nghiệp, không dùng từ mơ hồ, định dạng chuẩn 9:16 aspect ratio cho TikTok.

Hãy trả về kết quả dưới định dạng JSON với cấu trúc chính xác sau đây (không bọc trong thẻ markdown, trả về JSON thuần):
{
  "product_analysis": {
    "product_name": "Giá đỡ điện thoại xe máy có mũ bảo hiểm mini - Lắp ghép chi tiết",
    "components": [
      "Thân đỡ điện thoại màu đen",
      "Mũ bảo hiểm mini màu đen có kính trắng",
      "Đế gắn nhựa màu trắng hình vuông",
      "Cần nối màu đen dạng cong",
      "Con ốc màu đen",
      "Con ốc màu trắng"
    ],
    "assembly_steps": [
      "Bước 1 chi tiết lắp ráp trong video 220124...",
      "Bước 2...",
      "Bước 3...",
      "Bước 4..."
    ]
  },
  "title": "Storyboard quảng cáo lắp ghép giá đỡ điện thoại theo video 220124",
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
        response = requests.post(url, headers=headers, json=payload, timeout=120)
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
    
    md_content = f"# Báo cáo Phân tích & Storyboard Video AI: Lắp Ghép Giá Đỡ Điện Thoại Có Mũ Bảo Hiểm Mini (Chi Tiết Video 220124)\n\n"
    md_content += f"## 1. Phân tích quy trình lắp ráp trong video 220124\n"
    md_content += f"- **Tên sản phẩm**: {analysis.get('product_name', 'Giá đỡ điện thoại xe máy kèm mũ bảo hiểm mini')}\n"
    md_content += "\n### Các bộ phận chi tiết:\n"
    for comp in analysis.get("components", []):
        md_content += f"- {comp}\n"
    
    md_content += "\n### Quy trình lắp ráp chi tiết ghi nhận từ video 220124:\n"
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
        f.write("=== TẬP HỢP PROMPT PHỤC VỤ VỊ TRÍ TẠO ẢNH / VIDEO AI (CẬP NHẬT THEO VIDEO 220124) ===\n\n")
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
    storyboard = analyze_220124_assembly()
    if storyboard:
        save_outputs(storyboard, r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may")
        print("Detailed analysis and storyboard generation complete!")
    else:
        print("Failed to generate storyboard.")
