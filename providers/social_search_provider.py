import os
import sys
import yt_dlp

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class YDLLogger:
    def __init__(self, callback):
        self.callback = callback
    def debug(self, msg):
        pass
    def info(self, msg):
        if self.callback:
            self.callback(msg)
    def warning(self, msg):
        if self.callback:
            self.callback(f"[!] {msg}")
    def error(self, msg):
        if self.callback:
            self.callback(f"[x] {msg}")

def search_and_download_social(query, output_dir, limit=5, max_duration=60, vertical_only=True, browser_cookies=None, log_callback=None):
    """
    Searches social video platforms (Bilibili, YouTube Shorts, TikTok) for product review query using yt-dlp.
    Downloads matching vertical/product clips to output_dir with pre-filtering.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    os.makedirs(output_dir, exist_ok=True)
    downloaded_paths = []
    
    # Refine search queries to target review/unboxing product clips
    review_query = f"{query} review unboxing" if "review" not in query.lower() else query
    
    search_targets = [
        ("Bilibili Product Review", f"bilibilisearch{limit}:{query}"),
        ("YouTube Shorts Review", f"ytsearch{limit}:{review_query}")
    ]
    
    for platform_name, search_url in search_targets:
        log(f"[*] Đang tìm kiếm video phôi thực tế trên {platform_name}: '{query}'...")
        
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(output_dir, f'social_%(id)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        if log_callback:
            ydl_opts['logger'] = YDLLogger(log_callback)

        # Configure browser cookies
        if browser_cookies and str(browser_cookies).lower() != "không dùng cookie":
            bname = str(browser_cookies).lower().strip()
            valid_browsers = {'chrome', 'edge', 'firefox', 'opera', 'safari', 'brave', 'vivaldi'}
            if bname in valid_browsers:
                ydl_opts['cookiesfrombrowser'] = (bname,)
                log(f"[*] yt-dlp đang dùng cookie từ trình duyệt: {bname}")

        # Smart vertical format and max duration pre-filtering
        def make_pre_filter(max_dur, vert_only):
            def pre_filter(info, *, incomplete):
                duration = info.get('duration')
                if duration and max_dur and duration > max_dur:
                    return f'Video too long ({duration}s > {max_dur}s limit)'
                    
                if vert_only:
                    width = info.get('width')
                    height = info.get('height')
                    if width and height and width >= height:
                        return f'Not a vertical video (Landscape: {width}x{height})'
                return None
            return pre_filter

        ydl_opts['match_filter'] = make_pre_filter(max_duration, vertical_only)
            
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(search_url, download=True)
                entries = info.get('entries', []) if 'entries' in info else [info]
                
                for entry in entries:
                    if not entry:
                        continue
                    filepath = ydl.prepare_filename(entry)
                    basename, ext = os.path.splitext(filepath)
                    if ext != ".mp4" and os.path.exists(basename + ".mp4"):
                        filepath = basename + ".mp4"
                        
                    if os.path.exists(filepath):
                        abs_path = os.path.abspath(filepath)
                        if abs_path not in downloaded_paths:
                            downloaded_paths.append(abs_path)
                            log(f"[+] Tải thành công phôi video MXH ({platform_name}): {os.path.basename(abs_path)}")
                            
        except Exception as e:
            log(f"[!] Lỗi tìm kiếm trên {platform_name}: {e}")
            
    log(f"[+] Hoàn thành cào MXH. Tổng số phôi đã lấy: {len(downloaded_paths)}")
    return downloaded_paths


if __name__ == "__main__":
    test_query = "giá đỡ điện thoại cute"
    out = os.path.abspath("./scratch_social")
    search_and_download_social(test_query, out, limit=2)
