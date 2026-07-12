import os
import cv2
import json

def analyze_and_extract_frames(video_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    video_files = [f for f in os.listdir(video_dir) if f.endswith('.mp4')]
    video_files.sort()
    
    metadata = {}
    
    print(f"Found {len(video_files)} video files in {video_dir}")
    
    for video_file in video_files:
        video_path = os.path.join(video_dir, video_file)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Could not open video: {video_file}")
            continue
            
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        duration = total_frames / fps if fps > 0 else 0
        
        print(f"\nProcessing {video_file}:")
        print(f"  - Duration: {duration:.2f}s, FPS: {fps:.2f}, Frames: {total_frames}")
        print(f"  - Resolution: {width}x{height}")
        
        # Decide how many frames to extract based on duration
        if duration < 10:
            num_frames = 3
        elif duration < 30:
            num_frames = 6
        elif duration < 60:
            num_frames = 10
        else:
            num_frames = 15
            
        metadata[video_file] = {
            "duration_seconds": round(duration, 2),
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "width": width,
            "height": height,
            "extracted_frames": []
        }
        
        # Extract frames at equal intervals
        intervals = [int(i * (total_frames - 1) / (num_frames - 1)) for i in range(num_frames)] if num_frames > 1 else [0]
        
        video_base_name = os.path.splitext(video_file)[0]
        video_output_dir = os.path.join(output_dir, video_base_name)
        os.makedirs(video_output_dir, exist_ok=True)
        
        for idx, frame_idx in enumerate(intervals):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                print(f"  - Failed to read frame {frame_idx}")
                continue
                
            timestamp_sec = frame_idx / fps if fps > 0 else 0
            frame_name = f"{video_base_name}_f{frame_idx:06d}_t{timestamp_sec:.2f}.jpg"
            frame_path = os.path.join(video_output_dir, frame_name)
            
            # Save frame
            cv2.imwrite(frame_path, frame)
            
            metadata[video_file]["extracted_frames"].append({
                "frame_index": frame_idx,
                "timestamp_sec": round(timestamp_sec, 2),
                "local_path": frame_path,
                "relative_path": os.path.relpath(frame_path, video_dir)
            })
            
        cap.release()
        print(f"  - Extracted {len(metadata[video_file]['extracted_frames'])} frames to {video_output_dir}")
        
    # Write metadata to a JSON file
    with open(os.path.join(output_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)
        
    print(f"\nDone! Metadata saved to {os.path.join(output_dir, 'metadata.json')}")

if __name__ == "__main__":
    video_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may"
    output_dir = os.path.join(video_dir, "extracted_frames")
    analyze_and_extract_frames(video_dir, output_dir)
