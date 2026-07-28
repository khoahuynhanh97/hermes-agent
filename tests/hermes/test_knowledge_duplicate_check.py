import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from core.knowledge_store import UnifiedKnowledgeStore


def test_find_similar_entries_exact_title():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "bai-hoc-1",
            "title": "Hoc cach lam video TikTok viral",
            "status": "approved",
            "key_lessons": ["Hook 3s dau", "CTA cuoi video"],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries("Hoc cach lam video TikTok viral")
    assert len(similar) == 1
    assert similar[0]["match_type"] == "exact_title"
    assert similar[0]["similarity"] == 1.0


def test_find_similar_entries_similar_title():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "cach-lam-video-tiktok",
            "title": "Cach lam video TikTok viral cho nguoi moi",
            "status": "approved",
            "key_lessons": [],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries("Cach lam video TikTok viral cho nguoi ban")
    assert len(similar) >= 1
    assert similar[0]["match_type"] in ("similar_title", "contained_title")


def test_find_similar_entries_no_match():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "hoc-lam-video",
            "title": "Hoc cach lam video TikTok",
            "status": "approved",
            "key_lessons": [],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries("Nau an mon pho bo")
    assert len(similar) == 0


def test_find_similar_entries_skips_non_approved():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "bai-hoc-pending",
            "title": "Hoc lam video TikTok viral",
            "status": "pending",
            "key_lessons": [],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries("Hoc lam video TikTok viral")
    assert len(similar) == 0


def test_find_similar_entries_summary_overlap():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "tiktok-hook",
            "title": "Cong thuc ban hang TikTok",
            "status": "approved",
            "key_lessons": ["Hook", "Body", "CTA", "Retention"],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries(
        "Bi quyet TikTok",
        summary="Hook 3s dau, Body chinh, CTA cuoi, Retention devices",
        threshold=0.2,
    )
    assert len(similar) >= 1
    assert similar[0]["match_type"] == "similar_summary"


def test_find_similar_entries_empty_title():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "bai-hoc",
            "title": "Hoc lam video",
            "status": "approved",
            "key_lessons": [],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    similar = store.find_similar_entries("")
    assert len(similar) == 0


def test_find_similar_entries_threshold():
    store = UnifiedKnowledgeStore()
    store._index["entries"] = [
        {
            "id": "kb_1",
            "slug": "bai-hoc",
            "title": "Hoc cach lam video TikTok viral cho nguoi moi bat dau",
            "status": "approved",
            "key_lessons": [],
            "source_url": "",
            "platform": "tiktok",
            "category": "General",
        }
    ]
    store._save_index_atomic()

    # High threshold - only very similar
    similar_high = store.find_similar_entries(
        "Hoc lam video TikTok viral",
        threshold=0.8,
    )

    # Low threshold - more matches
    similar_low = store.find_similar_entries(
        "Hoc lam video TikTok viral",
        threshold=0.3,
    )

    assert len(similar_low) >= len(similar_high)
