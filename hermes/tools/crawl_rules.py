"""
Crawl rules for affiliate research pipeline.
Defines the workflow: topic -> number of products -> number of videos.
Loaded automatically so it doesn't ask again.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_RULES: dict[str, Any] = {
    "schema_version": "1.0",
    "description": "Crawl rules for affiliate product research pipeline. Reads from JSON, can be edited.",
    "defaults": {
        "topic": "thiet bi cong nghe thong minh",
        "topic_category": "smart_home",
        "no_products": 150,
        "no_videos": 8,
        "platforms": ["shopee", "lazada", "tiktok"],
        "price_range_vnd": {
            "min": 200000,
            "max": 1500000,
            "default_max": 500000,
        },
        "commission_min_pct": 3.0,
        "rating_min": 4.0,
        "shortlist_limit": 25,
        "package_limit": 10,
        "auto_run": True,
        "auto_run_interval_minutes": 60,
    },
    "scheduled_runs": [
        {
            "name": "daily_morning",
            "topic": "tai nghe bluetooth 2026",
            "no_products": 150,
            "no_videos": 5,
            "platforms": ["shopee"],
            "category": "audio",
            "time": "09:00",
            "enabled": True,
        },
        {
            "name": "daily_evening",
            "topic": "gia dung thong minh",
            "no_products": 200,
            "no_videos": 8,
            "platforms": ["shopee", "lazada"],
            "category": "smart_home",
            "time": "20:00",
            "enabled": False,
        },
    ],
    "filters": {
        "exclude_categories": ["adult", "gambling", "weapons"],
        "exclude_keywords": ["replica", "fake", "luxury brand"],
        "min_sold_count": 10,
        "min_review_count": 5,
    },
    "video_profiles": {
        "default_style": "review",
        "default_duration_seconds": 30,
        "languages": ["vi"],
        "require_voiceover": True,
        "generate_subtitles": True,
    },
    "auto_approval": {
        "enabled": False,
        "min_rating": 4.5,
        "min_commission_pct": 5.0,
        "auto_publish_to_sheets": False,
    },
    "delivery": {
        "telegram_chat_id": None,
        "google_sheets_enabled": False,
        "send_summary_to_telegram": True,
    },
}


def _resolve_default_path() -> Path:
    """Resolve project root and return hermes/config/crawl_rules.json path."""
    here = Path(__file__).resolve().parent  # hermes/tools/
    for _ in range(5):
        if (here / "hermes").exists() and (here / "tools").exists():
            return here / "hermes" / "config" / "crawl_rules.json"
        here = here.parent
    return Path("D:/work/hermes-agent/hermes/config/crawl_rules.json")


def load_rules(config_path: str | Path | None = None) -> dict[str, Any]:
    """Load crawl rules from JSON file. If file doesn't exist, create defaults."""
    if config_path is None:
        config_path = _resolve_default_path()

    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    if not config_path.exists():
        save_rules(DEFAULT_RULES, config_path)
        return DEFAULT_RULES

    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        save_rules(DEFAULT_RULES, config_path)
        return DEFAULT_RULES


def save_rules(rules: dict[str, Any], config_path: str | Path) -> None:
    """Save rules to JSON file."""
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(rules, f, indent=2, ensure_ascii=False)


def get_default_rules() -> dict[str, Any]:
    """Return default rules."""
    return DEFAULT_RULES.copy()


if __name__ == "__main__":
    import sys
    config_path = Path(__file__).resolve().parent.parent / "config" / "crawl_rules.json"
    print(f"Target path: {config_path}")
    rules = load_rules(config_path)
    print(f"Loaded rules from: {config_path}")
    print(f"Default topic: {rules['defaults']['topic']}")
    print(f"Default products: {rules['defaults']['no_products']}")
    print(f"Default videos: {rules['defaults']['no_videos']}")
    print(f"Platforms: {', '.join(rules['defaults']['platforms'])}")
    print(f"Auto-run: {rules['defaults']['auto_run']}")
    print(f"File exists: {config_path.exists()}")
