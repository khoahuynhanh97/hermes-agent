# tools/video — Render & biên tập video
#
# Sub-package tổ chức các module liên quan đến:
#   - Text-to-Speech (tts_engine)
#   - Quản lý nhạc nền (bgm_manager)
#   - Tạo kịch bản TikTok (script_generator)
#   - Xuất bản video (publisher)
#
# Re-export cho backward compatibility:
#   from tools.video import synthesize
#   from tools.video import generate_tiktok_script

from tools.tts_engine import synthesize, list_voices, VOICES_VI
from tools.bgm_manager import PIXABAY_TRACKS, detect_tone_from_script
from tools.script_generator import (
    generate_tiktok_script,
    check_ollama,
    get_ollama_client,
)
from tools.publisher import publish_recycled_video

__all__ = [
    # TTS
    "synthesize",
    "list_voices",
    "VOICES_VI",
    # BGM
    "PIXABAY_TRACKS",
    "detect_tone_from_script",
    # Script
    "generate_tiktok_script",
    "check_ollama",
    "get_ollama_client",
    # Publisher
    "publish_recycled_video",
]
