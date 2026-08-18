import os
import sys
import cv2
import numpy as np
from pathlib import Path

# Add parent directory to path for imports if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from hermes.runtime import config

def analyze_clip(video_path):
    """
    Analyzes the video clip quality locally using OpenCV.
    Computes brightness, motion, sharpness, scene change, and vertical compatibility.
    
    Returns:
        dict: Scores, recommendation, reason, and aspect ratios.
    """
    path_str = str(video_path)
    
    # Initialize failure return dict
    fail_res = {
        "brightness_score": 0.0,
        "motion_score": 0.0,
        "sharpness_score": 0.0,
        "scene_change_score": 0.0,
        "vertical_score": 0.0,
        "overall_score": 0.0,
        "recommendation": "Reject",
        "reason": "Lỗi: Không thể mở video hoặc video bị lỗi.",
        "source_width": 0,
        "source_height": 0,
        "source_aspect_ratio": 0.0,
        "output_width": 0,
        "output_height": 0,
        "output_aspect_ratio": 0.0
    }
    
    if not os.path.exists(path_str):
        fail_res["reason"] = f"Lỗi: Không tìm thấy file tại {path_str}"
        return fail_res
        
    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        return fail_res
        
    try:
        # 1. Read video metadata
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if total_frames <= 0 or width <= 0 or height <= 0:
            cap.release()
            fail_res["reason"] = "Lỗi: Kích thước hoặc thời lượng video không hợp lệ."
            return fail_res
            
        source_aspect_ratio = width / height
        
        # 2. Frame Sampling (Sample 10 frames spaced evenly)
        num_samples = 10
        # Ensure we have at least some spacing, avoid step=0
        step = max(1, total_frames // num_samples)
        sample_frames = []
        
        for i in range(num_samples):
            frame_idx = min(i * step, total_frames - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if ret and frame is not None:
                sample_frames.append(frame)
                
        cap.release()
        
        if len(sample_frames) < 2:
            fail_res["reason"] = "Lỗi: Không thể trích xuất đủ số khung hình để phân tích."
            return fail_res
            
        # 3. Calculate Scores
        # 3a. Vertical Score (based on original source aspect ratio)
        if source_aspect_ratio <= 0.65:
            # Native vertical (9:16 is ~0.56)
            vertical_score = 100.0
        elif source_aspect_ratio <= 1.1:
            # Square (1:1 is 1.0)
            vertical_score = 60.0
        elif source_aspect_ratio <= 1.8:
            # Landscape (16:9 is 1.77)
            vertical_score = 40.0
        else:
            # Extra wide
            vertical_score = max(10.0, 40.0 - ((source_aspect_ratio - 1.8) / 1.0) * 30.0)
            
        # 3b. Brightness Score
        brightness_vals = []
        for frame in sample_frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_bright = float(cv2.mean(gray)[0])
            brightness_vals.append(mean_bright)
            
        avg_brightness = float(np.mean(brightness_vals))
        
        # Mapping: Optimal target is 130
        dist = abs(avg_brightness - 130)
        if dist < 50:
            brightness_score = 100.0 - (dist * 0.4) # [80, 100]
        elif dist < 100:
            brightness_score = 80.0 - ((dist - 50) * 1.0) # [30, 80]
        else:
            brightness_score = max(0.0, 30.0 - ((dist - 100) * 1.2)) # [0, 30]
            
        # 3c. Sharpness Score (using Laplacian variance on normalized size)
        sharpness_vals = []
        for frame in sample_frames:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Normalize frame size to 512x512 for consistent focus measurement
            gray_resized = cv2.resize(gray, (512, 512))
            laplacian_var = cv2.Laplacian(gray_resized, cv2.CV_64F).var()
            sharpness_vals.append(laplacian_var)
            
        avg_sharpness = float(np.mean(sharpness_vals))
        
        # Mapping focus variance to 0-100 score:
        # Blurry < 20, OK 20-100, Sharp > 100
        if avg_sharpness < 20.0:
            sharpness_score = (avg_sharpness / 20.0) * 50.0
        elif avg_sharpness < 100.0:
            sharpness_score = 50.0 + ((avg_sharpness - 20.0) / 80.0) * 40.0
        else:
            sharpness_score = min(100.0, 90.0 + ((avg_sharpness - 100.0) / 200.0) * 10.0)
            
        # 3d. Motion Score (comparing consecutive sampled frames)
        motion_ratios = []
        for idx in range(len(sample_frames) - 1):
            f1 = sample_frames[idx]
            f2 = sample_frames[idx+1]
            
            g1 = cv2.resize(cv2.cvtColor(f1, cv2.COLOR_BGR2GRAY), (256, 256))
            g2 = cv2.resize(cv2.cvtColor(f2, cv2.COLOR_BGR2GRAY), (256, 256))
            
            diff = cv2.absdiff(g1, g2)
            _, thresh = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
            motion_ratio = cv2.countNonZero(thresh) / float(thresh.size)
            motion_ratios.append(motion_ratio)
            
        avg_motion_ratio = float(np.mean(motion_ratios))
        motion_percent = avg_motion_ratio * 100.0
        
        # Mapping: Typical motion percent is 0.5% to 15%
        if motion_percent < 0.5:
            motion_score = motion_percent * 20.0 # 0 to 10
        elif motion_percent < 5.0:
            motion_score = 10.0 + (motion_percent - 0.5) * (70.0 - 10.0) / 4.5 # 10 to 70
        else:
            motion_score = min(100.0, 70.0 + (motion_percent - 5.0) * 3.0) # 70 to 100
            
        # 3e. Scene Change Score (color histogram correlation changes)
        similarities = []
        for idx in range(len(sample_frames) - 1):
            f1 = sample_frames[idx]
            f2 = sample_frames[idx+1]
            
            # Compute a fast 3D BGR histogram (8 bins per channel)
            h1 = cv2.calcHist([f1], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            h2 = cv2.calcHist([f2], [0, 1, 2], None, [8, 8, 8], [0, 256, 0, 256, 0, 256])
            
            cv2.normalize(h1, h1)
            cv2.normalize(h2, h2)
            
            sim = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
            similarities.append(max(0.0, min(1.0, sim)))
            
        min_sim = float(np.min(similarities)) if similarities else 1.0
        scene_change_score = (1.0 - min_sim) * 100.0
        
        # 4. Calculate Overall Score
        # Weights: brightness (25%), motion (30%), sharpness (25%), verticality (20%)
        overall_score = (brightness_score * 0.25 + 
                         motion_score * 0.30 + 
                         sharpness_score * 0.25 + 
                         vertical_score * 0.20)
        
        # 5. Recommendation
        if overall_score >= 70.0:
            recommendation = "Good"
        elif overall_score >= 45.0:
            recommendation = "Okay"
        else:
            recommendation = "Reject"
            
        # 6. Reason
        if recommendation == "Good":
            if motion_score > 60.0:
                reason = "Clip sáng, rõ và có chuyển động tốt."
            else:
                reason = "Clip sáng, nét, bối cảnh đẹp."
        elif recommendation == "Okay":
            if motion_score < 30.0:
                reason = "Clip hơi tĩnh nhưng vẫn dùng được."
            elif sharpness_score < 60.0:
                reason = "Độ nét trung bình, độ sáng ổn."
            else:
                reason = "Chất lượng ổn, có thể sử dụng."
        else:
            if brightness_score < 40.0:
                reason = "Clip quá tối hoặc quá chói, không đạt."
            elif sharpness_score < 45.0:
                reason = "Clip bị mờ hoặc mất nét."
            else:
                reason = "Chất lượng hình ảnh thấp, nên bỏ qua."
                
        # Since we crop clips to 9:16 vertical in simple mode, output size is standard:
        # Default 720x1280 (vertical aspect ratio ~0.5625)
        # We will write these values in output parameters
        
        return {
            "brightness_score": round(brightness_score, 1),
            "motion_score": round(motion_score, 1),
            "sharpness_score": round(sharpness_score, 1),
            "scene_change_score": round(scene_change_score, 1),
            "vertical_score": round(vertical_score, 1),
            "overall_score": round(overall_score, 1),
            "recommendation": recommendation,
            "reason": reason,
            "source_width": width,
            "source_height": height,
            "source_aspect_ratio": round(source_aspect_ratio, 4),
            "output_width": 720,
            "output_height": 1280,
            "output_aspect_ratio": 0.5625
        }
        
    except Exception as e:
        fail_res["reason"] = f"Lỗi xử lý khung hình: {e}"
        return fail_res

def verify_final_video(video_path, log_callback=None):
    """
    Quality Gate check for the exported final video.
    Checks:
    - Resolution & Aspect ratio (9:16 vertical)
    - Black Screen Detection (grayscale average < 5.0 for > 0.5s)
    - Audio Presence & Volume level (mute / low volume check via ffprobe & ffmpeg)
    """
    import subprocess
    import re
    
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)
            
    log("[*] Bắt đầu kiểm tra Quality Gate tự động cho video...")
    
    path_str = str(video_path)
    if not os.path.exists(path_str):
        log(f"[x] File video không tồn tại: {path_str}")
        return {"success": False, "reason": "File video không tồn tại."}
        
    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        log(f"[x] Không thể mở video: {path_str}")
        return {"success": False, "reason": "Không thể mở file video."}
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if fps <= 0 or total_frames <= 0 or width <= 0 or height <= 0:
        cap.release()
        log("[x] Thông số video không hợp lệ.")
        return {"success": False, "reason": "Thông số video không hợp lệ."}
        
    duration = total_frames / fps
    aspect_ratio = width / height
    log(f"[*] Thông tin video: {width}x{height} | Aspect ratio: {aspect_ratio:.4f} | FPS: {fps:.2f} | Thời lượng: {duration:.2f}s")
    
    warnings = []
    
    # 1. Aspect Ratio check
    # vertical 9:16 is 0.5625. Allow tolerance
    target_ratio = 9.0 / 16.0
    if abs(aspect_ratio - target_ratio) > 0.05:
        w_msg = f"[WARNING] Tỷ lệ khung hình ({aspect_ratio:.2f}) lệch nhiều so với chuẩn dọc 9:16 (0.56)."
        log(w_msg)
        warnings.append(w_msg)
        
    # 2. Black Screen Detection
    # Scan frame every 0.2 seconds (5 frames per second)
    sample_interval_s = 0.2
    frame_step = max(1, int(fps * sample_interval_s))
    
    black_frames_indices = []
    black_threshold = 5.0  # grayscale mean intensity
    
    log("[*] Đang quét phát hiện lỗi màn hình đen (Black Screen)...")
    for frame_idx in range(0, total_frames, frame_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_intensity = float(np.mean(gray))
        if mean_intensity < black_threshold:
            black_frames_indices.append(frame_idx)
            
    cap.release()
    
    # Analyze consecutive black frames to identify gaps >= 0.5s
    black_gaps = []
    if black_frames_indices:
        # Group contiguous samples
        consecutive_groups = []
        current_group = [black_frames_indices[0]]
        
        for idx in black_frames_indices[1:]:
            if idx - current_group[-1] <= frame_step:
                current_group.append(idx)
            else:
                consecutive_groups.append(current_group)
                current_group = [idx]
        consecutive_groups.append(current_group)
        
        for group in consecutive_groups:
            # duration of this group in seconds
            group_duration = len(group) * sample_interval_s
            if group_duration >= 0.5:
                start_s = group[0] / fps
                end_s = group[-1] / fps
                black_gaps.append((round(start_s, 2), round(end_s, 2)))
                
    black_ratio = (len(black_frames_indices) * frame_step / total_frames) * 100.0 if total_frames > 0 else 0.0
    if black_gaps:
        w_msg = f"[WARNING] Phát hiện lỗi màn hình đen kéo dài tại các khoảng: {', '.join([f'{s}-{e}s' for s, e in black_gaps])}."
        log(w_msg)
        warnings.append(w_msg)
    else:
        log(f"[+] Không phát hiện lỗi màn hình đen nghiêm trọng. (Tỷ lệ vùng đen: {black_ratio:.1f}%)")
        
    # 3. Audio & Silence check (using ffprobe / ffmpeg)
    log("[*] Đang phân tích luồng âm thanh thuyết minh (Audio & Volume)...")
    has_audio = False
    mean_volume = None
    max_volume = None
    
    # Locate ffmpeg & ffprobe
    ffmpeg_exe = getattr(config, "FFMPEG_PATH", "ffmpeg")
    ffprobe_exe = "ffprobe"
    if ffmpeg_exe and os.path.exists(ffmpeg_exe):
        # Infer ffprobe path from ffmpeg.exe path
        if ffmpeg_exe.endswith("ffmpeg.exe"):
            inferred = ffmpeg_exe.replace("ffmpeg.exe", "ffprobe.exe")
            if os.path.exists(inferred):
                ffprobe_exe = inferred
        elif ffmpeg_exe.endswith("ffmpeg"):
            inferred = ffmpeg_exe[:-6] + "ffprobe"
            if os.path.exists(inferred):
                ffprobe_exe = inferred
                
    # Check audio stream using ffprobe
    try:
        cmd_ffprobe = [
            ffprobe_exe, "-v", "error", 
            "-select_streams", "a", 
            "-show_entries", "stream=codec_type", 
            "-of", "csv=p=0", path_str
        ]
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
        res_ffprobe = subprocess.run(cmd_ffprobe, capture_output=True, text=True, check=True, startupinfo=startupinfo)
        if "audio" in res_ffprobe.stdout.lower():
            has_audio = True
    except Exception as e:
        log(f"[!] Lỗi gọi ffprobe kiểm tra luồng audio (Dự phòng: Vẫn tiếp tục chạy ffmpeg): {e}")
        # fallback: we will try to run volume detect anyway
        has_audio = True # Assume true to run ffmpeg
        
    if not has_audio:
        w_msg = "[WARNING] Video không chứa luồng âm thanh (Mute Video)."
        log(w_msg)
        warnings.append(w_msg)
    else:
        # Run volume detect filter with ffmpeg
        try:
            cmd_ffmpeg = [
                ffmpeg_exe, "-y", "-i", path_str, 
                "-af", "volumedetect", 
                "-f", "null", "-"
            ]
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                
            res_ffmpeg = subprocess.run(cmd_ffmpeg, capture_output=True, text=True, startupinfo=startupinfo)
            err_out = res_ffmpeg.stderr
            
            # Parse mean_volume and max_volume
            mean_match = re.search(r"mean_volume:\s*([\-\d\.]+)\s*dB", err_out)
            max_match = re.search(r"max_volume:\s*([\-\d\.]+)\s*dB", err_out)
            
            if mean_match:
                mean_volume = float(mean_match.group(1))
            if max_match:
                max_volume = float(max_match.group(1))
                
            if max_volume is not None:
                log(f"[+] Độ lớn âm thanh: Max volume = {max_volume:.1f} dB | Mean volume = {mean_volume:.1f} dB" if mean_volume is not None else f"[+] Độ lớn âm thanh: Max volume = {max_volume:.1f} dB")
                if max_volume < -60.0:
                    w_msg = f"[WARNING] Âm lượng video quá nhỏ hoặc bị tắt tiếng hoàn toàn (max_volume = {max_volume:.1f} dB)."
                    log(w_msg)
                    warnings.append(w_msg)
                elif max_volume < -30.0:
                    w_msg = f"[WARNING] Âm lượng video ở mức thấp (max_volume = {max_volume:.1f} dB). Có thể cần khuếch đại âm thanh thuyết minh."
                    log(w_msg)
                    warnings.append(w_msg)
            else:
                # If we couldn't parse volume detect logs
                if "no audio stream" in err_out.lower() or "no stream" in err_out.lower():
                    has_audio = False
                    w_msg = "[WARNING] Video thực tế không chứa dữ liệu âm thanh."
                    log(w_msg)
                    warnings.append(w_msg)
                else:
                    log("[!] Không thể phân tích thông số âm lượng bằng ffmpeg (có thể luồng audio trống).")
        except Exception as e:
            log(f"[!] Lỗi gọi ffmpeg kiểm tra âm lượng: {e}")
            
    passed_gates = len(warnings) == 0
    if passed_gates:
        log("[+] Quality Gate: ĐẠT! Video hoàn toàn đạt chất lượng kết xuất.")
    else:
        log(f"[WARNING] Quality Gate: Có {len(warnings)} cảnh báo cần lưu ý!")
        
    return {
        "success": True,
        "duration": round(duration, 2),
        "fps": round(fps, 2),
        "resolution": (width, height),
        "aspect_ratio": round(aspect_ratio, 4),
        "has_audio": has_audio,
        "mean_volume_db": mean_volume,
        "max_volume_db": max_volume,
        "black_screen_percentage": round(black_ratio, 1),
        "black_screen_gaps": black_gaps,
        "warnings": warnings,
        "passed_gates": passed_gates
    }

