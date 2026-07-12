import yt_dlp
import sys

# Force stdout to UTF-8 on Windows
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

ydl_opts = {}
url = "https://www.youtube.com/watch?v=1pkCg35aLeU"
with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    info = ydl.extract_info(url, download=False)
    print("Title:", info.get("title"))
    print("Duration:", info.get("duration"), "seconds")
