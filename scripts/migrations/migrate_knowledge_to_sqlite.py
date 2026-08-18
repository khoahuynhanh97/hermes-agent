from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hermes.runtime import config
from hermes.application.core.telegram_auth import parse_user_ids
from hermes.db import Database
from hermes.migration import migrate_legacy_knowledge


def _default_owner() -> str:
    explicit = os.environ.get("HERMES_OWNER_USER_ID", "").strip()
    if explicit:
        return explicit
    allowed = sorted(parse_user_ids(os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")))
    if len(allowed) == 1:
        return str(allowed[0])
    raise SystemExit(
        "Set HERMES_OWNER_USER_ID or configure exactly one TELEGRAM_ALLOWED_USER_IDS value before migration."
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Hermes JSON knowledge into SQLite.")
    parser.add_argument(
        "--source-root",
        default=str(config.KNOWLEDGE_BASE_ROOT),
        help="Legacy knowledge root containing unified_index.json",
    )
    parser.add_argument("--database", default=config.HERMES_DB_PATH)
    parser.add_argument("--owner-user-id", default="")
    parser.add_argument("--apply", action="store_true", help="Write changes; default is dry-run")
    args = parser.parse_args()

    owner = args.owner_user_id.strip() or _default_owner()
    database = Database(args.database)
    database.initialize()
    report = migrate_legacy_knowledge(
        args.source_root,
        database,
        default_owner_user_id=owner,
        dry_run=not args.apply,
    )
    payload = {"mode": "apply" if args.apply else "dry-run", **report.as_dict()}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
