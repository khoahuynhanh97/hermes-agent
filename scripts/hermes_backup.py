from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401 - loads the repository .env for the standalone CLI
from hermes.backup import SQLiteBackupManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Backup, verify, export, or restore Hermes SQLite data")
    parser.add_argument("--backup-dir", default="", help="Override HERMES_BACKUP_DIR")
    parser.add_argument("--keep", type=int, default=14, help="Number of SQLite backups to retain")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    commands.add_parser("export")
    verify = commands.add_parser("verify")
    verify.add_argument("path")
    restore = commands.add_parser("restore")
    restore.add_argument("path")
    restore.add_argument("--confirm", action="store_true", help="Required because restore replaces the local DB")
    args = parser.parse_args()

    manager = SQLiteBackupManager(backup_dir=args.backup_dir or None, keep=args.keep)
    if args.command == "backup":
        result = manager.verify(manager.create_backup())
    elif args.command == "export":
        result = {"ok": True, "path": str(manager.export_json())}
    elif args.command == "verify":
        result = manager.verify(args.path)
    else:
        if not args.confirm:
            parser.error("restore requires --confirm")
        result = {"ok": True, **manager.restore(args.path)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
