"""
core/style_profiler.py — Smart Learning Loop / Style Profiler

Analyzes the Knowledge Base to extract reusable Style Profiles,
then injects them into script generation and idea engine prompts.
"""
import os
import sys
import json
import logging
from typing import Optional

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import config

logger = logging.getLogger(__name__)

KB_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'knowledge_base'))
PROFILES_FILE = os.path.join(KB_DIR, 'style_profiles.json')


def load_knowledge_base() -> list[dict]:
    """Load all approved learned video entries from UnifiedKnowledgeStore."""
    from core.knowledge_store import get_store
    store = get_store()
    # Tự động migrate index V1 cũ nếu có sang hệ thống mới
    try:
        store.migrate_from_v1_index()
    except Exception:
        pass

    approved = store.get_approved_entries()
    entries = []
    for entry in approved:
        detail = {}
        detail_file_rel = entry.get("detail_file", "")
        if detail_file_rel:
            detail_file = os.path.join(KB_DIR, detail_file_rel)
            if os.path.exists(detail_file):
                try:
                    with open(detail_file, 'r', encoding='utf-8') as f:
                        detail_data = json.load(f)
                        # Hỗ trợ cả cấu trúc bọc trong "detail" hoặc phẳng
                        detail = detail_data.get("detail", detail_data)
                except Exception:
                    pass

        if not detail:
            detail = {
                "title": entry.get("title"),
                "platform": entry.get("platform"),
                "key_lessons": "\n".join(entry.get("key_lessons", [])),
                "structure": f"Hook Type: {entry.get('hook_type')}\nCTA Style: {entry.get('cta_style')}",
                "copywriting_style": f"Voice Tone: {entry.get('voice_tone')}"
            }

        # Tạo trường "analysis" thống nhất từ các trường JSON cấu trúc mới để style_profiler đọc được
        analysis_parts = []
        if "summary" in detail:
            analysis_parts.append(detail["summary"])
        if "tools_and_concepts" in detail:
            analysis_parts.append(detail["tools_and_concepts"])
        if "workflow_steps" in detail:
            analysis_parts.append(detail["workflow_steps"])
        if "hermes_applications" in detail:
            analysis_parts.append(detail["hermes_applications"])
        if "hook_body_cta" in detail:
            analysis_parts.append(detail["hook_body_cta"])
        if "ideas_setup" in detail:
            analysis_parts.append(detail["ideas_setup"])
        if "prompt_router_mapping" in detail:
            analysis_parts.append(detail["prompt_router_mapping"])
        if "structure" in detail:
            analysis_parts.append(detail["structure"])
        if "copywriting_style" in detail:
            analysis_parts.append(detail["copywriting_style"])
        if "key_lessons" in detail:
            if isinstance(detail["key_lessons"], list):
                analysis_parts.append("\n".join(detail["key_lessons"]))
            else:
                analysis_parts.append(str(detail["key_lessons"]))
        if "raw_markdown" in detail:
            analysis_parts.append(detail["raw_markdown"])

        analysis_text = "\n\n".join(analysis_parts)
        detail["analysis"] = analysis_text

        entries.append({
            **entry,
            "detail": detail
        })

    return entries


def extract_style_profile(entries: list[dict]) -> dict:
    """
    Analyze knowledge base entries and extract a Style Profile.

    Returns a dict with:
        - hook_patterns: list of common hook opening styles
        - avg_scene_count: average number of scenes
        - voice_tone_keywords: common tone descriptors
        - pacing: fast/medium/slow
        - cta_styles: common call-to-action patterns
        - top_keywords: most frequent product keywords
        - video_structure: typical video flow
    """
    if not entries:
        return {}

    hook_patterns = []
    scene_counts = []
    keywords = []
    cta_styles = []
    tone_words = []
    structures = []

    for entry in entries:
        detail = entry.get("detail", {})
        analysis = detail.get("analysis", "") or detail.get("raw_analysis", "")

        if not analysis:
            continue

        analysis_lower = analysis.lower()

        # Extract hook patterns
        if "câu hỏi" in analysis_lower or "question" in analysis_lower:
            hook_patterns.append("question_hook")
        if "nỗi đau" in analysis_lower or "pain" in analysis_lower:
            hook_patterns.append("pain_hook")
        if "kết quả" in analysis_lower or "result" in analysis_lower:
            hook_patterns.append("result_hook")
        if "shock" in analysis_lower or "bất ngờ" in analysis_lower:
            hook_patterns.append("shock_hook")

        # Count scenes
        scene_markers = ["cảnh", "scene", "phân cảnh", "shot"]
        for marker in scene_markers:
            import re
            found = re.findall(rf'{marker}\s*\d+', analysis_lower)
            if found:
                scene_counts.append(len(found))
                break

        # Extract tone
        tone_markers = {
            "energetic": ["năng động", "nhanh", "sôi động", "energetic"],
            "warm": ["ấm áp", "gần gũi", "warm", "friendly"],
            "professional": ["chuyên nghiệp", "uy tín", "professional"],
            "fun": ["vui", "hài hước", "cute", "fun", "dễ thương"],
        }
        for tone, markers in tone_markers.items():
            if any(m in analysis_lower for m in markers):
                tone_words.append(tone)

        # CTA styles
        cta_markers = {
            "urgency": ["ngay hôm nay", "đặt ngay", "limited", "hết hàng"],
            "soft": ["tìm hiểu thêm", "để biết thêm", "xem ngay"],
            "social_proof": ["hàng nghìn", "khách hàng", "đánh giá 5 sao"],
        }
        for cta, markers in cta_markers.items():
            if any(m in analysis_lower for m in markers):
                cta_styles.append(cta)

    # Aggregate
    from collections import Counter

    def most_common(lst, n=3):
        if not lst:
            return []
        c = Counter(lst)
        return [item for item, _ in c.most_common(n)]

    avg_scenes = int(sum(scene_counts) / len(scene_counts)) if scene_counts else 4
    dominant_tone = most_common(tone_words, 1)
    dominant_hooks = most_common(hook_patterns, 3)
    dominant_ctas = most_common(cta_styles, 2)

    pacing = "fast" if avg_scenes >= 6 else ("slow" if avg_scenes <= 3 else "medium")

    profile = {
        "total_videos_analyzed": len(entries),
        "hook_patterns": dominant_hooks,
        "avg_scene_count": avg_scenes,
        "pacing": pacing,
        "voice_tone": dominant_tone[0] if dominant_tone else "warm",
        "cta_styles": dominant_ctas,
        "video_structure": {
            "intro": "Hook trong 3 giây đầu",
            "body": f"Demo sản phẩm {avg_scenes} phân cảnh",
            "outro": "CTA + hiện giá + link",
        },
    }
    return profile


def save_profile(profile: dict) -> None:
    os.makedirs(KB_DIR, exist_ok=True)
    with open(PROFILES_FILE, 'w', encoding='utf-8') as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)
    logger.info(f"[StyleProfiler] Profile saved → {PROFILES_FILE}")


def load_profile() -> Optional[dict]:
    if not os.path.exists(PROFILES_FILE):
        return None
    try:
        with open(PROFILES_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def build_profile(force_rebuild: bool = False) -> dict:
    """
    Build (or load cached) style profile from the knowledge base.

    Args:
        force_rebuild: If True, re-analyze even if cached profile exists

    Returns:
        Style profile dict
    """
    if not force_rebuild:
        cached = load_profile()
        if cached:
            logger.info(f"[StyleProfiler] Using cached profile ({cached.get('total_videos_analyzed',0)} videos)")
            return cached

    entries = load_knowledge_base()
    if not entries:
        logger.info("[StyleProfiler] Knowledge base is empty. Learn some videos first.")
        return {}

    logger.info(f"[StyleProfiler] Analyzing {len(entries)} learned videos...")
    profile = extract_style_profile(entries)
    save_profile(profile)
    return profile


def inject_style_into_prompt(base_prompt: str, profile: Optional[dict] = None) -> str:
    """
    Inject style profile context into an AI prompt.

    Args:
        base_prompt: Original prompt text
        profile: Style profile dict (auto-loaded if None)

    Returns:
        Enhanced prompt with style context prepended
    """
    if profile is None:
        profile = load_profile()

    if not profile:
        return base_prompt

    style_context = f"""
[PHONG CÁCH VIDEO HỌC ĐƯỢC TỪ {profile.get('total_videos_analyzed', 0)} VIDEO MẪU]:
- Hook ưa dùng: {', '.join(profile.get('hook_patterns', ['question_hook']))}
- Số phân cảnh trung bình: {profile.get('avg_scene_count', 4)} cảnh
- Nhịp độ: {profile.get('pacing', 'medium')} (tương đối nhanh/chậm)
- Giọng điệu: {profile.get('voice_tone', 'warm')} (ấm áp/năng động)
- Kiểu CTA: {', '.join(profile.get('cta_styles', ['urgency']))}

Hãy áp dụng phong cách trên vào nội dung bạn tạo ra.

"""
    return style_context + base_prompt


def get_profile_summary() -> str:
    """Return human-readable summary of current style profile."""
    profile = load_profile()
    if not profile:
        return "Chưa có Style Profile. Hãy học từ ít nhất 1 video mẫu trong tab Trí Thức AI."

    return (
        f"📊 Style Profile từ {profile.get('total_videos_analyzed', 0)} video đã học:\n"
        f"  • Hook: {', '.join(profile.get('hook_patterns', ['-']))}\n"
        f"  • Phân cảnh: trung bình {profile.get('avg_scene_count', 4)} cảnh\n"
        f"  • Nhịp độ: {profile.get('pacing', '-')}\n"
        f"  • Giọng điệu: {profile.get('voice_tone', '-')}\n"
        f"  • CTA: {', '.join(profile.get('cta_styles', ['-']))}"
    )
