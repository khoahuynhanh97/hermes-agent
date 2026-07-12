import os
import sys
import json
import cv2
import numpy as np

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from editor.clip_analyzer import analyze_clip

def create_dummy_video(filename, width=640, height=480, duration=3, fps=24):
    """Creates a short animated video for testing purposes."""
    print(f"[*] Đang tạo video mẫu thử nghiệm: {filename} ({width}x{height}, {duration}s)...")
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filename, fourcc, fps, (width, height))
    
    # Draw simple moving animations
    for frame_idx in range(duration * fps):
        # Create dark background frame
        img = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add background grid lines for sharpness testing
        for y in range(0, height, 40):
            cv2.line(img, (0, y), (width, y), (40, 40, 40), 1)
        for x in range(0, width, 40):
            cv2.line(img, (x, 0), (x, height), (40, 40, 40), 1)
            
        # Draw moving colorful circle for motion testing
        center_x = int(width / 2 + 100 * np.sin(frame_idx / 4.0))
        center_y = int(height / 2 + 50 * np.cos(frame_idx / 4.0))
        cv2.circle(img, (center_x, center_y), 50, (0, 180, 255), -1)
        
        # Draw a sharp white square to test sharpness
        cv2.rectangle(img, (50, 50), (120, 120), (255, 255, 255), 2)
        
        # Add moving text
        cv2.putText(img, f"Frame: {frame_idx}", (30, height - 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        
        out.write(img)
        
    out.release()
    print("[+] Tạo video mẫu thành công.")

def main():
    # standard stdout encoding configuration for Windows command prompt
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== KIỂM THỬ BỘ PHÂN TÍCH CLIP (CLIP ANALYZER) ===")
    
    # Use existing material from projects if any
    test_video = None
    projects_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "projects"))
    
    if os.path.exists(projects_dir):
        for slug in os.listdir(projects_dir):
            mats_dir = os.path.join(projects_dir, slug, "materials")
            if os.path.exists(mats_dir):
                for f in os.listdir(mats_dir):
                    if f.lower().endswith(('.mp4', '.mov', '.webm', '.m4v')):
                        test_video = os.path.join(mats_dir, f)
                        print(f"[*] Tìm thấy video có sẵn từ dự án: {test_video}")
                        break
            if test_video:
                break
                
    # If no existing video, generate a temporary dummy one
    temp_created = False
    if not test_video:
        test_video = os.path.abspath(os.path.join(os.path.dirname(__file__), "temp_test_video.mp4"))
        create_dummy_video(test_video)
        temp_created = True
        
    # Run analysis
    print(f"\n[*] Tiến hành phân tích chất lượng cho: {os.path.basename(test_video)}")
    scores = analyze_clip(test_video)
    
    print("\n=== KẾT QUẢ PHÂN TÍCH ===")
    print(json.dumps(scores, indent=4, ensure_ascii=False))
    
    # Clean up temp file
    if temp_created and os.path.exists(test_video):
        try:
            os.remove(test_video)
            print("\n[+] Đã dọn dẹp video mẫu tạm thời.")
        except Exception as e:
            print(f"\n[!] Cảnh báo: Không thể dọn dẹp file tạm {test_video}: {e}")

if __name__ == "__main__":
    main()
