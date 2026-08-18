"""Repair common UTF-8/Latin-1 mojibake in the Drive knowledge store."""

from __future__ import annotations

import json
import os
from pathlib import Path


ROOT = Path(os.environ.get("KNOWLEDGE_BASE_ROOT", "knowledge_base")).expanduser()
MARKERS = ("Ã", "Â", "á»", "Æ", "Ä", "â", "ð", "ï¿½", "\x81", "\x8f", "\x90", "\x91", "\x92", "\x93", "\x94")
CP1252_BYTES = str.maketrans({
    "\u2018": "\x91",
    "\u2019": "\x92",
    "\u201c": "\x93",
    "\u201d": "\x94",
    "\u2020": "\x86",
    "\u2021": "\x87",
    "\u2022": "\x95",
    "\u2026": "\x85",
    "\u2030": "\x89",
    "\u2039": "\x8b",
    "\u203a": "\x9b",
    "\u0192": "\x83",
    "\u02c6": "\x88",
    "\u02dc": "\x98",
    "\u2122": "\x99",
    "\u0161": "\x9a",
    "\u0153": "\x9c",
    "\u017e": "\x9e",
    "\u0178": "\x9f",
})


def _quality(value: str) -> int:
    return sum(value.count(marker) for marker in MARKERS)


def repair_text(value: str) -> str:
    current = value
    for _ in range(3):
        if _quality(current) == 0:
            break
        candidates = []
        normalized = current.translate(CP1252_BYTES)
        try:
            candidates.append(normalized.encode("latin1").decode("utf-8"))
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        for encoding in ("cp1252", "latin1"):
            try:
                candidates.append(current.encode(encoding).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        if not candidates:
            break
        candidate = min(candidates, key=_quality)
        if _quality(candidate) >= _quality(current):
            break
        current = candidate
    return current


def repair_json(path: Path) -> bool:
    original = path.read_text(encoding="utf-8-sig")
    data = json.loads(original)

    def visit(value):
        if isinstance(value, str):
            return repair_text(value)
        if isinstance(value, list):
            return [visit(item) for item in value]
        if isinstance(value, dict):
            return {key: visit(item) for key, item in value.items()}
        return value

    repaired = json.dumps(visit(data), ensure_ascii=False, indent=2) + "\n"
    if repaired == original:
        return False
    path.write_text(repaired, encoding="utf-8")
    return True


def repair_markdown(path: Path) -> bool:
    original = path.read_text(encoding="utf-8-sig")
    repaired = repair_text(original)
    if repaired == original:
        return False
    path.write_text(repaired, encoding="utf-8")
    return True


def main() -> None:
    changed = 0
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.name.startswith("unified_index.before_"):
            continue
        if path.suffix.lower() == ".json":
            changed += repair_json(path)
        elif path.suffix.lower() == ".md":
            changed += repair_markdown(path)
    print(f"encoding repair complete: changed={changed}, root={ROOT}")


if __name__ == "__main__":
    main()
