import os
import sys
import json
import re
import shutil

# Thêm thư mục gốc vào path để import các module khác
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config
from hermes.tools.video_downloader import download_video
from hermes.tools.video_analyser import analyze_video
from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor

KB_DIR = os.path.abspath(getattr(config, "KNOWLEDGE_BASE_ROOT", os.path.join(os.path.dirname(__file__), '..', 'knowledge_base')))
INDEX_FILE = os.path.join(KB_DIR, 'index.json')
TEMP_DL_DIR = os.path.join(KB_DIR, 'temp_downloads')

def ensure_kb_dirs():
    """Đảm bảo các thư mục của Kho tri thức tồn tại"""
    os.makedirs(KB_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'w', encoding='utf-8') as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def to_slug(text):
    """Chuyển đổi tiêu đề thành slug an toàn cho tên file"""
    text = text.lower()
    # Thay thế các ký tự tiếng Việt có dấu
    replacements = {
        '[áàảãạăắằẳẵặâấầẩẫậ]': 'a',
        '[éèẻẽẹêếềểễệ]': 'e',
        '[íìỉĩị]': 'i',
        '[óòỏõọôốồổỗộơớờởỡợ]': 'o',
        '[úùủũụưứừửữự]': 'u',
        '[ýỳỷỹỵ]': 'y',
        'đ': 'd'
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    # Loại bỏ ký tự đặc biệt, chỉ giữ lại chữ, số và dấu gạch ngang
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    # Thay khoảng trắng thành dấu gạch ngang
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text

def load_learned_list():
    """Đọc danh sách các video đã học từ UnifiedKnowledgeStore (V1 format compatibility)"""
    from hermes.application.core.knowledge_store import get_store
    store = get_store()
    
    # Trigger auto-migration of old index.json if it exists and hasn't been migrated
    try:
        store.migrate_from_v1_index()
    except Exception:
        pass
        
    entries = store.get_approved_entries()
    v1_list = []
    for e in entries:
        v1_list.append({
            "slug": e.get("slug"),
            "url": e.get("source_url"),
            "title": e.get("title"),
            "platform": e.get("platform", "YouTube"),
            "category": e.get("category", "Review"),
            "date_learned": (e.get("approved_at") or e.get("learned_at", "")).split("T")[0]
        })
    return v1_list

def save_learned_list(data):
    """Không cần lưu thủ công vì UnifiedKnowledgeStore tự quản lý. Giữ hàm để tương thích ngược."""
    return True

def get_learned_detail(slug):
    """Đọc thông tin chi tiết của một video đã học"""
    # Trước tiên thử tìm detail json file trong folder root (V1)
    file_path = os.path.join(KB_DIR, f"{slug}.json")
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[x] Lỗi đọc file {slug}.json: {e}")
            
    # Nếu không thấy, tìm qua UnifiedKnowledgeStore
    from hermes.application.core.knowledge_store import get_store
    entry = get_store().get_entry(slug)
    if entry and entry.get("detail_file"):
        detail_path = os.path.join(KB_DIR, entry["detail_file"])
        if os.path.exists(detail_path):
            try:
                with open(detail_path, 'r', encoding='utf-8') as f:
                    detail_data = json.load(f)
                    return detail_data.get("detail", detail_data)
            except Exception:
                pass
    return None

def delete_learned_item(slug):
    """Xóa một video khỏi kho tri thức"""
    ensure_kb_dirs()
    # Xóa các file V1
    json_path = os.path.join(KB_DIR, f"{slug}.json")
    md_path = os.path.join(KB_DIR, f"{slug}.md")
    if os.path.exists(json_path):
        try: os.remove(json_path)
        except Exception: pass
    if os.path.exists(md_path):
        try: os.remove(md_path)
        except Exception: pass
        
    # Xóa khỏi UnifiedKnowledgeStore
    from hermes.application.core.knowledge_store import get_store
    store = get_store()
    entry = store.get_entry(slug)
    if entry:
        # Xóa detail file nếu có
        detail_file_rel = entry.get("detail_file")
        if detail_file_rel:
            detail_path = os.path.join(KB_DIR, detail_file_rel)
            if os.path.exists(detail_path):
                try: os.remove(detail_path)
                except Exception: pass
        store.delete_entry(slug)
    return True

def learn_from_url(url, category="Review", log_callback=None, auto_approve=False, approved_by=None, approval_mode=None):
    """
    Tải video/audio từ URL, gọi Gemini phân tích rút ra cấu trúc/phong cách kịch bản
    và lưu lại vào Kho Tri Thức.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    ensure_kb_dirs()
    os.makedirs(TEMP_DL_DIR, exist_ok=True)

    log(f"[*] Bắt đầu quy trình học hỏi từ URL: {url}")
    
    # 1. Tải audio từ URL (Tải audio để tiết kiệm băng thông và tăng tốc xử lý)
    log("[*] Đang tải âm thanh từ video (MP3) để phân tích...")
    downloaded_file = download_video(
        url=url,
        output_dir=TEMP_DL_DIR,
        audio_only=True,
        max_duration=600, # Giới hạn tối đa 10 phút để tránh quá tải
        log_callback=log
    )
    
    if not downloaded_file or not os.path.exists(downloaded_file):
        log("[x] Tải file thất bại hoặc video vượt quá thời lượng tối đa.")
        return {"error": "Tải video/audio từ URL thất bại."}
        
    log(f"[+] Đã tải xong file âm thanh: {os.path.basename(downloaded_file)}")
    
    # 2. Gọi Gemini 2.5 Flash phân tích cấu trúc kịch bản và phong cách
    log("[*] Đang gửi dữ liệu lên Google Gemini để phân tích cấu trúc & hành văn...")
    
    prompt_text = """
Bạn là một chuyên gia phân tích nội dung viral trên YouTube và TikTok.
Hãy phân tích kỹ tệp âm thanh/video mẫu được tải lên ở trên và viết một báo cáo phân tích chi tiết bằng tiếng Việt để tôi có thể học hỏi và viết kịch bản bắt chước phong cách này.

Yêu cầu báo cáo trả về dạng cấu trúc JSON chi tiết sau (hãy trả về chuỗi JSON thô, không bọc trong ký hiệu markdown ```json):
{
  "title": "Tiêu đề bài học ngắn gọn (Ví dụ: Công thức review đồ gia dụng thông minh gây tò mò)",
  "platform": "Nền tảng của video (YouTube/TikTok/Douyin)",
  "transcript": "Lời thoại trích xuất chi tiết từng câu nói bằng tiếng Việt (Transcribe đầy đủ)",
  "structure": "Phân tích cấu trúc kịch bản: Gồm 3 phần rõ ràng Hook (chiêu trò giữ chân), Body (cách dẫn dắt tính năng) và CTA (kêu gọi hành động). Giải thích họ phân bổ thời gian thế nào.",
  "copywriting_style": "Phân tích chi tiết phong cách hành văn: Giọng điệu chủ đạo (hài hước, tự tin, giật gân...), cấu trúc câu nói (câu ngắn, nhịp nói dồn dập, hay đặt câu hỏi...), các từ ngữ/từ lóng đặc biệt họ dùng.",
  "key_lessons": "Gạch đầu dòng 3-5 bài học cốt lõi quan trọng nhất mà tôi cần làm theo để viết kịch bản bắt chước chính xác video này."
}
"""

    try:
        analysis_result = analyze_video(
            filepath=downloaded_file,
            prompt_text=prompt_text,
            log_callback=log
        )
        
        # Dọn dẹp file tải tạm thời ngay lập tức
        try:
            shutil.rmtree(TEMP_DL_DIR)
        except Exception:
            pass
            
        if not analysis_result or analysis_result.startswith("Lỗi"):
            log(f"[x] Phân tích thất bại: {analysis_result}")
            return {"error": f"Lỗi phân tích từ Gemini: {analysis_result}"}
            
        # Clean JSON markdown if model still returned it
        clean_json = analysis_result.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r'^```(?:json)?\n', '', clean_json)
            clean_json = re.sub(r'\n```$', '', clean_json)
        clean_json = clean_json.strip()
        
        # Parse kết quả JSON
        try:
            item_data = json.loads(clean_json)
        except Exception as json_ex:
            log(f"[!] Phân tích thành công nhưng kết quả trả về không đúng chuẩn JSON: {json_ex}")
            log(f"[*] Đang cố gắng tự sửa chữa định dạng JSON...")
            # Fallback nếu AI trả về text thường
            item_data = {
                "title": f"Bài học học từ video {category}",
                "platform": "Unknown",
                "transcript": "Không thể phân tách",
                "structure": clean_json,
                "copywriting_style": "Xem nội dung phân tích",
                "key_lessons": "Xem nội dung phân tích"
            }
            
        # 3. Tạo slug và lưu file
        title = item_data.get("title", "Bai hoc tu video")
        slug = to_slug(title)
        if not slug:
            slug = f"learned-video-{int(datetime.now().timestamp())}"
            
        # Thêm vào UnifiedKnowledgeStore
        from hermes.application.core.knowledge_store import get_store
        store = get_store()
        
        key_lessons_list = []
        raw_lessons = item_data.get("key_lessons", "")
        if isinstance(raw_lessons, list):
            key_lessons_list = raw_lessons
        elif isinstance(raw_lessons, str):
            key_lessons_list = [l.strip().lstrip("-* ").strip() for l in raw_lessons.split('\n') if l.strip()]
            
        platform = item_data.get("platform", "youtube").lower()
        if "tiktok" in url.lower():
            platform = "tiktok"
        elif "youtube" in url.lower() or "youtu.be" in url.lower():
            platform = "youtube"
            
        # Tạo entry mới
        new_entry = store.add_entry(
            title=title,
            source_url=url,
            platform=platform,
            category=category,
            key_lessons=key_lessons_list,
            detail_data=item_data,
            source="gui_learn",
        )
        if auto_approve:
            result = KnowledgeLifecycle(store).approve(
                new_entry["id"],
                LifecycleActor.system("gui-review"),
                mode=approval_mode or "",
            )
            if not result.ok:
                return {"error": f"Knowledge approval failed: {result.code}"}
            
        # Lấy lại entry để cập nhật slug chuẩn
        updated_entry = store.get_entry(new_entry["id"])
        slug = updated_entry["slug"] if updated_entry else new_entry["slug"]
        
        # Lưu file chi tiết JSON (Để tương thích ngược với các hàm đọc file V1 cũ)
        detail_path = os.path.join(KB_DIR, f"{slug}.json")
        with open(detail_path, 'w', encoding='utf-8') as f:
            json.dump(item_data, f, ensure_ascii=False, indent=2)
            
        # Lưu file chi tiết Markdown để người dùng tiện đọc
        md_path = os.path.join(KB_DIR, f"{slug}.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# BÀI HỌC AI: {title}\n\n")
            f.write(f"- **Nguồn URL**: {url}\n")
            f.write(f"- **Danh mục**: {category} | **Nền tảng**: {item_data.get('platform', 'N/A')}\n\n")
            f.write(f"## 1. Lời thoại chi tiết (Transcript)\n")
            f.write(f"```text\n{item_data.get('transcript', '')}\n```\n\n")
            f.write(f"## 2. Cấu trúc kịch bản (Hook - Body - CTA)\n")
            f.write(f"{item_data.get('structure', '')}\n\n")
            f.write(f"## 3. Phong cách Copywriting & Hành văn\n")
            f.write(f"{item_data.get('copywriting_style', '')}\n\n")
            f.write(f"## 4. Bài học cốt lõi để bắt chước\n")
            if isinstance(raw_lessons, list):
                f.write("\n".join([f"- {l}" for l in raw_lessons]) + "\n")
            else:
                f.write(f"{raw_lessons}\n")
            
        log(f"[+] Học hỏi thành công! Đã lưu bài học tại: {detail_path}")
        return {"success": True, "slug": slug, "title": title}
        
    except Exception as e:
        log(f"[x] Có lỗi xảy ra trong quá trình xử lý: {e}")
        try:
            shutil.rmtree(TEMP_DL_DIR)
        except Exception:
            pass
        return {"error": str(e)}
