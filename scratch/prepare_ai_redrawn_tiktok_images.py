from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep" / "exports" / "ai_redrawn_storyboard_singles"
OUT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep" / "exports" / "rabbit_redrawn_tiktok_1080x1920"

W, H = 1080, 1920


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    scale = max(size[0] / image.width, size[1] / image.height)
    resized = image.resize((int(image.width * scale + 0.5), int(image.height * scale + 0.5)), Image.Resampling.LANCZOS)
    x = (resized.width - size[0]) // 2
    y = (resized.height - size[1]) // 2
    return resized.crop((x, y, x + size[0], y + size[1]))


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.contain(image, size, Image.Resampling.LANCZOS)


def prepare_one(src: Path, dst: Path) -> None:
    image = Image.open(src).convert("RGB")
    bg = cover(image, (W, H)).filter(ImageFilter.GaussianBlur(32))
    bg = ImageEnhance.Brightness(bg).enhance(1.05)
    bg = ImageEnhance.Color(bg).enhance(0.92)

    fg = contain(image, (W, H))
    fg = ImageEnhance.Sharpness(fg).enhance(1.10)
    fg = ImageEnhance.Contrast(fg).enhance(1.02)

    canvas = bg.copy()
    x = (W - fg.width) // 2
    y = (H - fg.height) // 2
    canvas.paste(fg, (x, y))
    canvas.save(dst, quality=98)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("rabbit_story_*.png"):
        old.unlink()

    # First three files in this generation folder are older helper/contact images.
    # The actual single-shot redraw batch is raw_generated_04 through raw_generated_15.
    sources = sorted(SRC.glob("raw_generated_*.png"))[3:15]
    for i, src in enumerate(sources, start=1):
        prepare_one(src, OUT / f"rabbit_story_{i:02d}_1080x1920.png")


if __name__ == "__main__":
    main()
