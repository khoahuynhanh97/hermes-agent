import os
import sys

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from tools.video_analyser import analyze_video

def main():
    if sys.platform.startswith('win'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass
            
    print("=== TEST VIDEO PROMPT EXTRACTION ===")
    
    # Locate a sample video file from the project we just generated
    sample_video = r"c:\Work\Code\Hermes_download\hermes-agent\projects\gia-do-dien-thoai-co-the-xoay-360-do\materials\7961658011209.mp4"
    if not os.path.exists(sample_video):
        print(f"[!] Warning: Sample video not found at: {sample_video}")
        # Try to scan files in materials to find one
        materials_dir = r"c:\Work\Code\Hermes_download\hermes-agent\projects\gia-do-dien-thoai-co-the-xoay-360-do\materials"
        if os.path.exists(materials_dir):
            files = [os.path.join(materials_dir, f) for f in os.listdir(materials_dir) if f.lower().endswith(".mp4")]
            if files:
                sample_video = files[0]
                
    if not os.path.exists(sample_video):
        print("[x] Error: No sample video found to test with.")
        sys.exit(1)
        
    print(f"[*] Selected video: {sample_video}")
    
    # Check if Gemini key is available
    api_key = getattr(config, "GEMINI_API_KEY", "")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        print("[!] LỖI: Chưa cấu hình GEMINI_API_KEY trong file .env hoặc config.py.")
        sys.exit(0)
        
    prompt_text = """
Hãy xem kỹ video mẫu này và phân tích ngắn gọn:
1. Mô tả hành động chính (1 câu tiếng Việt).
2. Tạo 1 prompt tiếng Anh ngắn để tạo video tương tự.
"""
    
    print("[*] Gọi hàm phân tích video với callback log...")
    
    def test_log(msg):
        print(f"[TEST LOG CALLBACK] {msg}")
        
    result = analyze_video(sample_video, prompt_text=prompt_text, log_callback=test_log)
    
    print("\n=== KẾT QUẢ PHÂN TÍCH THÀNH CÔNG ===")
    print(result)

if __name__ == "__main__":
    main()
