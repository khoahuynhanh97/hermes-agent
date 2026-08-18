from __future__ import annotations

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class PromptTemplate:
    id: str
    name: str
    type: str
    description: str
    source_file: str
    content: str


CATEGORY_MAP: dict[str, str] = {
    "image_prompt": "image_generation",
    "video_prompt": "ai_video_generation",
    "voice_script": "voice_script",
    "analysis": "analysis",
    "writing": "writing",
}


def parse_frontmatter(content: str) -> tuple[dict[str, str], str]:
    """Extract YAML frontmatter and body from markdown content."""
    fm: dict[str, str] = {}
    body = content

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if match:
        fm_str = match.group(1)
        body = content[match.end():]
        for line in fm_str.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip()

    return fm, body


def load_templates(templates_dir: Path) -> list[PromptTemplate]:
    """Load all markdown templates from a directory."""
    templates = []
    if not templates_dir.exists():
        return templates

    for f in sorted(templates_dir.glob("*.md")):
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        fm, body = parse_frontmatter(content)
        templates.append(PromptTemplate(
            id=fm.get("id", f.stem),
            name=fm.get("name", f.stem),
            type=fm.get("type", "unknown"),
            description=fm.get("description", ""),
            source_file=str(f),
            content=content,
        ))

    return templates


def filter_by_type(templates: list[PromptTemplate], target_type: str) -> list[PromptTemplate]:
    """Filter templates by their 'type' frontmatter field."""
    return [t for t in templates if t.type == target_type]


def filter_by_category(templates: list[PromptTemplate], category: str) -> list[PromptTemplate]:
    """Filter templates by mapped category."""
    return [t for t in templates if CATEGORY_MAP.get(t.type) == category]


def filter_by_keywords(templates: list[PromptTemplate], keywords: list[str]) -> list[PromptTemplate]:
    """Filter templates whose name or description contains any keyword."""
    result = []
    for t in templates:
        text = f"{t.name} {t.description}".lower()
        if any(kw.lower() in text for kw in keywords):
            result.append(t)
    return result


def group_by_type(templates: list[PromptTemplate]) -> dict[str, list[PromptTemplate]]:
    """Group templates by their type."""
    groups: dict[str, list[PromptTemplate]] = {}
    for t in templates:
        groups.setdefault(t.type, []).append(t)
    return groups


def export_json(templates: list[PromptTemplate], output_path: Path) -> None:
    """Export templates to a JSON file."""
    data = [
        {
            "id": t.id,
            "name": t.name,
            "type": t.type,
            "description": t.description,
            "source_file": t.source_file,
            "body": t.content,
        }
        for t in templates
    ]
    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def export_markdown(templates: list[PromptTemplate], output_path: Path, title: str = "Filtered Prompts") -> None:
    """Export templates as a single markdown document with sections."""
    lines = [f"# {title}", ""]
    for t in templates:
        lines.append(f"## {t.name}")
        lines.append(f"**Type:** {t.type}  ")
        lines.append(f"**ID:** `{t.id}`  ")
        lines.append(f"**Source:** `{t.source_file}`  ")
        lines.append("")
        lines.append(t.content)
        lines.append("")
        lines.append("---")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def safe_print(text: str) -> None:
    """Print text handling Windows console encoding issues."""
    try:
        print(text.encode('utf-8', errors='replace').decode('utf-8', errors='replace'))
    except Exception:
        pass


def main() -> None:
    """Filter prompts from f/prompt.chat into organized categories."""
    source_dir = Path("f/prompt.chat/prompt_library/templates")
    output_dir = Path("prompt_output")
    output_dir.mkdir(exist_ok=True)

    templates = load_templates(source_dir)

    # Category 1: Image Generation (thay doi background, ghep nhan vat)
    image_prompts = filter_by_type(templates, "image_prompt")
    export_json(image_prompts, output_dir / "image_prompts.json")
    export_markdown(image_prompts, output_dir / "image_prompts.md", "Image Generation Prompts (Background & Character)")

    # Category 2: Storyboard Image Prompts
    storyboard_prompts = filter_by_keywords(image_prompts, ["storyboard", "background", "scene"])
    export_json(storyboard_prompts, output_dir / "storyboard_prompts.json")
    export_markdown(storyboard_prompts, output_dir / "storyboard_prompts.md", "Storyboard Image Prompts")

    # Category 3: AI Video Prompts (prompt tao video AI chuan)
    video_prompts = filter_by_type(templates, "video_prompt")
    export_json(video_prompts, output_dir / "ai_video_prompts.json")
    export_markdown(video_prompts, output_dir / "ai_video_prompts.md", "AI Video Generation Prompts")

    return image_prompts, storyboard_prompts, video_prompts


if __name__ == "__main__":
    main()