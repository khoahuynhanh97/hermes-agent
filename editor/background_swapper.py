"""
editor/background_swapper.py — AI Background Removal & Replacement

Official module for swapping video backgrounds using:
  - AI Cutout (rembg u2netp) — works on any background
  - Chroma Key (OpenCV) — for green/blue screen footage
  - Solid Color — replace with flat color
"""
import os
import sys
import cv2
import numpy as np
import logging
from pathlib import Path

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

logger = logging.getLogger(__name__)


def _read_image_safe(path: str) -> np.ndarray:
    """Read image safely even with Unicode path (Windows fix)."""
    arr = np.fromfile(path, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    return img


def swap_background_ai(
    video_path: str,
    bg_source,           # str (image path) | tuple (R,G,B) for solid color
    output_path: str,
    model_name: str = "u2netp",
    progress_callback=None,
    log_callback=None,
) -> str:
    """
    Replace video background using AI segmentation (rembg).

    Args:
        video_path: Source video path
        bg_source: Background image path OR (R,G,B) tuple for solid color
        output_path: Output video path (without audio)
        model_name: 'u2netp' (fast CPU) or 'u2net' (quality)
        progress_callback: fn(current_frame, total_frames)
        log_callback: fn(message)

    Returns:
        Path to output video (silent, use _merge_audio after)
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            logger.info(msg)

    try:
        from rembg import remove, new_session
        from PIL import Image as PILImage
    except ImportError:
        raise ImportError("rembg not installed. Run: pip install 'rembg[cpu]'")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # Prepare background
    if isinstance(bg_source, (tuple, list)):
        # Solid color (BGR)
        bg_bgr = np.full((h, w, 3), [bg_source[2], bg_source[1], bg_source[0]], dtype=np.uint8)
    else:
        bg_img = _read_image_safe(bg_source)
        if bg_img is None:
            raise FileNotFoundError(f"Cannot read background image: {bg_source}")
        bg_bgr = cv2.resize(bg_img, (w, h))

    # Setup video writer
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    log(f"[BgSwap] Loading AI model '{model_name}'...")
    session = new_session(model_name)
    log(f"[BgSwap] Processing {total} frames at {fps:.0f}fps...")

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        # AI background removal
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil = PILImage.fromarray(rgb)
        cutout = remove(pil, session=session)
        cutout_np = np.array(cutout)

        fg = cutout_np[:, :, :3]
        alpha = cutout_np[:, :, 3:4] / 255.0

        # Resize if needed
        if fg.shape[:2] != (h, w):
            fg = cv2.resize(fg, (w, h))
            alpha = cv2.resize(alpha.squeeze(), (w, h))[:, :, np.newaxis]

        # Composite over background
        bg_rgb = cv2.cvtColor(bg_bgr, cv2.COLOR_BGR2RGB)
        composite = (fg * alpha + bg_rgb * (1 - alpha)).astype(np.uint8)
        composite_bgr = cv2.cvtColor(composite, cv2.COLOR_RGB2BGR)
        out.write(composite_bgr)

        if progress_callback:
            progress_callback(frame_idx, total)
        elif frame_idx % 25 == 0:
            log(f"[BgSwap]   {frame_idx}/{total} ({frame_idx/total*100:.1f}%)")

    cap.release()
    out.release()
    log(f"[BgSwap] ✅ Silent video saved → {output_path}")
    return output_path


def swap_background_chroma(
    video_path: str,
    bg_source,
    output_path: str,
    key_color: str = "green",      # 'green' or 'blue'
    tolerance: int = 40,
    progress_callback=None,
    log_callback=None,
) -> str:
    """
    Replace video background using Chroma Key (green/blue screen).
    Much faster than AI mode — use when source has a clean green/blue screen.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            logger.info(msg)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if isinstance(bg_source, (tuple, list)):
        bg_bgr = np.full((h, w, 3), [bg_source[2], bg_source[1], bg_source[0]], dtype=np.uint8)
    else:
        bg_img = _read_image_safe(bg_source)
        bg_bgr = cv2.resize(bg_img, (w, h))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, (w, h))

    # Chroma key ranges (HSV)
    if key_color == "green":
        lower = np.array([35, 40, 40])
        upper = np.array([85, 255, 255])
    else:  # blue
        lower = np.array([100, 40, 40])
        upper = np.array([140, 255, 255])

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, lower, upper)
        # Dilate mask slightly to clean up edges
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.dilate(mask, kernel, iterations=1)
        mask_inv = cv2.bitwise_not(mask)

        fg = cv2.bitwise_and(frame, frame, mask=mask_inv)
        bg = cv2.bitwise_and(bg_bgr, bg_bgr, mask=mask)
        composite = cv2.add(fg, bg)
        out.write(composite)

        if progress_callback:
            progress_callback(frame_idx, total)

    cap.release()
    out.release()
    log(f"[BgSwap] ✅ Chroma key done → {output_path}")
    return output_path


def merge_audio(silent_video_path: str, audio_source_path: str, output_path: str,
                log_callback=None) -> str:
    """Merge original audio back into background-swapped silent video."""
    import subprocess

    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            logger.info(msg)

    ffmpeg = getattr(config, "FFMPEG_PATH", "") or "ffmpeg"
    if not os.path.exists(ffmpeg):
        ffmpeg = "ffmpeg"

    cmd = [
        ffmpeg, "-y",
        "-i", silent_video_path,
        "-i", audio_source_path,
        "-map", "0:v",
        "-map", "1:a",
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        output_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode == 0:
        log(f"[BgSwap] ✅ Audio merged → {output_path}")
        return output_path
    else:
        log(f"[BgSwap] ⚠️ Audio merge failed, returning silent video")
        return silent_video_path


def swap_background(
    video_path: str,
    bg_source,
    output_path: str,
    method: str = "ai",
    key_color: str = "green",
    progress_callback=None,
    log_callback=None,
) -> str:
    """
    Main interface — swap background of a video.

    Args:
        video_path: Input video path
        bg_source: str (image path) | tuple (R,G,B) solid color
        output_path: Final output video path (with audio)
        method: 'ai' (rembg, any background) | 'chroma' (green/blue screen)
        key_color: 'green' or 'blue' (only for chroma method)
        progress_callback: fn(current_frame, total_frames)
        log_callback: fn(message)

    Returns:
        Final output video path (with original audio merged back)
    """
    stem = Path(output_path).stem
    parent = Path(output_path).parent
    silent_path = str(parent / f"{stem}_silent.mp4")

    if method == "chroma":
        swap_background_chroma(
            video_path, bg_source, silent_path,
            key_color=key_color,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )
    else:
        swap_background_ai(
            video_path, bg_source, silent_path,
            progress_callback=progress_callback,
            log_callback=log_callback,
        )

    final = merge_audio(silent_path, video_path, output_path, log_callback=log_callback)

    # Cleanup silent temp
    try:
        if os.path.exists(silent_path) and silent_path != final:
            os.remove(silent_path)
    except Exception:
        pass

    return final
