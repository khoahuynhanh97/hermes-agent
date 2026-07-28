import shutil
import re
import json
from datetime import datetime
from pathlib import Path

from hermes.application.knowledge_lifecycle import KnowledgeLifecycle, LifecycleActor


class LearningReviewStore:
    """Local approval queue for Hermes learning proposals."""

    def __init__(self, root=None):
        import config
        repo_root = Path(__file__).resolve().parent.parent
        self.root = Path(root or getattr(config, "KNOWLEDGE_BASE_ROOT", repo_root / "knowledge_base")).resolve()
        self.queue_dir = self.root / "review_queue"
        self.approved_dir = self.root / "approved_lessons"
        self.rejected_dir = self.root / "rejected_lessons"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for folder in [self.queue_dir, self.approved_dir, self.rejected_dir]:
            folder.mkdir(parents=True, exist_ok=True)

    def list_pending(self):
        items = []
        for path in sorted(self.queue_dir.glob("*")):
            if path.is_file() and path.suffix.lower() in [".md", ".txt", ".json"]:
                items.append({
                    "name": path.name,
                    "path": str(path.resolve()),
                    "type": path.suffix.lower().lstrip("."),
                    "size": path.stat().st_size,
                })
        return items

    def read(self, name):
        path = self.queue_dir / name
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def create_proposal(self, title, body, prefix="learning"):
        """Write a learning/prompt proposal into the human review queue."""
        safe_prefix = self._slug(prefix or "learning")
        safe_title = self._slug(title or "proposal")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = self.queue_dir / f"{stamp}_{safe_prefix}_{safe_title}.md"
        path.write_text(body.strip() + "\n", encoding="utf-8")
        return str(path.resolve())

    def approve(self, name):
        # 1. Parse metadata from proposal before moving it
        from core.knowledge_store import get_store
        
        content = self.read(name)
        title = name.replace(".md", "").replace(".txt", "").replace(".json", "")
        # Remove stamp and prefix from slug/title if possible
        # e.g., 20260706_230000_knowledge_some-title -> some-title
        parts = title.split("_", 2)
        if len(parts) >= 3:
            title_slug = parts[2]
        else:
            title_slug = title
            
        source_url = ""
        output_dir_str = ""
        
        # Parse Source and Output folder from proposal content
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("Source:"):
                source_url = line.replace("Source:", "").strip()
            elif line.startswith("Output folder:"):
                output_dir_str = line.replace("Output folder:", "").strip()
                
        # Try loading metadata JSON from output directory if it exists
        meta_data = {}
        key_lessons = []
        hook_type = ""
        cta_style = ""
        voice_tone = ""
        category = "General"
        platform = "unknown"
        
        if output_dir_str:
            meta_json_path = Path(output_dir_str) / "proposal_meta.json"
            if not meta_json_path.exists():
                raise FileNotFoundError(f"Không tìm thấy file metadata bắt buộc: {meta_json_path}")
            try:
                meta_data = json.loads(meta_json_path.read_text(encoding="utf-8"))
                key_lessons = meta_data.get("key_lessons", [])
                hook_type = meta_data.get("hook_type", "")
                cta_style = meta_data.get("cta_style", "")
                voice_tone = meta_data.get("voice_tone", "")
                category = meta_data.get("category", "General")
                platform = meta_data.get("platform", "unknown")
            except Exception as e:
                raise ValueError(f"File proposal_meta.json bị lỗi định dạng JSON: {e}")
                    
        # Fallback: parse markdown content if JSON meta doesn't exist (e.g. legacy manual files)
        if not key_lessons:
            for line in content.split("\n"):
                line = line.strip()
                if (line.startswith("- ") or line.startswith("* ")) and len(line) > 5:
                    lesson_text = line[2:].strip()
                    if not lesson_text.startswith("Source:") and not lesson_text.startswith("Output folder:"):
                        key_lessons.append(lesson_text)
            key_lessons = key_lessons[:5]  # limit to top 5
            
        # Parse platform from URL
        if source_url and platform == "unknown":
            if "youtube.com" in source_url or "youtu.be" in source_url:
                platform = "youtube"
            elif "tiktok.com" in source_url:
                platform = "tiktok"
                
        # 2. Add to UnifiedKnowledgeStore
        store = get_store()
        lifecycle = KnowledgeLifecycle(store)
        # Check if entry already exists (by source_url)
        existing = None
        if source_url:
            existing = store.find_existing_entry(source_url)
                    
        clean_title = meta_data.get("title") if meta_data else None
        if not clean_title:
            # Extract first heading from markdown as title
            for line in content.split("\n"):
                if line.startswith("# ") or line.startswith("## "):
                    clean_title = line.replace("#", "").strip()
                    break
            if not clean_title:
                clean_title = title_slug.replace("-", " ").title()
                
        if existing:
            # Update existing status via ID
            result = lifecycle.approve(
                existing["id"], LifecycleActor.system("gui-review"), mode="manual"
            )
            logger_msg = f"[LearningReview] Updated existing entry status to approved: {existing['id']}"
        else:
            # Create new entry directly as approved
            new_entry = store.add_entry(
                title=clean_title,
                source_url=source_url,
                platform=platform,
                category=category,
                hook_type=hook_type,
                cta_style=cta_style,
                voice_tone=voice_tone,
                key_lessons=key_lessons,
                detail_data={"raw_markdown": content, **meta_data},
                job_output_dir=output_dir_str,
                source="telegram_job",
            )
            result = lifecycle.approve(
                new_entry["id"], LifecycleActor.system("gui-review"), mode="manual"
            )
            logger_msg = f"[LearningReview] Added new approved entry: {new_entry['id']}"

        if not result.ok:
            raise ValueError(f"Knowledge approval failed: {result.code}")
            
        print(logger_msg)
        
        # 3. Move the proposal file to approved folder
        return self._move(name, self.approved_dir)

    def reject(self, name):
        # Mark as rejected in UnifiedKnowledgeStore if we can find it
        from core.knowledge_store import get_store
        content = self.read(name)
        source_url = ""
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("Source:"):
                source_url = line.replace("Source:", "").strip()
                break
                
        if source_url:
            store = get_store()
            existing = store.find_existing_entry(source_url)
            if existing:
                lifecycle = KnowledgeLifecycle(store)
                result = lifecycle.reject(
                    existing["id"],
                    LifecycleActor.system("gui-review"),
                    reason="Rejected via review queue UI",
                )
                if not result.ok:
                    raise ValueError(f"Knowledge rejection failed: {result.code}")
                    
        return self._move(name, self.rejected_dir)

    def _move(self, name, target_dir):
        source = self.queue_dir / name
        if not source.exists():
            raise FileNotFoundError(name)
        target = target_dir / name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            index = 2
            while target.exists():
                target = target_dir / f"{stem}_{index}{suffix}"
                index += 1
        shutil.move(str(source), str(target))
        return str(target.resolve())


    def _slug(self, value):
        value = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value).strip())
        value = re.sub(r"-+", "-", value).strip("-").lower()
        return value[:80] or "proposal"
