from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
SCENE_DIR = PROJECT / "exports" / "review_batch_4_fixed_mechanism" / "scenes"
BG_DIR = Path(r"C:\Users\TeamSol\Downloads\TIKTOK\Background")
OUT_DIR = PROJECT / "exports" / "recreated_tiktok_pngs_clean"

W = 1080
H = 1920
FG_W = 1012
FG_H = 1800

BACKGROUNDS = [
    "My desk pink and white inspo🤍.jpg",
    "miffy bunny ear lamp.jpg",
    "938578378603975192.jpg",
    "𝘹𝘹𝘫𝘪𝘬𝘺𝘰 ｡ﾟ🥡🥢.jpg",
    "lilac purple multifunctional table mat, pu….jpg",
]

SCENES = [
    ("video_01_cute_desk_review_01.png", BACKGROUNDS[1]),
    ("video_01_cute_desk_review_04.png", BACKGROUNDS[3]),
    ("video_01_cute_desk_review_06.png", BACKGROUNDS[0]),
    ("video_01_cute_desk_review_07.png", BACKGROUNDS[2]),
    ("video_02_gap_xoay_chi_tiet_01.png", BACKGROUNDS[0]),
    ("video_03_so_mau_so_mau_01.png", BACKGROUNDS[4]),
    ("video_03_so_mau_so_mau_02.png", BACKGROUNDS[3]),
    ("video_03_so_mau_so_mau_03.png", BACKGROUNDS[1]),
    ("video_03_so_mau_so_mau_05.png", BACKGROUNDS[0]),
    ("video_03_so_mau_so_mau_07.png", BACKGROUNDS[2]),
    ("video_04_lifestyle_qua_tang_02.png", BACKGROUNDS[1]),
    ("video_04_lifestyle_qua_tang_08.png", BACKGROUNDS[3]),
]


def cover_resize(image: Image.Image, size: tuple[int, int], focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - tw) * min(1.0, max(0.0, focus[0])))
    top = int((nh - th) * min(1.0, max(0.0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def make_bg(path: Path) -> Image.Image:
    bg = cover_resize(Image.open(path).convert("RGB"), (W, H), focus=(0.5, 0.55))
    bg = bg.filter(ImageFilter.GaussianBlur(20))
    bg = ImageEnhance.Color(bg).enhance(1.10)
    bg = ImageEnhance.Brightness(bg).enhance(1.08)
    veil = Image.new("RGB", (W, H), (255, 238, 241))
    return Image.blend(bg, veil, 0.22)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def create_one(index: int, scene_name: str, bg_name: str) -> Path:
    bg = make_bg(BG_DIR / bg_name).convert("RGBA")
    scene = Image.open(SCENE_DIR / scene_name).convert("RGB")
    fg = cover_resize(scene, (FG_W, FG_H), focus=(0.5, 0.52))
    fg = ImageEnhance.Color(fg).enhance(1.04)
    fg = ImageEnhance.Contrast(fg).enhance(1.03)
    fg = fg.filter(ImageFilter.UnsharpMask(radius=1.0, percent=135, threshold=2))

    x = (W - FG_W) // 2
    y = (H - FG_H) // 2

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((x + 8, y + 16, x + FG_W + 8, y + FG_H + 16), radius=34, fill=(92, 45, 60, 62))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    bg.alpha_composite(shadow)

    mask = rounded_mask((FG_W, FG_H), 30)
    bg.paste(fg.convert("RGBA"), (x, y), mask)

    out = OUT_DIR / f"phone_stand_clean_{index:02d}_1080x1920.png"
    bg.convert("RGB").save(out)
    return out


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.png"):
        old.unlink()
    for i, (scene, bg) in enumerate(SCENES, 1):
        print(create_one(i, scene, bg))


if __name__ == "__main__":
    main()
