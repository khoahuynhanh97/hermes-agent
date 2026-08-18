import os
import sys
import cv2
import numpy as np

def calculate_image_similarity(img_path_1, img_path_2):
    """
    Calculates visual similarity score (0.0 to 100.0%) between two images
    using OpenCV Color Histograms (HSV) and ORB Feature Matching.
    """
    try:
        img1 = cv2.imread(img_path_1)
        img2 = cv2.imread(img_path_2)

        if img1 is None or img2 is None:
            return 0.0

        # 1. Color Histogram Similarity (HSV)
        hsv1 = cv2.cvtColor(img1, cv2.COLOR_BGR2HSV)
        hsv2 = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)

        hist1 = cv2.calcHist([hsv1], [0, 1], None, [50, 60], [0, 180, 0, 256])
        hist2 = cv2.calcHist([hsv2], [0, 1], None, [50, 60], [0, 180, 0, 256])

        cv2.normalize(hist1, hist1, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
        cv2.normalize(hist2, hist2, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)

        color_similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        color_score = max(0.0, float(color_similarity) * 100.0)

        # 2. ORB Feature Matching
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        orb = cv2.ORB_create(nfeatures=500)
        kp1, des1 = orb.detectAndCompute(gray1, None)
        kp2, des2 = orb.detectAndCompute(gray2, None)

        feature_score = 50.0
        if des1 is not None and des2 is not None and len(des1) > 0 and len(des2) > 0:
            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = bf.match(des1, des2)
            matches = sorted(matches, key=lambda x: x.distance)
            good_matches = [m for m in matches if m.distance < 50]
            feature_score = min(100.0, (len(good_matches) / max(1, min(len(kp1), len(kp2)))) * 200.0)

        # Combined Weighted Score (60% Color + 40% Feature)
        overall_similarity = (color_score * 0.6) + (feature_score * 0.4)
        return round(overall_similarity, 2)

    except Exception as e:
        print(f"[!] Lỗi so sánh tương đồng hình ảnh: {e}")
        return 0.0

def extract_sample_frame_from_video(video_path):
    """Extracts a middle frame from a video file as a temporary image for similarity checking."""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return None
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, frame = cap.read()
        cap.release()
        if ret:
            temp_path = video_path + "_temp_frame.jpg"
            cv2.imwrite(temp_path, frame)
            return temp_path
    except Exception:
        pass
    return None

def filter_materials_by_reference(materials_dir, reference_image_path, threshold=30.0, log_callback=None):
    """
    Audits downloaded materials (images and videos) in materials_dir against project reference image.
    Deletes materials that score below threshold similarity.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    if not os.path.exists(materials_dir) or not os.path.exists(reference_image_path):
        log("[!] Bỏ qua kiểm tra độ tương đồng: Chưa có ảnh mẫu reference hoặc thư mục Phoi/.")
        return []

    log(f"[*] Đang chạy OpenCV Visual Matcher so sánh phôi cào được với Ảnh Mẫu ({os.path.basename(reference_image_path)})...")
    valid_video_exts = {'.mp4', '.mov', '.m4v', '.webm', '.avi', '.mkv'}
    valid_image_exts = {'.png', '.jpg', '.jpeg', '.webp'}

    kept_files = []
    removed_files = []

    for f in os.listdir(materials_dir):
        file_path = os.path.join(materials_dir, f)
        if not os.path.isfile(file_path):
            continue

        ext = os.path.splitext(f)[1].lower()
        test_img_path = None
        is_temp_frame = False

        if ext in valid_image_exts:
            test_img_path = file_path
        elif ext in valid_video_exts:
            test_img_path = extract_sample_frame_from_video(file_path)
            is_temp_frame = True

        if test_img_path and os.path.exists(test_img_path):
            score = calculate_image_similarity(test_img_path, reference_image_path)
            if is_temp_frame and os.path.exists(test_img_path):
                try: os.remove(test_img_path)
                except Exception: pass

            if score >= threshold:
                log(f"  [+] Giữ phôi '{f}': Độ khớp ảnh mẫu {score}% (Đạt chuẩn)")
                kept_files.append(file_path)
            else:
                log(f"  [-] Loại bỏ phôi '{f}': Độ khớp ảnh mẫu chỉ {score}% (< {threshold}%)")
                try:
                    os.remove(file_path)
                    removed_files.append(file_path)
                except Exception as ex:
                    log(f"    [!] Lỗi xóa file sai mẫu: {ex}")

    log(f"[+] Hoàn thành đối soát ảnh mẫu! Giữ lại {len(kept_files)} tài nguyên đúng mẫu sản phẩm.")
    return kept_files

if __name__ == "__main__":
    print("Testing visual matcher module...")
