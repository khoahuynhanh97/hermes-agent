import os
import sys
import re
import requests
import urllib.parse
import yt_dlp
from pathlib import Path

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config
from hermes.integrations.downloaders.direct_downloader import download_direct
from hermes.video.editor.clip_analyzer import analyze_clip

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

def get_browser_cookies(browser_name, domain="shopee.vn", log_callback=None):
    """
    Trích xuất cookies từ trình duyệt qua yt-dlp để dùng cho requests.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not browser_name or str(browser_name).lower() == "không dùng cookie":
        return {}

    bname = str(browser_name).lower().strip()
    valid_browsers = {'chrome', 'edge', 'firefox', 'opera', 'safari', 'brave', 'vivaldi'}
    if bname not in valid_browsers:
        return {}

    log(f"[*] Đang trích xuất cookie từ trình duyệt: {bname}...")
    try:
        ydl_opts = {
            'cookiesfrombrowser': (bname,),
            'quiet': True,
            'no_warnings': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            cookie_jar = ydl.cookiejar
            session_cookies = {}
            for cookie in cookie_jar:
                if domain in cookie.domain:
                    session_cookies[cookie.name] = cookie.value
            if session_cookies:
                log(f"[+] Trích xuất thành công {len(session_cookies)} cookies Shopee từ {bname}.")
            else:
                log(f"[!] Không tìm thấy cookie Shopee trong trình duyệt {bname}.")
            return session_cookies
    except Exception as e:
        log(f"[!] Không thể trích xuất cookie từ {bname} ({e}). Tiến hành cào không dùng cookie...")
        return {}

def parse_shopee_url(url):
    """
    Parses Shopee URL to extract shopid and itemid.
    """
    m1 = re.search(r'product/(\d+)/(\d+)', url)
    if m1:
        return m1.group(1), m1.group(2)
    m2 = re.search(r'-i\.(\d+)\.(\d+)', url)
    if m2:
        return m2.group(1), m2.group(2)
    return None, None

def fetch_shopee_product_details(shop_id, item_id, browser_cookies=None, log_callback=None):
    """
    Fetches Shopee product details from API v4.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://shopee.vn/",
        "Accept": "application/json"
    }
    detail_url = f"https://shopee.vn/api/v4/item/get?itemid={item_id}&shopid={shop_id}"
    
    # Extract browser cookies if provided
    cookies = {}
    if browser_cookies:
        cookies = get_browser_cookies(browser_cookies, "shopee.vn", log_callback=log)
    
    try:
        log(f"[*] Đang cào thông tin chi tiết Shopee (Shop ID {shop_id}, Item ID {item_id})...")
        res = requests.get(detail_url, headers=headers, cookies=cookies, timeout=15)
        if res.status_code != 200:
            log(f"[x] Không thể cào Shopee API (HTTP {res.status_code})")
            return None
            
        data = res.json().get("data", {})
        if not data:
            log("[x] Dữ liệu Shopee API trống hoặc bị chặn.")
            return None
            
        return {
            "title": data.get("name", ""),
            "description": data.get("description", ""),
            "images": data.get("images", []),
            "video_info_list": data.get("video_info_list", [])
        }
    except Exception as e:
        log(f"[x] Lỗi cào chi tiết Shopee: {e}")
        return None


def search_duckduckgo_urls(query, site_domain, limit=3, log_callback=None):
    """
    Scrapes DuckDuckGo HTML search page to find TikTok or Douyin video URLs.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
            
    search_query = f"site:{site_domain} {query}"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(search_query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    urls = []
    try:
        log(f"[*] Đang tìm kiếm URL {site_domain} trên DuckDuckGo cho từ khóa: '{query}'...")
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            html = r.text
            matches = re.findall(r'uddg=([^&"\']+)', html)
            for m in matches:
                decoded = urllib.parse.unquote(m)
                # Filter for video links
                if site_domain in decoded and ("/video/" in decoded or "/shorts/" in decoded or "/v/" in decoded or "modal_id=" in decoded):
                    if decoded not in urls:
                        urls.append(decoded)
                        if len(urls) >= limit:
                            break
    except Exception as e:
        log(f"[!] Lỗi khi cào DuckDuckGo cho {site_domain}: {e}")

    # Fallback to Yahoo Search if no URLs found
    if not urls:
        try:
            log(f"[*] DuckDuckGo không có kết quả. Chuyển hướng sang Yahoo Search...")
            yahoo_query = f"site:{site_domain} {query}"
            yahoo_url = f"https://search.yahoo.com/search?q={urllib.parse.quote_plus(yahoo_query)}"
            r_yahoo = requests.get(yahoo_url, headers=headers, timeout=15)
            if r_yahoo.status_code == 200:
                yahoo_matches = re.findall(r'href=["\'](https?://r\.search\.yahoo\.com/[^\s"\']*)', r_yahoo.text)
                for l in yahoo_matches:
                    cleaned = urllib.parse.unquote(l)
                    m = re.search(r'RU=(https?://[^\s&]+)', cleaned)
                    if m:
                        real_url = m.group(1)
                        if site_domain in real_url:
                            # Verify it is a valid video/user/clip and not a search or homepage link
                            if "/video/" in real_url or "/shorts/" in real_url or "/v/" in real_url or "modal_id=" in real_url:
                                if real_url not in urls:
                                    urls.append(real_url)
                                    if len(urls) >= limit:
                                        break
        except Exception as e:
            log(f"[!] Lỗi khi cào Yahoo Search cho {site_domain}: {e}")
            
    return urls

def download_video_clean(url, output_dir, prefix="crawler", browser_cookies=None, vertical_only=True, max_duration=120, log_callback=None):
    """
    Downloads video using yt-dlp with pre-filtering for vertical aspect ratio and duration.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
            
    os.makedirs(output_dir, exist_ok=True)
    
    ydl_opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': os.path.join(output_dir, f'{prefix}_%(id)s.%(ext)s'),
        'merge_output_format': 'mp4',
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
    }
    
    if log_callback:
        ydl_opts['logger'] = YDLLogger(log_callback)

    # Configure cookies from browser
    if browser_cookies and str(browser_cookies).lower() != "không dùng cookie":
        bname = str(browser_cookies).lower().strip()
        valid_browsers = {'chrome', 'edge', 'firefox', 'opera', 'safari', 'brave', 'vivaldi'}
        if bname in valid_browsers:
            ydl_opts['cookiesfrombrowser'] = (bname,)
            log(f"[*] yt-dlp đang dùng cookie từ trình duyệt: {bname}")

    # Set up smart pre-filtering for orientation (vertical-only) & duration
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
            log(f"[*] Đang tải video qua yt-dlp: {url}")
            info = ydl.extract_info(url, download=True)
            if 'entries' in info:
                info = info['entries'][0]
            filepath = ydl.prepare_filename(info)
            # Resolve possible merged filename
            basename, ext = os.path.splitext(filepath)
            if ext != ".mp4" and os.path.exists(basename + ".mp4"):
                filepath = basename + ".mp4"
                
            if os.path.exists(filepath):
                abs_path = os.path.abspath(filepath)
                log(f"[+] Tải thành công tệp: {os.path.basename(abs_path)}")
                return abs_path
    except Exception as e:
        log(f"[!] Không thể tải URL {url} qua yt-dlp: {e}")
        
    return None


def apply_quality_filter(filepath, log_callback=None):
    """
    Runs the OpenCV quality analyzer. Deletes file if recommendation is 'Reject'.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    if not filepath or not os.path.exists(filepath):
        return False
        
    log(f"[*] Đang chạy bộ lọc thị giác OpenCV cho phôi: {os.path.basename(filepath)}...")
    res = analyze_clip(filepath)
    rec = res.get("recommendation", "Okay")
    score = res.get("overall_score", 0.0)
    reason = res.get("reason", "")
    
    log(f"  -> Kết quả phân tích: Điểm = {score:.1f} | Xếp loại = {rec} | Lý do: {reason}")
    
    if rec == "Reject":
        log(f"[WARNING] Loại bỏ phôi kém chất lượng: {os.path.basename(filepath)}")
        try:
            os.remove(filepath)
        except Exception as e:
            log(f"[!] Lỗi xóa file chất lượng kém: {e}")
        return False
        
    return True

def split_audio_video(video_path, output_dir_audio, output_dir_video, log_callback=None):
    """
    Splits video into separate audio (.mp3) and silent video (.mp4) files, then removes original.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    if not video_path or not os.path.exists(video_path):
        return None, None
        
    log(f"[*] Đang tách luồng âm thanh & hình ảnh cho: {os.path.basename(video_path)}...")
    
    # Configure custom FFmpeg binary path before importing moviepy
    if getattr(config, "FFMPEG_PATH", "") and os.path.exists(config.FFMPEG_PATH):
        os.environ["IMAGEIO_DICT"] = "{}"
        os.environ["FFMPEG_BINARY"] = config.FFMPEG_PATH
        
    from hermes.video.editor.moviepy_compat import VideoFileClip
    
    try:
        clip = VideoFileClip(video_path)
        base = os.path.splitext(os.path.basename(video_path))[0]
        
        audio_path = None
        # 1. Export audio
        if clip.audio is not None:
            os.makedirs(output_dir_audio, exist_ok=True)
            audio_path = os.path.join(output_dir_audio, f"{base}_audio.mp3")
            clip.audio.write_audiofile(audio_path, logger=None)
            log(f"  -> Đã tách file tiếng: {os.path.basename(audio_path)}")
            
        # 2. Export silent video
        os.makedirs(output_dir_video, exist_ok=True)
        silent_video_path = os.path.join(output_dir_video, f"{base}_silent.mp4")
        video_only_clip = clip.without_audio()
        video_only_clip.write_videofile(silent_video_path, codec="libx264", audio=False, logger=None, fps=clip.fps or 24)
        log(f"  -> Đã tách file hình tĩnh: {os.path.basename(silent_video_path)}")
        
        clip.close()
        video_only_clip.close()
        
        # Remove original file to keep workspace clean
        try:
            os.remove(video_path)
        except Exception:
            pass
            
        return silent_video_path, audio_path
    except Exception as e:
        log(f"[!] Lỗi khi thực hiện tách luồng Audio/Video: {e}")
        return None, None
