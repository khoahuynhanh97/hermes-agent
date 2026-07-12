"""
tools/tts_engine.py — Text-to-Speech Engine

Supports:
  - Edge TTS (Microsoft, FREE, no API key needed, high quality Vietnamese voices)
  - ElevenLabs (premium, requires API key)

Usage:
    from tools.tts_engine import synthesize, list_voices, VOICES_VI
    output_path = synthesize("Xin chào các bạn!", voice="HoaiMy", speed=1.1)
"""
import os
import sys
import asyncio
import logging
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Vietnamese voice presets (Edge TTS names)
# ---------------------------------------------------------------------------
VOICES_VI = {
    "HoaiMy":   "vi-VN-HoaiMyNeural",     # Nữ, giọng miền Bắc - tự nhiên, rõ ràng
    "NamMinh":  "vi-VN-NamMinhNeural",     # Nam, giọng miền Bắc - trầm ấm
}

# Full voice catalog (Edge TTS Vietnamese only)
VOICE_CATALOG = {
    "vi-VN-HoaiMyNeural":  "Nữ miền Bắc (HoaiMy)",
    "vi-VN-NamMinhNeural": "Nam miền Bắc (NamMinh)",
    # International extras useful for demos
    "en-US-JennyNeural":   "English Female (Jenny)",
    "en-US-GuyNeural":     "English Male (Guy)",
}

DEFAULT_VOICE = "vi-VN-HoaiMyNeural"
DEFAULT_SPEED = 1.0  # 1.0 = normal, <1 slower, >1 faster


# ---------------------------------------------------------------------------
# Edge TTS backend
# ---------------------------------------------------------------------------
async def _edge_tts_async(text: str, voice: str, rate: str, output_path: str):
    """Async Edge TTS synthesis."""
    try:
        import edge_tts
    except ImportError:
        raise ImportError("edge-tts not installed. Run: pip install edge-tts")

    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)


def _speed_to_rate(speed: float) -> str:
    """Convert speed float (0.7–1.5) to Edge TTS rate string (+25%, -15%, etc.)"""
    pct = int((speed - 1.0) * 100)
    if pct >= 0:
        return f"+{pct}%"
    return f"{pct}%"


def synthesize_edge_tts(text: str, voice: str = DEFAULT_VOICE,
                        speed: float = DEFAULT_SPEED,
                        output_path: str = None) -> str:
    """
    Synthesize speech using Microsoft Edge TTS (FREE, no API key).

    Args:
        text: Text to speak
        voice: Voice name (e.g. 'vi-VN-HoaiMyNeural' or shorthand 'HoaiMy')
        speed: Playback speed multiplier (0.7–1.5, default 1.0)
        output_path: Output .mp3 path (auto-generated if None)

    Returns:
        Absolute path to generated .mp3 file
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty.")

    # Resolve shorthand voice name
    voice = VOICES_VI.get(voice, voice) or DEFAULT_VOICE

    # Auto output path
    if not output_path:
        tmp = tempfile.mktemp(suffix=".mp3", prefix="tts_")
        output_path = tmp

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    rate_str = _speed_to_rate(speed)
    logger.info(f"[TTS] Edge TTS | Voice: {voice} | Speed: {speed}x ({rate_str}) | Output: {output_path}")

    # Run async in sync context
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _edge_tts_async(text, voice, rate_str, output_path))
                future.result(timeout=120)
        else:
            loop.run_until_complete(_edge_tts_async(text, voice, rate_str, output_path))
    except RuntimeError:
        asyncio.run(_edge_tts_async(text, voice, rate_str, output_path))

    if not os.path.exists(output_path):
        raise RuntimeError(f"[TTS] Edge TTS synthesis failed — output file not created.")

    size_kb = os.path.getsize(output_path) / 1024
    logger.info(f"[TTS] ✅ Generated {size_kb:.1f} KB → {output_path}")
    return output_path


def synthesize_elevenlabs(text: str, voice_id: str = "pNInz6obpgDQGcFmaJgB",
                          output_path: str = None) -> str:
    """
    Synthesize speech using ElevenLabs API (premium quality).

    Args:
        text: Text to speak
        voice_id: ElevenLabs voice ID
        output_path: Output .mp3 path

    Returns:
        Absolute path to generated .mp3 file
    """
    import requests as req
    api_key = getattr(config, "ELEVENLABS_API_KEY", "") or os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        raise ValueError("[TTS] ELEVENLABS_API_KEY not configured.")

    if not output_path:
        output_path = tempfile.mktemp(suffix=".mp3", prefix="el_tts_")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    resp = req.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)

    logger.info(f"[TTS] ElevenLabs ✅ → {output_path}")
    return output_path


# ---------------------------------------------------------------------------
# Unified interface
# ---------------------------------------------------------------------------
def synthesize(text: str,
               voice: str = "HoaiMy",
               speed: float = 1.0,
               output_path: str = None,
               provider: str = "edge") -> str:
    """
    Unified TTS synthesis function.

    Args:
        text: Text to speak
        voice: Voice shorthand ('HoaiMy', 'NamMinh') or full Edge TTS name
        speed: Speed multiplier 0.7–1.5
        output_path: Output file path (.mp3)
        provider: 'edge' (free) | 'elevenlabs' (premium)

    Returns:
        Path to generated .mp3 file
    """
    if provider == "elevenlabs":
        return synthesize_elevenlabs(text, output_path=output_path)
    return synthesize_edge_tts(text, voice=voice, speed=speed, output_path=output_path)


def list_voices() -> dict:
    """Return available Voice catalog."""
    return VOICE_CATALOG.copy()


def synthesize_to_project(text: str, project_folders: dict,
                           voice: str = "HoaiMy", speed: float = 1.0,
                           provider: str = "edge") -> str:
    """
    Synthesize TTS and save directly into project's audio/ folder as voice.mp3.
    Overwrites existing voice.mp3.

    Args:
        text: Voiceover script text
        project_folders: Dict from ProjectManager.get_project_folders()
        voice, speed, provider: TTS settings

    Returns:
        Path to voice.mp3
    """
    audio_dir = project_folders.get("audio", "")
    if not audio_dir:
        raise ValueError("project_folders must contain 'audio' key")
    os.makedirs(audio_dir, exist_ok=True)
    output_path = os.path.join(audio_dir, "voice.mp3")
    return synthesize(text, voice=voice, speed=speed,
                      output_path=output_path, provider=provider)
