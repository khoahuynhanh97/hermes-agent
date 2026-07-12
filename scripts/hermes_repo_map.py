"""
Build and query the Hermes repository map.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.repo_map import RepoMap


DEFAULT_OUTPUT = REPO_ROOT / "data" / "repo_maps" / "hermes_repo_map.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build or query Hermes repo map")
    sub = parser.add_subparsers(dest="command")

    build = sub.add_parser("build", help="Build the repo map")
    build.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output JSON path")

    search = sub.add_parser("search", help="Search the repo map")
    search.add_argument("query", help="Search query")
    search.add_argument("--map", default=str(DEFAULT_OUTPUT), help="Existing repo map JSON")
    search.add_argument("--limit", type=int, default=10, help="Max results")

    parser.set_defaults(command="build")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_map = RepoMap(REPO_ROOT)

    if args.command == "search":
        map_path = Path(args.map)
        map_data = None
        if map_path.exists():
            map_data = json.loads(map_path.read_text(encoding="utf-8"))
        results = repo_map.search(args.query, limit=args.limit, map_data=map_data)
        for item in results:
            symbols = ", ".join(item.get("symbols", [])[:8])
            print(f"{item['path']} | {item['size_bytes']} bytes | {symbols}")
        return 0

    data = repo_map.write(args.output)
    print(f"Wrote {args.output}")
    print(f"Entries: {data['entry_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
