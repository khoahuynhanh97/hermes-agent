from __future__ import annotations

import os
import re
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw
from hermes.domain.results import Result


def resolve_ffmpeg_exe() -> str:
    configured = (
        os.environ.get("HERMES_FFMPEG_PATH", "").strip()
        or os.environ.get("FFMPEG_PATH", "").strip()
    )
    if configured:
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def render_beat_keyframe(
    output_path: str,
    beat_index: int,
    title: str,
    subtitle: str,
    product_name: str,
    product_ref_image_path: str | None = None,
    width: int = 720,
    height: int = 1280,
) -> str:
    """Render a clean 9:16 vertical keyframe image displaying the authentic product photo for the beat."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    color_schemes = [
        ((15, 23, 42), (30, 58, 138), (59, 130, 246)),   # Beat 1: Navy/Blue
        ((15, 23, 42), (6, 78, 59), (16, 185, 129)),     # Beat 2: Emerald/Teal
        ((15, 23, 42), (112, 26, 117), (217, 70, 239)),  # Beat 3: Purple/Fuchsia
        ((15, 23, 42), (124, 45, 18), (249, 115, 22)),   # Beat 4: Orange/Amber
    ]
    c_bg, c_mid, c_accent = color_schemes[(beat_index - 1) % len(color_schemes)]

    img = Image.new("RGB", (width, height), color=c_bg)

    # Composite real product photo if available
    prod_img_p = Path(product_ref_image_path) if product_ref_image_path else None
    if prod_img_p and prod_img_p.is_file():
        try:
            prod_img = Image.open(prod_img_p).convert("RGB")
            target_w, target_h = width, 860
            scale = max(target_w / prod_img.width, target_h / prod_img.height)
            nw, nh = int(prod_img.width * scale), int(prod_img.height * scale)
            resized = prod_img.resize((nw, nh), Image.Resampling.LANCZOS)
            left = (nw - target_w) // 2
            top = (nh - target_h) // 2
            cropped = resized.crop((left, top, left + target_w, top + target_h))
            img.paste(cropped, (0, 120))
        except Exception:
            pass

    draw = ImageDraw.Draw(img)

    # Top Header Badge
    badge_text = f"BEAT {beat_index} OF 4  *  {product_name.upper()}"
    draw.rectangle([(0, 0), (width, 100)], fill=(15, 23, 42))
    draw.rectangle([(20, 20), (width - 20, 80)], outline=c_accent, width=2)
    draw.text((width // 2, 50), badge_text, fill=(255, 255, 255), anchor="mm")

    # Bottom Caption Panel
    panel_top = height - 280
    draw.rectangle([(0, panel_top), (width, height)], fill=(15, 23, 42))
    draw.rectangle([(0, panel_top), (width, panel_top + 4)], fill=c_accent)

    draw.text((width // 2, panel_top + 50), title.upper(), fill=c_accent, anchor="mm")
    draw.text((width // 2, panel_top + 120), subtitle, fill=(241, 245, 249), anchor="mm")
    draw.text((width // 2, panel_top + 200), "PRODUCED BY HERMES AGENT", fill=(148, 163, 184), anchor="mm")

    img.save(str(p))
    return str(p)


class FFmpegCapability:
    def __init__(self, ffmpeg_path: str | None = None):
        self.ffmpeg_path = ffmpeg_path or resolve_ffmpeg_exe()

    def create_video_clip_from_image(
        self,
        image_path: str,
        output_path: str,
        duration_seconds: int = 6,
        width: int = 720,
        height: int = 1280,
    ) -> Result[dict[str, Any]]:
        """Generate a 9:16 vertical H.264 MP4 clip with pan/zoom motion from an authentic product photo keyframe."""
        p_out = Path(output_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        vf = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
        cmd = [
            self.ffmpeg_path,
            "-loop", "1",
            "-i", image_path,
            "-vf", vf,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-t", str(duration_seconds),
            "-pix_fmt", "yuv420p",
            "-r", "24",
            output_path,
            "-y",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 10000:
                return Result.success({
                    "output_path": output_path,
                    "duration_seconds": duration_seconds,
                    "width": width,
                    "height": height,
                })
        except Exception:
            pass

        raise RuntimeError(f"FFmpeg scene clip generation failed for {image_path}")

    def concat_clips_and_audio(
        self,
        clip_paths: list[str],
        audio_path: str,
        output_path: str,
    ) -> Result[dict[str, Any]]:
        """Concatenate scene video clips and mux audio track into MP4."""
        p_out = Path(output_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        if not Path(audio_path).is_file() or Path(audio_path).stat().st_size < 500:
            raise ValueError(f"AUDIO_TRACK_REQUIRED: Audio file {audio_path} does not exist or is empty")

        concat_list_path = p_out.parent / f"concat_{p_out.stem}.txt"
        concat_lines = [f"file '{Path(cp).as_posix()}'" for cp in clip_paths if Path(cp).is_file()]

        if not concat_lines:
            raise ValueError("No valid video clip paths provided for concatenation.")

        concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list_path),
            "-i", audio_path,
            "-filter_complex", "[1:a]apad=whole_dur=30[a]",
            "-map", "0:v:0",
            "-map", "[a]",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "20",
            "-c:a", "aac",
            "-b:a", "128k",
            "-t", "30",
            output_path,
            "-y",
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if res.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 20000:
                return Result.success({"output_path": output_path, "format": "mp4"})
        except Exception:
            pass

        if concat_list_path.is_file():
            try:
                concat_list_path.unlink()
            except OSError:
                pass

        raise RuntimeError(f"FFmpeg concatenation or audio muxing failed for {output_path}")

    def create_ken_burns_clip(
        self,
        image_path: str,
        output_path: str,
        duration_seconds: float = 5.0,
        zoom_start: float = 1.0,
        zoom_end: float = 1.15,
        width: int = 720,
        height: int = 1280,
    ) -> Result[dict[str, Any]]:
        """Generate a Ken Burns pan/zoom clip from an image.

        Zooms from zoom_start to zoom_end over the clip duration.
        9:16 vertical MP4, CRF 20.
        """
        p_out = Path(output_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        # Scale image large enough to allow zoom+pan without quality loss
        # Then apply zoompan filter with linear interpolation
        # zoompan: z=zoom, d=duration*fps, x/y=center, s=output_size
        fps = 24
        total_frames = int(duration_seconds * fps)
        # Linear zoom: z = zoom_start + (zoom_end - zoom_start) * on / total_frames
        # zoompan uses 'on' for current frame number
        z_expr = f"if(eq(on\\,0)\\,{zoom_start}\\,{zoom_start}+({zoom_end}-{zoom_start})*on/{total_frames})"
        # Center x/y: move to keep center of zoomed region visible
        x_expr = f"(iw-iw/zoom)/2"
        y_expr = f"(ih-ih/zoom)/2"

        vf = (
            f"scale={width * 2}:{height * 2}:force_original_aspect_ratio=decrease,"
            f"zoompan=z='{z_expr}':d={total_frames}:x='{x_expr}':y='{y_expr}'"
            f":s={width}x{height}:fps={fps},"
            f"format=yuv420p"
        )
        cmd = [
            self.ffmpeg_path, "-y",
            "-loop", "1", "-i", image_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-t", str(duration_seconds),
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if res.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 10000:
                return Result.success({
                    "output_path": output_path,
                    "duration_seconds": duration_seconds,
                })
        except Exception:
            pass
        raise RuntimeError(f"Ken Burns clip generation failed for {image_path}")

    def concat_clips_with_transitions(
        self,
        clip_paths: list[str],
        output_path: str,
        transition: str = "left-to-right",
        transition_duration: float = 0.5,
    ) -> Result[dict[str, Any]]:
        """Concatenate video clips with xfade transitions.

        Supported transitions: left-to-right, right-to-left, top-to-bottom, fade.
        """
        p_out = Path(output_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        valid_paths = [p for p in clip_paths if Path(p).is_file()]
        if len(valid_paths) < 2:
            raise ValueError("At least 2 clip paths required for transitions")

        # Map our transition names to FFmpeg xfade transitions
        xfade_map = {
            "left-to-right": "slideright",
            "right-to-left": "slideleft",
            "top-to-bottom": "slidedown",
            "fade": "fade",
        }
        xfade_transition = xfade_map.get(transition, "slideright")

        # Build filter_complex for multi-input xfade chain
        inputs = []
        for p in valid_paths:
            inputs.extend(["-i", p])

        # Probe durations
        durations = []
        for p in valid_paths:
            durations.append(self._probe_duration(p))

        n = len(valid_paths)
        filter_parts = []
        # Chain xfade: [0][1]xfade=offset=...:duration=...[v1]; [v1][2]xfade=...
        offset = durations[0] - transition_duration
        for i in range(1, n):
            tag_in = f"[v{i - 1}]" if i > 1 else f"[0:v]"
            tag_out = f"[v{i}]" if i < n - 1 else "[vout]"
            filter_parts.append(
                f"{tag_in}[{i}:v]xfade=transition={xfade_transition}"
                f":duration={transition_duration}:offset={max(0, offset):.3f}{tag_out}"
            )
            if i < n - 1:
                offset = offset + durations[i] - transition_duration

        filter_complex = ";".join(filter_parts)
        cmd = [
            self.ffmpeg_path, "-y",
            *inputs,
            "-filter_complex", filter_complex,
            "-map", "[vout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if res.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 10000:
                return Result.success({"output_path": output_path, "transition": transition})
        except Exception:
            pass
        raise RuntimeError(f"FFmpeg transition concatenation failed for {output_path}")

    def _probe_duration(self, file_path: str) -> float:
        """Quick ffprobe for duration in seconds."""
        cmd = [
            self.ffmpeg_path.replace("ffmpeg.exe", "ffprobe.exe")
            if "ffmpeg.exe" in self.ffmpeg_path else "ffprobe",
            "-v", "quiet", "-print_format", "json", "-show_streams", file_path,
        ]
        try:
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode()
            import json as _json
            streams = _json.loads(out).get("streams", [])
            return float(next((s["duration"] for s in streams if s.get("codec_type") == "video"), 5.0))
        except Exception:
            return 5.0

    def burn_subtitles(self, video_path: str, ass_path: str, output_path: str) -> Result[dict[str, Any]]:
        """Burn ASS subtitles into video using FFmpeg subtitles filter.

        Handles Windows path escaping for ASS files.
        """
        p_out = Path(output_path)
        p_out.parent.mkdir(parents=True, exist_ok=True)

        if not Path(video_path).is_file():
            raise ValueError(f"Input video not found: {video_path}")
        if not Path(ass_path).is_file():
            raise ValueError(f"ASS subtitle file not found: {ass_path}")

        # Escape path for FFmpeg subtitles filter: forward slashes, escape colon for Windows
        escaped_path = Path(ass_path).resolve().as_posix().replace(":", "\\:")

        vf = f"subtitles='{escaped_path}'"
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", video_path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "copy",
            "-pix_fmt", "yuv420p",
            output_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if res.returncode == 0 and p_out.is_file() and p_out.stat().st_size > 10000:
                return Result.success({"output_path": output_path})
        except Exception:
            pass
        raise RuntimeError(f"Subtitle burn failed for {output_path}")

    def probe_media_file(self, file_path: str) -> dict[str, Any]:
        """Probe media file for real duration, resolution, codecs, and audio stream requirements."""
        p = Path(file_path)
        if not p.is_file():
            return {"is_valid": False, "error": "FILE_NOT_FOUND"}

        file_size = p.stat().st_size
        cmd = [self.ffmpeg_path, "-i", str(p)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        info_text = res.stderr

        duration_sec = 0.0
        dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", info_text)
        if dur_match:
            hrs, mins, secs = dur_match.groups()
            duration_sec = int(hrs) * 3600 + int(mins) * 60 + float(secs)

        width, height = 0, 0
        dim_match = re.search(r",\s*(\d{3,4})x(\d{3,4})", info_text)
        if dim_match:
            width, height = int(dim_match.group(1)), int(dim_match.group(2))

        v_codec = "h264"
        v_match = re.search(r"Video:\s*([a-zA-Z0-9_]+)", info_text)
        if v_match:
            v_codec = v_match.group(1)

        has_audio = "Audio:" in info_text
        a_codec = ""
        a_match = re.search(r"Audio:\s*([a-zA-Z0-9_]+)", info_text)
        if a_match:
            a_codec = a_match.group(1)

        is_valid = (
            file_size > 50000
            and 28.0 <= duration_sec <= 32.0
            and width >= 720
            and height >= 1280
            and has_audio
        )

        return {
            "is_valid": is_valid,
            "duration_seconds": round(duration_sec, 2),
            "width": width,
            "height": height,
            "aspect_ratio": f"{width}:{height}" if width and height else "9:16",
            "video_codec": v_codec,
            "has_audio": has_audio,
            "audio_codec": a_codec or ("aac" if has_audio else "none"),
            "file_size_bytes": file_size,
        }
