from __future__ import annotations

import math
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep" / "exports" / "duck_foldable_commercial"
KEYFRAME = OUT_DIR / "duck_holder_keyframe.png"
BG_PLATE = OUT_DIR / "duck_holder_background_plate.png"
W, H = 1080, 1920
FPS = 25
DURATION = 7.0


def fit_cover(image: Image.Image) -> Image.Image:
    return ImageOps.fit(image.convert("RGB"), (W, H), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def make_product_mask(frame_rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(frame_rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]

    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    yellow = cv2.inRange(hsv, np.array([16, 72, 90]), np.array([44, 255, 255]))
    orange = cv2.inRange(hsv, np.array([2, 90, 80]), np.array([24, 255, 255]))
    metal = cv2.inRange(hsv, np.array([0, 0, 115]), np.array([179, 85, 255]))
    region = np.zeros((h, w), np.uint8)
    x, y, rw, rh = (int(w * 0.20), int(h * 0.14), int(w * 0.62), int(h * 0.78))
    region[y : y + rh, x : x + rw] = 255
    color_hint = cv2.bitwise_and(cv2.bitwise_or(yellow, orange), region)
    metal_hint = cv2.bitwise_and(metal, cv2.dilate(color_hint, np.ones((55, 55), np.uint8), iterations=1))

    combined = cv2.bitwise_or(color_hint, metal_hint)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, np.ones((19, 19), np.uint8), iterations=2)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(combined)
    keep = np.zeros_like(combined)
    for idx in range(1, num):
        area = stats[idx, cv2.CC_STAT_AREA]
        cx = stats[idx, cv2.CC_STAT_LEFT] + stats[idx, cv2.CC_STAT_WIDTH] / 2
        cy = stats[idx, cv2.CC_STAT_TOP] + stats[idx, cv2.CC_STAT_HEIGHT] / 2
        if area > 900 and w * 0.20 < cx < w * 0.82 and h * 0.14 < cy < h * 0.92:
            keep[labels == idx] = 255

    keep = cv2.dilate(keep, np.ones((5, 5), np.uint8), iterations=1)
    keep = cv2.GaussianBlur(keep, (0, 0), 2.5)
    return keep


def bbox_from_alpha(alpha: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(alpha > 8)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def rotate_rgba(rgba: Image.Image, degrees: float, pivot_rel: tuple[float, float]) -> Image.Image:
    arr = np.array(rgba)
    h, w = arr.shape[:2]
    pivot = (w * pivot_rel[0], h * pivot_rel[1])
    m = cv2.getRotationMatrix2D(pivot, degrees, 1.0)
    cos = abs(m[0, 0])
    sin = abs(m[0, 1])
    nw = int((h * sin) + (w * cos))
    nh = int((h * cos) + (w * sin))
    m[0, 2] += (nw / 2) - pivot[0]
    m[1, 2] += (nh / 2) - pivot[1]
    rotated = cv2.warpAffine(arr, m, (nw, nh), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    return Image.fromarray(rotated, "RGBA")


def camera_transform(image: Image.Image, scale: float, slide_x: float) -> Image.Image:
    nw = int(W * scale + 0.5)
    nh = int(H * scale + 0.5)
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    cx = (nw - W) / 2 + slide_x
    cy = (nh - H) / 2 - 5 * (scale - 1.0) / 0.07
    return resized.crop((int(cx), int(cy), int(cx) + W, int(cy) + H))


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    source = fit_cover(Image.open(KEYFRAME))
    source = ImageEnhance.Sharpness(source).enhance(1.05)
    source_rgb = np.array(source)

    alpha = make_product_mask(source_rgb)
    if BG_PLATE.exists():
        bg = fit_cover(Image.open(BG_PLATE))
        bg = ImageEnhance.Brightness(bg).enhance(1.01)
    else:
        bg = source.filter(ImageFilter.GaussianBlur(24))
        bg = ImageEnhance.Brightness(bg).enhance(1.04)
        bg = ImageEnhance.Color(bg).enhance(0.96)

    x1, y1, x2, y2 = bbox_from_alpha(alpha)
    crop_rgb = source.crop((x1, y1, x2, y2)).convert("RGBA")
    crop_alpha = Image.fromarray(alpha[y1:y2, x1:x2], "L")
    crop_rgb.putalpha(crop_alpha)
    # Product base sits near bottom of the cutout; rock around that base, not the center.
    pivot_rel = (0.50, 0.86)

    silent = OUT_DIR / "duck_holder_commercial_silent.mp4"
    writer = cv2.VideoWriter(str(silent), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    total = int(FPS * DURATION)
    for i in range(total):
        t = i / max(1, total - 1)
        ease = 0.5 - 0.5 * math.cos(math.pi * t)
        angle = math.sin(t * math.tau * 1.15) * 2.1
        scale = 1.00 + 0.065 * ease
        slide = -10 + 20 * ease

        frame = bg.convert("RGBA")
        product = rotate_rgba(crop_rgb, angle, pivot_rel)
        px = int(x1 - (product.width - crop_rgb.width) / 2)
        py = int(y1 - (product.height - crop_rgb.height) / 2)
        shadow = product.getchannel("A").filter(ImageFilter.GaussianBlur(28))
        shadow_layer = Image.new("RGBA", product.size, (75, 45, 20, 70))
        shadow_layer.putalpha(shadow.point(lambda p: int(p * 0.22)))
        frame.alpha_composite(shadow_layer, (px + 16, py + 28))
        frame.alpha_composite(product, (px, py))
        frame = camera_transform(frame.convert("RGB"), scale, slide)
        frame = ImageEnhance.Color(frame).enhance(1.03)
        writer.write(cv2.cvtColor(np.array(frame), cv2.COLOR_RGB2BGR))
    writer.release()

    final = OUT_DIR / "duck_holder_folded_commercial_1080x1920_7s.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent),
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(final),
        ],
        check=True,
    )

    preview = OUT_DIR / "duck_holder_preview_contact.jpg"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(final),
            "-vf",
            "fps=1,scale=180:320,tile=4x2:margin=8:padding=4:color=white",
            "-frames:v",
            "1",
            "-update",
            "1",
            str(preview),
        ],
        check=True,
    )
    print(final)
    print(preview)


if __name__ == "__main__":
    main()
