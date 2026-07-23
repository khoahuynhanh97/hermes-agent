import os
import re
import subprocess
import logging
from pathlib import Path

# Setup logging
logger = logging.getLogger("video_fetcher")
logger.setLevel(logging.INFO)

def parse_vtt_to_text(vtt_path: str) -> str:
    """
    Parses a WebVTT file (.vtt) and extracts clean, deduplicated plain text.
    Handles timestamp lines, VTT headers, style tags, and duplicates.
    """
    if not os.path.exists(vtt_path):
        return ""
        
    try:
        with open(vtt_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except Exception as e:
        logger.error(f"Failed to read VTT file: {e}")
        return ""

    clean_lines = []
    seen_phrases = set()

    for line in lines:
        line_strip = line.strip()
        # Skip VTT metadata, notes, and empty lines
        if not line_strip or line_strip.startswith("WEBVTT") or line_strip.startswith("NOTE") or line_strip.startswith("Kind:") or line_strip.startswith("Language:"):
            continue
            
        # Skip timestamp lines (e.g. 00:00:00.000 --> 00:00:02.000)
        if "-->" in line_strip:
            continue
            
        # Strip HTML/VTT tags like <c> or <00:00:00.100>
        line_clean = re.sub(r"<[^>]+>", "", line_strip)
        line_clean = line_clean.strip()
        
        if not line_clean:
            continue
            
        # Deduplicate consecutive/duplicate phrases commonly found in auto-captions
        if line_clean not in seen_phrases:
            clean_lines.append(line_clean)
            seen_phrases.add(line_clean)

    # Join lines to form a clean transcript paragraph
    return " ".join(clean_lines)

def is_blocked_error(output: str) -> bool:
    """Helper to detect IP blocked errors in yt-dlp output."""
    if not output:
        return False
    lower_out = output.lower()
    return any(
        re.search(pattern, lower_out)
        for pattern in (
            r"\b403\b",
            r"\bblocked\b",
            r"\bdenied\b",
            r"\bip\s+(?:address|filter|ban|blocked)\b",
        )
    )

def fetch_transcript(url: str, output_dir: str) -> dict:
    """
    Fetches the transcript of a video URL using two fallback strategies:
    1. Download auto-captions using yt-dlp, and parse the VTT/SRT file.
    2. Download the audio as MP3 using yt-dlp, and transcribe using OpenAI Whisper (base model).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    result = {
        "status": "failed",
        "method": "",
        "transcript": "",
        "language": "vi",
        "error": "",
        "metadata": {},
        "confidence": "needs_source",
    }
    
    # Check if the url is actually a local file path
    if os.path.exists(url):
        logger.info(f"Input is a local file: {url}. Transcribing directly via Whisper...")
        try:
            import whisper
            model = whisper.load_model("base")
            # TASK 2: Language auto-detect
            transcribe_res = model.transcribe(url)
            transcript = transcribe_res.get("text", "").strip()
            detected_lang = transcribe_res.get("language", "vi")
            logger.info(f"Whisper auto-detected language for local file: {detected_lang}")
            
            if transcript:
                result.update({
                    "status": "ok",
                    "method": "whisper",
                    "transcript": transcript,
                    "language": detected_lang,
                    "error": "",
                    "confidence": "high",
                })
                # TASK 3: No-speech detection
                if len(transcript.strip()) < 20:
                    result["warning"] = "no_speech_detected"
                return result
            else:
                raise ValueError("Whisper produced empty transcript from local file.")
        except Exception as e:
            err_msg = f"Whisper transcription of local file failed: {e}"
            logger.error(err_msg)
            result["error"] = err_msg
            return result

    # Prefix for temp subtitle files
    sub_prefix = out_path / "temp_sub"
    
    # ==========================================
    # STRATEGY 1: Auto Subtitle Download via yt-dlp
    # ==========================================
    logger.info(f"Trying to fetch auto-subtitles for URL: {url}")
    
    ip_blocked = False
    try:
        # Run yt-dlp to download auto-subtitles without downloading the video
        sub_cmd = [
            "python", "-m", "yt_dlp",
            "--write-auto-subs",
            "--skip-download",
            "--sub-langs", "vi,en",
            "-o", str(sub_prefix),
            url
        ]
        
        # Try 1: Without cookies
        process = subprocess.run(sub_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
        combined_output = (process.stdout or "") + "\n" + (process.stderr or "")
        
        # TASK 1: IP Block retry logic
        if process.returncode != 0 or is_blocked_error(combined_output):
            if is_blocked_error(combined_output):
                logger.warning("Attempt 1 blocked by IP filter. Retrying with Chrome cookies...")
                ip_blocked = True
            else:
                logger.warning(f"Attempt 1 failed (code {process.returncode}). Retrying with Chrome cookies...")
                
            # Try 2: With Chrome cookies
            sub_cmd_retry = sub_cmd + ["--cookies-from-browser", "chrome"]
            process = subprocess.run(sub_cmd_retry, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=45)
            combined_output = (process.stdout or "") + "\n" + (process.stderr or "")
            if is_blocked_error(combined_output):
                ip_blocked = True
        
        # Check if any subtitle files were created
        sub_files = list(out_path.glob("temp_sub*"))
        if sub_files:
            # Find the best subtitle file (prefer Vietnamese 'vi', then 'en')
            best_sub = None
            lang = "vi"
            
            for sf in sub_files:
                if ".vi." in sf.name:
                    best_sub = sf
                    lang = "vi"
                    break
                elif ".en." in sf.name:
                    best_sub = sf
                    lang = "en"
            
            if not best_sub:
                best_sub = sub_files[0]
                lang = "en" if "en" in best_sub.name else "vi"
                
            logger.info(f"Successfully downloaded auto-subtitle: {best_sub.name}")
            transcript = parse_vtt_to_text(str(best_sub.resolve()))
            
            if transcript.strip():
                # Cleanup temp subtitle files
                for sf in sub_files:
                    try:
                        sf.unlink()
                    except Exception:
                        pass
                
                result.update({
                    "status": "ok",
                    "method": "caption",
                    "transcript": transcript,
                    "language": lang,
                    "error": "",
                    "confidence": "medium",
                })
                # TASK 3: No-speech detection
                if len(transcript.strip()) < 20:
                    result["warning"] = "no_speech_detected"
                return result
            else:
                logger.warning("Subtitle file was empty or failed to parse.")
        else:
            logger.info("No auto-subtitle files downloaded by yt-dlp.")
            
    except Exception as e:
        logger.error(f"Strategy 1 (auto-sub) failed: {e}")
        
    # ==========================================
    # STRATEGY 2: Audio Download & Whisper Transcribe
    # ==========================================
    logger.info("Falling back to Strategy 2: Audio download and Whisper transcription.")
    audio_file = out_path / "temp_audio.mp3"
    
    try:
        # Cleanup any pre-existing audio file
        if audio_file.exists():
            audio_file.unlink()
            
        # Download audio using yt-dlp
        audio_cmd = [
            "python", "-m", "yt_dlp",
            "-x",
            "--audio-format", "mp3",
            "-o", str(out_path / "temp_audio.%(ext)s"),
            url
        ]
        
        # Try 1: Without cookies
        process = subprocess.run(audio_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
        combined_output = (process.stdout or "") + "\n" + (process.stderr or "")
        
        # TASK 1: IP Block retry logic
        if process.returncode != 0 or is_blocked_error(combined_output):
            if is_blocked_error(combined_output):
                logger.warning("Audio download blocked by IP filter. Retrying with Chrome cookies...")
                ip_blocked = True
            else:
                logger.warning(f"Audio download failed (code {process.returncode}). Retrying with Chrome cookies...")
                
            # Try 2: With Chrome cookies
            audio_cmd_retry = audio_cmd + ["--cookies-from-browser", "chrome"]
            process = subprocess.run(audio_cmd_retry, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            combined_output = (process.stdout or "") + "\n" + (process.stderr or "")
            if is_blocked_error(combined_output):
                ip_blocked = True
        
        if audio_file.exists():
            logger.info(f"Successfully downloaded audio to: {audio_file.name}. Loading Whisper base model...")
            
            import whisper
            # Load the base model (runs well on CPU)
            model = whisper.load_model("base")
            
            logger.info("Transcribing audio...")
            # TASK 2: Language auto-detect
            transcribe_res = model.transcribe(str(audio_file.resolve()))
            transcript = transcribe_res.get("text", "").strip()
            detected_lang = transcribe_res.get("language", "vi")
            logger.info(f"Whisper auto-detected language: {detected_lang}")
            
            # Cleanup audio file
            try:
                audio_file.unlink()
            except Exception:
                pass
                
            if transcript:
                result.update({
                    "status": "ok",
                    "method": "whisper",
                    "transcript": transcript,
                    "language": detected_lang,
                    "error": "",
                    "confidence": "medium",
                })
                # TASK 3: No-speech detection
                if len(transcript.strip()) < 20:
                    result["warning"] = "no_speech_detected"
                return result
            else:
                raise ValueError("Whisper produced an empty transcript.")
        else:
            err_msg = f"Audio download failed. yt-dlp stderr: {process.stderr}"
            logger.error(err_msg)
            if ip_blocked:
                result.update({
                    "status": "failed",
                    "error": "ip_blocked",
                    "suggestion": "Thu lai sau hoac cau hinh proxy"
                })
            else:
                result["error"] = err_msg
            
    except Exception as e:
        err_msg = f"Strategy 2 (Whisper) failed: {e}"
        logger.error(err_msg)
        if ip_blocked:
            result.update({
                "status": "failed",
                "error": "ip_blocked",
                "suggestion": "Thu lai sau hoac cau hinh proxy"
            })
        else:
            result["error"] = err_msg
        
        # Cleanup audio file if it exists
        if audio_file.exists():
            try:
                audio_file.unlink()
            except Exception:
                pass
                
    if not os.path.exists(url) and re.match(r"^https?://", url, re.IGNORECASE):
        metadata = _fetch_metadata(url)
        if metadata:
            result.update({
                "status": "partial",
                "method": "metadata",
                "metadata": metadata,
                "confidence": "low",
            })
    return result


def _fetch_metadata(url: str) -> dict:
    """Fetch bounded public metadata without downloading media."""
    try:
        process = subprocess.run(
            [
                "python", "-m", "yt_dlp", "--dump-single-json",
                "--skip-download", "--no-warnings", url,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=45,
        )
        if process.returncode != 0 or not process.stdout.strip():
            return {}
        import json
        raw = json.loads(process.stdout)
        if not isinstance(raw, dict):
            return {}
        fields = {
            "title": raw.get("title"),
            "description": raw.get("description"),
            "uploader": raw.get("uploader") or raw.get("channel"),
            "duration_seconds": raw.get("duration"),
            "webpage_url": raw.get("webpage_url") or url,
        }
        return {
            key: (str(value)[:8000] if key == "description" else value)
            for key, value in fields.items()
            if value not in (None, "")
        }
    except Exception as exc:
        logger.info("Metadata fallback unavailable: %s", exc)
        return {}
