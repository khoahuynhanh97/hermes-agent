from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: F401 - loads the repository .env for the standalone CLI
from hermes.backup import BackupOperationError, SQLiteBackupManager


def _unexpected_failure(
    operation: str,
    path: str | Path,
) -> dict[str, object]:
    return {
        "ok": False,
        "operation": operation,
        "code": "unexpected_error",
        "path": str(Path(path).expanduser().resolve()),
        "detail": f"{operation} failed",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Backup, verify, export, or restore Hermes SQLite data")
    parser.add_argument("--backup-dir", default="", help="Override HERMES_BACKUP_DIR")
    parser.add_argument(
        "--keep",
        type=int,
        default=14,
        help="Deprecated compatibility option; backups are never deleted automatically",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("backup")
    commands.add_parser("export")
    verify = commands.add_parser("verify")
    verify.add_argument("path")
    restore = commands.add_parser("restore")
    restore.add_argument("path")
    restore.add_argument("--confirm", action="store_true", help="Required because restore replaces the local DB")
    args = parser.parse_args(argv)

    intended_path: str | Path = (
        args.path
        if args.command in {"verify", "restore"}
        else Path(args.backup_dir or ".")
    )
    if args.command == "restore" and not args.confirm:
        result = {
            "ok": False,
            "operation": "restore",
            "code": "confirmation_required",
            "path": str(Path(args.path).expanduser().resolve()),
            "detail": "restore requires confirmation",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2

    try:
        manager = SQLiteBackupManager(
            backup_dir=args.backup_dir or None,
            keep=args.keep,
        )
        if args.command not in {"verify", "restore"}:
            intended_path = manager.database.path
        if args.command == "backup":
            result = manager.verify(manager.create_backup())
        elif args.command == "export":
            result = {"ok": True, "path": str(manager.export_json())}
        elif args.command == "verify":
            result = manager.verify(args.path)
        else:
            result = {"ok": True, **manager.restore(args.path)}
    except BackupOperationError as exc:
        result = exc.to_payload()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    except Exception:
        result = _unexpected_failure(args.command, intended_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
