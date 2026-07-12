"""
Hermes tool scaffold and export helpers.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import zipfile


class ToolExporter:
    """Create and package local Hermes tools."""

    def __init__(self, repo_root: str | Path):
        self.repo_root = Path(repo_root).resolve()
        self.generated_root = self.repo_root / "tools" / "generated"
        self.export_root = self.repo_root / "tools" / "exports"

    def scaffold(self, name: str, description: str = "") -> Path:
        tool_name = normalize_tool_name(name)
        if not tool_name:
            raise ValueError("tool name is required")
        tool_dir = self.generated_root / tool_name
        tool_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "schema_version": 1,
            "name": tool_name,
            "version": "0.1.0",
            "description": description or f"Hermes local tool: {tool_name}",
            "type": "cli",
            "entrypoint": "main.py",
            "inputs": [],
            "outputs": [
                "report.md"
            ],
            "permissions": {
                "filesystem_read": [],
                "filesystem_write": [
                    "output/**"
                ],
                "network": [],
                "shell": False
            },
            "providers": [
                "ollama",
                "gemini",
                "openrouter"
            ]
        }
        (tool_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (tool_dir / "README.md").write_text(
            f"# {tool_name}\n\n{manifest['description']}\n\n## Run\n\n```cmd\npython main.py\n```\n",
            encoding="utf-8",
        )
        (tool_dir / "main.py").write_text(
            "from pathlib import Path\n\n\n"
            "def main():\n"
            "    output = Path('output')\n"
            "    output.mkdir(exist_ok=True)\n"
            "    report = output / 'report.md'\n"
            "    report.write_text('# Tool Report\\n\\nTool executed.\\n', encoding='utf-8')\n"
            "    print(report)\n\n\n"
            "if __name__ == '__main__':\n"
            "    main()\n",
            encoding="utf-8",
        )
        return tool_dir

    def export(self, tool_name: str) -> Path:
        name = normalize_tool_name(tool_name)
        tool_dir = self.generated_root / name
        if not tool_dir.exists():
            raise FileNotFoundError(f"tool not found: {tool_dir}")
        self.export_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_path = self.export_root / f"{name}_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(tool_dir.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=str(path.relative_to(tool_dir)).replace("\\", "/"))
        return zip_path


def normalize_tool_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", name or "").strip("-").lower()
    cleaned = re.sub(r"-+", "-", cleaned)
    return cleaned
