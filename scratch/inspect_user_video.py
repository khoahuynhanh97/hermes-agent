import cv2
import os

video_path = r"C:\Users\TeamSol\Downloads\TIKTOK\gia_do_dien_thoai_hinh_thu\vn-11110107-6v98x-mk5ai3f0f18g8e.16000081769863419.mp4"
output_image = r"C:\Work\Code\Hermes_download\hermes-agent\scratch\user_video_midframe.png"

os.makedirs(os.path.dirname(output_image), exist_ok=True)

cap = cv2.VideoCapture(video_path)
if not cap.isOpened():
    print("Error: Could not open video.")
    exit(1)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = cap.get(cv2.CAP_PROP_FPS)
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
duration = frame_count / fps if fps > 0 else 0

print(f"Resolution: {width}x{height}")
print(f"FPS: {fps:.2f}")
print(f"Frame Count: {frame_count}")
print(f"Duration: {duration:.2f}s")

# Read middle frame
mid_frame_idx = frame_count // 2
cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame_idx)
ret, frame = cap.read()
if ret:
    cv2.imwrite(output_image, frame)
    print(f"Saved middle frame to: {output_image}")
else:
    print("Error: Could not read middle frame.")

cap.release()
