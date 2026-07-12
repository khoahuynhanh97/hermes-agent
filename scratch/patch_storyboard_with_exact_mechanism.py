from pathlib import Path

from PIL import Image, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "projects" / "gia-do-dien-thoai-hinh-thu-xinh-dep"
SOURCE_STORYBOARD = PROJECT / "storyboards" / "phone_stand_window_background_12shot_storyboard_v2_fixed_structure.png"
EXACT_SIDE = PROJECT / "materials" / "upscaled_panels" / "panel_super_res_3.jpg"
OUT = PROJECT / "storyboards" / "phone_stand_window_background_12shot_storyboard_v4_exact_mechanism.png"


def cover(image: Image.Image, size: tuple[int, int], focus=(0.5, 0.5)) -> Image.Image:
    tw, th = size
    scale = max(tw / image.width, th / image.height)
    nw = max(tw, int(image.width * scale + 0.5))
    nh = max(th, int(image.height * scale + 0.5))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    left = int((nw - tw) * min(1, max(0, focus[0])))
    top = int((nh - th) * min(1, max(0, focus[1])))
    return resized.crop((left, top, left + tw, top + th))


def paste_panel(board: Image.Image, panel: Image.Image, index: int, rows=4, cols=3) -> None:
    cell_w = board.width // cols
    cell_h = board.height // rows
    row = index // cols
    col = index % cols
    x = col * cell_w
    y = row * cell_h
    board.paste(panel.resize((cell_w, cell_h), Image.Resampling.LANCZOS), (x, y))


def main() -> None:
    board = Image.open(SOURCE_STORYBOARD).convert("RGB")
    exact = Image.open(EXACT_SIDE).convert("RGB")

    cell_w = board.width // 3
    cell_h = board.height // 4

    # Panel 02: exact full side angle. It shows the real upright support geometry,
    # phone angle, circular base, and screw positions from the provided reference.
    side_panel = cover(exact, (cell_w, cell_h), focus=(0.52, 0.56))
    side_panel = side_panel.filter(ImageFilter.UnsharpMask(radius=1.0, percent=130, threshold=2))

    # Panel 07: exact close-up crop of the base/lower hinge area from the same real angle.
    # This avoids the AI-created base mechanism that looked structurally wrong.
    base_crop = exact.crop((455, 560, 1065, 1364))
    base_panel = cover(base_crop, (cell_w, cell_h), focus=(0.55, 0.74))
    base_panel = base_panel.filter(ImageFilter.UnsharpMask(radius=1.0, percent=145, threshold=2))

    paste_panel(board, side_panel, 1)
    paste_panel(board, base_panel, 6)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    board.save(OUT, quality=95)
    print(OUT)


if __name__ == "__main__":
    main()
