import os
import sys
import json
import requests
import re

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config

def generate_storyboard(
    product_name,
    product_description,
    selling_points,
    target_audience,
    pain_points,
    video_style,
    background_description,
    product_image_note,
    background_image_note,
    duration_seconds=24,
    scene_count=6,
    output_language="vi",
    prompt_target="Google Labs / Veo",
):
    """
    Queries Gemini API to generate a scene-by-scene storyboard with AI prompts.
    Returns a dictionary matching the specified structured JSON schema.
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "Chưa cấu hình GEMINI_API_KEY trong file .env"}
        
    model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
Bạn là một đạo diễn hình ảnh và chuyên gia viết prompt AI Art/Video hàng đầu.
Nhiệm vụ của bạn là tạo ra một kịch bản phân cảnh (Storyboard AI) chi tiết và bộ prompt hoàn chỉnh để người dùng có thể sao chép trực tiếp vào các công cụ sinh ảnh/video AI (như ChatGPT, Gemini, Google Labs, Veo, Luma, Runway, Sora, v.v.).

Hãy lên ý tưởng phân cảnh cho sản phẩm sau:
- Tên sản phẩm: {product_name}
- Mô tả sản phẩm: {product_description}
- Điểm bán hàng chính (USP): {selling_points}
- Khách hàng mục tiêu: {target_audience}
- Nỗi đau khách hàng: {pain_points}

Định hướng sáng tạo video:
- Phong cách video: {video_style}
- Thời lượng video: {duration_seconds} giây
- Số phân cảnh yêu cầu: {scene_count} cảnh
- Bối cảnh/Background mong muốn: {background_description}
- Ghi chú về ảnh sản phẩm tham chiếu: {product_image_note}
- Ghi chú về ảnh background tham chiếu: {background_image_note}
- Công cụ sinh AI đích nhắm tới: {prompt_target}

Yêu cầu chi tiết về phân cảnh:
- Chia đều {duration_seconds} giây cho {scene_count} cảnh. Đánh số cảnh tăng dần.
- Mỗi cảnh phải có mục đích rõ ràng (ví dụ: Cảnh 1: Hook giữ chân, Cảnh 2: Đặt vấn đề/nỗi đau, Cảnh 3: Giới thiệu sản phẩm, Cảnh 4: Trải nghiệm thực tế, Cảnh 5: Lợi ích vượt trội, Cảnh 6: CTA mua hàng).
- Trả về chi tiết các thông số quay: Mô tả hình ảnh (Visual), Thao tác/hành động (Action), Góc máy (Camera angle), Chuyển động (Camera movement), Ánh sáng (Lighting), Bối cảnh (Background), Tiêu điểm sản phẩm (Product focus), Lời đọc thuyết minh (Voiceover), Chữ trên màn hình (On-screen text).
- Tạo prompt sinh hình ảnh (Image Prompt) và prompt sinh video (Video Prompt) cho mỗi cảnh bằng cả tiếng Việt (vi) và tiếng Anh (en).
- Các prompt tiếng Anh (en) rất quan trọng và cần được viết cực kỳ chi tiết, chuyên nghiệp theo phong cách nhiếp ảnh/quay phim quảng cáo:
  + Đối với video prompt, phải chứa các từ khóa định hình: "vertical 9:16 aspect ratio", "realistic TikTok product review video style", "product-focused close-up", "natural hand movement", "clean studio background", "smooth slow camera panning", "commercial photography", "high detail", "8k resolution".
  + Negative prompt phải ngăn chặn các lỗi AI phổ biến: "no watermark, no logo, no distorted hands, no deformed product, no text artifacts, no blurry text, extra fingers, bad anatomy, deformed fingers".

Định dạng JSON yêu cầu (Trả về ĐÚNG cấu trúc JSON này, không thêm văn bản phụ nào khác):
{{
  "title": "Storyboard quảng cáo cho {product_name}",
  "concept_summary": "Tóm tắt ý tưởng chủ đạo toàn bài...",
  "video_duration": {duration_seconds},
  "scene_count": {scene_count},
  "hook_options": ["Tùy chọn câu giật tít 1", "Tùy chọn câu giật tít 2"],
  "cta_options": ["Tùy chọn kêu gọi hành động 1", "Tùy chọn kêu gọi hành động 2"],
  "scenes": [
    {{
      "scene_number": 1,
      "time_range": "Khung thời gian (ví dụ: 0-4s)",
      "scene_purpose": "Mục đích cảnh",
      "visual_description": "Mô tả chi tiết hình ảnh xuất hiện...",
      "action_description": "Thao tác của tay hoặc sản phẩm...",
      "camera_angle": "Góc máy (ví dụ: Eye-level close-up, Macro, Top-down...)",
      "camera_movement": "Chuyển động camera (ví dụ: Panning left, Zoom in, Static...)",
      "lighting": "Ánh sáng (ví dụ: Soft studio lighting, Bright sunlight, Neon...)",
      "background": "Bối cảnh xung quanh...",
      "product_focus": "Sản phẩm được làm nổi bật như thế nào...",
      "voiceover_line": "Câu nói thuyết minh tiếng Việt trong cảnh này...",
      "on_screen_text": "Chữ chạy trên màn hình cảnh này...",
      "image_prompt_vi": "Prompt sinh hình ảnh bằng tiếng Việt...",
      "image_prompt_en": "Prompt sinh hình ảnh bằng tiếng Anh chi tiết...",
      "video_prompt_vi": "Prompt sinh video bằng tiếng Việt...",
      "video_prompt_en": "Prompt sinh video bằng tiếng Anh chi tiết...",
      "negative_prompt": "Các từ khóa loại trừ lỗi..."
    }}
  ],
  "full_image_prompt_set_vi": "Tập hợp tất cả các image prompts tiếng Việt dòng dọc phân tách nhau rõ ràng...",
  "full_video_prompt_set_vi": "Tập hợp tất cả các video prompts tiếng Việt dòng dọc phân tách nhau rõ ràng...",
  "full_image_prompt_set_en": "Tập hợp tất cả các image prompts tiếng Anh dòng dọc phân tách nhau rõ ràng...",
  "full_video_prompt_set_en": "Tập hợp tất cả các video prompts tiếng Anh dòng dọc phân tách nhau rõ ràng..."
}}
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            return {"error": f"Lỗi Gemini API (HTTP {response.status_code}): {response.text}"}
            
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Strip markdown formatting
        if text_content.startswith("```"):
            text_content = re.sub(r'^```(json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
            
        storyboard_dict = json.loads(text_content)
        return storyboard_dict
        
    except Exception as e:
        print(f"[x] Error generating storyboard: {e}")
        return {"error": f"Lỗi kết nối Gemini API: {str(e)}"}
