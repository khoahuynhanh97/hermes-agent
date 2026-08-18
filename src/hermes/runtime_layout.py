from __future__ import annotations

import os
import shutil
from io import StringIO
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from ruamel.yaml import YAML
except ImportError:
    # Fallback to PyYAML with a compatible wrapper
    import yaml
    class YAML:  # Simple wrapper mimicking ruamel.yaml.YAML API used in this module
        def __init__(self):
            self.preserve_quotes = True  # attribute kept for compatibility
        def load(self, stream):
            return yaml.safe_load(stream)
        def dump(self, data, stream):
            yaml.safe_dump(data, stream)



CANONICAL_MCP_MODULES = {
    "hermes_product": "mcp_servers.product.server",
    "hermes_research": "mcp_servers.research.server",
    "hermes_knowledge": "mcp_servers.knowledge.server",
    "hermes_video": "mcp_servers.video.server",
    "hermes_video_factory": "mcp_servers.video_factory.server",
    "hermes_work_journal": "mcp_servers.work_journal.server",
}


@dataclass(frozen=True)
class RuntimeConfigResult:
    config_path: Path
    backup_path: Path | None
    changed: bool


def canonical_repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_data_dir(repo_root: str | Path | None = None) -> Path:
    return get_data_root()


def get_data_root() -> Path:
    configured = os.environ.get("HERMES_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = canonical_repo_root().resolve()
    return (root.parent / "hermes-agent-data").resolve()


def get_product_intelligence_data_root() -> Path | None:
    """Return the configured read-only Product Intelligence data root."""
    configured = os.environ.get("HERMES_PI_DATA_DIR", "").strip()
    if not configured:
        return None
    return Path(configured).expanduser().resolve()


def _check_safe_path(path: Path, root: Path) -> Path:
    # Do not mutate user data (avoid mkdir here unless explicit)
    resolved_path = path.resolve()
    resolved_root = root.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError:
        raise ValueError(f"Path traversal detected: {path} is outside of {root}")
    if ".." in path.parts or ".." in resolved_path.parts:
        raise ValueError("Path traversal detected: '..' in path parts")
    return resolved_path


def get_jobs_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "jobs", root)


def get_logs_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "logs", root)


def get_workspaces_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "workspaces", root)


def get_knowledge_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "knowledge", root)


def get_outputs_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "outputs", root)


def get_caches_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "caches", root)


def get_artifacts_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "artifacts", root)


def get_work_journal_dir() -> Path:
    root = get_data_root()
    return _check_safe_path(root / "work-journal", root)


def get_knowledge_base_db_path() -> Path:
    """Returns the canonical path to the knowledge base SQLite database."""
    root = get_data_root()
    return _check_safe_path(root / "db" / "knowledge.sqlite", root)


def get_analytics_db_path() -> Path:
    """Returns the canonical path to the analytics SQLite database."""
    root = get_data_root()
    return _check_safe_path(root / "db" / "analytics.sqlite", root)


def get_project_workspace(project_id: str) -> Path:
    if not project_id or not isinstance(project_id, str):
        raise ValueError("Invalid project_id: must be a non-empty string")
    import re
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", project_id):
        raise ValueError(f"Invalid project_id characters: {project_id}")
    root = get_data_root()
    p = root / "workspaces" / "projects" / project_id
    return _check_safe_path(p, root)


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
        "hermes_work_journal": {
            "HERMES_WORK_JOURNAL_DB_PATH": str((data / "db" / "work_journal.sqlite").resolve()),
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
