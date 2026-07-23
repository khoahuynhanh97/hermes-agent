import os
import mutagen
from editor.moviepy_compat import AudioFileClip

def get_audio_duration(audio_path):
    """
    Returns the duration of the audio file in seconds.
    Uses mutagen for speed, falls back to moviepy.
    """
    if not os.path.exists(audio_path):
        return 0.0
        
    # Method 1: Mutagen (fast, does not lock files)
    try:
        audio = mutagen.File(audio_path)
        if audio is not None and audio.info is not None:
            return float(audio.info.length)
    except Exception as e:
        print(f"[!] Mutagen duration check failed: {e}")
        
    # Method 2: MoviePy fallback
    try:
        clip = AudioFileClip(audio_path)
        duration = float(clip.duration)
        clip.close()
        return duration
    except Exception as e:
        print(f"[!] MoviePy duration check failed: {e}")
        
    return 0.0
