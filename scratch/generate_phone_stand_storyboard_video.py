import math
import os
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGE = Path(
    r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu"
    r"\ChatGPT Image 22_43_49 29 thg 6, 2026.png"
)
PROJECT_DIR = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
FRAME_DIR = ROOT / "scratch" / "phone_stand_storyboard_frames"
OUTPUT_VIDEO = PROJECT_DIR / "exports" / "phone_stand_storyboard_clean_showcase.mp4"

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 24
SECONDS_PER_SCENE = 1.45
SCENE_FRAMES = int(FPS * SECONDS_PER_SCENE)
SHOW_OVERLAY_TEXT = False
CROP_STORYBOARD_TEXT = True

CAPTIONS = [
    "Tổng quan sản phẩm",
    "Cận cảnh chi tiết dễ thương",
    "Thiết kế gấp gọn tiện lợi",
    "Mở ra dễ dàng chỉ một bước",
    "Điều chỉnh góc độ linh hoạt",
    "Xoay đủ các góc sản phẩm",
    "Giữ điện thoại chắc chắn",
    "Xem phim thoải mái",
    "Để máy tính bảng tiện lợi",
    "Chân đế vững chắc, chống trượt",
    "Chất liệu nhựa cao cấp",
    "Nhỏ gọn, dễ mang theo",
    "Phù hợp mọi không gian",
    "Màu sắc pastel xinh xắn",
    "Món quà dễ thương, ý nghĩa",
]


def cover_resize(image, target_size):
    target_w, target_h = target_size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (int(image.width * scale) + 1, int(image.height * scale) + 1)
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def contain_resize(image, max_size):
    max_w, max_h = max_size
    scale = min(max_w / image.width, max_h / image.height)
    new_size = (int(image.width * scale), int(image.height * scale))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def rounded_paste(base, image, xy, radius=30, shadow=True):
    x, y = xy
    if shadow:
        shadow_layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow_layer)
        shadow_box = (x + 8, y + 14, x + image.width + 8, y + image.height + 14)
        shadow_draw.rounded_rectangle(shadow_box, radius=radius, fill=(120, 64, 78, 78))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(18))
        base.alpha_composite(shadow_layer)

    mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)
    base.paste(image, (x, y), mask)


def draw_pill(draw, xy, text, font, fill=(255, 255, 255, 230), text_fill=(224, 101, 113, 255)):
    x, y = xy
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x = 34
    pad_y = 18
    box = (x, y, x + tw + pad_x * 2, y + th + pad_y * 2)
    draw.rounded_rectangle(box, radius=34, fill=fill)
    draw.text((x + pad_x, y + pad_y - 2), text, font=font, fill=text_fill)


def load_font(size, bold=False):
    font_name = "arialbd.ttf" if bold else "arial.ttf"
    font_path = Path(r"C:\Windows\Fonts") / font_name
    return ImageFont.truetype(str(font_path), size=size)


def split_storyboard(image):
    cell_w = image.width // 3
    cell_h = image.height // 5
    panels = []
    for row in range(5):
        for col in range(3):
            left = col * cell_w
            top = row * cell_h
            panel = image.crop((left, top, left + cell_w, top + cell_h))
            if CROP_STORYBOARD_TEXT:
                # Remove neighboring caption strips and blur any remaining numbered badge.
                panel = panel.crop((8, 44, panel.width - 8, panel.height - 42))
                blurred = panel.filter(ImageFilter.GaussianBlur(18))
                badge_mask = Image.new("L", panel.size, 0)
                badge_draw = ImageDraw.Draw(badge_mask)
                badge_draw.ellipse((-22, -22, 82, 82), fill=255)
                panel.paste(blurred, (0, 0), badge_mask)
            panels.append(panel)
    return panels


def make_frame(panel, scene_index, frame_index, title_font, caption_font, cta_font):
    progress = frame_index / max(1, SCENE_FRAMES - 1)
    ease = 0.5 - 0.5 * math.cos(progress * math.pi)

    bg = cover_resize(panel, (CANVAS_W, CANVAS_H)).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (255, 226, 228)), 0.22)
    canvas = bg.convert("RGBA")
    overlay = Image.new("RGBA", canvas.size, (255, 238, 240, 22))
    canvas.alpha_composite(overlay)

    zoom = 1.0 + 0.065 * ease
    base_panel = contain_resize(panel, (980, 1180))
    panel_w = int(base_panel.width * zoom)
    panel_h = int(base_panel.height * zoom)
    moving_panel = base_panel.resize((panel_w, panel_h), Image.Resampling.LANCZOS)
    moving_panel = moving_panel.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))

    direction = -1 if scene_index % 2 else 1
    pan_x = int(direction * (-34 + 68 * ease))
    pan_y = int(-16 + 32 * ease)
    x = (CANVAS_W - panel_w) // 2 + pan_x
    y = (CANVAS_H - panel_h) // 2 + pan_y
    rounded_paste(canvas, moving_panel.convert("RGBA"), (x, y), radius=26)

    if SHOW_OVERLAY_TEXT:
        draw = ImageDraw.Draw(canvas)
        scene_text = CAPTIONS[scene_index]
        scene_bbox = draw.textbbox((0, 0), scene_text, font=caption_font)
        draw_pill(
            draw,
            ((CANVAS_W - (scene_bbox[2] - scene_bbox[0] + 68)) // 2, 1484),
            scene_text,
            caption_font,
        )

    return canvas.convert("RGB")


def main():
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(SOURCE_IMAGE)

    PROJECT_DIR.joinpath("exports").mkdir(parents=True, exist_ok=True)
    storyboard = Image.open(SOURCE_IMAGE).convert("RGB")
    panels = split_storyboard(storyboard)
    title_font = load_font(58, bold=True)
    caption_font = load_font(44, bold=True)
    cta_font = load_font(44, bold=True)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{CANVAS_W}x{CANVAS_H}",
        "-r",
        str(FPS),
        "-i",
        "-",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-movflags",
        "+faststart",
        str(OUTPUT_VIDEO),
    ]
    process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE)
    try:
        for scene_index, panel in enumerate(panels):
            for frame_index in range(SCENE_FRAMES):
                frame = make_frame(panel, scene_index, frame_index, title_font, caption_font, cta_font)
                process.stdin.write(frame.tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding storyboard video")
    print(OUTPUT_VIDEO)


if __name__ == "__main__":
    main()
