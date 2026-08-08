# tools/crawler — Cào dữ liệu & tải media
#
# Sub-package tổ chức các module liên quan đến:
#   - Tải video (YouTube, TikTok, direct MP4)
#   - Phân giải link TikTok (media resolver)
#   - Kiểm tra URL (inspector)
#   - Quản lý cookie
#
# Re-export cho backward compatibility:
#   from tools.crawler import download_video
#   from tools.crawler import resolve_tiktok_media

from tools.video_downloader import download_video, clean_filename
from tools.tiktok_media_resolver import (
    is_tiktok_url,
    resolve_tiktok_media,
    TikTokMediaResult,
)
from tools.url_inspector import inspect_url, URLInspectionError
from tools.cookie_helper import *

__all__ = [
    "download_video",
    "clean_filename",
    "is_tiktok_url",
    "resolve_tiktok_media",
    "TikTokMediaResult",
    "inspect_url",
    "URLInspectionError",
]
