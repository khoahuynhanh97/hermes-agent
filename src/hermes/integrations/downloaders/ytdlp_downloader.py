import os
import re
import yt_dlp

class YDLLogger:
    def __init__(self, callback):
        self.callback = callback
    def debug(self, msg):
        # Prevent logging cookies or sensitive headers
        if "cookie" not in msg.lower() and "token" not in msg.lower():
            self.callback(msg)
    def info(self, msg):
        if "cookie" not in msg.lower():
            self.callback(msg)
    def warning(self, msg):
        if "cookie" not in msg.lower():
            self.callback(f"[!] {msg}")
    def error(self, msg):
        if "cookie" not in msg.lower():
            self.callback(f"[x] {msg}")

def download_with_ytdlp(url, output_dir, max_duration=None, browser_cookies=None, log_callback=None):
    """
    Downloads a video from public sites using yt-dlp.
    - browser_cookies: Name of browser (e.g. 'chrome', 'edge', 'firefox') or None. Cookies are ONLY loaded if specified.
    - max_duration: Max duration in seconds to download (skip if longer).
    """
    os.makedirs(output_dir, exist_ok=True)
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    # Setup safe logger
    if log_callback:
        ydl_opts['logger'] = YDLLogger(log_callback)
    
    # Configure browser cookies only if explicitly requested
    if browser_cookies and browser_cookies.lower() != "không dùng cookie":
        # Safe lookup: only use browser name, clean up just in case
        browser_name = browser_cookies.lower().strip()
        # Acceptable browser types in yt-dlp: chrome, edge, firefox, opera, safari, brave, vivaldi
        valid_browsers = {'chrome', 'edge', 'firefox', 'opera', 'safari', 'brave', 'vivaldi'}
        if browser_name in valid_browsers:
            log(f"[*] Sử dụng cookie từ trình duyệt: {browser_name}")
            ydl_opts['cookiesfrombrowser'] = (browser_name,)
        else:
            log(f"[!] Trình duyệt cookie không hợp lệ: {browser_name}. Bỏ qua sử dụng cookie.")
            
    if max_duration:
        ydl_opts['match_filter'] = lambda info, *, incomplete: None if info.get('duration') and info.get('duration') <= max_duration else 'Video too long'

    try:
        log(f"[*] Đang tải link qua yt-dlp: {url}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if 'entries' in info:
                # If playlist, just get the first one
                info = info['entries'][0]
            filename = ydl.prepare_filename(info)
            # Handle postprocessing format merge filename
            base, ext = os.path.splitext(filename)
            final_filename = base + ".mp4"
            
            if os.path.exists(final_filename):
                log(f"[+] Tải thành công: {final_filename}")
                return os.path.abspath(final_filename)
            elif os.path.exists(filename):
                log(f"[+] Tải thành công: {filename}")
                return os.path.abspath(filename)
            else:
                # Search directory for file starting with title
                title = info.get('title', '')
                if title:
                    safe_title = re.sub(r'[\\/*?:"<>|]', '', title)
                    for file in os.listdir(output_dir):
                        if safe_title in file or file.endswith('.mp4'):
                            full_p = os.path.join(output_dir, file)
                            log(f"[+] Tìm thấy file đã tải: {full_p}")
                            return os.path.abspath(full_p)
                log("[!] Tải thành công nhưng không xác định được file cụ thể.")
                return None
    except Exception as e:
        log(f"[x] Lỗi yt-dlp: {e}")
        return None
