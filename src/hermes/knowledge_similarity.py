from __future__ import annotations

import string
from collections.abc import Iterable, Mapping
from typing import Any


STOP_WORDS = frozenset(
    {
        "cach",
        "lam",
        "cho",
        "va",
        "cua",
        "trong",
        "voi",
        "tu",
        "de",
        "mot",
        "cac",
        "nay",
        "do",
        "duoc",
        "khong",
        "con",
        "neu",
        "hay",
        "hoac",
        "the",
        "how",
        "to",
        "and",
        "for",
        "with",
        "from",
        "a",
        "an",
        "is",
        "in",
    }
)


def _keywords(text: str, *, strip_punctuation: bool = False) -> set[str]:
    normalized = (text or "").lower().strip()
    if strip_punctuation:
        normalized = normalized.translate(str.maketrans("", "", string.punctuation))
    return set(normalized.split()) - STOP_WORDS


def find_similar_knowledge_entries(
    title: str,
    summary: str,
    entries: Iterable[Mapping[str, Any]],
    *,
    threshold: float = 0.6,
) -> list[dict[str, Any]]:
    title_normalized = (title or "").lower().strip()
    if not title_normalized:
        return []

    title_keywords = _keywords(title_normalized)
    summary_keywords = _keywords(summary, strip_punctuation=True)
    matches: list[dict[str, Any]] = []

    for entry in entries:
        if entry.get("status") != "approved":
            continue
        entry_title = str(entry.get("title") or "").lower().strip()
        entry_keywords = _keywords(entry_title)

        if title_normalized == entry_title:
            matches.append({**entry, "match_type": "exact_title", "similarity": 1.0})
            continue

        title_similarity = 0.0
        if title_keywords and entry_keywords:
            intersection = title_keywords & entry_keywords
            union = title_keywords | entry_keywords
            title_similarity = len(intersection) / len(union) if union else 0.0
            if title_similarity >= threshold:
                matches.append(
                    {
                        **entry,
                        "match_type": "similar_title",
                        "similarity": title_similarity,
                        "common_keywords": sorted(intersection),
                    }
                )
                continue

        contains_title = (
            len(title_normalized) > 10 and title_normalized in entry_title
        ) or (len(entry_title) > 10 and entry_title in title_normalized)
        if contains_title:
            contained_similarity = min(len(title_normalized), len(entry_title)) / max(
                len(title_normalized), len(entry_title)
            )
            if contained_similarity >= threshold:
                matches.append(
                    {
                        **entry,
                        "match_type": "contained_title",
                        "similarity": contained_similarity,
                    }
                )
                continue

        lesson_keywords: set[str] = set()
        for lesson in entry.get("key_lessons") or []:
            lesson_keywords.update(_keywords(str(lesson), strip_punctuation=True))
        all_entry_keywords = entry_keywords | lesson_keywords
        if summary_keywords and all_entry_keywords:
            intersection = summary_keywords & all_entry_keywords
            union = summary_keywords | all_entry_keywords
            summary_similarity = len(intersection) / len(union) if union else 0.0
            combined_similarity = title_similarity * 0.5 + summary_similarity * 0.5
            if combined_similarity >= threshold:
                matches.append(
                    {
                        **entry,
                        "match_type": "similar_summary",
                        "similarity": combined_similarity,
                        "common_keywords": sorted(intersection),
                    }
                )

    return sorted(matches, key=lambda item: item.get("similarity", 0), reverse=True)


def build_duplicate_warning(
    similar_entries: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "has_duplicates": True,
        "similar_count": len(similar_entries),
        "similar_entries": [
            {
                "id": entry.get("id"),
                "title": entry.get("title"),
                "similarity": round(float(entry.get("similarity", 0)) * 100, 1),
                "match_type": entry.get("match_type"),
                "common_keywords": list(entry.get("common_keywords", [])),
            }
            for entry in similar_entries[:5]
        ],
    }
