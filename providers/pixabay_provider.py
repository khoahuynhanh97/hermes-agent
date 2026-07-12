import os
import sys
import requests

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config
from downloaders.direct_downloader import download_direct

def search_and_download_pixabay(query, output_dir, limit=5, max_duration=60, log_callback=None):
    """
    Searches Pixabay Video API for query.
    Downloads matching videos to output_dir.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    api_key = getattr(config, "PIXABAY_API_KEY", "")
    if not api_key:
        log("[!] Bỏ qua Pixabay: Chưa cấu hình PIXABAY_API_KEY trong .env")
        return []

    # Prepare query (must be urlencoded and spaces replaced with +)
    encoded_query = requests.utils.quote(query.replace(' ', '+'))
    url = f"https://pixabay.com/api/videos/?key={api_key}&q={encoded_query}&per_page={limit*2}"
    
    try:
        log(f"[*] Đang tìm kiếm trên Pixabay: '{query}'...")
        response = requests.get(url, timeout=15)
        
        if response.status_code != 200:
            log(f"[!] Lỗi Pixabay API (HTTP {response.status_code}): {response.text}")
            return []
            
        data = response.json()
        hits = data.get("hits", [])
        log(f"[+] Tìm thấy {len(hits)} video thô trên Pixabay.")
        
        downloaded_paths = []
        count = 0
        
        for hit in hits:
            if count >= limit:
                break
                
            duration = hit.get("duration", 0)
            if max_duration and duration > max_duration:
                continue
                
            # Grab the best available video resolution link (medium is usually good: 1280x720)
            videos_dict = hit.get("videos", {})
            download_url = None
            
            # Prefer medium, then small, then large, then tiny
            for size in ['medium', 'small', 'large', 'tiny']:
                if size in videos_dict and videos_dict[size].get('url'):
                    download_url = videos_dict[size].get('url')
                    break
                    
            if not download_url:
                continue
                
            video_id = hit.get("id")
            filename = f"pixabay_{query.replace(' ', '_')}_{video_id}.mp4"
            target_path = os.path.abspath(os.path.join(output_dir, filename))
            
            # Skip if already downloaded
            if os.path.exists(target_path):
                log(f"[*] Đã tồn tại phôi: {filename}")
                downloaded_paths.append(target_path)
                count += 1
                continue
                
            success = download_direct(download_url, target_path, log_callback)
            if success:
                downloaded_paths.append(target_path)
                count += 1
                
        return downloaded_paths
        
    except Exception as e:
        log(f"[x] Lỗi tìm kiếm/tải video Pixabay: {e}")
        return []
