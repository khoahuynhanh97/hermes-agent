from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
STORYBOARD = PROJECT / "storyboards" / "phone_stand_window_background_12shot_storyboard_v4_exact_mechanism.png"
OUT_DIR = PROJECT / "exports" / "front_lifestyle_review"
SCENE_DIR = OUT_DIR / "scenes"
SEGMENT_DIR = OUT_DIR / "segments"
OUTPUT = OUT_DIR / "phone_stand_front_lifestyle_review_1080x1920.mp4"

W = 1080
H = 1920
FPS = 30

# Mostly front/lifestyle shots. Rear/mechanism panels are intentionally omitted.
# Index is zero-based from the 3x4 storyboard.
SCENES = [
    (0, 2.45, (0.50, 0.50), "front hero"),
    (4, 2.55, (0.50, 0.50), "phone vertical"),
    (5, 2.45, (0.50, 0.50), "phone horizontal"),
    (7, 2.35, (0.50, 0.50), "hand hold front"),
    (8, 2.55, (0.52, 0.50), "desk laptop"),
    (9, 2.45, (0.50, 0.50), "window hero"),
    (10, 2.35, (0.50, 0.50), "two colors"),
    (11, 2.45, (0.50, 0.50), "gift closeup"),
    (0, 1.85, (0.50, 0.50), "final hero"),
]


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def split_storyboard(image: Image.Image) -> list[Image.Image]:
    cell_w = image.width // 3
    cell_h = image.height // 4
    panels = []
    for row in range(4):
        for col in range(3):
            panel = image.crop((col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h))
            # The generated 12-panel sheet has repeated slivers from the panel above
            # at the top of lower rows. Remove them before making full-screen scenes.
            top_trim = 54 if row > 0 else 0
            side_trim = 4
            panel = panel.crop((side_trim, top_trim, panel.width - side_trim, panel.height - 2))
            panels.append(panel)
    return panels


def cover(image: Image.Image, size: tuple[int, int], focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - tw) * min(1, max(0, focus[0])))
    top = int((nh - th) * min(1, max(0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def make_scene_image(panel: Image.Image, scene_number: int, focus=(0.5, 0.5)) -> Path:
    # Use full-screen cover rather than a small centered card.
    frame = cover(panel, (W, H), focus)
    frame = frame.filter(ImageFilter.UnsharpMask(radius=1.1, percent=145, threshold=2))
    path = SCENE_DIR / f"scene_{scene_number:02d}.png"
    frame.save(path, quality=95)
    return path


def make_segment(scene_path: Path, segment_path: Path, duration: float, scene_index: int) -> None:
    frames = max(1, int(FPS * duration))
    drift = 16 if scene_index % 2 else -16
    zoom_expr = f"min(1.050,1+0.050*on/{max(1, frames - 1)})"
    x_expr = f"iw/2-(iw/zoom/2)+{drift}*sin(on/20)"
    y_expr = "ih/2-(ih/zoom/2)+8*sin(on/28)"
    fade_out_start = max(0.0, duration - 0.16)
    vf = (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={frames}:s={W}x{H}:fps={FPS},"
        f"fade=t=in:st=0:d=0.12,fade=t=out:st={fade_out_start:.2f}:d=0.12,"
        "format=yuv420p"
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(scene_path),
            "-vf",
            vf,
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(segment_path),
        ]
    )


def concat_segments(segments: list[Path]) -> None:
    concat_file = SEGMENT_DIR / "concat.txt"
    concat_file.write_text("".join(f"file '{p.as_posix()}'\n" for p in segments), encoding="utf-8")
    run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(OUTPUT),
        ]
    )


def main() -> None:
    if not STORYBOARD.exists():
        raise FileNotFoundError(STORYBOARD)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)

    for folder in [SCENE_DIR, SEGMENT_DIR]:
        for file in folder.glob("*"):
            if file.is_file():
                file.unlink()

    panels = split_storyboard(Image.open(STORYBOARD).convert("RGB"))
    segments = []
    for scene_number, (panel_index, duration, focus, _label) in enumerate(SCENES, 1):
        scene_image = make_scene_image(panels[panel_index], scene_number, focus)
        segment_path = SEGMENT_DIR / f"segment_{scene_number:02d}.mp4"
        make_segment(scene_image, segment_path, duration, scene_number)
        segments.append(segment_path)

    concat_segments(segments)
    print(OUTPUT)


if __name__ == "__main__":
    main()
