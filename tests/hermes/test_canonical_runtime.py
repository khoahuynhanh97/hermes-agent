from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from dotenv import dotenv_values

from hermes.config import get_data_root


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_default_data_root_is_sibling_of_canonical_repo(monkeypatch):
    monkeypatch.delenv("HERMES_DATA_DIR", raising=False)

    assert get_data_root() == (REPO_ROOT.parent / "hermes-agent-data").resolve()


def test_runtime_config_normalizer_preserves_unrelated_config(tmp_path):
    from hermes.runtime_layout import normalize_hermes_config

    hermes_home = tmp_path / "hermes-home"
    config_path = hermes_home / "config.yaml"
    hermes_home.mkdir()
    config_path.write_text(
        yaml.safe_dump(
            {
                "model": {"default": "old", "api_key": "preserve-me"},
                "agent": {"max_turns": 99},
                "skills": {"external_dirs": ["D:/shared-hermes-skills"]},
                "mcp_servers": {
                    "unrelated": {"command": "keep", "args": ["this"]},
                    "hermes_product": {"enabled": False, "env": {"KEEP": "yes"}},
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    repo_root = tmp_path / "checkout"
    (repo_root / ".venv" / "Scripts").mkdir(parents=True)
    data_dir = tmp_path / "hermes-agent-data"

    result = normalize_hermes_config(
        repo_root=repo_root,
        hermes_home=hermes_home,
        data_dir=data_dir,
    )

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert result.backup_path is not None and result.backup_path.exists()
    assert config["agent"] == {"max_turns": 99}
    assert config["model"]["api_key"] == "preserve-me"
    assert config["model"]["default"] == "reason_combo"
    assert config["model"]["provider"] == "custom"
    assert config["model"]["base_url"] == "http://127.0.0.1:20128/v1"
    assert config["skills"]["external_dirs"] == [
        "D:/shared-hermes-skills",
        str((repo_root / "skills").resolve()),
    ]
    assert config["mcp_servers"]["unrelated"] == {"command": "keep", "args": ["this"]}

    expected = {
        "hermes_product": ("mcp_servers.product.server", "HERMES_P1_DB_PATH", "hermes.db"),
        "hermes_research": ("mcp_servers.research.server", "HERMES_RESEARCH_DB_PATH", "hermes.db"),
        "hermes_knowledge": ("mcp_servers.knowledge.server", "HERMES_KNOWLEDGE_DB_PATH", "hermes.db"),
        "hermes_video": ("mcp_servers.video.server", "HERMES_VIDEO_DB_PATH", "video.sqlite"),
        "hermes_video_factory": (
            "mcp_servers.video_factory.server",
            "HERMES_VIDEO_FACTORY_DB_PATH",
            "video_factory.sqlite",
        ),
    }
    python = str((repo_root / ".venv" / "Scripts" / "python.exe").resolve())
    for name, (module, db_variable, db_name) in expected.items():
        server = config["mcp_servers"][name]
        assert server["command"] == python
        assert server["args"] == ["-m", module]
        assert server["enabled"] is True
        assert server["env"]["HERMES_DATA_DIR"] == str(data_dir.resolve())
        assert server["env"][db_variable] == str((data_dir / "db" / db_name).resolve())
        assert "AppData\\Local\\Temp" not in str(server)
    assert config["mcp_servers"]["hermes_product"]["env"]["KEEP"] == "yes"

    second = normalize_hermes_config(
        repo_root=repo_root,
        hermes_home=hermes_home,
        data_dir=data_dir,
    )
    assert second.changed is False
    assert second.backup_path is None


def test_powershell_entrypoints_are_valid_and_repo_local():
    for script_name in ("setup.ps1", "start.ps1"):
        script_path = REPO_ROOT / script_name
        command = (
            "$ErrorActionPreference='Stop'; "
            f"[void][ScriptBlock]::Create([IO.File]::ReadAllText('{script_path}'))"
        )
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            capture_output=True,
            text=True,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    setup = (REPO_ROOT / "setup.ps1").read_text(encoding="utf-8")
    start = (REPO_ROOT / "start.ps1").read_text(encoding="utf-8")
    assert 'pip install -e ".[dev]"' in setup
    assert "scripts\\install.ps1" not in setup
    assert "git clone" not in setup
    assert '.venv\\Scripts\\hermes.exe' in start
    assert "localappdata\\hermes\\hermes-agent" not in start.lower()
    assert "appdata\\local\\hermes\\hermes-agent" not in start.lower()


def test_dotenv_normalization_preserves_secrets_and_is_idempotent(tmp_path):
    from scripts.configure_canonical_runtime import _normalize_dotenv

    env_file = tmp_path / ".env"
    env_file.write_text(
        "SECRET_TOKEN=keep-me\nLLM_MODEL_CHAT=old-model\nHERMES_DATA_DIR=old-data\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "hermes-agent-data"
    backup_dir = data_dir / "backups" / "runtime-config"

    backup = _normalize_dotenv(env_file, data_dir, backup_dir)

    values = dotenv_values(env_file)
    assert backup is not None and backup.parent == backup_dir
    assert values["SECRET_TOKEN"] == "keep-me"
    for key in ("LLM_DEFAULT_MODEL", "LLM_MODEL_CHAT", "LLM_MODEL_LEARNING", "LLM_MODEL_CODE"):
        assert values[key] == "reason_combo"
    assert values["LLM_ENABLE_LEGACY_PROVIDER_FALLBACK"] == "0"
    assert _normalize_dotenv(env_file, data_dir, backup_dir) is None


def test_env_example_defaults_to_fake_providers():
    """Ensure .env.example uses fake providers so new clones never make paid calls by accident."""
    env_example = REPO_ROOT / ".env.example"
    values = dotenv_values(env_example)
    assert values.get("IMAGE_PROVIDER") == "fake", (
        f"IMAGE_PROVIDER should default to 'fake' in .env.example, got {values.get('IMAGE_PROVIDER')!r}"
    )
    assert values.get("VIDEO_PROVIDER") == "fake", (
        f"VIDEO_PROVIDER should default to 'fake' in .env.example, got {values.get('VIDEO_PROVIDER')!r}"
    )
    assert values.get("TTS_PROVIDER") == "fake", (
        f"TTS_PROVIDER should default to 'fake' in .env.example, got {values.get('TTS_PROVIDER')!r}"
    )
