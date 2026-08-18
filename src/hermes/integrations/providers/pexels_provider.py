import os
import sys
import requests

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config
from hermes.integrations.downloaders.direct_downloader import download_direct

def search_and_download_pexels(query, output_dir, limit=5, max_duration=60, log_callback=None):
    """
    Searches Pexels Video API for query.
    Downloads matching vertical videos to output_dir.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    api_key = getattr(config, "PEXELS_API_KEY", "")
    if not api_key:
        log("[!] Bỏ qua Pexels: Chưa cấu hình PEXELS_API_KEY trong .env")
        return []

    url = f"https://api.pexels.com/videos/search?query={requests.utils.quote(query)}&per_page={limit*2}&orientation=portrait"
    headers = {"Authorization": api_key}
    
    try:
        log(f"[*] Đang tìm kiếm trên Pexels: '{query}'...")
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            log(f"[!] Lỗi Pexels API (HTTP {response.status_code}): {response.text}")
            return []
            
        data = response.json()
        videos = data.get("videos", [])
        log(f"[+] Tìm thấy {len(videos)} video thô trên Pexels.")
        
        downloaded_paths = []
        count = 0
        
        for video in videos:
            if count >= limit:
                break
                
            duration = video.get("duration", 0)
            if max_duration and duration > max_duration:
                continue
                
            # Find the best MP4 file (usually hd or sd)
            video_files = video.get("video_files", [])
            download_url = None
            for file in video_files:
                file_type = file.get("file_type", "")
                if "video/mp4" in file_type or file.get("link", "").endswith(".mp4"):
                    download_url = file.get("link")
                    break
                    
            if not download_url:
                continue
                
            video_id = video.get("id")
            filename = f"pexels_{query.replace(' ', '_')}_{video_id}.mp4"
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
        log(f"[x] Lỗi tìm kiếm/tải video Pexels: {e}")
        return []
