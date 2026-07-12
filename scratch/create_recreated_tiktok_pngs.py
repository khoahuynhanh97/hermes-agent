from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
SCENE_DIR = PROJECT / "exports" / "review_batch_4_fixed_mechanism" / "scenes"
BG_DIR = Path(r"C:\Users\TeamSol\Downloads\TIKTOK\Background")
OUT_DIR = PROJECT / "exports" / "recreated_tiktok_pngs"

W = 1080
H = 1920

BACKGROUNDS = [
    "My desk pink and white inspo🤍.jpg",
    "miffy bunny ear lamp.jpg",
    "𝘹𝘹𝘫𝘪𝘬𝘺𝘰 ｡ﾟ🥡🥢.jpg",
    "938578378603975192.jpg",
    "lilac purple multifunctional table mat, pu….jpg",
]

# Clean product scenes only: avoid sources with visible labels, subtitles, or UI text.
# rect: crop region around the product inside source scene, as relative left/top/right/bottom.
# target_h: approximate object height in the final 1080x1920 composition.
ITEMS = [
    ("video_01_cute_desk_review_01.png", BACKGROUNDS[1], (0.04, 0.16, 0.96, 0.94), 1280, 0.52, 0.70),
    ("video_01_cute_desk_review_04.png", BACKGROUNDS[2], (0.08, 0.08, 0.94, 0.98), 1450, 0.52, 0.70),
    ("video_01_cute_desk_review_06.png", BACKGROUNDS[0], (0.12, 0.08, 0.92, 0.98), 1440, 0.50, 0.70),
    ("video_01_cute_desk_review_07.png", BACKGROUNDS[3], (0.04, 0.12, 0.96, 0.88), 1260, 0.50, 0.70),
    ("video_02_gap_xoay_chi_tiet_01.png", BACKGROUNDS[0], (0.06, 0.08, 0.96, 0.96), 1430, 0.52, 0.70),
    ("video_03_so_mau_so_mau_01.png", BACKGROUNDS[4], (0.04, 0.16, 0.96, 0.94), 1280, 0.52, 0.70),
    ("video_03_so_mau_so_mau_02.png", BACKGROUNDS[2], (0.04, 0.12, 0.98, 0.94), 1330, 0.50, 0.70),
    ("video_03_so_mau_so_mau_03.png", BACKGROUNDS[1], (0.14, 0.08, 0.86, 0.98), 1390, 0.50, 0.70),
    ("video_03_so_mau_so_mau_05.png", BACKGROUNDS[0], (0.08, 0.08, 0.92, 0.98), 1410, 0.50, 0.70),
    ("video_03_so_mau_so_mau_07.png", BACKGROUNDS[3], (0.03, 0.08, 0.98, 0.92), 1280, 0.52, 0.70),
    ("video_04_lifestyle_qua_tang_02.png", BACKGROUNDS[1], (0.10, 0.04, 0.90, 0.98), 1380, 0.50, 0.70),
    ("video_04_lifestyle_qua_tang_08.png", BACKGROUNDS[2], (0.03, 0.08, 0.98, 0.92), 1280, 0.50, 0.70),
]


def cover_resize(image: Image.Image, size=(W, H), focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - tw) * min(1.0, max(0.0, focus[0])))
    top = int((nh - th) * min(1.0, max(0.0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def make_background(path: Path) -> Image.Image:
    bg = Image.open(path).convert("RGB")
    bg = cover_resize(bg, (W, H), focus=(0.5, 0.55))
    bg = bg.filter(ImageFilter.GaussianBlur(2.2))
    bg = ImageEnhance.Color(bg).enhance(1.08)
    bg = ImageEnhance.Contrast(bg).enhance(1.03)
    bg = ImageEnhance.Brightness(bg).enhance(1.04)
    return bg


def crop_rel(image: Image.Image, rect: tuple[float, float, float, float]) -> Image.Image:
    l, t, r, b = rect
    return image.crop((int(image.width * l), int(image.height * t), int(image.width * r), int(image.height * b)))


def grabcut_cutout(image: Image.Image) -> Image.Image:
    source = image.convert("RGB")
    max_side = 760
    scale_down = min(1.0, max_side / max(source.width, source.height))
    work = source.resize(
        (int(source.width * scale_down), int(source.height * scale_down)),
        Image.Resampling.LANCZOS,
    )
    rgb = np.array(work)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    rect = (max(2, int(w * 0.05)), max(2, int(h * 0.05)), int(w * 0.90), int(h * 0.90))
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(bgr, mask, rect, bgd, fgd, 6, cv2.GC_INIT_WITH_RECT)
    alpha = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype("uint8")
    kernel = np.ones((5, 5), np.uint8)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_OPEN, kernel, iterations=1)
    alpha = cv2.morphologyEx(alpha, cv2.MORPH_CLOSE, kernel, iterations=2)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.4)
    if scale_down != 1.0:
        alpha = Image.fromarray(alpha, "L").resize(source.size, Image.Resampling.LANCZOS)
        rgb_full = np.array(source)
        alpha_full = np.array(alpha)
        rgba = Image.fromarray(np.dstack([rgb_full, alpha_full]), "RGBA")
    else:
        rgba = Image.fromarray(np.dstack([rgb, alpha]), "RGBA")
    bbox = rgba.getbbox()
    if bbox:
        rgba = rgba.crop(bbox)
    return rgba


def paste_with_shadow(base: Image.Image, cutout: Image.Image, center_x: int, bottom_y: int) -> Image.Image:
    x = int(center_x - cutout.width / 2)
    y = int(bottom_y - cutout.height)

    shadow_alpha = cutout.getchannel("A").filter(ImageFilter.GaussianBlur(20))
    shadow = Image.new("RGBA", cutout.size, (65, 32, 42, 90))
    shadow.putalpha(shadow_alpha.point(lambda p: int(p * 0.34)))
    base.alpha_composite(shadow, (x + 18, y + 26))
    base.alpha_composite(cutout, (x, y))
    return base


def create_image(index: int, scene_name: str, bg_name: str, rect, target_h: int, cx: float, bottom: float) -> Path:
    scene = Image.open(SCENE_DIR / scene_name).convert("RGB")
    crop = crop_rel(scene, rect)
    cutout = grabcut_cutout(crop)

    scale = target_h / cutout.height
    cutout = cutout.resize((int(cutout.width * scale), target_h), Image.Resampling.LANCZOS)
    cutout = cutout.filter(ImageFilter.UnsharpMask(radius=1.0, percent=140, threshold=2))

    bg = make_background(BG_DIR / bg_name).convert("RGBA")
    bg = paste_with_shadow(bg, cutout, int(W * cx), int(H * bottom))
    final = bg.convert("RGB")
    final = final.filter(ImageFilter.UnsharpMask(radius=1.0, percent=115, threshold=3))

    out = OUT_DIR / f"phone_stand_recreated_{index:02d}_1080x1920.png"
    final.save(out)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.png"):
        old.unlink()
    outputs = []
    for i, item in enumerate(ITEMS, start=1):
        outputs.append(create_image(i, *item))
    for out in outputs:
        print(out)


if __name__ == "__main__":
    main()
