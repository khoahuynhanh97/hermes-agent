import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGE = Path(
    r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu"
    r"\ChatGPT Image 22_43_49 29 thg 6, 2026.png"
)
PROJECT_DIR = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
OUTPUT_VIDEO = PROJECT_DIR / "exports" / "phone_stand_storyboard_tiktok_large_scene.mp4"

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 24
SECONDS_PER_SCENE = 1.08
SCENE_FRAMES = int(FPS * SECONDS_PER_SCENE)
FOREGROUND_H = 1320
FOREGROUND_W = 1040

FOCAL_X = [
    0.50, 0.50, 0.50,
    0.43, 0.50, 0.50,
    0.50, 0.50, 0.50,
    0.47, 0.50, 0.54,
    0.50, 0.50, 0.50,
]


def cover_resize(image, target_size):
    target_w, target_h = target_size
    scale = max(target_w / image.width, target_h / image.height)
    new_size = (int(image.width * scale) + 1, int(image.height * scale) + 1)
    resized = image.resize(new_size, Image.Resampling.LANCZOS)
    left = (resized.width - target_w) // 2
    top = (resized.height - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def split_storyboard(image):
    cell_w = image.width // 3
    cell_h = image.height // 5
    panels = []
    for row in range(5):
        for col in range(3):
            left = col * cell_w
            top = row * cell_h
            panel = image.crop((left, top, left + cell_w, top + cell_h))
            panel = panel.crop((8, 44, panel.width - 8, panel.height - 42))

            blurred = panel.filter(ImageFilter.GaussianBlur(20))
            badge_mask = Image.new("L", panel.size, 0)
            badge_draw = ImageDraw.Draw(badge_mask)
            badge_draw.ellipse((-24, -24, 92, 92), fill=255)
            panel.paste(blurred, (0, 0), badge_mask)
            panels.append(panel)
    return panels


def crop_wide_focus(panel, scene_index, frame_index):
    progress = frame_index / max(1, SCENE_FRAMES - 1)
    drift = math.sin((progress - 0.5) * math.pi) * 0.018
    focal_x = min(0.90, max(0.10, FOCAL_X[scene_index] + drift))

    scale = FOREGROUND_H / panel.height
    resized = panel.resize(
        (int(panel.width * scale), FOREGROUND_H),
        Image.Resampling.LANCZOS,
    )
    center_x = int(resized.width * focal_x)
    left = max(0, min(resized.width - FOREGROUND_W, center_x - FOREGROUND_W // 2))
    return resized.crop((left, 0, left + FOREGROUND_W, FOREGROUND_H))


def rounded_paste(base, image, xy, radius=36):
    x, y = xy
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle(
        (x + 10, y + 18, x + image.width + 10, y + image.height + 18),
        radius=radius,
        fill=(124, 64, 72, 80),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(20))
    base.alpha_composite(shadow)

    mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle((0, 0, image.width, image.height), radius=radius, fill=255)
    base.paste(image, (x, y), mask)


def make_frame(panel, scene_index, frame_index):
    progress = frame_index / max(1, SCENE_FRAMES - 1)
    ease = 0.5 - 0.5 * math.cos(progress * math.pi)

    bg = cover_resize(panel, (CANVAS_W, CANVAS_H)).filter(ImageFilter.GaussianBlur(18))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (255, 229, 232)), 0.18)
    canvas = bg.convert("RGBA")

    fg = crop_wide_focus(panel, scene_index, frame_index)
    zoom = 1.0 + 0.025 * ease
    zw = int(fg.width / zoom)
    zh = int(fg.height / zoom)
    fg = fg.crop(
        (
            (fg.width - zw) // 2,
            (fg.height - zh) // 2,
            (fg.width - zw) // 2 + zw,
            (fg.height - zh) // 2 + zh,
        )
    ).resize((FOREGROUND_W, FOREGROUND_H), Image.Resampling.LANCZOS)
    fg = fg.filter(ImageFilter.UnsharpMask(radius=1.0, percent=145, threshold=2))

    x = (CANVAS_W - FOREGROUND_W) // 2
    y = (CANVAS_H - FOREGROUND_H) // 2
    rounded_paste(canvas, fg.convert("RGBA"), (x, y))
    return canvas.convert("RGB")


def main():
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(SOURCE_IMAGE)
    PROJECT_DIR.joinpath("exports").mkdir(parents=True, exist_ok=True)
    panels = split_storyboard(Image.open(SOURCE_IMAGE).convert("RGB"))

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
        "-crf",
        "18",
        "-preset",
        "veryfast",
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
                process.stdin.write(make_frame(panel, scene_index, frame_index).tobytes())
    finally:
        if process.stdin:
            process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError("ffmpeg failed while encoding large-scene TikTok video")
    print(OUTPUT_VIDEO)


if __name__ == "__main__":
    main()
