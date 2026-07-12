import os
import sys
import json
import requests
import re

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

# List of supported styles
SCRIPT_STYLES = {
    "Mở đầu tò mò": "Mở đầu tò mò (kích thích trí tò mò của người xem ngay từ giây đầu tiên, tạo câu hỏi bỏ lửng)",
    "Đánh thẳng nỗi đau": "Mở đầu đánh thẳng nỗi đau (nêu bật vấn đề khó chịu mà đối tượng mục tiêu đang gặp phải)",
    "Trước và sau": "Mở đầu trước/sau (so sánh sự khác biệt rõ rệt trước và sau khi dùng sản phẩm)",
    "Đánh giá chân thực": "Đánh giá chân thực (phong cách trải nghiệm thực tế khách quan, tin cậy)",
    "Ngon bổ rẻ": "Ngon bổ rẻ (nhấn mạnh tính năng hữu dụng vượt trội so với giá tiền hạt dẻ)",
    "TikTok Viral (Bắt trend)": "Phong cách bắt trend (sử dụng ngôn từ năng động, nhịp điệu nhanh, hợp với xu hướng giới trẻ)",
    "Tin tức & Tóm tắt": "Điểm tin nhanh (tóm tắt ý chính súc tích, nhịp độ nhanh, giọng điệu chuyên nghiệp, cập nhật công nghệ/tin tức)"
}

def generate_script(product_name, description="", price="", selling_points="", target_audience="", pain_points="", style="Mở đầu tò mò", reference_style_json=None):
    """
    Queries Gemini API to generate a TikTok script in Vietnamese based on product info, style, and optional reference learned style.
    Returns a dict:
    {
      "voice_script": "...",
      "caption": "...",
      "hashtags": "..."
    }
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {
            "error": "Chưa cấu hình GEMINI_API_KEY trong file .env",
            "voice_script": "Lỗi: Chưa cấu hình Gemini API Key",
            "caption": "",
            "hashtags": ""
        }
        
    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    style_desc = SCRIPT_STYLES.get(style, SCRIPT_STYLES["Mở đầu tò mò"])
    
    ref_instruction = ""
    if reference_style_json and isinstance(reference_style_json, dict):
        ref_title = reference_style_json.get("title", "")
        ref_structure = reference_style_json.get("structure", "")
        ref_copywriting = reference_style_json.get("copywriting_style", "")
        ref_lessons = reference_style_json.get("key_lessons", "")
        if isinstance(ref_lessons, list):
            ref_lessons = "\n".join([f"- {l}" for l in ref_lessons])
        
        ref_instruction = f"""
ĐẶC BIỆT QUAN TRỌNG: Bạn cần BẮT CHƯỚC phong cách, cấu trúc kịch bản và cách hành văn của video thành công sau đây:
- Tiêu đề video mẫu: {ref_title}
- Cấu trúc kịch bản mẫu: {ref_structure}
- Cách hành văn/Copywriting: {ref_copywriting}
- Các bài học cốt lõi cần bắt chước: {ref_lessons}

Yêu cầu cụ thể:
1. Hãy mô phỏng lại chính xác cấu trúc hook (cách mở đầu), cách dẫn dắt giới thiệu lợi ích sản phẩm, và cách kêu gọi hành động của video mẫu này để áp dụng viết cho sản phẩm mới '{product_name}'.
2. Giữ nguyên nhịp điệu hành văn và giọng điệu (ví dụ: hài hước, giật gân, nhịp câu ngắn...) nhưng thay thế toàn bộ thông tin sản phẩm và nỗi đau sao cho phù hợp hoàn toàn với sản phẩm mới của tôi.
"""
    else:
        # Tự động truy vấn và inject bài học đã duyệt từ UnifiedKnowledgeStore
        try:
            from core.knowledge_store import get_store
            prod_text = f"{product_name} {description}".lower()
            category_guess = None
            if any(k in prod_text for k in ["mụn", "da", "skincare", "kem chống nắng", "son", "mỹ phẩm", "serum", "sữa rửa mặt"]):
                category_guess = "review sản phẩm"
            elif any(k in prod_text for k in ["điện thoại", "tai nghe", "sạc", "cáp", "tech", "laptop", "pc", "loa", "phụ kiện", "tin tức", "news", "bản tin"]):
                category_guess = "tin tức / công nghệ"
            elif any(k in prod_text for k in ["bếp", "nồi", "chảo", "gia dụng", "nhà cửa", "tủ", "chổi"]):
                category_guess = "chia sẻ kiến thức"
                
            store = get_store()
            # Giới hạn tối đa 3 approved entries
            style_context = store.get_style_context_for_script(category=category_guess, max_lessons=3)
            if not style_context and category_guess:
                style_context = store.get_style_context_for_script(category=None, max_lessons=3)
                
            if style_context:
                # Giới hạn tối đa 3500 ký tự
                if len(style_context) > 3500:
                    style_context = style_context[:3500] + "\n... [Context truncated due to length limits]"
                
                safety_instruction = (
                    "\n--- HƯỚNG DẪN SỬ DỤNG BÀI HỌC (AN TOÀN SÁNG TẠO) ---\n"
                    "Use the following approved lessons as reusable creative patterns only.\n"
                    "Do not copy exact wording, scenes, brands, claims, logos, unique artwork, or creator-specific details from the source.\n"
                    "Adapt only the structure, pacing, hook style, CTA style, and reusable product demonstration logic.\n"
                    "----------------------------------------------------\n\n"
                )
                ref_instruction = f"\n{safety_instruction}{style_context}\n"
                print(f"[ScriptGenerator] 🧠 Đã tự động inject bài học từ Kho tri thức (Category: {category_guess or 'General'})")
        except Exception as e:
            print(f"[!] Lỗi khi load style context từ UnifiedKnowledgeStore: {e}")

    prompt = f"""
Bạn là một chuyên gia sáng tạo nội dung TikTok triệu view và nhà biên kịch quảng cáo bán hàng xuất sắc.
Hãy viết một kịch bản video ngắn (TikTok/Reels/Shorts) dài khoảng 30-60 giây bằng TIẾNG VIỆT để quảng bá sản phẩm dưới đây.

Thông tin sản phẩm:
- Tên sản phẩm: {product_name}
- Mô tả: {description}
- Giá bán: {price}
- Điểm bán hàng chính (USP): {selling_points}
- Khách hàng mục tiêu: {target_audience}
- Nỗi đau khách hàng (Pain points): {pain_points}

Phong cách viết kịch bản mặc định: {style} - {style_desc}
{ref_instruction}

Yêu cầu kịch bản voiceover (Giọng đọc):
1. Kịch bản voiceover PHẢI chia thành các phần rõ rệt theo cấu trúc:
   - Hook (3-5 giây đầu thu hút chú ý)
   - Problem (Nêu vấn đề/nỗi đau)
   - Product introduction (Giới thiệu sản phẩm giải quyết vấn đề)
   - Main benefit (Lợi ích lớn nhất)
   - Short demo explanation (Giải thích cách hoạt động ngắn gọn)
   - CTA (Kêu gọi hành động như mua hàng, bấm link bio)
2. Viết bằng ngôn ngữ nói tự nhiên, lôi cuốn, ngắn gọn, súc tích, tránh từ ngữ sáo rỗng.
3. Kịch bản này chỉ chứa LỜI ĐỌC (giọng đọc thuyết minh), KHÔNG bao gồm các chỉ dẫn hình ảnh hay âm thanh (như [Cảnh quay...], [Tiếng nhạc...]) để người dùng có thể nạp trực tiếp vào ElevenLabs tạo file audio sạch.
4. Mỗi phân đoạn câu thoại nên viết trên một dòng mới để dễ phân tích phụ đề.

Yêu cầu Caption và Hashtags:
- Viết 1 dòng caption ngắn gọn, kích thích tương tác trên TikTok.
- Gợi ý 5-10 hashtags hot, đúng chủ đề sản phẩm.

Hãy trả về kết quả dưới định dạng JSON sau đây và KHÔNG có văn bản nào khác ngoài JSON:
{{
  "voice_script": "Dòng 1 lời đọc kịch bản\\nDòng 2 lời đọc kịch bản\\nDòng 3 lời đọc kịch bản...",
  "caption": "Mô tả video thu hút...",
  "hashtags": "#hashtag1 #hashtag2 #hashtag3..."
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
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code != 200:
            return {
                "error": f"Lỗi Gemini API (HTTP {response.status_code}): {response.text}",
                "voice_script": f"Lỗi kết nối Gemini API (HTTP {response.status_code})",
                "caption": "",
                "hashtags": ""
            }
            
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Clean any markdown formatting
        if text_content.startswith("```"):
            text_content = re.sub(r'^```(?:json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
            
        script_dict = json.loads(text_content)
        
        # Ensure all keys exist
        for key in ['voice_script', 'caption', 'hashtags']:
            if key not in script_dict:
                script_dict[key] = ""
                
        return script_dict
        
    except Exception as e:
        print(f"[x] Error generating script: {e}")
        return {
            "error": f"Lỗi kết nối Gemini API: {str(e)}",
            "voice_script": f"Gặp lỗi khi tạo kịch bản: {str(e)}",
            "caption": "",
            "hashtags": ""
        }

def save_script_files(scripts_dir, script_data):
    """Saves the generated script data into the project's scripts folder."""
    os.makedirs(scripts_dir, exist_ok=True)
    
    voice_path = os.path.join(scripts_dir, 'voice_script.txt')
    caption_path = os.path.join(scripts_dir, 'caption.txt')
    hashtags_path = os.path.join(scripts_dir, 'hashtags.txt')
    
    with open(voice_path, 'w', encoding='utf-8') as f:
        f.write(script_data.get('voice_script', ''))
        
    with open(caption_path, 'w', encoding='utf-8') as f:
        f.write(script_data.get('caption', ''))
        
    with open(hashtags_path, 'w', encoding='utf-8') as f:
        f.write(script_data.get('hashtags', ''))
        
    return voice_path, caption_path, hashtags_path
