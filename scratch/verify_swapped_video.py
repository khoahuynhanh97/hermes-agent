import os
import sys

# Ensure root directory is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from editor.clip_analyzer import verify_final_video

# Force stdout/stderr to use UTF-8 encoding on Windows to prevent UnicodeEncodeError
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

video_path = r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu\vn-11110107-6v98x-mk5ai3f0f18g8e_swapped.mp4"

print(f"[*] Đang thực hiện chạy kiểm định Quality Gate cho video vừa tạo tại: {video_path}")
if not os.path.exists(video_path):
    print("Error: File video không tồn tại.")
    exit(1)

# Run verification
report = verify_final_video(video_path)

print("\n" + "="*50)
print("             KẾT QUẢ KIỂM ĐỊNH QUALITY GATE")
print("="*50)
print(f"File: {os.path.basename(video_path)}")
print(f"Resolution: {report.get('width')}x{report.get('height')}")
print(f"Aspect Ratio: {report.get('aspect_ratio')}")
print(f"FPS: {report.get('fps')}")
print(f"Thời lượng: {report.get('duration')} giây")
print(f"Có luồng âm thanh: {'Có' if report.get('has_audio') else 'Không'}")
print(f"Tỉ lệ màn hình đen: {report.get('black_ratio', 0)*100:.2f}%")

if report.get("warnings"):
    print("\n[⚠️ WARNINGS ĐƯỢC PHÁT HIỆN]:")
    for w in report["warnings"]:
        print(f"  - {w}")
else:
    print("\n[✅ HOÀN HẢO]: Không phát hiện bất kỳ lỗi hay cảnh báo nào! Video đạt chuẩn phân phối TikTok.")
print("="*50)
