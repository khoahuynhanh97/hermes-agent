"""
tools/bgm_manager.py — Auto Background Music Manager

Automatically selects and mixes background music based on script tone.
Downloads free BGM from Pixabay or uses local library.
"""
import os
import sys
import json
import random
import logging
import requests

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

logger = logging.getLogger(__name__)

BGM_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'bgm_library'))

# ---------------------------------------------------------------------------
# Tone-based curated Pixabay Music tracks (public domain, no login needed)
# ---------------------------------------------------------------------------
PIXABAY_TRACKS = {
    "energetic": [
        {"title": "Energetic Sport", "url": "https://cdn.pixabay.com/download/audio/2022/08/25/audio_4e2c36e3e8.mp3"},
        {"title": "Upbeat Funk", "url": "https://cdn.pixabay.com/download/audio/2022/10/25/audio_7b33451a41.mp3"},
    ],
    "happy": [
        {"title": "Happy Ukelele", "url": "https://cdn.pixabay.com/download/audio/2022/01/18/audio_d0c6ff1faf.mp3"},
        {"title": "Sunny Morning", "url": "https://cdn.pixabay.com/download/audio/2021/11/25/audio_b8b1c32cfd.mp3"},
    ],
    "calm": [
        {"title": "Calm Piano", "url": "https://cdn.pixabay.com/download/audio/2024/02/20/audio_30b5c11df7.mp3"},
        {"title": "Soft Background", "url": "https://cdn.pixabay.com/download/audio/2022/05/27/audio_1808fbf07a.mp3"},
    ],
    "inspirational": [
        {"title": "Motivational", "url": "https://cdn.pixabay.com/download/audio/2022/11/09/audio_c5d59a0085.mp3"},
        {"title": "Rise Up", "url": "https://cdn.pixabay.com/download/audio/2021/10/25/audio_b46a4e0e0d.mp3"},
    ],
    "trendy": [
        {"title": "Lofi Chill", "url": "https://cdn.pixabay.com/download/audio/2022/05/17/audio_69a61cd6d6.mp3"},
        {"title": "TikTok Vibe", "url": "https://cdn.pixabay.com/download/audio/2022/09/07/audio_a3f2c2bb72.mp3"},
    ],
}


def ensure_bgm_dirs():
    for tone in PIXABAY_TRACKS:
        os.makedirs(os.path.join(BGM_DIR, tone), exist_ok=True)


def detect_tone_from_script(script_text: str) -> str:
    """
    Simple heuristic tone detection from script text.
    Returns: 'energetic', 'happy', 'calm', 'inspirational', 'trendy'
    """
    text_lower = script_text.lower()

    energetic_kw = ["năng động", "nhanh", "mạnh", "sport", "gym", "chạy", "explosive", "power"]
    happy_kw = ["vui", "hạnh phúc", "tươi", "cute", "dễ thương", "thú vị", "vui vẻ"]
    calm_kw = ["nhẹ nhàng", "tĩnh lặng", "bình yên", "thư giãn", "relax", "calm", "spa", "tối giản"]
    inspirational_kw = ["truyền cảm hứng", "thay đổi", "nâng cấp", "tốt hơn", "thành công", "mục tiêu"]
    trendy_kw = ["trend", "viral", "tiktok", "hot", "hot trend", "chill", "lofi", "aesthetic"]

    scores = {
        "energetic": sum(1 for kw in energetic_kw if kw in text_lower),
        "happy": sum(1 for kw in happy_kw if kw in text_lower),
        "calm": sum(1 for kw in calm_kw if kw in text_lower),
        "inspirational": sum(1 for kw in inspirational_kw if kw in text_lower),
        "trendy": sum(1 for kw in trendy_kw if kw in text_lower),
    }

    # Use AI router if no clear winner
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "happy"  # Default tone
    return best


def download_bgm(url: str, output_path: str) -> bool:
    """Download a BGM track from URL."""
    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"[BGM] Downloaded → {output_path}")
        return True
    except Exception as e:
        logger.warning(f"[BGM] Download failed: {e}")
        return False


def pick_bgm(tone: str = "happy", duration_seconds: float = 30.0,
             log_callback=None) -> str:
    """
    Select and download an appropriate BGM track for the given tone.

    Args:
        tone: 'energetic', 'happy', 'calm', 'inspirational', 'trendy'
        duration_seconds: Target video duration (for reference)
        log_callback: Optional function to log progress

    Returns:
        Absolute path to .mp3 BGM file, or empty string if unavailable
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            logger.info(msg)

    ensure_bgm_dirs()

    if tone not in PIXABAY_TRACKS:
        tone = "happy"

    # Check local cache first
    tone_dir = os.path.join(BGM_DIR, tone)
    local_files = [f for f in os.listdir(tone_dir) if f.endswith(".mp3")]
    if local_files:
        chosen = os.path.join(tone_dir, random.choice(local_files))
        log(f"[BGM] Using cached track: {os.path.basename(chosen)}")
        return chosen

    # Download from Pixabay
    tracks = PIXABAY_TRACKS[tone]
    random.shuffle(tracks)
    for track in tracks:
        filename = track["title"].replace(" ", "_").lower() + ".mp3"
        output_path = os.path.join(tone_dir, filename)
        log(f"[BGM] Downloading '{track['title']}' ({tone})...")
        if download_bgm(track["url"], output_path):
            return output_path

    log(f"[BGM] ⚠️ Could not download BGM for tone '{tone}'")
    return ""


def mix_bgm_with_video(video_path: str, bgm_path: str, output_path: str,
                        bgm_volume: float = 0.15,
                        fade_in: float = 2.0, fade_out: float = 3.0,
                        log_callback=None) -> str:
    """
    Mix background music into video using FFmpeg.
    BGM volume is ducked to bgm_volume (0.0–1.0) relative to voice.

    Args:
        video_path: Input video with voice audio
        bgm_path: BGM .mp3 file path
        output_path: Output mixed video path
        bgm_volume: BGM loudness ratio (0.15 = 15% = about -16dB)
        fade_in: BGM fade-in seconds
        fade_out: BGM fade-out seconds

    Returns:
        Path to output video
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            logger.info(msg)

    ffmpeg_path = getattr(config, "FFMPEG_PATH", "") or "ffmpeg"
    if not ffmpeg_path or not os.path.exists(ffmpeg_path):
        ffmpeg_path = "ffmpeg"

    # Get video duration
    import subprocess, json as _json
    probe_cmd = [
        ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe") if "ffmpeg.exe" in ffmpeg_path else "ffprobe",
        "-v", "quiet", "-print_format", "json", "-show_streams", video_path
    ]
    try:
        probe_out = subprocess.check_output(probe_cmd, stderr=subprocess.DEVNULL).decode()
        streams = _json.loads(probe_out).get("streams", [])
        duration = float(next((s["duration"] for s in streams if s.get("codec_type") == "video"), 30))
    except Exception:
        duration = 30.0

    fade_out_start = max(0, duration - fade_out)

    # FFmpeg filter: mix video audio + BGM with fade
    filter_complex = (
        f"[1:a]afade=t=in:st=0:d={fade_in},"
        f"afade=t=out:st={fade_out_start:.2f}:d={fade_out},"
        f"aloop=loop=-1:size=2e+09[bgm];"
        f"[0:a][bgm]amix=inputs=2:weights=1 {bgm_volume:.2f}:normalize=0[aout]"
    )

    cmd = [
        ffmpeg_path, "-y",
        "-i", video_path,
        "-i", bgm_path,
        "-filter_complex", filter_complex,
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]

    log(f"[BGM] Mixing BGM into video (volume={bgm_volume:.0%})...")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log(f"[BGM] ✅ BGM mixed successfully → {output_path}")
            return output_path
        else:
            log(f"[BGM] FFmpeg error: {result.stderr[-300:]}")
            return video_path  # Return original if mixing fails
    except Exception as e:
        log(f"[BGM] Exception during mixing: {e}")
        return video_path
