# tools/video — Render & biên tập video
#
# Sub-package tổ chức các module liên quan đến:
#   - Text-to-Speech (tts_engine)
#   - Quản lý nhạc nền (bgm_manager)
#   - Tạo kịch bản TikTok (script_generator)
#   - Xuất bản video (publisher)
#
# Re-export cho backward compatibility:
#   from hermes.tools.video import synthesize
#   from hermes.tools.video import generate_tiktok_script

from hermes.tools.tts_engine import synthesize, list_voices, VOICES_VI
from hermes.tools.bgm_manager import PIXABAY_TRACKS, detect_tone_from_script
from hermes.tools.script_generator import (
    generate_tiktok_script,
    check_ollama,
    get_ollama_client,
)
from hermes.tools.publisher import publish_recycled_video

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
