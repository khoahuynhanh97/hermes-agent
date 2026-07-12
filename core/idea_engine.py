import os
import sys
import json
import requests
import re

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config


ANGLE_TYPES = [
    "Review chân thực",
    "Demo tính năng",
    "Before / After",
    "Giải quyết pain point",
    "Setup / Lifestyle",
    "3 lý do nên mua",
    "Món đồ nhỏ tiện lợi",
    "Dùng thử lần đầu",
    "So sánh sản phẩm",
    "Unboxing / mở hộp",
    "Câu chuyện người dùng",
    "Trending hook",
]


def generate_ideas(
    product_name,
    description="",
    price="",
    selling_points="",
    target_audience="",
    pain_points="",
    color_material="",
    video_context="",
    image_style="",
    num_ideas=15,
):
    """
    Gọi Gemini API để sinh nhiều ý tưởng angle video TikTok từ thông tin sản phẩm.
    Trả về list các idea dict đã được chấm điểm.
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "Chưa cấu hình GEMINI_API_KEY trong file .env"}

    model = getattr(config, "GEMINI_MODEL", "gemini-2.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = f"""Bạn là chuyên gia sáng tạo nội dung TikTok affiliate hàng đầu, chuyên tạo video phôi 9:16 không âm thanh để đưa vào CapCut hoàn thiện.

Thông tin sản phẩm:
- Tên sản phẩm: {product_name}
- Mô tả: {description}
- Giá bán: {price}
- Điểm bán hàng (USP): {selling_points}
- Đối tượng mục tiêu: {target_audience}
- Nỗi đau khách hàng: {pain_points}
- Màu sắc / chất liệu: {color_material}
- Bối cảnh video mong muốn: {video_context}
- Phong cách hình ảnh: {image_style}

Nhiệm vụ: Tạo {num_ideas} ý tưởng angle video TikTok affiliate KHÁC NHAU cho sản phẩm này.

Tiêu chí chấm điểm mỗi angle (0-100):
- ai_video_score: Độ dễ tạo bằng AI Video (Veo/Kling/Runway) — cảnh đơn giản, sạch, ít người
- demo_score: Độ dễ demo sản phẩm bằng hình ảnh — rõ sản phẩm, action cụ thể
- sell_score: Tiềm năng bán hàng TikTok affiliate — hook mạnh, CTA rõ
- reuse_score: Khả năng tái sử dụng phôi — clip có thể dùng cho video khác
- tiktok_fit: Phù hợp format TikTok — trendy, ngắn, cuốn hút

Trả về JSON với cấu trúc sau và KHÔNG có văn bản nào khác:
{{
  "ideas": [
    {{
      "idea_id": "A01",
      "title": "Tên angle ngắn gọn (< 50 ký tự)",
      "angle_type": "Loại angle (Review chân thực / Demo tính năng / Before-After / Giải quyết pain point / Setup Lifestyle / 3 lý do / Unboxing / ...)",
      "hook_style": "Kiểu hook đầu video (Câu hỏi gây tò mò / Nỗi đau trực tiếp / Kết quả bất ngờ / So sánh / ...)",
      "description": "Mô tả ngắn gọn ý tưởng video này (2-3 câu): bắt đầu thế nào, giữa có gì, kết thúc ra sao",
      "scene_flow": "Flow cảnh ví dụ: Cảnh 1: Hook → Cảnh 2: Pain → Cảnh 3: Product → Cảnh 4: Demo → Cảnh 5: Result",
      "ai_video_score": 85,
      "demo_score": 90,
      "sell_score": 80,
      "reuse_score": 75,
      "tiktok_fit": 88,
      "total_score": 84,
      "difficulty": "Dễ",
      "estimated_scenes": 5,
      "notes": "Ghi chú thêm về điểm mạnh hoặc lưu ý khi triển khai"
    }}
  ]
}}
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=90)
        if response.status_code != 200:
            return {"error": f"Lỗi Gemini API (HTTP {response.status_code}): {response.text}"}

        res_data = response.json()
        text_content = res_data["candidates"][0]["content"]["parts"][0]["text"].strip()

        # Strip markdown formatting if present
        if text_content.startswith("```"):
            text_content = re.sub(r"^```(json)?\n", "", text_content)
            text_content = re.sub(r"\n```$", "", text_content)

        ideas_dict = json.loads(text_content)
        return ideas_dict

    except Exception as e:
        return {"error": f"Lỗi kết nối Gemini API: {str(e)}"}


def save_ideas(project_dir, ideas_data):
    """Lưu ideas.json vào thư mục project."""
    os.makedirs(project_dir, exist_ok=True)
    path = os.path.join(project_dir, "ideas.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ideas_data, f, ensure_ascii=False, indent=4)
    return path


def load_ideas(project_dir):
    """Tải ideas.json từ thư mục project. Trả về dict hoặc None."""
    path = os.path.join(project_dir, "ideas.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_selected_angles(project_dir, selected_ideas):
    """Lưu selected_angles.json — danh sách angle user đã chọn."""
    os.makedirs(project_dir, exist_ok=True)
    path = os.path.join(project_dir, "selected_angles.json")
    data = {"selected_angles": selected_ideas}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    return path


def load_selected_angles(project_dir):
    """Tải selected_angles.json từ thư mục project."""
    path = os.path.join(project_dir, "selected_angles.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
