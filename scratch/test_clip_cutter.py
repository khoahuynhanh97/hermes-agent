import os
import sys
import json
import shutil
import cv2
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from editor.clip_cutter import cut_materials_into_clips

def create_long_dummy_video(filename, width=640, height=480, duration=6, fps=24):
    """Creates a longer animated video for testing cutting."""
    print(f"[*] Đang tạo video mẫu dài thử nghiệm: {filename} ({width}x{height}, {duration}s)...")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    
    for frame_idx in range(duration * fps):
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Grid lines
        for y in range(0, height, 40):
            cv2.line(img, (0, y), (width, y), (50, 50, 50), 1)
        for x in range(0, width, 40):
            cv2.line(img, (x, 0), (x, height), (50, 50, 50), 1)
            
        # Draw bouncing circle
        center_x = int(width / 2 + 150 * np.sin(frame_idx / 8.0))
        center_y = int(height / 2 + 80 * np.cos(frame_idx / 6.0))
        cv2.circle(img, (center_x, center_y), 45, (0, 255, 0), -1)
        
        cv2.putText(img, f"Long Frame: {frame_idx}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        out.write(img)
        
    out.release()
    print("[+] Tạo video mẫu dài thành công.")

def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== KIỂM THỬ BỘ CẮT CLIP (CLIP CUTTER) ===")
    
    # Paths setup
    base_dir = os.path.dirname(os.path.abspath(__file__))
    temp_materials = os.path.join(base_dir, "temp_materials")
    temp_clips = os.path.join(base_dir, "temp_clips")
    
    os.makedirs(temp_materials, exist_ok=True)
    os.makedirs(temp_clips, exist_ok=True)
    
    temp_created = False
    
    try:
        # Check if we have files in existing project materials
        projects_dir = os.path.abspath(os.path.join(base_dir, "..", "projects"))
        mats_to_use = temp_materials
        
        has_existing = False
        if os.path.exists(projects_dir):
            for slug in os.listdir(projects_dir):
                mats_dir = os.path.join(projects_dir, slug, "materials")
                if os.path.exists(mats_dir):
                    valid_files = [f for f in os.listdir(mats_dir) if f.lower().endswith(('.mp4', '.mov', '.webm', '.m4v'))]
                    if valid_files:
                        mats_to_use = mats_dir
                        # Set destination clips dir to this project's clips dir
                        clips_to_use = os.path.join(projects_dir, slug, "clips")
                        os.makedirs(clips_to_use, exist_ok=True)
                        product_slug = slug
                        has_existing = True
                        print(f"[*] Sử dụng phôi thực tế từ dự án: {slug}")
                        break
                        
        if not has_existing:
            # Create a 6-second video in temp_materials
            dummy_file = os.path.join(temp_materials, "dummy_product_video.mp4")
            create_long_dummy_video(dummy_file)
            clips_to_use = temp_clips
            product_slug = "test_product"
            temp_created = True
            
        print(f"\n[*] Bắt đầu cắt phôi từ '{mats_to_use}' vào '{clips_to_use}'...")
        
        # Run cutter
        # Cut 2.0s clips, skip 1.0s, max 2 clips
        new_clips = cut_materials_into_clips(
            mats_to_use,
            clips_to_use,
            product_slug,
            clip_duration=2.0,
            skip_start_seconds=1.0,
            max_clips_per_video=2,
            export_vertical=True,
            mute_audio=True,
            analyze_quality=True,
            reject_bad_clips=False
        )
        
        print(f"\n[+] Đã cắt thành công {len(new_clips)} clips.")
        for idx, clip in enumerate(new_clips):
            print(f"\n--- Clip {idx + 1} ---")
            print(f"File: {os.path.basename(clip['file_path']) if clip['file_path'] else 'Deleted/Failed'}")
            print(f"Source: {clip['source_file']}")
            print(f"Thời gian: {clip['start_time']}s - {clip['end_time']}s")
            print(f"Overall Score: {clip['overall_score']}")
            print(f"Đánh giá: {clip['recommendation']}")
            print(f"Lý do: {clip['reason']}")
            
    finally:
        # Cleanup temporary test folders if they were used
        if temp_created:
            print("\n[*] Đang dọn dẹp các thư mục thử nghiệm tạm thời...")
            try:
                shutil.rmtree(temp_materials)
                shutil.rmtree(temp_clips)
                print("[+] Đã dọn dẹp xong.")
            except Exception as e:
                print(f"[!] Cảnh báo: Lỗi dọn dẹp thư mục: {e}")

if __name__ == "__main__":
    main()
