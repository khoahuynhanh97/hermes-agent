import os
import csv
import json
from hermes.integrations.downloaders.direct_downloader import download_direct
from hermes.integrations.downloaders.ytdlp_downloader import download_with_ytdlp
from hermes.application.core.file_manager import clean_filename

def parse_supplier_feed(file_path):
    """
    Parses a CSV or JSON feed file.
    Returns a list of dictionaries with standard columns:
    product_name, keyword, title, platform, source_url, direct_media_url, video_url, etc.
    """
    items = []
    if not os.path.exists(file_path):
        return items
        
    ext = os.path.splitext(file_path)[1].lower()
    
    if ext == '.csv':
        try:
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    items.append(dict(row))
        except Exception as e:
            print(f"[x] Lỗi đọc Supplier Feed CSV: {e}")
            
    elif ext == '.json':
        try:
            with open(file_path, mode='r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict) and "items" in data:
                    items = data["items"]
        except Exception as e:
            print(f"[x] Lỗi đọc Supplier Feed JSON: {e}")
            
    return items

def run_supplier_feed_provider(feed_file_path, product_name, output_dir, keywords_list=None, log_callback=None):
    """
    Processes the supplier feed file for a product.
    Finds matching entries, extracts video links, and downloads them.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    items = parse_supplier_feed(feed_file_path)
    if not items:
        log(f"[!] Không tìm thấy dữ liệu hoặc lỗi file Supplier Feed: {feed_file_path}")
        return []

    log(f"[*] Đang quét feed với {len(items)} dòng để tìm phôi cho '{product_name}'...")
    
    # Matching terms (lowercase)
    match_terms = {product_name.lower()}
    if keywords_list:
        for kw in keywords_list:
            match_terms.add(kw.lower())

    matching_items = []
    for row in items:
        prod_name_val = str(row.get('product_name', '')).lower()
        keyword_val = str(row.get('keyword', '')).lower()
        title_val = str(row.get('title', '')).lower()
        
        # Check if product name or keywords match any fields in the row
        matched = False
        for term in match_terms:
            if term in prod_name_val or term in keyword_val or term in title_val:
                matched = True
                break
                
        if matched:
            matching_items.append(row)

    log(f"[+] Tìm thấy {len(matching_items)} dòng phù hợp trong feed.")
    downloaded_paths = []
    
    for idx, row in enumerate(matching_items):
        # 1. Map columns as requested
        direct_url = row.get('direct_media_url', '')
        video_url = row.get('video_url', '')
        source_url = row.get('source_url', '')
        title = row.get('title', f"feed_video_{idx}")
        
        # Map video_url to direct_media_url if direct_media_url is empty
        if video_url and not direct_url:
            direct_url = video_url
            
        downloadable_url = direct_url if direct_url else source_url
        
        if not downloadable_url:
            log(f"[-] Dòng {idx+1}: Không có link tải hay nguồn tham khảo.")
            continue
            
        # If we only have source_url (no direct media link mapped), log it as reference
        if not direct_url and source_url:
            log(f"[*] Dòng {idx+1}: Chỉ có source_url '{source_url}', lưu làm nguồn tham khảo.")
            # We don't download, just record (can write to metadata later)
            continue
            
        # Download
        safe_title = clean_filename(title)
        filename = f"feed_{safe_title}_{idx}.mp4"
        target_path = os.path.abspath(os.path.join(output_dir, filename))
        
        if os.path.exists(target_path):
            log(f"[*] Đã tồn tại phôi: {filename}")
            downloaded_paths.append(target_path)
            continue
            
        # Select download method based on URL format
        # If it contains static media extension, download directly. Otherwise, try yt-dlp.
        is_direct = any(ext in downloadable_url.lower() for ext in ['.mp4', '.mkv', '.mov', '.avi'])
        
        success = False
        if is_direct:
            success = download_direct(downloadable_url, target_path, log_callback)
            if success:
                downloaded_paths.append(target_path)
        else:
            # Try yt-dlp as fallback
            res = download_with_ytdlp(downloadable_url, output_dir, log_callback=log_callback)
            if res:
                # Rename the file downloaded by yt-dlp to match our target name if necessary
                if os.path.exists(res):
                    try:
                        os.rename(res, target_path)
                        downloaded_paths.append(target_path)
                    except Exception:
                        downloaded_paths.append(res)
                else:
                    downloaded_paths.append(res)
                    
    return downloaded_paths
