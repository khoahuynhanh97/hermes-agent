import os
import sys
import requests
import urllib.parse

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.integrations.downloaders.direct_downloader import download_direct
from hermes.integrations.providers.smart_crawler_provider import get_browser_cookies

def search_and_download_shopee(query, output_dir, limit=5, download_images=True, download_videos=True, browser_cookies=None, log_callback=None):
    """
    Searches Shopee for product query, extracts product videos and high-res gallery images from shops,
    and downloads direct MP4/JPG files to output_dir with browser cookie support.
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
        "Referer": "https://shopee.vn/",
        "Accept": "application/json"
    }
    
    # Extract browser cookies if provided
    cookies = {}
    if browser_cookies:
        cookies = get_browser_cookies(browser_cookies, "shopee.vn", log_callback=log)
    
    clean_query = " ".join(query.strip().split()[:4]) if len(query.strip().split()) > 4 else query.strip()
    encoded_query = urllib.parse.quote(clean_query)
    search_url = f"https://shopee.vn/api/v4/search/search_items?by=relevance&keyword={encoded_query}&limit=20&newest=0&order=desc&page_type=search&scenario=PAGE_GLOBAL_SEARCH&version=2"
    
    try:
        log(f"[*] Đang tìm kiếm tài nguyên sản phẩm Shopee: '{clean_query}'...")
        response = requests.get(search_url, headers=headers, cookies=cookies, timeout=15)
        
        if response.status_code != 200:
            log(f"[!] Shopee API trả về mã lỗi HTTP {response.status_code}")
            return []
            
        data = response.json()
        items = data.get("items", []) or data.get("data", {}).get("item_card", {}).get("items", [])
        log(f"[+] Tìm thấy {len(items)} gian hàng sản phẩm liên quan trên Shopee.")
        
        video_count = 0
        image_count = 0
        
        for item_data in items:
            if video_count >= limit and image_count >= limit:
                break
                
            item_basic = item_data.get("item_basic", {}) or item_data
            item_id = item_basic.get("itemid")
            shop_id = item_basic.get("shopid")
            
            if not item_id or not shop_id:
                continue
                
            # Query item detail to get video_info_list and images
            detail_url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}"
            try:
                detail_res = requests.get(detail_url, headers=headers, cookies=cookies, timeout=10)
                if detail_res.status_code == 200:
                    detail_data = detail_res.json().get("data", {})

                    
                    # 1. Download Videos
                    if download_videos and video_count < limit:
                        video_list = detail_data.get("video_info_list", [])
                        for video in video_list:
                            video_url = video.get("default_format", {}).get("url") or video.get("url")
                            video_id = video.get("video_id")
                            if not video_url and video_id:
                                video_url = f"https://cvf.shopee.vn/{video_id}"
                                
                            if video_url:
                                target_filename = f"shopee_{item_id}_v{video_count+1}.mp4"
                                target_path = os.path.abspath(os.path.join(output_dir, target_filename))
                                
                                if os.path.exists(target_path):
                                    downloaded_paths.append(target_path)
                                    video_count += 1
                                    break
                                    
                                log(f"[*] Đang tải phôi video Shopee từ Shop ID {shop_id}...")
                                success = download_direct(video_url, target_path, log_callback)
                                if success:
                                    downloaded_paths.append(target_path)
                                    video_count += 1
                                    break
                                    
                    # 2. Download High-Res Gallery Images
                    if download_images and image_count < limit:
                        images = detail_data.get("images", [])
                        for img_hash in images[:2]: # Top 2 images per product
                            if image_count >= limit:
                                break
                            img_url = f"https://down-vn.img.susercontent.com/file/{img_hash}"
                            target_filename = f"shopee_{item_id}_img{image_count+1}.jpg"
                            target_path = os.path.abspath(os.path.join(output_dir, target_filename))
                            
                            if os.path.exists(target_path):
                                downloaded_paths.append(target_path)
                                image_count += 1
                                continue
                                
                            success = download_direct(img_url, target_path, log_callback)
                            if success:
                                downloaded_paths.append(target_path)
                                image_count += 1
                                log(f"[+] Đã tải ảnh sản phẩm HD Shopee: {target_filename}")

            except Exception as item_err:
                continue
                
        log(f"[+] Hoàn thành cào Shopee. Tổng số phôi đã tải: {len(downloaded_paths)}")
        return downloaded_paths
        
    except Exception as e:
        log(f"[x] Lỗi tìm kiếm/tải tài nguyên Shopee: {e}")
        return []

if __name__ == "__main__":
    test_q = "giá đỡ điện thoại cute"
    out = os.path.abspath("./scratch_shopee")
    search_and_download_shopee(test_q, out, limit=2)
