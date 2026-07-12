"""
Hermes coding-agent dry-run planner.

This module does not edit code. It selects likely source files from the repo
map, reads small previews, and writes a reviewable implementation plan. The
patch executor belongs in a later job behind a permission gate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
from pathlib import Path
import re

from core.repo_map import RepoMap


SOURCE_SUFFIXES = {".py", ".md", ".json", ".ps1", ".txt"}
MAX_FILE_PREVIEW_CHARS = 6000
MAX_SELECTED_FILES = 8
SEARCH_STOPWORDS = {
    "a",
    "an",
    "and",
    "add",
    "change",
    "create",
    "fix",
    "for",
    "from",
    "in",
    "make",
    "of",
    "on",
    "the",
    "to",
    "update",
    "with",
}


@dataclass
class SelectedFile:
    path: str
    suffix: str
    size_bytes: int
    symbols: list[str]
    reason: str
    preview: str


@dataclass
class CodingPlan:
    request: str
    created_at: str
    selected_files: list[SelectedFile]
    implementation_steps: list[str]
    risks: list[str]
    verification_commands: list[str]
    blocked_paths: list[str]
    notes: list[str]


class CodingAgentPlanner:
    """Create dry-run implementation plans for coding requests."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.repo_map = RepoMap(self.repo_root)

    def build_plan(self, request: str, limit: int = MAX_SELECTED_FILES) -> CodingPlan:
        request = (request or "").strip()
        map_data = self._load_or_build_map()
        search_query = build_search_query(request)
        candidates = self.repo_map.search(search_query, limit=max(limit * 3, 20), map_data=map_data)
        candidates = rerank_candidates(candidates, request)
        selected_entries = self._select_source_entries(candidates, limit=limit)
        selected_files = [self._entry_to_selected_file(entry, request) for entry in selected_entries]
        return CodingPlan(
            request=request,
            created_at=datetime.now().isoformat(timespec="seconds"),
            selected_files=selected_files,
            implementation_steps=self._implementation_steps(request, selected_files),
            risks=self._risks(request, selected_files),
            verification_commands=self._verification_commands(selected_files),
            blocked_paths=self._blocked_paths(),
            notes=[
                "Dry-run only: no source files were modified.",
                "Use this plan to review scope before enabling patch execution.",
                "If selected files look wrong, rebuild the repo map or make the request more specific.",
            ],
        )

    def write_report(self, plan: CodingPlan, output_path: str | Path | None = None) -> Path:
        output = Path(output_path) if output_path else self._default_report_path(plan.request)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.format_markdown(plan), encoding="utf-8")
        return output

    def format_markdown(self, plan: CodingPlan) -> str:
        lines = [
            "# Hermes Coding Agent Plan",
            "",
            f"Created at: {plan.created_at}",
            f"Request: {plan.request}",
            "",
            "## Selected files",
        ]
        if not plan.selected_files:
            lines.append("- No relevant source files selected.")
        for item in plan.selected_files:
            symbols = ", ".join(item.symbols[:12]) if item.symbols else "(no symbols detected)"
            lines.extend(
                [
                    f"- `{item.path}`",
                    f"  - Reason: {item.reason}",
                    f"  - Size: {item.size_bytes} bytes",
                    f"  - Symbols: {symbols}",
                ]
            )

        lines.extend(["", "## Implementation steps"])
        for index, step in enumerate(plan.implementation_steps, start=1):
            lines.append(f"{index}. {step}")

        lines.extend(["", "## Risks"])
        for risk in plan.risks:
            lines.append(f"- {risk}")

        lines.extend(["", "## Verification commands"])
        for command in plan.verification_commands:
            lines.append(f"- `{command}`")

        lines.extend(["", "## Blocked paths"])
        for path in plan.blocked_paths:
            lines.append(f"- `{path}`")

        lines.extend(["", "## Notes"])
        for note in plan.notes:
            lines.append(f"- {note}")
        return "\n".join(lines) + "\n"

    def to_dict(self, plan: CodingPlan) -> dict:
        data = asdict(plan)
        data["selected_files"] = [asdict(item) for item in plan.selected_files]
        return data

    def _load_or_build_map(self) -> dict:
        map_path = self.repo_root / "data" / "repo_maps" / "hermes_repo_map.json"
        if map_path.exists():
            try:
                return json.loads(map_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass
        return self.repo_map.write(map_path)

    def _select_source_entries(self, candidates: list[dict], limit: int) -> list[dict]:
        selected = []
        seen = set()
        for entry in candidates:
            path = entry.get("path", "")
            suffix = entry.get("suffix", "")
            if not path or path in seen:
                continue
            if suffix not in SOURCE_SUFFIXES:
                continue
            if is_generated_or_runtime_path(path):
                continue
            selected.append(entry)
            seen.add(path)
            if len(selected) >= limit:
                break
        return selected

    def _entry_to_selected_file(self, entry: dict, request: str) -> SelectedFile:
        path = entry.get("path", "")
        abs_path = self.repo_root / path
        preview = read_preview(abs_path)
        return SelectedFile(
            path=path,
            suffix=entry.get("suffix", ""),
            size_bytes=int(entry.get("size_bytes") or 0),
            symbols=list(entry.get("symbols") or []),
            reason=match_reason(path, entry, request),
            preview=preview,
        )

    def _implementation_steps(self, request: str, files: list[SelectedFile]) -> list[str]:
        lower = request.lower()
        steps = [
            "Confirm the requested behavior and keep the change scoped to the selected files.",
            "Read the selected files fully before editing; use the previews only for triage.",
        ]
        if any(term in lower for term in ["telegram", "bot", "message", "chat"]):
            steps.append("Trace Telegram command handlers, message routing, and background loops before changing behavior.")
        if any(term in lower for term in ["duplicate", "dedup", "retry", "race"]):
            steps.append("Check existing state/dedup stores and make the operation idempotent before creating new jobs.")
        if any(term in lower for term in ["knowledge", "learn", "hoc", "proposal"]):
            steps.append("Preserve review-queue behavior so learned knowledge still requires approval.")
        if any(term in lower for term in ["tool", "manifest", "export", "deploy"]):
            steps.append("Keep the tool contract manifest-first: inputs, outputs, permissions, and entrypoint.")
        if files:
            touched = ", ".join(f"`{item.path}`" for item in files[:5])
            steps.append(f"Prepare a minimal patch touching only the necessary files, likely starting with {touched}.")
        steps.append("After edits, run focused syntax checks and any existing targeted test scripts.")
        steps.append("Write an implementation report under `reports/` with files, behavior, verification, and notes.")
        return steps

    def _risks(self, request: str, files: list[SelectedFile]) -> list[str]:
        risks = [
            "Planner output is heuristic; a human or stronger model should review before patch execution.",
            "Runtime artifacts, secrets, downloads, and knowledge-base content are intentionally excluded from source selection.",
        ]
        lower = request.lower()
        if any(term in lower for term in ["telegram", "bot"]):
            risks.append("Telegram changes can affect live message handling; keep fallback replies and long-message splitting intact.")
        if any(term in lower for term in ["worker", "job", "queue"]):
            risks.append("Job queue changes can create duplicate, lost, or stuck jobs if state transitions are not atomic.")
        if not files:
            risks.append("No source files were selected; the request may be too broad or the repo map may need rebuilding.")
        return risks

    def _verification_commands(self, files: list[SelectedFile]) -> list[str]:
        py_files = [item.path.replace("/", "\\") for item in files if item.suffix == ".py"]
        commands = []
        if py_files:
            quoted = ",".join(repr(path.replace("\\", "/")) for path in py_files)
            commands.append(
                "python -c \"import ast, pathlib; "
                f"[ast.parse(pathlib.Path(p).read_text(encoding='utf-8')) for p in [{quoted}]]; "
                "print('syntax ok')\""
            )
        commands.append("python scripts\\hermes_repo_map.py build")
        return commands

    def _blocked_paths(self) -> list[str]:
        return [
            ".env",
            "userbot.session",
            ".git/**",
            "downloads/**",
            "scratch/**",
            "projects/**",
            "knowledge_base/approved_lessons/**",
            "knowledge_base/entries/**",
        ]

    def _default_report_path(self, request: str) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        slug = slugify(request) or "coding_plan"
        return self.repo_root / "reports" / f"coding_plan_{stamp}_{slug[:48]}.md"


def read_preview(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    if len(text) <= MAX_FILE_PREVIEW_CHARS:
        return text
    return text[:MAX_FILE_PREVIEW_CHARS] + "\n\n... preview truncated ...\n"


def match_reason(path: str, entry: dict, request: str) -> str:
    terms = [term for term in re.split(r"\W+", request.lower()) if term]
    haystack = " ".join(
        [
            path,
            " ".join(entry.get("symbols") or []),
            " ".join(entry.get("imports") or []),
        ]
    ).lower()
    matches = [term for term in terms if term in haystack]
    if matches:
        return "Matched request terms: " + ", ".join(sorted(set(matches))[:8])
    return "Selected by repo-map relevance score."


def is_generated_or_runtime_path(path: str) -> bool:
    blocked_prefixes = (
        "data/",
        "reports/",
        "downloads/",
        "scratch/",
        "scratch_test_downloads/",
        "projects/",
        "knowledge_base/",
        ".git/",
    )
    return path.startswith(blocked_prefixes)


def slugify(text: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_").lower()
    return cleaned[:80]


def build_search_query(request: str) -> str:
    terms = [term for term in re.split(r"\W+", (request or "").lower()) if term]
    filtered = [term for term in terms if term not in SEARCH_STOPWORDS and len(term) > 2]
    return " ".join(filtered or terms)


def rerank_candidates(candidates: list[dict], request: str) -> list[dict]:
    terms = [term for term in re.split(r"\W+", (request or "").lower()) if term]
    terms = [term for term in terms if term not in SEARCH_STOPWORDS and len(term) > 2]
    scored = [(candidate_score(entry, terms), entry) for entry in candidates]
    scored.sort(key=lambda item: (-item[0], item[1].get("path", "")))
    return [entry for _, entry in scored]


def candidate_score(entry: dict, terms: list[str]) -> int:
    path = (entry.get("path") or "").lower()
    filename = Path(path).stem.lower()
    symbols = [symbol.lower() for symbol in entry.get("symbols") or []]
    imports = [item.lower() for item in entry.get("imports") or []]

    score = 0
    for term in terms:
        if term in filename:
            score += 80
        if term in path:
            score += 35
        if any(term in symbol for symbol in symbols):
            score += 30
        if any(term in item for item in imports):
            score += 5

    if "duplicate" in terms and ("dedup" in path or any("dedup" in symbol for symbol in symbols)):
        score += 100
    if "telegram" in terms and path == "telegram_bot.py":
        score += 60
    if "report" in terms and "telegram_review_watcher" in path:
        score += 60
    return score
