"""BGM track selector module."""
from __future__ import annotations

import random
from pathlib import Path
from typing import Optional


BGM_DIR = Path(__file__).parent.parent / "bgm_library"


def select_bgm_track(mood: str = "energetic") -> Optional[str]:
    """Select a background music track path based on requested mood.

    Mood options: 'calm', 'energetic', 'happy', 'inspirational', 'trendy'
    """
    category_dir = BGM_DIR / mood.lower()
    if not category_dir.exists():
        category_dir = BGM_DIR / "energetic"

    tracks = list(category_dir.glob("*.mp3")) + list(category_dir.glob("*.wav"))
    if not tracks:
        # Fallback to any track in entire bgm_library
        tracks = list(BGM_DIR.rglob("*.mp3")) + list(BGM_DIR.rglob("*.wav"))

    if tracks:
        selected = random.choice(tracks)
        return str(selected.resolve())

    return None
