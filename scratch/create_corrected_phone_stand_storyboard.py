from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
ASSETS = PROJECT / "source_assets"
OUT = PROJECT / "storyboards" / "phone_stand_corrected_structure_storyboard.png"

PANEL_W = 720
PANEL_H = 720
GRID_COLS = 3
GRID_ROWS = 3
GAP = 18
HEADER_H = 108
MARGIN = 24
CAPTION_H = 88


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    font = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path(r"C:\Windows\Fonts") / font), size=size)


def open_rgb(name: str) -> Image.Image:
    return Image.open(ASSETS / name).convert("RGB")


def cover(image: Image.Image, size: tuple[int, int], focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - tw) * min(1, max(0, focus[0])))
    top = int((nh - th) * min(1, max(0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def split_grid(image: Image.Image, rows: int, cols: int, crop=(0, 0, 0, 0), top_margin=0):
    usable = image.crop((0, top_margin, image.width, image.height))
    cw = usable.width // cols
    ch = usable.height // rows
    panels = []
    l, t, r, b = crop
    for row in range(rows):
        for col in range(cols):
            cell = usable.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch))
            panels.append(cell.crop((l, t, cell.width - r, cell.height - b)).convert("RGB"))
    return panels


def crop_phone_screenshot(image: Image.Image, y1=0.27, y2=0.72, x1=0.0, x2=1.0) -> Image.Image:
    w, h = image.size
    return image.crop((int(w * x1), int(h * y1), int(w * x2), int(h * y2))).convert("RGB")


def draw_panel(
    canvas: Image.Image,
    image: Image.Image,
    idx: int,
    title: str,
    note: str,
    cell_x: int,
    cell_y: int,
    focus=(0.5, 0.5),
):
    draw = ImageDraw.Draw(canvas)
    x = MARGIN + cell_x * (PANEL_W + GAP)
    y = HEADER_H + MARGIN + cell_y * (PANEL_H + GAP)

    panel_img = cover(image, (PANEL_W, PANEL_H), focus)
    panel_img = panel_img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=135, threshold=2))

    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle(
        (x + 6, y + 10, x + PANEL_W + 6, y + PANEL_H + 10),
        radius=18,
        fill=(128, 74, 79, 46),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    canvas.alpha_composite(shadow)

    mask = Image.new("L", (PANEL_W, PANEL_H), 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rounded_rectangle((0, 0, PANEL_W, PANEL_H), radius=18, fill=255)
    canvas.paste(panel_img, (x, y), mask)

    badge_r = 48
    draw.ellipse((x + 18, y + 18, x + 18 + badge_r * 2, y + 18 + badge_r * 2), fill=(232, 125, 136, 238))
    num = str(idx).zfill(2)
    bbox = draw.textbbox((0, 0), num, font=FONT_BADGE)
    draw.text(
        (x + 18 + badge_r - (bbox[2] - bbox[0]) / 2, y + 18 + badge_r - (bbox[3] - bbox[1]) / 2 - 4),
        num,
        font=FONT_BADGE,
        fill=(255, 255, 255, 255),
    )

    caption_y = y + PANEL_H - CAPTION_H - 16
    draw.rounded_rectangle(
        (x + 28, caption_y, x + PANEL_W - 28, caption_y + CAPTION_H),
        radius=26,
        fill=(255, 244, 246, 230),
    )
    title_bbox = draw.textbbox((0, 0), title, font=FONT_TITLE)
    note_bbox = draw.textbbox((0, 0), note, font=FONT_NOTE)
    draw.text((x + (PANEL_W - (title_bbox[2] - title_bbox[0])) / 2, caption_y + 13), title, font=FONT_TITLE, fill=(202, 86, 94))
    draw.text((x + (PANEL_W - (note_bbox[2] - note_bbox[0])) / 2, caption_y + 49), note, font=FONT_NOTE, fill=(92, 70, 66))


FONT_HEADER = load_font(44, True)
FONT_SUB = load_font(25)
FONT_TITLE = load_font(28, True)
FONT_NOTE = load_font(22)
FONT_BADGE = load_font(42, True)


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)

    mix = split_grid(open_rgb("ChatGPT Image 22_39_52 29 thg 6, 2026.png"), 3, 3, crop=(6, 6, 6, 6))
    cat = split_grid(open_rgb("ChatGPT Image 22_47_53 29 thg 6, 2026.png"), 3, 3, crop=(12, 28, 12, 92), top_margin=58)

    hero = open_rgb("ChatGPT Image 01_48_44 29 thg 6, 2026.png")
    rear = crop_phone_screenshot(open_rgb("z7985967842473_b40fbb735d56d2ca40d662c957dd0173.jpg"), 0.27, 0.72)
    rotate = crop_phone_screenshot(open_rgb("z7985967814255_f659dffbfd342ce3b99b1712ca623480.jpg"), 0.27, 0.72)
    folded = crop_phone_screenshot(open_rgb("z7985967828921_082bd3dee84a71bef50fa8a990cdbe4c.jpg"), 0.27, 0.72)

    W = GRID_COLS * PANEL_W + (GRID_COLS - 1) * GAP + MARGIN * 2
    H = HEADER_H + GRID_ROWS * PANEL_H + (GRID_ROWS - 1) * GAP + MARGIN * 2
    canvas = Image.new("RGBA", (W, H), (255, 236, 238, 255))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((0, 0, W, HEADER_H + 12), fill=(255, 247, 241, 255))
    header = "STORYBOARD ĐÃ SỬA - GIÁ ĐỠ ĐIỆN THOẠI HÌNH THÚ"
    sub = "Fix cấu trúc: mặt sau đúng ba khớp xoay, hai thanh đỡ song song, chân đế tròn"
    hb = draw.textbbox((0, 0), header, font=FONT_HEADER)
    sb = draw.textbbox((0, 0), sub, font=FONT_SUB)
    draw.text(((W - (hb[2] - hb[0])) / 2, 22), header, font=FONT_HEADER, fill=(108, 62, 48))
    draw.text(((W - (sb[2] - sb[0])) / 2, 72), sub, font=FONT_SUB, fill=(158, 101, 91))

    items = [
        (hero, "Tổng quan decor", "bố cục và kích thước", (0.50, 0.45)),
        (mix[1], "Mặt trước cute", "giữ đúng hình thú", (0.50, 0.48)),
        (rear, "Mặt sau đúng", "ba cụm khớp xoay rõ", (0.54, 0.50)),
        (rear, "Góc nghiêng cơ khí", "hai thanh đỡ song song", (0.42, 0.50)),
        (folded, "Trạng thái gấp gọn", "chân đế và trục xoay đúng", (0.48, 0.50)),
        (rotate, "Chân đế xoay", "đế tròn xoay ba trăm sáu mươi", (0.50, 0.50)),
        (mix[2], "Dựng điện thoại dọc", "hai chân ôm máy", (0.50, 0.50)),
        (cat[6], "Dùng ngang xem phim", "giữ cơ cấu như mẫu thật", (0.50, 0.50)),
        (cat[8], "Mang theo / quà tặng", "không đổi cấu trúc sản phẩm", (0.50, 0.50)),
    ]

    for i, (image, title, note, focus) in enumerate(items, start=1):
        draw_panel(canvas, image, i, title, note, (i - 1) % 3, (i - 1) // 3, focus)

    canvas.convert("RGB").save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__":
    main()
