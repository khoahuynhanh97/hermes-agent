from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import dotenv_values, set_key  # noqa: E402

from hermes.runtime_layout import (  # noqa: E402
    canonical_data_dir,
    default_hermes_home,
    normalize_hermes_config,
)


def _normalize_dotenv(env_file: Path, data_dir: Path, backup_dir: Path) -> Path | None:
    if not env_file.exists():
        return None
    expected = {
        "HERMES_DATA_DIR": str(data_dir),
        "HERMES_DB_PATH": str(data_dir / "db" / "hermes.db"),
        "LLM_DEFAULT_MODEL": "reason_combo",
        "LLM_MODEL_CHAT": "reason_combo",
        "LLM_MODEL_LEARNING": "reason_combo",
        "LLM_MODEL_CODE": "reason_combo",
        "LLM_ENABLE_LEGACY_PROVIDER_FALLBACK": "0",
    }
    current = dotenv_values(env_file)
    if all(current.get(key) == value for key, value in expected.items()):
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup = backup_dir / f"repo-env.backup-{stamp}"
    shutil.copy2(env_file, backup)
    for key, value in expected.items():
        set_key(str(env_file), key, value, quote_mode="always")
    return backup


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize the canonical Hermes Personal runtime")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--hermes-home", type=Path, default=None)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--env-file", type=Path, default=None)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    data_dir = (args.data_dir or canonical_data_dir(repo_root)).resolve()
    hermes_home = (args.hermes_home or default_hermes_home()).resolve()
    result = normalize_hermes_config(
        repo_root=repo_root,
        hermes_home=hermes_home,
        data_dir=data_dir,
    )
    env_backup = (
        _normalize_dotenv(
            args.env_file.resolve(),
            data_dir,
            data_dir / "backups" / "runtime-config",
        )
        if args.env_file
        else None
    )

    print(f"repo_root={repo_root}")
    print(f"data_dir={data_dir}")
    print(f"hermes_config={result.config_path}")
    print(f"config_backup={result.backup_path or 'none'}")
    print(f"env_backup={env_backup or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
