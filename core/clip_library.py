import os
import sys
import json
import uuid
from datetime import datetime

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


CLIP_STATUSES = ["pending", "approved", "okay", "rejected", "needs_cut"]
ASSET_TYPES = ["universal", "category", "product_specific", "cta_beauty"]
SCENE_TYPES = ["hook", "pain_point", "product_intro", "demo", "lifestyle", "result", "cta", "broll"]


class ClipLibrary:
    """
    Quản lý kho phôi (Clip Library) của từng project.
    Library file: <project_dir>/clip_library/library.json
    """

    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.library_dir = os.path.join(project_dir, "clip_library")
        self.library_file = os.path.join(self.library_dir, "library.json")
        os.makedirs(self.library_dir, exist_ok=True)
        self._ensure_subdirs()
        self._data = self._load()

    def _ensure_subdirs(self):
        for sub in ["universal", "categories", "products"]:
            os.makedirs(os.path.join(self.library_dir, sub), exist_ok=True)

    def _load(self):
        if os.path.exists(self.library_file):
            try:
                with open(self.library_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"clips": [], "version": 1}

    def _save(self):
        with open(self.library_file, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=4)

    def get_all_clips(self):
        """Trả về toàn bộ danh sách clips."""
        return self._data.get("clips", [])

    def get_clips_by_status(self, status):
        """Lọc clips theo status."""
        return [c for c in self.get_all_clips() if c.get("status") == status]

    def get_clips_by_tag(self, tag):
        """Lọc clips có chứa tag."""
        return [c for c in self.get_all_clips() if tag in c.get("tags", [])]

    def get_usable_clips(self):
        """Clips có thể dùng để ghép video (approved hoặc okay)."""
        return [c for c in self.get_all_clips() if c.get("status") in ("approved", "okay")]

    def add_clip(
        self,
        file_path,
        scene_type="broll",
        asset_type="product_specific",
        tags=None,
        quality_score=0,
        reuse_score=0,
        status="pending",
        notes="",
        angle_id="",
        product_id="",
    ):
        """Thêm một clip mới vào library. Trả về clip dict."""
        import cv2
        duration = 0.0
        width = 0
        height = 0
        thumbnail_path = ""

        # Lấy metadata từ file video nếu có
        if os.path.exists(file_path):
            try:
                cap = cv2.VideoCapture(file_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                duration = frames / fps if fps > 0 else 0.0

                # Tạo thumbnail từ frame giữa
                mid_frame = int(frames / 2)
                cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame)
                ret, frame = cap.read()
                if ret:
                    thumb_dir = os.path.join(self.library_dir, ".thumbnails")
                    os.makedirs(thumb_dir, exist_ok=True)
                    thumb_name = os.path.splitext(os.path.basename(file_path))[0] + "_thumb.jpg"
                    thumb_path = os.path.join(thumb_dir, thumb_name)
                    # Resize to small thumbnail
                    import cv2 as _cv2
                    small = _cv2.resize(frame, (120, 213))  # 9:16 ratio thumbnail
                    _cv2.imwrite(thumb_path, small)
                    thumbnail_path = thumb_path
                cap.release()
            except Exception:
                pass

        clip_id = f"CLK-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now().isoformat()

        clip = {
            "clip_id": clip_id,
            "product_id": product_id,
            "angle_id": angle_id,
            "file_path": os.path.abspath(file_path),
            "file_name": os.path.basename(file_path),
            "thumbnail_path": thumbnail_path,
            "scene_type": scene_type,
            "asset_type": asset_type,
            "tags": tags or [],
            "duration": round(duration, 2),
            "width": width,
            "height": height,
            "quality_score": quality_score,
            "reuse_score": reuse_score,
            "status": status,
            "notes": notes,
            "added_at": now,
            "updated_at": now,
        }

        self._data["clips"].append(clip)
        self._save()
        return clip

    def update_clip(self, clip_id, **kwargs):
        """Cập nhật metadata của clip theo clip_id."""
        for clip in self._data["clips"]:
            if clip["clip_id"] == clip_id:
                kwargs["updated_at"] = datetime.now().isoformat()
                clip.update(kwargs)
                self._save()
                return clip
        return None

    def remove_clip(self, clip_id):
        """Xóa clip khỏi library (không xóa file thực)."""
        before = len(self._data["clips"])
        self._data["clips"] = [c for c in self._data["clips"] if c["clip_id"] != clip_id]
        if len(self._data["clips"]) < before:
            self._save()
            return True
        return False

    def search_clips(self, query="", status_filter=None, tag_filter=None, asset_type_filter=None):
        """Tìm kiếm clips theo nhiều tiêu chí."""
        results = self.get_all_clips()

        if status_filter:
            results = [c for c in results if c.get("status") == status_filter]

        if tag_filter:
            results = [c for c in results if tag_filter in c.get("tags", [])]

        if asset_type_filter:
            results = [c for c in results if c.get("asset_type") == asset_type_filter]

        if query:
            q = query.lower()
            results = [
                c for c in results
                if q in c.get("file_name", "").lower()
                or q in c.get("notes", "").lower()
                or any(q in t.lower() for t in c.get("tags", []))
                or q in c.get("scene_type", "").lower()
            ]

        return results

    def get_stats(self):
        """Thống kê nhanh về library."""
        clips = self.get_all_clips()
        stats = {
            "total": len(clips),
            "approved": sum(1 for c in clips if c.get("status") == "approved"),
            "okay": sum(1 for c in clips if c.get("status") == "okay"),
            "pending": sum(1 for c in clips if c.get("status") == "pending"),
            "rejected": sum(1 for c in clips if c.get("status") == "rejected"),
            "needs_cut": sum(1 for c in clips if c.get("status") == "needs_cut"),
            "total_duration": round(sum(c.get("duration", 0) for c in clips), 1),
        }
        return stats
