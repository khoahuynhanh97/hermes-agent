import os
import sys
import shutil
import json
import re
import requests
import urllib.parse

# Thêm thư mục gốc vào python path để import các module khác
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from hermes.runtime import config
from hermes.application.core.project_manager import ProjectManager
from hermes.tools.video_downloader import download_video
from hermes.tools.video_analyser import analyze_video
from hermes.integrations.providers.pexels_provider import search_and_download_pexels
from hermes.integrations.providers.pixabay_provider import search_and_download_pixabay
from hermes.integrations.providers.shopee_search_provider import search_and_download_shopee
from hermes.integrations.providers.social_search_provider import search_and_download_social
from hermes.integrations.providers.product_image_provider import search_and_download_product_images
from hermes.video.editor.clip_cutter import cut_materials_into_clips
from hermes.application.core.script_generator import generate_script, save_script_files
from hermes.application.core.keyword_generator import extract_smart_keywords
from hermes.application.core.visual_matcher import filter_materials_by_reference

def extract_metadata_from_text(title, description, log_callback=None):
    """Sử dụng Gemini API để trích xuất metadata dạng JSON từ tiêu đề/mô tả cào được"""
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key:
        return {"error": "Chưa cấu hình GEMINI_API_KEY trong file .env"}

    model = getattr(config, "GEMINI_MODEL", "gemini-1.5-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    prompt = f"""
Bạn là một chuyên gia marketing thương mại điện tử chuyên tối ưu hóa dữ liệu sản phẩm.
Dưới đây là thông tin cào được từ trang sản phẩm TMĐT:
- Tiêu đề gốc: {title}
- Mô tả gốc: {description}

Hãy phân tích thông tin này và trích xuất/ước lượng các thuộc tính sản phẩm chi tiết dưới dạng JSON sau (vui lòng trả về chuỗi JSON thô, không bọc trong ký hiệu markdown ```json):
{{
  "product_name": "Tên sản phẩm ngắn gọn, viết hoa chữ cái đầu (Ví dụ: Máy Tăm Nước Cầm Tay Panworld)",
  "description": "Mô tả sản phẩm tóm tắt 2-3 câu ngắn gọn",
  "price": "Giá bán sản phẩm (Ví dụ: 350.000 VNĐ, hoặc ghi N/A nếu không rõ)",
  "selling_points": "Gạch đầu dòng 2-3 điểm bán hàng cốt lõi (USP) nổi bật nhất",
  "target_audience": "Khách hàng mục tiêu phù hợp",
  "pain_points": "Nỗi đau/vấn đề của khách hàng mà sản phẩm này giải quyết",
  "keywords": ["từ khóa tiếng Anh 1", "từ khóa tiếng Anh 2", "từ khóa tiếng Anh 3"]
}}
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"}
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        if response.status_code != 200:
            return {"error": f"Lỗi Gemini API (HTTP {response.status_code})"}
            
        res_data = response.json()
        text_content = res_data['candidates'][0]['content']['parts'][0]['text'].strip()
        
        # Clean markdown wrappers if any
        if text_content.startswith("```"):
            text_content = re.sub(r'^```(?:json)?\n', '', text_content)
            text_content = re.sub(r'\n```$', '', text_content)
        text_content = text_content.strip()
        
        return json.loads(text_content)
    except Exception as e:
        log(f"[x] Lỗi gọi Gemini để trích xuất text metadata: {e}")
        return {"error": str(e)}

def scrape_shopee_metadata(url, log_callback=None):
    """
    Cào thẻ tiêu đề và mô tả từ link Shopee bằng requests.
    Có fallback lấy từ URL nếu bị chặn Cloudflare.
    """
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    log("[*] Đang kết nối tới Shopee để lấy thông tin sản phẩm...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    }
    
    title = ""
    description = ""
    
    try:
        # Tải HTML
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            html = r.text
            # Regex tìm tiêu đề và mô tả SEO
            title_match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            og_title_match = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            og_desc_match = re.search(r'<meta\s+(?:property|name)=["\'](?:og:)?description["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
            
            if og_title_match:
                title = og_title_match.group(1)
            elif title_match:
                title = title_match.group(1)
                
            if og_desc_match:
                description = og_desc_match.group(1)
                
            # Clean title
            title = re.sub(r'\s*\|\s*Shopee.*', '', title).strip()
            
    except Exception as e:
        log(f"[!] Gặp lỗi kết nối mạng Shopee: {e}")
        
    # FALLBACK: Nếu không cào được tiêu đề từ HTML (do Cloudflare), phân tích từ chính URL
    if not title:
        log("[!] Không cào được HTML trực tiếp (do chặn bot). Đang cố gắng lấy tên từ link URL...")
        parsed_url = urllib.parse.urlparse(url)
        path_parts = [p for p in parsed_url.path.split('/') if p]
        
        # Shopee URL thường có dạng shopee.vn/Tên-Sản-Phẩm-i.123.456
        if path_parts:
            slug = path_parts[0]
            # Loại bỏ đuôi ID i.xxxx.xxxx ở cuối nếu có
            slug_clean = re.sub(r'-i\.\d+\.\d+$', '', slug)
            # Thay thế dấu gạch ngang bằng khoảng trắng và decode URL
            decoded_slug = urllib.parse.unquote(slug_clean)
            title = decoded_slug.replace('-', ' ')
            log(f"[+] Trích xuất tên sản phẩm từ URL thành công: {title}")
            description = f"Sản phẩm bán chạy trên Shopee Việt Nam tại đường dẫn: {url}"
            
    if not title:
        title = "Sản phẩm Shopee mới"
        description = "Sản phẩm Shopee chưa phân tích được nội dung chi tiết."
        
def verify_material_prerequisites(materials_dir):
    """
    Scans materials_dir for valid product videos or images.
    Returns (is_valid, video_count, image_count, message).
    """
    if not os.path.exists(materials_dir):
        return False, 0, 0, "Thư mục Phoi/ không tồn tại."
        
    valid_video_exts = {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv'}
    valid_image_exts = {'.png', '.jpg', '.jpeg', '.webp'}
    
    video_count = 0
    image_count = 0
    
    for f in os.listdir(materials_dir):
        file_path = os.path.join(materials_dir, f)
        if os.path.isfile(file_path):
            ext = os.path.splitext(f)[1].lower()
            if ext in valid_video_exts:
                video_count += 1
            elif ext in valid_image_exts:
                image_count += 1
                
    total = video_count + image_count
    if total > 0:
        return True, video_count, image_count, f"Tìm thấy {video_count} video phôi và {image_count} ảnh sản phẩm HD."
    else:
        return False, 0, 0, "Không tải được bất kỳ video phôi hay hình ảnh sản phẩm hợp lệ nào."

def run_auto_pipeline(url, log_callback=None):
    """
    Quy trình tự động hóa 1-click toàn diện:
    1. Cào / tải dữ liệu từ URL.
    2. Dùng AI phân tích sản phẩm và tạo dự án.
    3. Tải phôi video (hoặc dùng video tải về).
    4. Tự động cắt phôi thành clip 9:16 dọc và phân tích chất lượng.
    5. Tự động viết kịch bản.
    """
    def log(msg):
        if log_callback: log_callback(msg)
        else: print(msg)

    log(f"[*] BẮT ĐẦU QUY TRÌNH TỰ ĐỘNG HÓA 1-CLICK CHO LINK: {url}")
    url_lower = url.lower()
    
    is_tiktok = "tiktok.com" in url_lower
    is_shopee = "shopee.vn" in url_lower or "shopee.com" in url_lower
    
    pm = ProjectManager()
    product_meta = {}
    temp_video_path = None
    
    # === BƯỚC 1: CÀO & PHÂN TÍCH THÔNG TIN SẢN PHẨM BẰNG AI ===
    if is_tiktok:
        log("[*] Phát hiện link TikTok. Đang tải video TikTok về máy để phân tích...")
        temp_dir = os.path.join(os.getcwd(), "projects", "temp_auto_dl")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Tải video
        temp_video_path = download_video(
            url=url,
            output_dir=temp_dir,
            audio_only=False,
            max_duration=120, # Giới hạn tối đa 2 phút
            log_callback=log
        )
        
        if not temp_video_path or not os.path.exists(temp_video_path):
            return {"error": "Không thể tải video TikTok làm phôi."}
            
        log(f"[+] Tải video TikTok thành công: {os.path.basename(temp_video_path)}")
        log("[*] Đang gửi video lên Gemini Vision để tự động trích xuất thông tin sản phẩm...")
        
        prompt = """
Hãy xem kỹ video review sản phẩm này và trích xuất thông tin chi tiết dưới dạng JSON sau (vui lòng trả về chuỗi JSON thô, không bọc trong ký hiệu markdown ```json):
{
  "product_name": "Tên sản phẩm chính xác, viết hoa chữ đầu (Ví dụ: Giá Đỡ Điện Thoại Xoay 360)",
  "description": "Mô tả sản phẩm tóm tắt 2-3 câu ngắn gọn",
  "price": "Giá bán sản phẩm nếu có nhắc đến, hoặc ước lượng (Ví dụ: 99.000 VNĐ, hoặc N/A)",
  "selling_points": "Gạch đầu dòng 2-3 điểm bán hàng cốt lõi (USP) nổi bật nhất của sản phẩm",
  "target_audience": "Khách hàng mục tiêu của sản phẩm này",
  "pain_points": "Nỗi đau/vấn đề của khách hàng mà sản phẩm giải quyết",
  "keywords": ["từ khóa tiếng Anh 1", "từ khóa tiếng Anh 2", "từ khóa tiếng Anh 3"]
}
"""
        analysis_result = analyze_video(filepath=temp_video_path, prompt_text=prompt, log_callback=log)
        
        # Dọn dẹp markdown code blocks nếu có
        clean_json = analysis_result.strip()
        if clean_json.startswith("```"):
            clean_json = re.sub(r'^```(?:json)?\n', '', clean_json)
            clean_json = re.sub(r'\n```$', '', clean_json)
        clean_json = clean_json.strip()
        
        try:
            product_meta = json.loads(clean_json)
        except Exception as e:
            log(f"[!] Lỗi phân tích JSON từ Gemini Vision: {e}. Sử dụng dữ liệu fallback.")
            product_meta = {
                "product_name": f"Dự án TikTok {int(os.path.getmtime(temp_video_path))}",
                "description": "Video review sản phẩm tải từ TikTok.",
                "price": "N/A",
                "selling_points": "Review trực quan sinh động",
                "target_audience": "Người dùng TikTok",
                "pain_points": "Cần tìm phôi video UGC thực tế",
                "keywords": ["gadgets", "tiktok reviews", "cool products"]
            }
            
    elif is_shopee:
        log("[*] Phát hiện link Shopee. Đang cào thông tin trang sản phẩm...")
        title, description = scrape_shopee_metadata(url, log_callback=log)
        log(f"[+] Đã lấy được thông tin sơ bộ: Title = '{title[:40]}...'")
        log("[*] Đang gửi thông tin cho Gemini AI để tối ưu hóa thuộc tính sản phẩm...")
        
        extracted = extract_metadata_from_text(title, description, log_callback=log)
        if "error" in extracted:
            return {"error": f"Lỗi AI phân tích thông tin Shopee: {extracted['error']}"}
        product_meta = extracted
        
    else:
        # Link không xác định, sử dụng AI phân tích từ URL
        log("[!] Link không thuộc TikTok hay Shopee. Đang thử phân tích tên từ URL...")
        title = url.split('/')[-1] or "Dự án mới"
        product_meta = {
            "product_name": title.replace('-', ' ').replace('_', ' ')[:30],
            "description": f"Dự án tự động tạo từ link: {url}",
            "price": "N/A",
            "selling_points": "Tự động phân tích",
            "target_audience": "Khách hàng mua online",
            "pain_points": "Tiện ích tiêu dùng",
            "keywords": ["gadgets", "home tools", "creative items"]
        }

    # === BƯỚC 2: KHỞI TẠO DỰ ÁN MỚI ===
    prod_name = product_meta.get("product_name", "San pham moi").strip()
    log(f"\n[*] Đang tiến hành tạo dự án mới: '{prod_name}'...")
    
    project_path, slug = pm.initialize_project(
        product_name=prod_name,
        description=product_meta.get("description", ""),
        price=product_meta.get("price", "N/A"),
        selling_points=product_meta.get("selling_points", ""),
        target_audience=product_meta.get("target_audience", ""),
        pain_points=product_meta.get("pain_points", "")
    )
    
    folders = pm.get_project_folders(slug)
    log(f"[+] Thư mục dự án đã tạo tại: {project_path}")

    # Cập nhật keywords cào được vào metadata
    meta = pm.get_metadata(slug)
    meta["keywords"] = {
        "manual": product_meta.get("keywords", ["gadget"]),
        "vi": [],
        "en": [],
        "zh": []
    }
    pm.save_metadata(slug, meta)

    # === BƯỚC 3: TẢI VIDEO PHÔI GỐC ===
    if is_tiktok and temp_video_path and os.path.exists(temp_video_path):
        log("\n[*] Đang chuyển video TikTok tải về vào thư mục phôi của dự án...")
        dest_video = os.path.join(folders["materials"], os.path.basename(temp_video_path))
        shutil.move(temp_video_path, dest_video)
        log(f"[+] Đã di chuyển phôi video gốc thành công: {os.path.basename(dest_video)}")
        # Xóa folder tạm
        try: shutil.rmtree(os.path.dirname(temp_video_path))
        except Exception: pass
        
    else:
        # Nếu là Shopee hoặc nguồn khác, cào tài nguyên thực tế từ Shopee, MXH & Web
        log("\n[*] Đang tiến hành khai thác tài nguyên phôi chuẩn sản phẩm (Ảnh HD & Video thực tế)...")
        smart_keys = extract_smart_keywords(prod_name)
        search_terms = smart_keys + product_meta.get("keywords", [])
        
        # 1. Cào bộ ảnh HD & video từ Shopee
        if is_shopee:
            log("[*] Đang cào bộ sưu tập ảnh sản phẩm HD & video mô tả từ Shopee...")
            search_query = smart_keys[0] if smart_keys else prod_name
            search_and_download_shopee(search_query, folders["materials"], limit=4, download_images=True, download_videos=True, log_callback=log)
            
        # 2. Cào video review thực tế từ TikTok / Bilibili / Shorts
        log("[*] Đang tìm cào video review thực tế trên TikTok / Bilibili / Shorts...")
        for term in search_terms[:2]:
            search_and_download_social(term, folders["materials"], limit=3, log_callback=log)
            
        # 3. Cào bổ sung ảnh sản phẩm HD từ Web
        log("[*] Đang cào bổ sung bộ sưu tập ảnh sản phẩm HD từ Google Product Search...")
        for term in search_terms[:2]:
            search_and_download_product_images(term, folders["materials"], limit=3, log_callback=log)
    # === BƯỚC 3.5: SO SÁNH ĐỘ TƯƠNG ĐỒNG VỚI ẢNH MẪU SẢN PHẨM (NẾU CÓ) ===
    ref_path = meta.get("reference_image") or os.path.join(folders.get("reference", ""), "reference_image.png")
    if not os.path.exists(ref_path) and folders.get("reference"):
        for ref_f in os.listdir(folders["reference"]):
            if os.path.splitext(ref_f)[1].lower() in {'.png', '.jpg', '.jpeg', '.webp'}:
                ref_path = os.path.join(folders["reference"], ref_f)
                break
                
    if os.path.exists(ref_path):
        log(f"\n[*] Phát hiện ảnh mẫu sản phẩm: {os.path.basename(ref_path)}. Tiến hành đối soát hình ảnh OpenCV...")
        filter_materials_by_reference(folders["materials"], ref_path, threshold=28.0, log_callback=log)

    # === BƯỚC 3.6: KIỂM TRA ĐIỀU KIỆN TIÊN QUYẾT TÀI NGUYÊN (STRICT VALIDATION) ===
    is_valid, v_cnt, img_cnt, msg = verify_material_prerequisites(folders["materials"])
    if not is_valid:
        log("\n" + "="*50)
        log("[x] 🛑 DỪNG QUY TRÌNH TỰ ĐỘNG: KIỂM TRA THẤT BẠI!")
        log(f"[x] Lý do: {msg}")
        log("[!] Hệ thống không thể triển khai bước cắt phôi hay viết kịch bản khi chưa có tài nguyên sản phẩm.")
        log("[!] Vui lòng kiểm tra lại đường link URL, kết nối mạng hoặc thử dán ảnh sản phẩm thủ công vào thư mục Phoi/.")
        log("="*50)
        return {
            "error": msg,
            "stopped_at": "materials",
            "project_slug": slug
        }

    # === BƯỚC 4: TỰ ĐỘNG CẮT PHÔI THÀNH CLIP 9:16 DỌC & REVIEW CHẤT LƯỢNG ===
    log(f"\n[*] {msg} Tiến hành tự động quét thư mục phôi và cắt thành các clips 2.0 giây...")
    new_clips = cut_materials_into_clips(
        materials_dir=folders["materials"],
        clips_dir=folders["clips"],
        product_slug=slug,
        clip_duration=2.0,
        skip_start_seconds=1.0,
        max_clips_per_video=6,
        export_vertical=True,
        mute_audio=True,
        analyze_quality=True,
        reject_bad_clips=False, # Không xóa hoàn toàn, giữ lại trong thư mục nhưng tag status
        progress_callback=log
    )
    log(f"[+] Cắt phôi hoàn thành! Đã tạo được {len(new_clips)} clip phôi.")
    
    # Cập nhật metadata clips
    meta = pm.get_metadata(slug)
    meta["clips"] = new_clips
    pm.save_metadata(slug, meta)

    # === BƯỚC 5: TỰ ĐỘNG VIẾT KỊCH BẢN MỚI BẰNG AI ===
    log("\n[*] Đang tự động tạo kịch bản thuyết minh TikTok mới bằng AI Gemini...")
    script_res = generate_script(
        product_name=prod_name,
        description=product_meta.get("description", ""),
        price=product_meta.get("price", "N/A"),
        selling_points=product_meta.get("selling_points", ""),
        target_audience=product_meta.get("target_audience", ""),
        pain_points=product_meta.get("pain_points", ""),
        style="Mở đầu tò mò"
    )
    
    if "error" in script_res:
        log(f"[!] Cảnh báo: AI không tự viết được kịch bản: {script_res['error']}")
    else:
        # Lưu file kịch bản
        save_script_files(folders["scripts"], script_res)
        
        # Cập nhật metadata kịch bản
        meta = pm.get_metadata(slug)
        meta["scripts"] = {
            "style": "Mở đầu tò mò",
            "voice_script": script_res["voice_script"],
            "caption": script_res["caption"],
            "hashtags": script_res["hashtags"]
        }
        pm.save_metadata(slug, meta)
        log("[+] Đã tự động tạo kịch bản chi tiết và caption/hashtags.")

    log("\n" + "="*50)
    log(f"[+] QUY TRÌNH HOÀN THÀNH MỸ MÃN! DỰ ÁN MỚI: {slug}")
    log("="*50)
    
    return {"success": True, "slug": slug, "product_name": prod_name}
