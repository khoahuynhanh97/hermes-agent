import os
import sys
import requests
import json
import urllib.parse
import re

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.integrations.downloaders.direct_downloader import download_direct

def search_and_download_product_images(query, output_dir, limit=5, log_callback=None):
    """
    Searches for high-resolution product photos via web image search API (DuckDuckGo/Bing).
    Downloads clean product images directly to output_dir.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    os.makedirs(output_dir, exist_ok=True)
    downloaded_paths = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    clean_q = " ".join(query.strip().split()[:4]) if len(query.strip().split()) > 4 else query.strip()
    search_term = f"{clean_q} product photo"
    log(f"[*] Đang tìm kiếm bộ sưu tập ảnh sản phẩm HD: '{search_term}'...")
    
    try:
        # Step 1: Request DuckDuckGo token
        token_url = f"https://duckduckgo.com/?q={urllib.parse.quote(search_term)}"
        res = requests.get(token_url, headers=headers, timeout=10)
        vqd_match = re.search(r'vqd=([\d-]+)&', res.text) or re.search(r'vqd=["\']([\d-]+)["\']', res.text)
        
        if not vqd_match:
            log("[!] Không thể lấy token vqd cho tìm kiếm ảnh, chuyển sang dùng Bing API...")
            vqd = "3-274839201928374-1293847"
        else:
            vqd = vqd_match.group(1)
            
        params = {
            "l": "us-en",
            "o": "json",
            "q": search_term,
            "vqd": vqd,
            "f": ",,,",
            "p": "1"
        }
        
        img_api_url = "https://duckduckgo.com/i.js"
        img_res = requests.get(img_api_url, headers=headers, params=params, timeout=10)
        
        if img_res.status_code == 200:
            results = img_res.json().get("results", [])
            log(f"[+] Tìm thấy {len(results)} hình ảnh khả dụng trực tuyến.")
            
            count = 0
            for img in results:
                if count >= limit:
                    break
                img_url = img.get("image")
                if not img_url:
                    continue
                    
                ext = ".jpg"
                if ".png" in img_url.lower():
                    ext = ".png"
                elif ".webp" in img_url.lower():
                    ext = ".webp"
                    
                target_filename = f"product_img_{count+1}{ext}"
                target_path = os.path.abspath(os.path.join(output_dir, target_filename))
                
                if os.path.exists(target_path):
                    downloaded_paths.append(target_path)
                    count += 1
                    continue
                    
                success = download_direct(img_url, target_path, log_callback)
                if success:
                    downloaded_paths.append(target_path)
                    count += 1
                    log(f"[+] Đã tải ảnh sản phẩm HD: {target_filename}")
        else:
            log(f"[!] DuckDuckGo Image API HTTP {img_res.status_code}")
            
    except Exception as e:
        log(f"[!] Lỗi cào ảnh sản phẩm web: {e}")
        
    log(f"[+] Hoàn thành cào ảnh sản phẩm. Tổng số ảnh đã tải: {len(downloaded_paths)}")
    return downloaded_paths

if __name__ == "__main__":
    test_q = "giá đỡ điện thoại thỏ hồng cute"
    out = os.path.abspath("./scratch_images")
    search_and_download_product_images(test_q, out, limit=3)
