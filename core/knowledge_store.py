"""
core/knowledge_store.py — Unified Knowledge Store (Single Source of Truth)

Thay thế và hợp nhất:
  - knowledge_base/index.json  (hệ thống cũ V1)
  - knowledge_base/approved_lessons/  (hệ thống mới từ job queue)

Mọi module đọc/ghi kiến thức đều phải thông qua UnifiedKnowledgeStore.

Trạng thái vòng đời (lifecycle status):
  pending   → vừa được phân tích, đang chờ người dùng duyệt
  approved  → đã được duyệt, sẽ được inject vào script generation
  rejected  → đã bị từ chối, không dùng
"""

import os
import sys
import json
import re
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

logger = logging.getLogger(__name__)

KB_DIR = Path(__file__).resolve().parent.parent / "knowledge_base"
UNIFIED_INDEX_FILE = KB_DIR / "unified_index.json"
ENTRIES_DIR = KB_DIR / "entries"

_CURRENT_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_dirs():
    KB_DIR.mkdir(parents=True, exist_ok=True)
    ENTRIES_DIR.mkdir(parents=True, exist_ok=True)


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def _unique_id() -> str:
    import uuid
    return f"kb_{uuid.uuid4().hex[:12]}"


def _slug(text: str) -> str:
    """Chuyển văn bản tiếng Việt thành slug an toàn cho tên file."""
    text = text.lower()
    replacements = {
        '[áàảãạăắằẳẵặâấầẩẫậ]': 'a',
        '[éèẻẽẹêếềểễệ]': 'e',
        '[íìỉĩị]': 'i',
        '[óòỏõọôốồổỗộơớờởỡợ]': 'o',
        '[úùủũụưứừửữự]': 'u',
        '[ýỳỷỹỵ]': 'y',
        'đ': 'd',
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'[\s-]+', '-', text).strip('-')
    return text[:80] or "lesson"


# ---------------------------------------------------------------------------
# UnifiedKnowledgeStore
# ---------------------------------------------------------------------------

class UnifiedKnowledgeStore:
    """
    SINGLE SOURCE OF TRUTH cho toàn bộ kiến thức học được của Hermes.

    Unified Index Schema (unified_index.json):
    {
        "version": 2,
        "entries": [
            {
                "id": "kb_20260706_001",
                "slug": "ten-bai-hoc",
                "source_url": "https://...",
                "platform": "tiktok|youtube|instagram|...",
                "category": "skincare|tech|food|...",
                "status": "pending|approved|rejected",
    """

    def __init__(self):
        _ensure_dirs()
        self._is_migrating = False
        self._index = self._load_index()

    # ------------------------------------------------------------------
    # Index I/O
    # ------------------------------------------------------------------

    def _load_index(self) -> dict:
        if UNIFIED_INDEX_FILE.exists():
            try:
                data = json.loads(UNIFIED_INDEX_FILE.read_text(encoding="utf-8-sig"))
                # Migrate từ format cũ (list) nếu cần
                if isinstance(data, list):
                    return {"version": _CURRENT_SCHEMA_VERSION, "entries": data}
                return data
            except json.JSONDecodeError as e:
                logger.warning(f"[KnowledgeStore] Lỗi đọc unified_index.json (JSON lỗi): {e}. Thử khôi phục từ backup...")
                backup_file = KB_DIR / "unified_index.backup.json"
                if backup_file.exists():
                    try:
                        data = json.loads(backup_file.read_text(encoding="utf-8-sig"))
                        if isinstance(data, list):
                            return {"version": _CURRENT_SCHEMA_VERSION, "entries": data}
                        return data
                    except Exception as e2:
                        logger.error(f"[KnowledgeStore] Không thể load backup file: {e2}")
            except Exception as e:
                logger.warning(f"[KnowledgeStore] Lỗi đọc unified_index.json: {e}")
        return {"version": _CURRENT_SCHEMA_VERSION, "entries": []}

    def _save_index(self):
        self._save_index_atomic()

    def _save_index_atomic(self):
        import shutil
        # 1. Tạo backup nếu file cũ tồn tại và đọc hợp lệ
        if UNIFIED_INDEX_FILE.exists():
            try:
                backup_file = KB_DIR / "unified_index.backup.json"
                shutil.copy2(str(UNIFIED_INDEX_FILE), str(backup_file))
            except Exception as e:
                logger.warning(f"[KnowledgeStore] Không thể tạo backup file: {e}")

        # 2. Ghi ra file tạm
        tmp_file = KB_DIR / "unified_index.tmp"
        try:
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self._index, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())  # Đảm bảo ghi đĩa hoàn toàn
            
            # 3. Rename atomic
            os.replace(str(tmp_file), str(UNIFIED_INDEX_FILE))
        except Exception as e:
            logger.error(f"[KnowledgeStore] Lỗi khi ghi index atomic: {e}")
            if tmp_file.exists():
                try: tmp_file.unlink()
                except Exception: pass
            raise e

    def _reload(self):
        """Reload từ disk (dùng khi nhiều process cùng chạy)."""
        self._index = self._load_index()

    # ------------------------------------------------------------------
    # URL Normalization & Duplication Check Helpers
    # ------------------------------------------------------------------

    def normalize_source_url(self, url: str) -> str:
        if not url:
            return ""
        url = url.strip()
        import urllib.parse as urlparse
        try:
            parsed = urlparse.urlparse(url)
            query_params = urlparse.parse_qs(parsed.query)
            clean_query_params = {}
            # Giữ các tham số quan trọng cho YouTube
            for k in ["v", "t"]:
                if k in query_params:
                    clean_query_params[k] = query_params[k]
            new_query = urlparse.urlencode(clean_query_params, doseq=True)
            path = parsed.path.rstrip('/')
            url = urlparse.urlunparse((
                parsed.scheme,
                parsed.netloc.lower(),
                path,
                parsed.params,
                new_query,
                parsed.fragment
            ))
        except Exception:
            pass
        return url

    def make_source_hash(self, url: str) -> str:
        normalized = self.normalize_source_url(url)
        if not normalized:
            return ""
        import hashlib
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def find_existing_entry(self, source_url: str) -> Optional[dict]:
        if not source_url:
            return None
        norm_url = self.normalize_source_url(source_url)
        for e in self._index["entries"]:
            if e.get("source_url") and self.normalize_source_url(e["source_url"]) == norm_url:
                return e
        return None

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def add_entry(
        self,
        title: str,
        source_url: str = "",
        platform: str = "unknown",
        category: str = "General",
        hook_type: str = "",
        cta_style: str = "",
        voice_tone: str = "",
        key_lessons: list = None,
        detail_data: dict = None,
        job_output_dir: str = "",
        source: str = "telegram_job",
    ) -> dict:
        """
        Thêm entry mới vào unified index với status='pending'.
        Nếu trùng URL và status=approved, trả về entry cũ.
        Nếu trùng URL và status=pending, cập nhật metadata và trả về.
        """
        self._reload()

        # Duplicate check
        if source_url:
            existing = self.find_existing_entry(source_url)
            if existing:
                if existing.get("status") == "approved":
                    logger.info(f"[KnowledgeStore] Entry trùng lặp đã approved tồn tại: {existing['id']}")
                    return existing
                elif existing.get("status") == "pending":
                    logger.info(f"[KnowledgeStore] Cập nhật pending entry trùng lặp: {existing['id']}")
                    existing["learned_at"] = _now_iso()
                    existing["key_lessons"] = key_lessons or []
                    existing["title"] = title
                    existing["category"] = category
                    existing["hook_type"] = hook_type
                    existing["cta_style"] = cta_style
                    existing["voice_tone"] = voice_tone
                    existing["job_output_dir"] = job_output_dir
                    existing["source"] = source
                    
                    if detail_data:
                        detail_path = ENTRIES_DIR / f"{existing['id']}.json"
                        detail_path.write_text(
                            json.dumps({**existing, "detail": detail_data}, ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                    self._save_index_atomic()
                    return existing

        entry_id = _unique_id()
        entry_slug = _slug(title) or entry_id

        # Đảm bảo slug không trùng
        existing_slugs = {e.get("slug") for e in self._index["entries"]}
        base_slug = entry_slug
        counter = 2
        while entry_slug in existing_slugs:
            entry_slug = f"{base_slug}-{counter}"
            counter += 1

        entry = {
            "id": entry_id,
            "slug": entry_slug,
            "source_url": source_url,
            "platform": platform,
            "category": category,
            "status": "pending",
            "learned_at": _now_iso(),
            "approved_at": None,
            "approved_by": None,
            "approval_mode": None,
            "title": title,
            "hook_type": hook_type,
            "cta_style": cta_style,
            "voice_tone": voice_tone,
            "key_lessons": key_lessons or [],
            "detail_file": f"entries/{entry_id}.json",
            "job_output_dir": job_output_dir,
            "source": source,
        }

        # Lưu detail file riêng nếu có data chi tiết
        if detail_data:
            detail_path = ENTRIES_DIR / f"{entry_id}.json"
            detail_path.write_text(
                json.dumps({**entry, "detail": detail_data}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        self._index["entries"].append(entry)
        self._save_index_atomic()
        logger.info(f"[KnowledgeStore] ✅ Đã thêm entry mới: [{entry_id}] {title} (status=pending)")
        return entry

    def get_entry(self, slug_or_id: str) -> Optional[dict]:
        """Tìm entry theo slug hoặc id."""
        self._reload()
        for e in self._index["entries"]:
            if e.get("id") == slug_or_id:
                return e
        for e in self._index["entries"]:
            if e.get("slug") == slug_or_id:
                return e
        return None

    def list_entries(self, status: str = None, category: str = None) -> list:
        """Lấy danh sách entries, có thể filter theo status và/hoặc category."""
        self._reload()
        entries = self._index["entries"]
        if status:
            entries = [e for e in entries if e.get("status") == status]
        if category:
            cat_lower = category.lower()
            entries = [e for e in entries if cat_lower in (e.get("category") or "").lower()]
        return entries

    def get_approved_entries(self, category: str = None) -> list:
        """Trả về các entries đã được approve (đủ điều kiện inject vào script generation)."""
        return self.list_entries(status="approved", category=category)

    def get_pending_entries(self) -> list:
        """Trả về các entries đang chờ duyệt."""
        return self.list_entries(status="pending")

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def mark_approved(self, identifier: str, approved_by: str = None, approval_mode: str = None) -> Optional[dict]:
        """
        Duyệt một entry: status → approved.
        Tự động trigger rebuild style profile.
        """
        self._reload()
        # Ưu tiên ID trước, sau đó slug
        matched_entry = None
        for entry in self._index["entries"]:
            if entry.get("id") == identifier:
                matched_entry = entry
                break
        if not matched_entry:
            for entry in self._index["entries"]:
                if entry.get("slug") == identifier:
                    matched_entry = entry
                    break

        if matched_entry:
            matched_entry["status"] = "approved"
            matched_entry["approved_at"] = _now_iso()
            matched_entry["approved_by"] = approved_by
            matched_entry["approval_mode"] = approval_mode
            matched_entry["updated_at"] = _now_iso()
            self._save_index_atomic()
            logger.info(f"[KnowledgeStore] ✅ Approved: {matched_entry['title']} (by={approved_by}, mode={approval_mode})")
            try:
                self._rebuild_style_profile()
            except Exception as e:
                logger.warning(f"[KnowledgeStore] Không thể rebuild style profile: {e}")
            return matched_entry

        logger.warning(f"[KnowledgeStore] Không tìm thấy entry để duyệt: {identifier}")
        return None

    def mark_rejected(self, identifier: str, rejected_by: str = None, rejection_reason: str = None) -> Optional[dict]:
        """Từ chối một entry: status → rejected."""
        self._reload()
        matched_entry = None
        for entry in self._index["entries"]:
            if entry.get("id") == identifier:
                matched_entry = entry
                break
        if not matched_entry:
            for entry in self._index["entries"]:
                if entry.get("slug") == identifier:
                    matched_entry = entry
                    break

        if matched_entry:
            matched_entry["status"] = "rejected"
            matched_entry["rejected_at"] = _now_iso()
            matched_entry["rejected_by"] = rejected_by
            if rejection_reason:
                matched_entry["rejection_reason"] = rejection_reason
            matched_entry["updated_at"] = _now_iso()
            self._save_index_atomic()
            logger.info(f"[KnowledgeStore] ❌ Rejected: {matched_entry['title']} (reason={rejection_reason})")
            return matched_entry
        return None

    def delete_entry(self, slug_or_id: str) -> bool:
        """Xóa hoàn toàn một entry."""
        self._reload()
        before = len(self._index["entries"])
        self._index["entries"] = [
            e for e in self._index["entries"]
            if e.get("id") != slug_or_id and e.get("slug") != slug_or_id
        ]
        if len(self._index["entries"]) < before:
            self._save_index_atomic()
            return True
        return False

    # ------------------------------------------------------------------
    # Knowledge injection for script generation
    # ------------------------------------------------------------------

    def get_style_context_for_script(
        self,
        category: str = None,
        max_lessons: int = 3,
    ) -> str:
        """
        Trả về context string để inject vào AI prompt khi generate script.
        Chỉ dùng approved entries.

        Returns:
            Chuỗi context hoặc "" nếu chưa có knowledge nào được approve.
        """
        approved = self.get_approved_entries(category=category)
        if not approved:
            return ""

        # Ưu tiên entries mới nhất
        approved_sorted = sorted(
            approved,
            key=lambda e: e.get("approved_at") or e.get("learned_at") or "",
            reverse=True,
        )
        top_entries = approved_sorted[:max_lessons]

        lines = [
            f"[KIẾN THỨC ĐÃ HỌC TỪ {len(approved)} VIDEO MẪU ĐÃ DUYỆT]",
            "Áp dụng những bài học thực tế sau đây vào nội dung bạn tạo ra:\n",
        ]
        for i, entry in enumerate(top_entries, 1):
            lines.append(f"--- Bài học #{i}: {entry.get('title', 'N/A')} ---")
            if entry.get("hook_type"):
                lines.append(f"  • Loại Hook: {entry['hook_type']}")
            if entry.get("voice_tone"):
                lines.append(f"  • Giọng điệu: {entry['voice_tone']}")
            if entry.get("cta_style"):
                lines.append(f"  • Kiểu CTA: {entry['cta_style']}")
            if entry.get("key_lessons"):
                lines.append("  • Bài học cốt lõi:")
                for lesson in entry["key_lessons"][:3]:
                    lines.append(f"    - {lesson}")
            lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Migration: Import từ hệ thống cũ (V1)
    # ------------------------------------------------------------------

    def migrate_from_v1_index(self) -> int:
        """
        Import tất cả entries từ knowledge_base/index.json (hệ thống cũ)
        vào unified_index.json nếu chưa có.
        Trả về số entry đã import.
        """
        if getattr(self, "_is_migrating", False):
            return 0
            
        self._is_migrating = True
        try:
            return self._execute_migration()
        finally:
            self._is_migrating = False

    def _execute_migration(self) -> int:
        old_index_file = KB_DIR / "index.json"
        if not old_index_file.exists():
            return 0

        try:
            old_data = json.loads(old_index_file.read_text(encoding="utf-8"))
        except Exception:
            return 0

        if not isinstance(old_data, list):
            return 0

        self._reload()
        existing_urls = {e.get("source_url") for e in self._index["entries"]}
        count = 0

        for old_entry in old_data:
            url = old_entry.get("url", "")
            if url in existing_urls:
                continue  # Đã có rồi

            # Load detail file nếu có
            slug = old_entry.get("slug", "")
            detail = None
            detail_file = KB_DIR / f"{slug}.json"
            if detail_file.exists():
                try:
                    detail = json.loads(detail_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            # Extract key_lessons từ detail
            key_lessons = []
            if detail:
                raw_lessons = detail.get("key_lessons", "")
                if isinstance(raw_lessons, list):
                    key_lessons = raw_lessons
                elif isinstance(raw_lessons, str):
                    key_lessons = [l.strip() for l in raw_lessons.split('\n') if l.strip()][:5]

            new_entry = self.add_entry(
                title=old_entry.get("title", slug),
                source_url=url,
                platform=old_entry.get("platform", "youtube").lower(),
                category=old_entry.get("category", "General"),
                key_lessons=key_lessons,
                detail_data=detail,
                source="gui_learn_v1",
            )
            self.mark_approved(new_entry["id"])
            existing_urls.add(url)
            count += 1

        if count > 0:
            logger.info(f"[KnowledgeStore] 📦 Đã migrate {count} entries từ V1 index.json")
        return count

    # ------------------------------------------------------------------
    # Private: rebuild style profile
    # ------------------------------------------------------------------

    def _rebuild_style_profile(self):
        """Rebuild style_profiles.json từ toàn bộ approved entries."""
        from core.style_profiler import build_profile
        logger.info("[KnowledgeStore] 🔄 Đang rebuild Style Profile từ approved entries...")
        build_profile(force_rebuild=True)
        logger.info("[KnowledgeStore] ✅ Style Profile đã được cập nhật.")


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def get_store() -> UnifiedKnowledgeStore:
    """Factory function — trả về một instance mới của store."""
    return UnifiedKnowledgeStore()


def get_style_context(category: str = None) -> str:
    """
    Convenience: lấy context string để inject vào script generation.
    Trả về "" nếu chưa có approved knowledge.
    """
    return UnifiedKnowledgeStore().get_style_context_for_script(category=category)


def approve_entry(slug_or_id: str, approved_by: str = None, approval_mode: str = None) -> Optional[dict]:
    """Convenience: approve một entry và rebuild style profile."""
    return UnifiedKnowledgeStore().mark_approved(slug_or_id, approved_by=approved_by, approval_mode=approval_mode)


def reject_entry(slug_or_id: str, rejected_by: str = None, rejection_reason: str = None) -> Optional[dict]:
    """Convenience: reject một entry."""
    return UnifiedKnowledgeStore().mark_rejected(slug_or_id, rejected_by=rejected_by, rejection_reason=rejection_reason)
