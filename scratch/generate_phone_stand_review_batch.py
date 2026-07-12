from __future__ import annotations

import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
ASSETS = PROJECT / "source_assets"
OUT_DIR = PROJECT / "exports" / "review_batch_4_fixed_mechanism"
SCENE_DIR = OUT_DIR / "scenes"
SEGMENT_DIR = OUT_DIR / "segments"
SCRIPT_DIR = OUT_DIR / "voice_scripts"

W = 1080
H = 1920
FPS = 30
SCENE_SECONDS = 2.65
SCENE_FRAMES = int(FPS * SCENE_SECONDS)


def open_rgb(name: str) -> Image.Image:
    path = ASSETS / name
    if not path.exists():
        raise FileNotFoundError(path)
    return Image.open(path).convert("RGB")


def crop_phone_screenshot(image: Image.Image) -> Image.Image:
    # The real supplier references are phone screenshots with black UI above/below.
    # Crop to the product photo area so the rendered TikTok video stays clean.
    w, h = image.size
    return image.crop((0, int(h * 0.27), w, int(h * 0.72))).convert("RGB")


def cover_resize(image: Image.Image, size=(W, H), focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    max_left = nw - tw
    max_top = nh - th
    left = int(max_left * min(1.0, max(0.0, focus[0])))
    top = int(max_top * min(1.0, max(0.0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def contain_resize(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    mw, mh = max_size
    scale = min(mw / image.width, mh / image.height)
    return image.resize((int(image.width * scale), int(image.height * scale)), Image.Resampling.LANCZOS)


def soft_canvas(image: Image.Image, foreground_height=1540, focus=(0.5, 0.5)) -> Image.Image:
    bg = cover_resize(image, (W, H), focus).filter(ImageFilter.GaussianBlur(28))
    bg = Image.blend(bg, Image.new("RGB", (W, H), (255, 232, 235)), 0.20)
    canvas = bg.convert("RGBA")

    scale = foreground_height / image.height
    fg = image.resize((int(image.width * scale), foreground_height), Image.Resampling.LANCZOS)
    fg = fg.filter(ImageFilter.UnsharpMask(radius=1.1, percent=145, threshold=2))
    x = int((W - fg.width) * min(1.0, max(0.0, focus[0])))
    y = (H - fg.height) // 2
    canvas.alpha_composite(fg.convert("RGBA"), (x, y))
    return canvas.convert("RGB")


def full_scene(image: Image.Image, focus=(0.5, 0.5)) -> Image.Image:
    out = cover_resize(image, (W, H), focus)
    out = out.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))
    return out


def split_grid(image: Image.Image, rows: int, cols: int, *, crop=(0, 0, 0, 0), top_margin=0) -> list[Image.Image]:
    usable = image.crop((0, top_margin, image.width, image.height))
    cw = usable.width // cols
    ch = usable.height // rows
    panels = []
    l_crop, t_crop, r_crop, b_crop = crop
    for row in range(rows):
        for col in range(cols):
            left = col * cw
            top = row * ch
            cell = usable.crop((left, top, left + cw, top + ch))
            cell = cell.crop((l_crop, t_crop, cell.width - r_crop, cell.height - b_crop))
            panels.append(cell.convert("RGB"))
    return panels


def blur_number_badge(panel: Image.Image) -> Image.Image:
    out = panel.copy()
    blurred = out.filter(ImageFilter.GaussianBlur(18))
    mask = Image.new("L", out.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((-28, -28, 104, 104), fill=255)
    out.paste(blurred, (0, 0), mask)
    return out


def prepare_sources() -> dict[str, Image.Image]:
    img_hero = open_rgb("ChatGPT Image 01_48_44 29 thg 6, 2026.png")
    grid_mix = split_grid(open_rgb("ChatGPT Image 22_39_52 29 thg 6, 2026.png"), 3, 3, crop=(6, 6, 6, 6))
    grid_pink = split_grid(open_rgb("ChatGPT Image 22_39_58 29 thg 6, 2026.png"), 3, 3, crop=(6, 6, 6, 6))
    grid_story = [
        blur_number_badge(p)
        for p in split_grid(
            open_rgb("ChatGPT Image 22_43_49 29 thg 6, 2026.png"),
            5,
            3,
            crop=(8, 44, 8, 42),
        )
    ]
    grid_cat = [
        blur_number_badge(p)
        for p in split_grid(
            open_rgb("ChatGPT Image 22_47_53 29 thg 6, 2026.png"),
            3,
            3,
            crop=(12, 28, 12, 92),
            top_margin=58,
        )
    ]
    return {
        "hero": img_hero,
        **{f"mix_{i+1}": p for i, p in enumerate(grid_mix)},
        **{f"pink_{i+1}": p for i, p in enumerate(grid_pink)},
        **{f"story_{i+1}": p for i, p in enumerate(grid_story)},
        **{f"cat_{i+1}": p for i, p in enumerate(grid_cat)},
        "pink_sku": open_rgb("vn-11134207-7ras8-m3x1ajyk5kn0e5.png"),
        "yellow_sku": open_rgb("vn-11134207-7ras8-m3x1ak0i2psx5e.png"),
        "combo_sku": open_rgb("vn-11134207-7ras8-m3x1ak6ltsqk74.png"),
        "real_front_rotate": crop_phone_screenshot(
            open_rgb("z7985967814255_f659dffbfd342ce3b99b1712ca623480.jpg")
        ),
        "real_front_pair": crop_phone_screenshot(
            open_rgb("z7985967828921_082bd3dee84a71bef50fa8a990cdbe4c.jpg")
        ),
        "real_back_mechanism": crop_phone_screenshot(
            open_rgb("z7985967842473_b40fbb735d56d2ca40d662c957dd0173.jpg")
        ),
    }


VIDEOS = {
    "video_01_cute_desk_review": [
        ("hero", "full", (0.50, 0.48)),
        ("mix_1", "soft", (0.50, 0.50)),
        ("mix_2", "full", (0.48, 0.48)),
        ("mix_3", "full", (0.50, 0.50)),
        ("mix_6", "full", (0.52, 0.48)),
        ("mix_8", "full", (0.50, 0.48)),
        ("pink_9", "soft", (0.52, 0.50)),
        ("story_15", "full", (0.54, 0.50)),
    ],
    "video_02_gap_xoay_chi_tiet": [
        ("pink_2", "full", (0.50, 0.48)),
        ("real_back_mechanism", "full", (0.52, 0.50)),
        ("real_front_pair", "full", (0.48, 0.50)),
        ("real_back_mechanism", "full", (0.50, 0.50)),
        ("real_front_rotate", "full", (0.50, 0.50)),
        ("pink_7", "full", (0.50, 0.52)),
        ("real_front_rotate", "full", (0.52, 0.50)),
        ("pink_9", "full", (0.50, 0.50)),
    ],
    "video_03_so_mau_so_mau": [
        ("hero", "full", (0.48, 0.48)),
        ("mix_1", "full", (0.50, 0.48)),
        ("pink_1", "full", (0.50, 0.48)),
        ("mix_1", "full", (0.50, 0.48)),
        ("mix_7", "full", (0.50, 0.50)),
        ("mix_8", "full", (0.50, 0.50)),
        ("story_13", "full", (0.50, 0.48)),
        ("story_14", "full", (0.50, 0.48)),
    ],
    "video_04_lifestyle_qua_tang": [
        ("cat_1", "soft", (0.50, 0.50)),
        ("cat_2", "full", (0.50, 0.46)),
        ("real_back_mechanism", "full", (0.52, 0.50)),
        ("real_front_pair", "full", (0.50, 0.50)),
        ("real_back_mechanism", "full", (0.50, 0.50)),
        ("real_front_rotate", "full", (0.50, 0.50)),
        ("cat_8", "full", (0.50, 0.50)),
        ("cat_9", "soft", (0.50, 0.50)),
    ],
}


VOICE_SCRIPTS = {
    "voice_01_cute_desk_review.txt": """[curious] Mấy ní có hay vừa xem phim vừa cắm cúi tìm chỗ kê điện thoại không...
[gasp] Cái giá đỡ hình thú này nhìn cái mặt thôi là muốn bấm mua rồi á.
[happy] Để trên bàn học hay bàn làm việc là góc nhỏ tự nhiên sáng bừng lên liền.
[explaining] Phần chân đế rộng, hai chân đỡ phía trước ôm máy khá chắc, dựng dọc để lướt TikTok cũng ổn.
[excited] Xoay sang ngang xem phim thì đúng kiểu rảnh tay, vừa ăn vặt vừa chill được luôn.
[confident] Điểm mình thích là nó không chỉ xinh, mà còn gấp lại gọn, bỏ túi mang đi học đi làm cũng tiện.
[playful] Ai mê đồ pastel cute cute, mấy dợ nhìn em này chắc khó thoát.
[confident] Mình để ở giỏ hàng, bấm xem mẫu còn màu nào nha... Dứt lẹ!""",
    "voice_02_gap_xoay_chi_tiet.txt": """[gasp] Khoan đã mấy dợ, cái giá đỡ nhỏ xíu này mà chỉnh được nhiều góc phết.
[excited] Mở ra một cái là thành chân kê điện thoại, không cần lắp ráp gì lằng nhằng.
[explaining] Phần khớp sau có thể nâng hạ, đổi góc nhìn cho đỡ mỏi cổ khi học online hoặc xem video.
[confident] Chân đế tròn bên dưới giúp đặt trên bàn nhìn vững hơn, không bị cảm giác chông chênh.
[curious] Dựng dọc thì lướt tin nhắn, xoay ngang thì xem phim, để tablet nhỏ cũng khá hợp.
[playful] Nói đơn giản là vừa là đồ trang trí, vừa là trợ thủ giữ máy cho mấy ní.
[happy] Mẫu hình thú nhìn rất dễ thương, lên góc bàn là có mood học bài liền.
[confident] Thích kiểu vừa xinh vừa dùng được thì bấm giỏ hàng xem màu nha... Dứt!""",
    "voice_03_so_mau_so_mau.txt": """[happy] Nếu mấy ní thích đồ cute nhưng không muốn quá trẻ con, bộ giá đỡ này khá đáng xem.
[amazed] Có thỏ hồng, vịt vàng, mèo nâu, nhìn mỗi mẫu một vibe khác nhau luôn.
[explaining] Thỏ hồng hợp bàn pastel, vịt vàng nhìn nổi bật hơn, còn mèo nâu thì dịu và dễ phối góc làm việc.
[confident] Điểm chung là đều có chân đỡ điện thoại phía trước, đặt máy lên nhìn gọn gàng hơn hẳn.
[playful] Một món nhỏ thôi mà cứu được cảnh điện thoại nằm úp nằm nghiêng khắp bàn đó mấy dợ.
[softly] Mình thấy hợp để dùng hằng ngày, decor phòng, hoặc mua tặng bạn thân cũng xinh.
[excited] Ai đang setup góc học tập cho dễ thương hơn thì nên nghía thử.
[confident] Link mình để ở giỏ hàng, vào chọn màu hợp vibe của mấy ní nha... Dứt lẹ!""",
    "voice_04_lifestyle_qua_tang.txt": """[curious] Có món nào vừa decor bàn, vừa dùng được, lại đem tặng không bị nhạt không ta...
[gasp] Đây nè mấy dợ, giá đỡ điện thoại hình thú, nhìn nhỏ mà có võ.
[happy] Đặt lên bàn là góc học tập trông mềm hơn, đáng yêu hơn, mà vẫn rất gọn.
[explaining] Khi cần dùng thì mở chân đỡ ra, chỉnh góc rồi đặt điện thoại lên để xem bài, xem phim hoặc gọi video.
[confident] Không dùng nữa thì gấp lại, bỏ vào túi vải hoặc hộp quà nhìn cũng rất xinh.
[playful] Tặng bạn mê đồ cute là khả năng bị hỏi link khá cao nha.
[softly] Với mình đây là kiểu món nhỏ, giá dễ chịu, nhưng lên hình rất bắt mắt.
[confident] Muốn xem thêm mẫu thỏ, mèo, vịt thì bấm giỏ hàng ngay nha... Dứt!""",
}


def render_scenes(sources: dict[str, Image.Image]) -> dict[str, list[Path]]:
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, list[Path]] = {}
    for video_name, specs in VIDEOS.items():
        paths = []
        for index, (key, mode, focus) in enumerate(specs, 1):
            src = sources[key]
            if mode == "soft":
                scene = soft_canvas(src, focus=focus)
            else:
                scene = full_scene(src, focus=focus)
            path = SCENE_DIR / f"{video_name}_{index:02d}.png"
            scene.save(path, quality=95)
            paths.append(path)
        result[video_name] = paths
    return result


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def make_segment(scene_path: Path, segment_path: Path, scene_index: int) -> None:
    drift = 18 if scene_index % 2 else -18
    zoom_expr = "min(1.055,1+0.055*on/{frames})".format(frames=max(1, SCENE_FRAMES - 1))
    x_expr = f"iw/2-(iw/zoom/2)+{drift}*sin(on/18)"
    y_expr = "ih/2-(ih/zoom/2)+10*sin(on/23)"
    vf = (
        f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':"
        f"d={SCENE_FRAMES}:s={W}x{H}:fps={FPS},"
        "fade=t=in:st=0:d=0.12,fade=t=out:st=2.53:d=0.12,format=yuv420p"
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
            str(SCENE_FRAMES),
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


def make_video(video_name: str, scene_paths: list[Path]) -> Path:
    video_segments = SEGMENT_DIR / video_name
    video_segments.mkdir(parents=True, exist_ok=True)
    segments = []
    for index, scene_path in enumerate(scene_paths, 1):
        segment_path = video_segments / f"segment_{index:02d}.mp4"
        make_segment(scene_path, segment_path, index)
        segments.append(segment_path)

    concat_list = video_segments / "concat.txt"
    concat_list.write_text(
        "".join(f"file '{p.as_posix()}'\n" for p in segments),
        encoding="utf-8",
    )
    output = OUT_DIR / f"{video_name}_1080x1920.mp4"
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
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output),
        ]
    )
    return output


def write_voice_scripts() -> None:
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in VOICE_SCRIPTS.items():
        (SCRIPT_DIR / name).write_text(text.strip() + "\n", encoding="utf-8")


def clean_outputs() -> None:
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    SEGMENT_DIR.mkdir(parents=True, exist_ok=True)
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    clean_outputs()
    sources = prepare_sources()
    scene_map = render_scenes(sources)
    outputs = [make_video(name, scenes) for name, scenes in scene_map.items()]
    write_voice_scripts()
    for output in outputs:
        print(output)
    for script in sorted(SCRIPT_DIR.glob("*.txt")):
        print(script)


if __name__ == "__main__":
    main()
