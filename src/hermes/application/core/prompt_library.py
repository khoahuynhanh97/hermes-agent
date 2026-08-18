import os
import re
from pathlib import Path


from hermes.runtime.resources import get_prompts_dir

PROMPT_LIBRARY_DIR = get_prompts_dir()
TEMPLATES_DIR = PROMPT_LIBRARY_DIR / "templates"


class PromptTemplateError(Exception):
    pass


def ensure_prompt_library():
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)


def list_prompt_templates():
    """Return all prompt templates found in prompt_library/templates."""
    ensure_prompt_library()
    templates = []
    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        template = load_prompt_template(path)
        templates.append({
            "id": template["meta"].get("id") or path.stem,
            "name": template["meta"].get("name") or path.stem,
            "type": template["meta"].get("type") or "",
            "description": template["meta"].get("description") or "",
            "path": str(path),
            "variables": extract_variables(template["body"]),
        })
    return templates


def find_prompt_template(template_id):
    """Find a template by metadata id, filename stem, or exact path."""
    ensure_prompt_library()
    candidate = Path(template_id)
    if candidate.exists():
        return candidate

    for path in sorted(TEMPLATES_DIR.glob("*.md")):
        template = load_prompt_template(path)
        meta_id = template["meta"].get("id")
        if template_id in {meta_id, path.stem}:
            return path

    raise PromptTemplateError(f"Prompt template not found: {template_id}")


def load_prompt_template(template_id_or_path):
    path = Path(template_id_or_path)
    if not path.exists():
        path = find_prompt_template(str(template_id_or_path))

    text = path.read_text(encoding="utf-8")
    meta, body = parse_prompt_template(text)
    return {
        "path": str(path),
        "meta": meta,
        "body": body,
        "variables": extract_variables(body),
    }


def parse_prompt_template(text):
    if not text.startswith("---"):
        return {}, text.strip()

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, flags=re.DOTALL)
    if not match:
        return {}, text.strip()

    meta_text, body = match.groups()
    meta = {}
    for line in meta_text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, body.strip()


def extract_variables(template_body):
    variables = re.findall(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}", template_body)
    return sorted(set(variables))


def render_prompt_template(template_id, values=None, strict=False):
    """Render a prompt template with dict values."""
    template = load_prompt_template(template_id)
    values = values or {}

    missing = [name for name in template["variables"] if not str(values.get(name, "")).strip()]
    if strict and missing:
        raise PromptTemplateError(f"Missing prompt variables: {', '.join(missing)}")

    def replace(match):
        name = match.group(1).strip()
        return str(values.get(name, f"{{{{ {name} }}}}"))

    rendered = re.sub(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}", replace, template["body"])
    return {
        "id": template["meta"].get("id") or Path(template["path"]).stem,
        "name": template["meta"].get("name") or Path(template["path"]).stem,
        "type": template["meta"].get("type") or "",
        "path": template["path"],
        "missing": missing,
        "text": rendered,
    }


def save_prompt_template(template_id, name, template_type, body, description=""):
    """Create or update a local prompt template."""
    ensure_prompt_library()
    safe_id = re.sub(r"[^a-zA-Z0-9_-]+", "-", template_id.strip()).strip("-")
    if not safe_id:
        raise PromptTemplateError("template_id is required")

    path = TEMPLATES_DIR / f"{safe_id}.md"
    content = (
        "---\n"
        f"id: {safe_id}\n"
        f"name: {name.strip() or safe_id}\n"
        f"type: {template_type.strip()}\n"
        f"description: {description.strip()}\n"
        "---\n\n"
        f"{body.strip()}\n"
    )
    path.write_text(content, encoding="utf-8")
    return str(path)
