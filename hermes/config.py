from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_data_dir() -> Path:
    configured = os.environ.get("HERMES_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    if os.name == "nt":
        return Path(r"D:\HermesData")
    return (Path.home() / ".hermes").resolve()


def load_settings() -> "HermesPaths":
    """Load application settings from environment variables."""
    return HermesPaths.from_env()


@dataclass(frozen=True)
class HermesPaths:
    data_dir: Path
    database: Path
    artifacts: Path
    backups: Path
    exports: Path

    @classmethod
    def from_env(cls) -> "HermesPaths":
        data_dir = _default_data_dir()
        database_value = os.environ.get("HERMES_DB_PATH", "").strip()
        database = Path(database_value).expanduser().resolve() if database_value else data_dir / "hermes.db"
        return cls(
            data_dir=data_dir,
            database=database,
            artifacts=data_dir / "artifacts",
            backups=data_dir / "backups",
            exports=data_dir / "exports",
        )

    @property
    def database_path(self) -> Path:
        return self.database

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.exports.mkdir(parents=True, exist_ok=True)

