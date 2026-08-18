"""
Lightweight repository map for Hermes coding-agent workflows.

The map is designed to reduce model cost: inspect metadata and symbols first,
then read only the files that are likely relevant to a request.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Iterable


DEFAULT_EXCLUDED_SUB_DIRS = {
    ".git",
    ".agents",
    ".codex",
    "__pycache__",
    "downloads",
    "scratch",
    "scratch_test_downloads",
    "projects",
    ".venv",
    "venv",
    "node_modules",
    "site-packages",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}

DEFAULT_EXCLUDED_SUFFIXES = {
    ".pyc",
    ".pyo",
    ".log",
    ".mp4",
    ".mp3",
    ".wav",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".session",
    ".bin",
}

DEFAULT_EXCLUDED_NAMES = {
    ".env",
    "userbot.session",
}

DEFAULT_EXCLUDED_TOP_LEVEL_DIRS = {
    "data",
    "reports",
    "knowledge_base",
}


@dataclass
class RepoMapEntry:
    path: str
    suffix: str
    size_bytes: int
    modified_at: float
    symbols: list[str]
    imports: list[str]


class RepoMap:
    """Build and query a lightweight source map for a repository."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()

    def build(self) -> dict:
        entries = []
        for path in self._iter_files():
            entry = self._map_file(path)
            if entry:
                entries.append(asdict(entry))
        entries.sort(key=lambda item: item["path"])
        return {
            "schema_version": 1,
            "repo_root": str(self.repo_root),
            "entry_count": len(entries),
            "entries": entries,
        }

    def write(self, output_path: str | Path) -> dict:
        data = self.build()
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data

    def search(self, query: str, limit: int = 20, map_data: dict | None = None) -> list[dict]:
        terms = [term for term in re.split(r"\W+", (query or "").lower()) if term]
        if not terms:
            return []
        data = map_data or self.build()
        scored = []
        for entry in data.get("entries", []):
            haystack = " ".join(
                [
                    entry.get("path", ""),
                    " ".join(entry.get("symbols", [])),
                    " ".join(entry.get("imports", [])),
                ]
            ).lower()
            score = sum(haystack.count(term) for term in terms)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1]["path"]))
        return [entry for _, entry in scored[:limit]]

    def _iter_files(self) -> Iterable[Path]:
        for path in self.repo_root.rglob("*"):
            if not path.is_file():
                continue
            if self._is_excluded(path):
                continue
            yield path

    def _is_excluded(self, path: Path) -> bool:
        relative = path.relative_to(self.repo_root)

        # Exclude top-level directories first
        if relative.parts and relative.parts[0] in DEFAULT_EXCLUDED_TOP_LEVEL_DIRS:
            return True

        # Exclude common dev/build artifact dirs regardless of nesting
        if any(part in DEFAULT_EXCLUDED_SUB_DIRS for part in relative.parts):
            return True

        if path.name in DEFAULT_EXCLUDED_NAMES:
            return True
        if path.suffix.lower() in DEFAULT_EXCLUDED_SUFFIXES:
            return True
        if path.stat().st_size > 512_000:
            return True
        return False

    def _map_file(self, path: Path) -> RepoMapEntry | None:
        try:
            stat = path.stat()
        except OSError:
            return None
        text = ""
        if path.suffix.lower() in {".py", ".md", ".json", ".txt", ".ps1"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                text = ""
        symbols = extract_symbols(text, path.suffix.lower())
        imports = extract_imports(text, path.suffix.lower())
        return RepoMapEntry(
            path=str(path.relative_to(self.repo_root)).replace("\\", "/"),
            suffix=path.suffix.lower(),
            size_bytes=stat.st_size,
            modified_at=stat.st_mtime,
            symbols=symbols,
            imports=imports,
        )


def extract_symbols(text: str, suffix: str) -> list[str]:
    if suffix != ".py" or not text:
        return []
    symbols = []
    patterns = [
        r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)",
        r"^\s*async\s+def\s+([A-Za-z_][A-Za-z0-9_]*)",
    ]
    for pattern in patterns:
        symbols.extend(re.findall(pattern, text, flags=re.M))
    return sorted(set(symbols))[:80]


def extract_imports(text: str, suffix: str) -> list[str]:
    if suffix != ".py" or not text:
        return []
    imports = []
    for match in re.findall(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", text, flags=re.M):
        imports.extend([part for part in match if part])
    return sorted(set(imports))[:80]