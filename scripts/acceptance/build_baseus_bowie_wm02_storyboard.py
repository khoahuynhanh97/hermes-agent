"""
scripts/build_baseus_bowie_wm02_storyboard.py — Draft Frame Storyboard for Baseus Bowie WM02
"""

import json
from pathlib import Path

def main():
    print("=== DRAFTING FRAME STORYBOARD FOR BASEUS BOWIE WM02 ===")

    storyboard = {
        "product_name": "Baseus Bowie WM02",
        "concept": "Tiny, Bold, Freedom",
        "audience": "Gen Z, mobile-first, tech-minimalists",
        "format": "15s social ad (TikTok / Reels / Shorts)",
        "pacing": "Fast cuts, bass-heavy beat",
        "frames": [
            {
                "frame_id": "frame_1",
                "time_range": "0s - 3s",
                "scene_title": "Hook & Form Factor",
                "visual_description": "Extreme close-up of the translucent capsule charging case opening under neon lights. The ultra-compact earbuds glow softly.",
                "voiceover_text": "Tí hon nhưng cực chiến! Đây là Baseus Bowie WM02.",
                "on_screen_text": "Tiny & Bold | Baseus Bowie WM02",
                "camera_movement": "Rapid zoom-in & rotate"
            },
            {
                "frame_id": "frame_2",
                "time_range": "3s - 7s",
                "scene_title": "Instant Connectivity",
                "visual_description": "Seamless Bluetooth 5.3 pairing animation connecting to a smartphone screen instantaneously with zero lag visual wave.",
                "voiceover_text": "Bluetooth 5.3 - Kết nối siêu tốc, không độ trễ.",
                "on_screen_text": "Bluetooth 5.3 | Ultra-Fast Pairing",
                "camera_movement": "Quick side pan"
            },
            {
                "frame_id": "frame_3",
                "time_range": "7s - 11s",
                "scene_title": "All-Day Battery Power",
                "visual_description": "Dynamic split-screen showing a Gen Z user listening to music from morning coffee to late-night gaming. Battery ring fills to 25 Hours.",
                "voiceover_text": "Pin 25 giờ liên tục. Quẩy nhạc cả ngày không lo hết pin.",
                "on_screen_text": "25 Hours Battery | Play All Day",
                "camera_movement": "Dynamic split-screen tracking"
            },
            {
                "frame_id": "frame_4",
                "time_range": "11s - 15s",
                "scene_title": "Call To Action & Freedom",
                "visual_description": "Hero shot of the user wearing the lightweight earbud effortlessly, popping the capsule case shut. Bold CTA button pops up.",
                "voiceover_text": "Chỏm tai siêu nhẹ, tự do trải nghiệm ngay!",
                "on_screen_text": "Baseus Bowie WM02 - Mua Ngay",
                "camera_movement": "Hero front shot with pulse zoom"
            }
        ]
    }

    out_path = Path(r"C:\Users\ninak\Downloads\baseus_bowie_wm02_storyboard.json")
    out_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== STORYBOARD DRAFTED SUCCESSFULLY ===")
    print(f"Total Frames : {len(storyboard['frames'])}")
    print(f"Saved JSON   : {out_path}")


if __name__ == "__main__":
    main()
