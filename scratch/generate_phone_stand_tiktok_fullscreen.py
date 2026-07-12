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
OUTPUT_VIDEO = PROJECT_DIR / "exports" / "phone_stand_storyboard_tiktok_fullscreen.mp4"

CANVAS_W = 1080
CANVAS_H = 1920
FPS = 24
SECONDS_PER_SCENE = 1.25
SCENE_FRAMES = int(FPS * SECONDS_PER_SCENE)

# Focal points keep the main product/hand centered after converting landscape storyboard cells to 9:16.
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
            # Remove the original caption strip and reduce grid borders.
            panel = panel.crop((8, 18, panel.width - 8, panel.height - 46))

            # Blur the numbered storyboard badge without adding replacement text.
            blurred = panel.filter(ImageFilter.GaussianBlur(20))
            badge_mask = Image.new("L", panel.size, 0)
            badge_draw = ImageDraw.Draw(badge_mask)
            badge_draw.ellipse((-24, -24, 92, 92), fill=255)
            panel.paste(blurred, (0, 0), badge_mask)
            panels.append(panel)
    return panels


def portrait_crop(panel, scene_index, frame_index):
    progress = frame_index / max(1, SCENE_FRAMES - 1)
    drift = math.sin((progress - 0.5) * math.pi) * 0.025
    focal_x = min(0.92, max(0.08, FOCAL_X[scene_index] + drift))

    crop_h = panel.height
    crop_w = int(crop_h * CANVAS_W / CANVAS_H)
    crop_w = max(90, min(crop_w, panel.width))

    center_x = int(panel.width * focal_x)
    left = max(0, min(panel.width - crop_w, center_x - crop_w // 2))
    return panel.crop((left, 0, left + crop_w, crop_h))


def make_frame(panel, scene_index, frame_index):
    progress = frame_index / max(1, SCENE_FRAMES - 1)
    ease = 0.5 - 0.5 * math.cos(progress * math.pi)

    crop = portrait_crop(panel, scene_index, frame_index)
    frame = cover_resize(crop, (CANVAS_W, CANVAS_H))

    # Small push-in, then sharpen for TikTok upload compression.
    zoom = 1.0 + 0.035 * ease
    zw = int(CANVAS_W / zoom)
    zh = int(CANVAS_H / zoom)
    left = (CANVAS_W - zw) // 2
    top = (CANVAS_H - zh) // 2
    frame = frame.crop((left, top, left + zw, top + zh)).resize(
        (CANVAS_W, CANVAS_H),
        Image.Resampling.LANCZOS,
    )
    frame = frame.filter(ImageFilter.UnsharpMask(radius=1.0, percent=135, threshold=2))
    return frame.convert("RGB")


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
        "medium",
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
        raise RuntimeError("ffmpeg failed while encoding fullscreen TikTok video")
    print(OUTPUT_VIDEO)


if __name__ == "__main__":
    main()
