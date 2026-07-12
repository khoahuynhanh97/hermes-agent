import cv2
import numpy as np
import os
import sys
from rembg import remove, new_session
from PIL import Image

# Ensure stdout is UTF-8 on Windows
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

video_path = r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu\vn-11110107-6v98x-mk5ai3f0f18g8e.16000081769863419.mp4"
bg_image_path = r"C:\Users\TeamSol\Downloads\TIKTOK\Background\My desk pink and white inspo🤍.jpg"
output_dir = r"C:\Work\Code\Hermes_download\hermes-agent\scratch"
os.makedirs(output_dir, exist_ok=True)
output_video_path = os.path.join(output_dir, "output_swapped_no_audio.mp4")
final_video_path = os.path.join(output_dir, "output_swapped_with_audio.mp4")

print(f"[*] Khởi động tiến trình tách nền AI cho video: {os.path.basename(video_path)}")
print(f"[*] Nền mới sử dụng: {os.path.basename(bg_image_path)}")

# 1. Đọc ảnh nền an toàn với ký tự Unicode đường dẫn Windows
try:
    img_array = np.fromfile(bg_image_path, dtype=np.uint8)
    bg_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
except Exception as e:
    print(f"Error: Không thể đọc mảng tệp ảnh nền: {e}")
    bg_img = None

if bg_img is None:
    print(f"Error: Không thể giải mã ảnh nền tại {bg_image_path}")
    exit(1)
bg_img_resized = cv2.resize(bg_img, (720, 1280))

# 2. Khởi tạo video capture
cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Error: Không thể mở video gốc.")
    exit(1)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print(f"[i] Video resolution: {width}x{height} | FPS: {fps:.2f} | Tổng số khung hình: {frame_count}")

# 3. Khởi tạo video writer (ghi file MP4 tạm thời không tiếng)
fourcc = cv2.VideoWriter_fourcc(*'mp4v')
out = cv2.VideoWriter(output_video_path, fourcc, fps, (720, 1280))

# Khởi tạo phiên rembg (u2net) để tối ưu hóa bộ nhớ và tốc độ
print("[*] Đang tải mô hình AI tách nền u2net...")
session = new_session("u2netp") # Dùng bản u2netp (phiên bản gọn nhẹ) để chạy siêu nhanh trên CPU!

print("[*] Bắt đầu quét tách nền và ghép nối khung hình...")
frame_idx = 0

while True:
    ret, frame = cap.read()
    if not ret:
        break
        
    frame_idx += 1
    
    # 4. Tách nền bằng rembg
    # Chuyển BGR (OpenCV) sang RGB (PIL)
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_frame)
    
    # Chạy tách nền
    cutout = remove(pil_img, session=session)
    cutout_np = np.array(cutout)
    
    # Tách kênh màu và kênh alpha (độ mờ nền)
    fg_rgb = cutout_np[:, :, :3]
    alpha = cutout_np[:, :, 3] / 255.0
    alpha = np.expand_dims(alpha, axis=2)
    
    # Đảm bảo kích thước khớp với 720x1280
    if fg_rgb.shape[0] != 1280 or fg_rgb.shape[1] != 720:
        fg_rgb = cv2.resize(fg_rgb, (720, 1280))
        alpha = cv2.resize(alpha, (720, 1280))
        alpha = np.expand_dims(alpha, axis=2)
        
    # Ghép đè lên ảnh nền
    composite = (fg_rgb * alpha + bg_img_resized * (1 - alpha)).astype(np.uint8)
    
    # Chuyển RGB về BGR để lưu bằng OpenCV VideoWriter
    composite_bgr = cv2.cvtColor(composite, cv2.COLOR_RGB2BGR)
    out.write(composite_bgr)
    
    if frame_idx % 20 == 0 or frame_idx == frame_count:
        print(f"  -> Tiến trình: {frame_idx}/{frame_count} khung hình ({frame_idx/frame_count*100:.1f}%)")

cap.release()
out.release()
print(f"[+] Đã tạo xong video tạm thời không tiếng tại: {output_video_path}")

# 5. Ghép lại âm thanh gốc bằng FFmpeg
print("[*] Đang ghép lại âm thanh gốc từ video ban đầu...")
ffmpeg_cmd = f'ffmpeg -y -i "{output_video_path}" -i "{video_path}" -map 0:v -map 1:a -c:v copy -c:a aac "{final_video_path}"'
ret_code = os.system(ffmpeg_cmd)

if ret_code == 0 and os.path.exists(final_video_path):
    print(f"[+] THÀNH CÔNG! Video thành phẩm đã được ghép nền và giữ nguyên âm thanh:")
    print(f"    Đường dẫn: {final_video_path}")
else:
    print(f"[!] Cảnh báo: Lỗi ghép âm thanh hoặc không tìm thấy ffmpeg. Dùng video không tiếng tại {output_video_path}")
