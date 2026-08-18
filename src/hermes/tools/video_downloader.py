import os
import yt_dlp
import re
import random
import time

# Nháº­p cÃ¡c parser tÃ¹y chá»‰nh cho cÃ¡c sÃ n TMÄT
try:
    from hermes.tools.custom_parsers import extract_ecommerce_video, download_direct_mp4
except ImportError:
    from custom_parsers import extract_ecommerce_video, download_direct_mp4

def clean_filename(filename):
    """Lá»c kÃ½ tá»± Ä‘áº·c biá»‡t Ä‘á»ƒ táº¡o tÃªn file an toÃ n"""
    return re.sub(r'[\\/*?:"<>| ]', '_', filename)

class YDLLogger:
    def __init__(self, callback):
        self.callback = callback
    def debug(self, msg):
        self.callback(msg)
    def info(self, msg):
        self.callback(msg)
    def warning(self, msg):
        self.callback(f"[!] {msg}")
    def error(self, msg):
        self.callback(f"[x] {msg}")

def download_video(url, output_dir="downloads", audio_only=False, max_duration=None, browser_cookies=None, log_callback=None):
    """
    Táº£i video hoáº·c Ã¢m thanh tá»« cÃ¡c nguá»“n URL (TikTok, YouTube, Douyin, Xiaohongshu, 1688, Taobao...) vá» mÃ¡y local.
    
    Args:
        url (str): ÄÆ°á»ng dáº«n link video cáº§n táº£i.
        output_dir (str): ThÆ° má»¥c lÆ°u trá»¯ káº¿t quáº£. Máº·c Ä‘á»‹nh lÃ  'downloads'.
        audio_only (bool): Náº¿u True, chá»‰ táº£i vÃ  tÃ¡ch Ã¢m thanh dÆ°á»›i dáº¡ng MP3.
        max_duration (int, optional): Thá»i lÆ°á»£ng tá»‘i Ä‘a (giÃ¢y). Bá» qua náº¿u video dÃ i hÆ¡n.
        browser_cookies (str, optional): TÃªn trÃ¬nh duyá»‡t Ä‘á»ƒ láº¥y cookie (vÃ­ dá»¥: 'chrome', 'edge').
        log_callback (callable, optional): HÃ m nháº­n log chuá»—i Ä‘á»ƒ hiá»ƒn thá»‹ trÃªn giao diá»‡n GUI.
        
    Returns:
        str: ÄÆ°á»ng dáº«n tuyá»‡t Ä‘á»‘i cá»§a file táº£i vá» thÃ nh cÃ´ng, hoáº·c None náº¿u tháº¥t báº¡i.
    """
    os.makedirs(output_dir, exist_ok=True)
    url_lower = url.lower()
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    # 1. Kiá»ƒm tra xem cÃ³ pháº£i lÃ  link sáº£n pháº©m TMÄT Trung Quá»‘c khÃ´ng (1688, JD, Taobao, Pinduoduo)
    is_ecommerce = any(domain in url_lower for domain in ["1688.com", "jd.com", "taobao.com", "tmall.com", "pinduoduo.com", "360buyimg"])
    
    if is_ecommerce and not audio_only:
        log("[*] PhÃ¡t hiá»‡n link sÃ n TMÄT. Äang quÃ©t tÃ¬m video trá»±c tiáº¿p...")
        direct_mp4 = extract_ecommerce_video(url)
        if direct_mp4:
            file_title = f"ecommerce_video_{clean_filename(url[-15:])}"
            output_path = os.path.join(output_dir, f"{file_title}.mp4")
            # Override print trong custom_parsers báº±ng log náº¿u cáº§n, nhÆ°ng Ä‘Æ¡n giáº£n chá»‰ cáº§n táº£i trá»±c tiáº¿p
            log(f"[*] Báº¯t Ä‘áº§u táº£i trá»±c tiáº¿p MP4 tá»« sÃ n TMÄT...")
            success = download_direct_mp4(direct_mp4, output_path)
            if success:
                log(f"[+] Táº£i thÃ nh cÃ´ng: {os.path.abspath(output_path)}")
                return os.path.abspath(output_path)
            else:
                log("[-] Thá»­ táº£i trá»±c tiáº¿p tháº¥t báº¡i, chuyá»ƒn sang phÆ°Æ¡ng Ã¡n yt-dlp...")
        else:
            log("[-] KhÃ´ng tÃ¬m tháº¥y link MP4 trá»±c tiáº¿p trong mÃ£ HTML, chuyá»ƒn sang phÆ°Æ¡ng Ã¡n yt-dlp...")

    # 2. Cáº¥u hÃ¬nh táº£i thÃ´ng thÆ°á»ng báº±ng yt-dlp
    if audio_only:
        ydl_opts = {
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'noplaylist': True,
            'quiet': False,
        }
    else:
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4',
            'noplaylist': True,
            'quiet': False,
        }
        
    # Cáº¥u hÃ¬nh log cho yt-dlp
    if log_callback:
        ydl_opts['logger'] = YDLLogger(log_callback)
        ydl_opts['quiet'] = True
        
    # Cáº¥u hÃ¬nh lá»c thá»i lÆ°á»£ng
    if max_duration:
        ydl_opts['match_filter'] = lambda info, *, incomplete: None if info.get('duration') and info.get('duration') <= max_duration else 'Video quÃ¡ dÃ i'
        
    # Cáº¥u hÃ¬nh náº¡p cookie trÃ¬nh duyá»‡t náº¿u Ä‘Æ°á»£c chá»n
    if browser_cookies and browser_cookies != "KhÃ´ng dÃ¹ng cookie":
        log(f"[*] Äang náº¡p Cookie tá»« trÃ¬nh duyá»‡t: {browser_cookies}")
        ydl_opts['cookiesfrombrowser'] = (browser_cookies,)
    log(f"[*] Bat dau cao video tu URL: {url}")
    delays = [2, 5, 15]
    last_error = None
    for attempt, base_delay in enumerate(delays, start=1):
        try:
            if attempt > 1:
                jitter = random.uniform(0.3, 1.7)
                sleep_seconds = base_delay + jitter
                log(f"[*] Retry yt-dlp attempt {attempt}/3 after {sleep_seconds:.1f}s...")
                time.sleep(sleep_seconds)
            else:
                log("[*] yt-dlp attempt 1/3...")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filepath = ydl.prepare_filename(info)

                if audio_only:
                    basename, _ = os.path.splitext(filepath)
                    filepath = basename + ".mp3"
                else:
                    basename, ext = os.path.splitext(filepath)
                    if ext != ".mp4" and os.path.exists(basename + ".mp4"):
                        filepath = basename + ".mp4"

                if os.path.exists(filepath):
                    log(f"[+] Tai thanh cong: {os.path.abspath(filepath)}")
                    return os.path.abspath(filepath)
                return os.path.abspath(filepath)

        except Exception as e:
            last_error = e
            log(f"[x] Loi tai qua yt-dlp attempt {attempt}/3: {e}")

    log(f"[x] yt-dlp failed after 3 attempts: {last_error}")
    return None

if __name__ == "__main__":
    test_url = input("Nháº­p URL cáº§n táº£i thá»­: ").strip()
    if test_url:
        download_video(test_url)
