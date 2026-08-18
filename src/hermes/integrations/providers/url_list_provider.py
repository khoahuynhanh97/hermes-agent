import os
from hermes.integrations.downloaders.direct_downloader import download_direct
from hermes.integrations.downloaders.ytdlp_downloader import download_with_ytdlp
from hermes.application.core.file_manager import clean_filename

def download_url_list(urls_list, output_dir, browser_cookies=None, log_callback=None):
    """
    Downloads videos from a list of URLs.
    Checks if a URL points directly to an MP4 file or needs yt-dlp.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    downloaded_paths = []
    
    # Filter empty lines
    urls = [u.strip() for u in urls_list if u.strip()]
    log(f"[*] Bắt đầu tải danh sách {len(urls)} URLs...")
    
    for idx, url in enumerate(urls):
        log(f"\n[*] Đang xử lý URL ({idx + 1}/{len(urls)}): {url}")
        
        # Check if URL ends with standard video extension
        is_direct = any(ext in url.lower() for ext in ['.mp4', '.mkv', '.mov', '.avi', '.webm']) or "direct_media" in url
        
        if is_direct:
            filename = f"url_direct_{idx}_{clean_filename(url[-15:])}.mp4"
            target_path = os.path.abspath(os.path.join(output_dir, filename))
            
            if os.path.exists(target_path):
                log(f"[*] Đã tồn tại phôi: {filename}")
                downloaded_paths.append(target_path)
                continue
                
            success = download_direct(url, target_path, log_callback)
            if success:
                downloaded_paths.append(target_path)
        else:
            # Platform URLs like TikTok/YouTube/Douyin
            res_path = download_with_ytdlp(url, output_dir, browser_cookies=browser_cookies, log_callback=log_callback)
            if res_path and os.path.exists(res_path):
                downloaded_paths.append(res_path)
                
    return downloaded_paths
