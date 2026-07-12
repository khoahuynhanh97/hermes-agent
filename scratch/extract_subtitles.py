import yt_dlp
import sys
import os

# Force stdout to UTF-8
if sys.platform.startswith('win'):
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

url = "https://www.youtube.com/watch?v=1pkCg35aLeU"

# We want to download the automatic subtitles in srv1 (XML) or vtt format
ydl_opts = {
    'writeautomaticsub': True,
    'subtitleslangs': ['vi'],
    'skip_download': True,
    'outtmpl': 'scratch/subtitles',
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    try:
        ydl.download([url])
        print("Subtitles downloaded successfully.")
    except Exception as e:
        print(f"Error downloading subtitles: {e}")
