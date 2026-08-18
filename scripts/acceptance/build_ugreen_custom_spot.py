"""
scripts/build_ugreen_custom_spot.py — Recreate Official 30s Ugreen Nexode Robot Uno Spot
"""

import os
import sys
import subprocess
from pathlib import Path

ffmpeg = os.environ.get("FFMPEG_PATH", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe")
src_dir = Path(r"C:\Users\ninak\Downloads\sac-ugreen")
out_dir = src_dir / "render_spot_30s"
out_dir.mkdir(parents=True, exist_ok=True)

# Product images
img_front = src_dir / "sg-11134201-7rbm5-m62nvl361r4n2c.png"
img_variants = src_dir / "sg-11134201-7rbm9-m62nviffzac796.png"
img_led = src_dir / "vn-11134103-81ztc-mlftjsv7bklkcc.png"

def render_scene(img_path, duration_sec, out_path, filter_complex):
    cmd = [
        ffmpeg, "-y",
        "-loop", "1",
        "-i", str(img_path),
        "-t", str(duration_sec),
        "-vf", filter_complex,
        "-c:v", "libx264",
        "-preset", "medium",
        "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        str(out_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error rendering {out_path.name}: {res.stderr}")
        raise RuntimeError(f"FFmpeg render failed for {out_path.name}")
    print(f"Rendered scene: {out_path.name} ({duration_sec}s)")

def main():
    print("=== RECREATING OFFICIAL 30S UGREEN SPOT ===")

    # Scene 1 [0-5s] (5s): Front shot (smile LED) - Smooth zoom-in
    sc1_path = out_dir / "scene_1.mp4"
    vf1 = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,"
        "zoompan=z='min(zoom+0.0012,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=150:s=720x1280"
    )
    render_scene(img_front, 5.0, sc1_path, vf1)

    # Scene 2 [5-15s] (10s): Quick switch between 30W/65W - Smooth panning
    sc2_path = out_dir / "scene_2.mp4"
    vf2 = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,"
        "zoompan=z='min(zoom+0.0008,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=300:s=720x1280"
    )
    render_scene(img_variants, 10.0, sc2_path, vf2)

    # Scene 3 [15-25s] (10s): Close-up LED face showing charge state
    sc3_path = out_dir / "scene_3.mp4"
    vf3 = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,"
        "zoompan=z='min(zoom+0.0015,1.20)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=300:s=720x1280"
    )
    render_scene(img_led, 10.0, sc3_path, vf3)

    # Scene 4 [25-30s] (5s): Hero Product + Phone with Call To Action Text Overlay
    sc4_path = out_dir / "scene_4.mp4"
    text_overlay = "Ugreen Uno - Nho gon, Sac cuc nhanh."
    vf4 = (
        "scale=720:1280:force_original_aspect_ratio=decrease,"
        "pad=720:1280:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"drawtext=text='{text_overlay}':fontcolor=white:fontsize=36:box=1:boxcolor=black@0.6:boxborderw=10:x=(w-text_w)/2:y=h-180"
    )
    render_scene(img_front, 5.0, sc4_path, vf4)

    # Concatenate into official final video
    concat_list = out_dir / "concat.txt"
    with open(concat_list, "w", encoding="utf-8") as f:
        f.write(f"file '{sc1_path.resolve()}'\n")
        f.write(f"file '{sc2_path.resolve()}'\n")
        f.write(f"file '{sc3_path.resolve()}'\n")
        f.write(f"file '{sc4_path.resolve()}'\n")

    final_spot = src_dir / "ugreen_robot_uno_30s_official.mp4"
    concat_cmd = [
        ffmpeg, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(final_spot)
    ]
    subprocess.run(concat_cmd, check=True)

    print("\n=== FINISHED RECREATING OFFICIAL SPOT ===")
    print(f"Official Video File : {final_spot}")
    print(f"Video File Size     : {final_spot.stat().st_size} bytes")

if __name__ == "__main__":
    main()
