import os
import cv2

def extract_detailed(video_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print("Could not open video.")
        return
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"FPS: {fps}, Total Frames: {total_frames}")
    
    frame_idx = 0
    extracted_count = 0
    
    # Extract frame every 30 frames (approx. 1 second interval)
    interval = 30
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        if frame_idx % interval == 0:
            timestamp_sec = frame_idx / fps
            frame_name = f"frame_{frame_idx:04d}_t{timestamp_sec:.2f}.jpg"
            cv2.imwrite(os.path.join(output_dir, frame_name), frame)
            extracted_count += 1
            
        frame_idx += 1
        
    cap.release()
    print(f"Extracted {extracted_count} frames to {output_dir}")

if __name__ == "__main__":
    video_path = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\VID_20260703_220247.mp4"
    output_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may\extracted_frames\VID_20260703_220247_detailed"
    extract_detailed(video_path, output_dir)
