# tools/crawler — Cào dữ liệu & tải media
#
# Sub-package tổ chức các module liên quan đến:
#   - Tải video (YouTube, TikTok, direct MP4)
#   - Phân giải link TikTok (media resolver)
#   - Kiểm tra URL (inspector)
#   - Quản lý cookie
#
# Re-export cho backward compatibility:
#   from hermes.tools.crawler import download_video
#   from hermes.tools.crawler import resolve_tiktok_media

from hermes.tools.video_downloader import download_video, clean_filename
from hermes.tools.tiktok_media_resolver import (
    is_tiktok_url,
    resolve_tiktok_media,
    TikTokMediaResult,
)
from hermes.tools.url_inspector import inspect_url, URLInspectionError
from hermes.tools.cookie_helper import *

__all__ = [
    "download_video",
    "clean_filename",
    "is_tiktok_url",
    "resolve_tiktok_media",
    "TikTokMediaResult",
    "inspect_url",
    "URLInspectionError",
]
