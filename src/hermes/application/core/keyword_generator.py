import os
import sys
import json
import re
import requests

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config

def generate_keywords(product_name, description="", price="", selling_points="", target_audience="", pain_points=""):
    """
    Calls the Gemini API to generate video search keywords in Vietnamese, English, and Simplified Chinese.
    Returns a dictionary:
    {
       "vi": [...],
       "en": [...],
       "zh": [...]
    }
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "Chưa cấu hình GEMINI_API_KEY trong file .env", "vi": [], "en": [], "zh": []}
        
    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
Bạn là một chuyên gia Marketing E-commerce và SEO Video.
Nhiệm vụ của bạn là tạo ra danh sách từ khóa tìm kiếm (search keywords) phù hợp để tìm kiếm các video clip/phôi video về sản phẩm này trên các nền tảng (như TikTok, Youtube, Pexels, Pixabay, Douyin, 1688, Taobao...).

Thông tin sản phẩm:
- Tên sản phẩm: {product_name}
- Mô tả: {description}
- Giá bán: {price}
- Điểm bán hàng chính (USP): {selling_points}
- Khách hàng mục tiêu: {target_audience}
- Nỗi đau khách hàng (Pain points): {pain_points}

Yêu cầu:
1. Tạo từ khóa trong 3 ngôn ngữ: tiếng Việt (vi), tiếng Anh (en), và chữ Hán giản thể (zh - Trung Quốc, rất quan trọng để tìm video trên 1688/Douyin/Taobao).
2. Trả về đúng định dạng JSON bên dưới. Không viết lời bình hay văn bản phụ nào khác ngoài JSON.

Định dạng JSON yêu cầu:
{{
  "vi": ["từ khóa 1", "từ khóa 2", "từ khóa 3", "từ khóa 4", "từ khóa 5"],
  "en": ["keyword 1", "keyword 2", "keyword 3", "keyword 4", "keyword 5"],
  "zh": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"]
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
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code != 200:
            return {
                "error": f"Lỗi Gemini API (HTTP {response.status_code}): {response.text}",
                "vi": [product_name], "en": [product_name], "zh": []
            }
            
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Clean any markdown formatting if LLM didn't respect responseMimeType
        if text_content.startswith("```"):
            # Strip ```json and ```
            text_content = re.sub(r'^```(?:json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
            
        keywords_dict = json.loads(text_content)
        # Ensure all keys exist
        for lang in ['vi', 'en', 'zh']:
            if lang not in keywords_dict:
                keywords_dict[lang] = []
                
        return keywords_dict
        
    except Exception as e:
        print(f"[x] Error generating keywords: {e}")
        return {
            "error": f"Lỗi kết nối Gemini API: {str(e)}",
            "vi": [product_name], "en": [product_name], "zh": []
        }

def translate_to_zh(text):
    """
    Dịch tên sản phẩm hoặc từ khóa từ tiếng Việt sang chữ Hán giản thể (Trung Quốc)
    để tiện lợi tìm kiếm phôi video trên Douyin, 1688, Taobao.
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return "Lỗi: Chưa cấu hình GEMINI_API_KEY trong file .env"
        
    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
Bạn là một chuyên gia dịch thuật và Marketing E-commerce Trung - Việt.
Hãy dịch tên sản phẩm hoặc từ khóa tìm kiếm sau đây từ tiếng Việt sang tiếng Trung Giản thể (Simplified Chinese).
Mục đích là dùng để tìm kiếm phôi video trên các trang thương mại điện tử Trung Quốc như Douyin, 1688, Taobao.
Yêu cầu: Chỉ trả về bản dịch tiếng Trung ngắn gọn, chính xác nhất, không chứa bất kỳ giải thích, chú thích hay văn bản nào khác.

Từ khóa tiếng Việt cần dịch: "{text}"
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code != 200:
            return f"Lỗi Gemini API (HTTP {response.status_code}): {response.text}"
            
        res_data = response.json()
        translated = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        # Clean any quotes or formatting
        translated = translated.strip('"`\' \n')
        return translated
    except Exception as e:
        return f"Lỗi kết nối Gemini: {str(e)}"

def extract_smart_keywords(text_or_url):
    """
    Strips noise words (freeship, chính hãng, giá rẻ, sale...) from product title/URL
    and extracts concise, meaningful search key phrases (2-4 words).
    """
    if not text_or_url:
        return []
        
    raw = text_or_url
    # If URL, unquote and extract path slug
    if "http://" in raw or "https://" in raw:
        parsed = re.sub(r'https?://[^\s]+', '', raw)
        if not parsed.strip():
            path = raw.split('?')[0].split('/')[-1]
            path = re.sub(r'-i\.\d+\.\d+$', '', path)
            raw = urllib.parse.unquote(path).replace('-', ' ').replace('_', ' ')
            
    # List of common Vietnamese e-commerce stop words to remove
    stop_words = [
        r'chính hãng', r'freeship', r'giá rẻ', r'cao cấp', r'hàng mới', r'nhập khẩu',
        r'khuyến mãi', r'chịu lực', r'siêu bền', r'quà tặng', r'combo', r'thế hệ mới',
        r'đa năng', r'tiện lợi', r'xịn', r'bán chạy', r'top 1', r'tốt nhất', r'mẫu mới'
    ]
    
    clean_text = raw
    for kw in stop_words:
        clean_text = re.sub(kw, '', clean_text, flags=re.IGNORECASE)
        
    clean_text = re.sub(r'[^\w\s\u00C0-\u024F\u1EA0-\u1EF9]', ' ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    words = clean_text.split()
    if not words:
        return [raw[:20]]
        
    phrases = []
    # Primary short phrase (first 3-4 words)
    primary = " ".join(words[:4])
    phrases.append(primary)
    
    if len(words) >= 6:
        secondary = " ".join(words[2:6])
        phrases.append(secondary)
        
    return phrases

def nlp_expand_keywords(query_text):
    """
    Calls the Gemini API to parse query_text into entities (Product, Features, Color)
    and expands it into optimal search terms for vi, en, zh.
    Returns:
      dict: {
         "entities": {"product": "...", "features": "...", "color": "..."},
         "vi": [...],
         "en": [...],
         "zh": [...]
      }
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {
            "entities": {"product": query_text, "features": "", "color": ""},
            "vi": [query_text],
            "en": [query_text],
            "zh": [query_text]
        }
        
    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
Bạn là một chuyên gia AI NLP và Marketing E-commerce.
Hãy phân tích câu lệnh tìm kiếm sản phẩm sau: "{query_text}"

Yêu cầu:
1. Phân tách câu lệnh thành các thực thể (entities):
   - product: Tên sản phẩm chính (ví dụ: "giá đỡ điện thoại")
   - features: Các đặc tính, tính năng đi kèm (ví dụ: "xoay", "gập gọn")
   - color: Màu sắc (ví dụ: "trắng")
2. Tạo ra các từ khóa tìm kiếm (search terms) tối ưu bằng 3 ngôn ngữ:
   - vi: Tiếng Việt (ví dụ: "giá đỡ điện thoại xoay gập gọn", "kệ để điện thoại xoay 360")
   - en: Tiếng Anh (ví dụ: "phone stand 360 rotatable foldable", "folding desktop phone holder")
   - zh: Tiếng Trung Giản thể (ví dụ: "旋转折叠手机支架", "桌面手机支架 360度旋转")
3. Trả về đúng định dạng JSON mẫu bên dưới. Không viết lời bình hay văn bản phụ nào khác.

Định dạng JSON yêu cầu:
{{
  "entities": {{
    "product": "...",
    "features": "...",
    "color": "..."
  }},
  "vi": ["keyword_vi_1", "keyword_vi_2", "keyword_vi_3"],
  "en": ["keyword_en_1", "keyword_en_2", "keyword_en_3"],
  "zh": ["keyword_zh_1", "keyword_zh_2", "keyword_zh_3"]
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
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_data = response.json()
            text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            if text_content.startswith("```"):
                text_content = re.sub(r'^```(?:json)?\n', '', text_content)
                text_content = re.sub(r'\n```$', '', text_content)
                
            return json.loads(text_content)
    except Exception as e:
        print(f"[!] Error in nlp_expand_keywords: {e}")
        
    return {
        "entities": {"product": query_text, "features": "", "color": ""},
        "vi": [query_text],
        "en": [query_text],
        "zh": [query_text]
    }

def extract_keywords_from_product_page(title, description):
    """
    Calls the Gemini API to analyze raw product page title and description.
    Strips noise words and extracts core search phrases (vi, en, zh).
    Returns a dict with vi, en, zh keyword lists.
    """
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        clean = " ".join(title.strip().split()[:4])
        return {"vi": [clean], "en": [clean], "zh": []}
        
    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    prompt = f"""
Bạn là một chuyên gia E-commerce SEO.
Hãy lọc sạch tiêu đề và mô tả sản phẩm thương mại điện tử sau để rút trích các từ khóa tìm kiếm cốt lõi (search keywords).

Tiêu đề gốc: "{title}"
Mô tả: "{description[:800]}"

Yêu cầu:
1. Loại bỏ các từ khóa rác, từ quảng cáo tiếp thị (ví dụ: "Freeship", "Chính hãng", "Giảm giá", "Sale", "Mẫu mới", "Giá sỉ", "Độc quyền").
2. Trích xuất ra 3-5 từ khóa tìm kiếm cốt lõi (ngắn gọn, tập trung vào tên sản phẩm và tính năng chính) bằng:
   - vi (tiếng Việt)
   - en (tiếng Anh)
   - zh (chữ Hán giản thể - Trung Quốc)
3. Trả về đúng định dạng JSON bên dưới. Không có thêm lời bình.

Định dạng JSON yêu cầu:
{{
  "vi": ["từ khóa vi 1", "từ khóa vi 2", "từ khóa vi 3"],
  "en": ["keyword en 1", "keyword en 2", "keyword en 3"],
  "zh": ["关键词 zh 1", "关键词 zh 2", "关键词 zh 3"]
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
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code == 200:
            res_data = response.json()
            text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
            
            if text_content.startswith("```"):
                text_content = re.sub(r'^```(?:json)?\n', '', text_content)
                text_content = re.sub(r'\n```$', '', text_content)
                
            return json.loads(text_content)
    except Exception as e:
        print(f"[!] Error in extract_keywords_from_product_page: {e}")
        
    clean = " ".join(title.strip().split()[:4])
    return {"vi": [clean], "en": [clean], "zh": []}

if __name__ == "__main__":
    # Test keywords generator CLI
    config.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")
    print("Testing generate_keywords...")
    res = generate_keywords("Bình giữ nhiệt hiển thị nhiệt độ", "Giữ nhiệt tốt, hiển thị màn hình LED")
    print(json.dumps(res, indent=4, ensure_ascii=False))
    print("\nTesting translate_to_zh...")
    print(translate_to_zh("Giá đỡ điện thoại xoay 360 độ"))
