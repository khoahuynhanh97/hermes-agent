from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

import cv2
import numpy as np


SRC_DEFAULT = Path(
    r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu\vn-11110107-6v98x-mk5ai3f0f18g8e.16000081769863419.mp4"
)
OUT_DIR_DEFAULT = Path(
    r"C:\Work\Code\Hermes_download\hermes-agent\projects\gia-do-dien-thoai-hinh-thu-xinh-dep\exports\rebackground_no_text"
)


def make_background(width: int, height: int) -> np.ndarray:
    bg = np.zeros((height, width, 3), dtype=np.uint8)

    # Bright blue window / sky.
    for y in range(height):
        t = y / max(1, height - 1)
        top = np.array([245, 226, 160], dtype=np.float32)
        bottom = np.array([250, 244, 238], dtype=np.float32)
        bg[y, :, :] = (top * (1 - t) + bottom * t).astype(np.uint8)

    # Window panels.
    cv2.rectangle(bg, (35, 45), (width - 35, int(height * 0.42)), (250, 252, 246), -1)
    cv2.rectangle(bg, (55, 65), (width // 2 - 8, int(height * 0.39)), (240, 222, 155), -1)
    cv2.rectangle(bg, (width // 2 + 8, 65), (width - 55, int(height * 0.39)), (238, 218, 148), -1)
    cv2.line(bg, (width // 2, 55), (width // 2, int(height * 0.42)), (238, 242, 235), 10)
    cv2.line(bg, (45, int(height * 0.42)), (width - 45, int(height * 0.42)), (238, 242, 235), 12)

    # Soft desk area.
    desk_y = int(height * 0.45)
    cv2.rectangle(bg, (0, desk_y), (width, height), (232, 235, 167), -1)
    step = max(26, width // 18)
    for x in range(-step, width + step, step):
        cv2.rectangle(bg, (x, desk_y), (x + step // 2, height), (246, 246, 201), -1)
    for y in range(desk_y, height + step, step):
        cv2.rectangle(bg, (0, y), (width, y + step // 2), (246, 246, 201), -1)

    # Blurred pastel props with no readable text.
    cv2.circle(bg, (95, int(height * 0.57)), 54, (228, 230, 240), -1)
    cv2.rectangle(bg, (width - 190, int(height * 0.50)), (width - 55, int(height * 0.62)), (235, 215, 226), -1)
    cv2.circle(bg, (width - 110, int(height * 0.31)), 42, (235, 242, 236), -1)
    cv2.circle(bg, (width - 105, int(height * 0.31)), 24, (215, 226, 214), -1)

    # Flower-like color blobs, intentionally blurred.
    for i in range(15):
        angle = i / 15 * math.tau
        cx = int(width * 0.18 + math.cos(angle) * 32)
        cy = int(height * 0.32 + math.sin(angle) * 25)
        cv2.circle(bg, (cx, cy), 14, (190, 178, 236), -1)
    cv2.rectangle(bg, (int(width * 0.17), int(height * 0.35)), (int(width * 0.19), int(height * 0.48)), (115, 160, 115), -1)

    bg = cv2.GaussianBlur(bg, (0, 0), 5.0)
    return bg


def remove_pink_text(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    height, width = frame.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)

    # The source has a fixed pink caption near the upper center.
    y1, y2 = int(height * 0.13), int(height * 0.25)
    x1, x2 = int(width * 0.12), int(width * 0.88)
    roi = hsv[y1:y2, x1:x2]

    pink = cv2.inRange(roi, np.array([140, 35, 80]), np.array([179, 255, 255]))
    pink |= cv2.inRange(roi, np.array([0, 35, 100]), np.array([8, 255, 255]))
    pink = cv2.dilate(pink, np.ones((5, 11), np.uint8), iterations=2)
    mask[y1:y2, x1:x2] = pink

    if int(mask.sum()) == 0:
        return frame
    return cv2.inpaint(frame, mask, 5, cv2.INPAINT_TELEA)


def foreground_mask(frame: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    small = cv2.resize(frame, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    sh, sw = small.shape[:2]

    mask = np.zeros((sh, sw), dtype=np.uint8)
    rect = (int(sw * 0.04), int(sh * 0.20), int(sw * 0.92), int(sh * 0.78))
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    cv2.grabCut(small, mask, rect, bgd, fgd, 2, cv2.GC_INIT_WITH_RECT)
    mask = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)

    # Remove specks, keep the review subject and hands.
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8), iterations=2)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros_like(mask)
    for idx in range(1, num):
        area = stats[idx, cv2.CC_STAT_AREA]
        x = stats[idx, cv2.CC_STAT_LEFT]
        y = stats[idx, cv2.CC_STAT_TOP]
        comp_w = stats[idx, cv2.CC_STAT_WIDTH]
        comp_h = stats[idx, cv2.CC_STAT_HEIGHT]
        bottom = y + comp_h
        center_x = x + comp_w / 2
        is_front_subject = bottom > sh * 0.82 and sw * 0.08 < center_x < sw * 0.92
        if area >= 700 and is_front_subject:
            keep[labels == idx] = 255

    keep = cv2.resize(keep, (w, h), interpolation=cv2.INTER_LINEAR)
    keep = cv2.GaussianBlur(keep, (0, 0), 2.5)
    return keep.astype(np.float32) / 255.0


def render_samples(src: Path, out_dir: Path, count: int = 8) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(src))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    bg = make_background(width, height)

    frames = []
    for i, pos in enumerate(np.linspace(0, max(0, total - 1), count).astype(int), start=1):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(pos))
        ok, frame = cap.read()
        if not ok:
            continue
        clean = remove_pink_text(frame)
        alpha = foreground_mask(clean)[..., None]
        comp = (clean.astype(np.float32) * alpha + bg.astype(np.float32) * (1 - alpha)).astype(np.uint8)
        sample = cv2.resize(comp, (360, 640), interpolation=cv2.INTER_AREA)
        cv2.imwrite(str(out_dir / f"sample_{i:02d}.jpg"), sample)
        frames.append(sample)
    cap.release()

    if frames:
        cols, rows = 2, math.ceil(len(frames) / 2)
        sheet = np.full((rows * 640 + (rows + 1) * 8, cols * 360 + (cols + 1) * 8, 3), 255, dtype=np.uint8)
        for idx, frame in enumerate(frames):
            r, c = divmod(idx, cols)
            y = 8 + r * (640 + 8)
            x = 8 + c * (360 + 8)
            sheet[y : y + 640, x : x + 360] = frame
        cv2.imwrite(str(out_dir / "contact.jpg"), sheet)


def render_video(src: Path, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(src))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    bg = make_background(width, height)

    temp = out_dir / "rebackground_no_text_720p_silent.mp4"
    writer = cv2.VideoWriter(str(temp), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    frame_idx = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        clean = remove_pink_text(frame)
        alpha = foreground_mask(clean)[..., None]
        comp = (clean.astype(np.float32) * alpha + bg.astype(np.float32) * (1 - alpha)).astype(np.uint8)
        writer.write(comp)
        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"processed {frame_idx}/{total}")

    cap.release()
    writer.release()

    final = out_dir / "gia_do_hinh_thu_rebackground_no_text_1080p.mp4"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(temp),
        "-i",
        str(src),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0?",
        "-vf",
        "scale=1080:1920:flags=lanczos",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        str(final),
    ]
    subprocess.run(cmd, check=True)
    return final


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=Path, default=SRC_DEFAULT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT)
    parser.add_argument("--samples", action="store_true")
    args = parser.parse_args()

    if args.samples:
        render_samples(args.src, args.out_dir / "samples")
    else:
        print(render_video(args.src, args.out_dir))


if __name__ == "__main__":
    main()
