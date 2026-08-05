from __future__ import annotations

import os
import shutil
from io import StringIO
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML


CANONICAL_MCP_MODULES = {
    "hermes_product": "mcp_servers.product.server",
    "hermes_research": "mcp_servers.research.server",
    "hermes_knowledge": "mcp_servers.knowledge.server",
    "hermes_video": "mcp_servers.video.server",
    "hermes_video_factory": "mcp_servers.video_factory.server",
}


@dataclass(frozen=True)
class RuntimeConfigResult:
    config_path: Path
    backup_path: Path | None
    changed: bool


def canonical_repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def canonical_data_dir(repo_root: str | Path | None = None) -> Path:
    configured = os.environ.get("HERMES_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(repo_root or canonical_repo_root()).resolve()
    return (root.parent / "hermes-agent-data").resolve()


def default_hermes_home() -> Path:
    configured = os.environ.get("HERMES_HOME", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return (base / "hermes").resolve()
    return (Path.home() / ".hermes").resolve()


def normalize_hermes_config(
    *,
    repo_root: str | Path | None = None,
    hermes_home: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> RuntimeConfigResult:
    root = Path(repo_root or canonical_repo_root()).resolve()
    home = Path(hermes_home or default_hermes_home()).expanduser().resolve()
    data = Path(data_dir or canonical_data_dir(root)).expanduser().resolve()
    config_path = home / "config.yaml"
    home.mkdir(parents=True, exist_ok=True)
    data.joinpath("db").mkdir(parents=True, exist_ok=True)
    data.joinpath("workspaces").mkdir(parents=True, exist_ok=True)

    yaml = YAML()
    yaml.preserve_quotes = True
    existing_text = ""
    if config_path.exists():
        existing_text = config_path.read_text(encoding="utf-8")
        with config_path.open("r", encoding="utf-8") as stream:
            config: dict[str, Any] = yaml.load(stream) or {}
    else:
        config = {}

    model = config.setdefault("model", {})
    model["default"] = "reason_combo"
    model["provider"] = "custom"
    model["base_url"] = "http://127.0.0.1:20128/v1"

    skills = config.setdefault("skills", {})
    external_dirs = skills.get("external_dirs", [])
    if isinstance(external_dirs, str):
        external_dirs = [external_dirs]
    elif not isinstance(external_dirs, list):
        external_dirs = []
    source_skills = str((root / "skills").resolve())
    if source_skills not in external_dirs:
        external_dirs.append(source_skills)
    skills["external_dirs"] = external_dirs

    servers = config.setdefault("mcp_servers", {})
    python = str((root / ".venv" / "Scripts" / "python.exe").resolve())
    shared_db = str((data / "db" / "hermes.db").resolve())
    specs = {
        "hermes_product": {
            "HERMES_P1_DB_PATH": shared_db,
            "AFFILIATE_IMPORT_DIR": str((data / "affiliate_imports").resolve()),
        },
        "hermes_research": {"HERMES_RESEARCH_DB_PATH": shared_db},
        "hermes_knowledge": {"HERMES_KNOWLEDGE_DB_PATH": shared_db},
        "hermes_video": {
            "HERMES_VIDEO_DB_PATH": str((data / "db" / "video.sqlite").resolve()),
            "HERMES_VIDEO_WORKSPACE": str((data / "workspaces" / "video").resolve()),
        },
        "hermes_video_factory": {
            "HERMES_VIDEO_FACTORY_DB_PATH": str((data / "db" / "video_factory.sqlite").resolve()),
            "HERMES_VIDEO_FACTORY_WORKSPACE": str((data / "workspaces" / "video-factory").resolve()),
        },
    }
    for name, module in CANONICAL_MCP_MODULES.items():
        server = servers.setdefault(name, {})
        server["command"] = python
        server["args"] = ["-m", module]
        server["enabled"] = True
        env = server.setdefault("env", {})
        env["HERMES_DATA_DIR"] = str(data)
        for key, value in specs[name].items():
            env[key] = value

    rendered = StringIO()
    yaml.dump(config, rendered)
    desired_text = rendered.getvalue()
    if desired_text == existing_text:
        return RuntimeConfigResult(config_path, None, False)

    backup_path = None
    if config_path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = config_path.with_name(f"config.yaml.backup-{stamp}")
        shutil.copy2(config_path, backup_path)

    temporary = config_path.with_suffix(".yaml.tmp")
    with temporary.open("w", encoding="utf-8", newline="") as stream:
        stream.write(desired_text)
    os.replace(temporary, config_path)
    return RuntimeConfigResult(config_path, backup_path, True)
