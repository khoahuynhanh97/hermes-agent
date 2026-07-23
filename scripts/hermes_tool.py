"""
Hermes tool registry/scaffold/export CLI.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.tool_exporter import ToolExporter
from core.tool_registry import ToolRegistry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Hermes tool helper")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List registered tool manifests")

    create = sub.add_parser("create", help="Create a local tool scaffold")
    create.add_argument("name", help="Tool name")
    create.add_argument("--description", default="", help="Tool description")

    run = sub.add_parser("run", help="Run a generated Python tool")
    run.add_argument("name", help="Tool name")
    run.add_argument("--input", action="append", default=[], metavar="KEY=VALUE", help="Declared tool input")
    run.add_argument("--timeout", type=int, default=30, help="Timeout in seconds, capped at 60")

    export = sub.add_parser("export", help="Export a generated tool as zip")
    export.add_argument("name", help="Tool name")

    parser.set_defaults(command="list")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = ToolRegistry(REPO_ROOT)
    exporter = ToolExporter(REPO_ROOT)

    if args.command == "create":
        path = exporter.scaffold(args.name, description=args.description)
        print(f"Created: {path}")
        return 0

    if args.command == "export":
        path = exporter.export(args.name)
        print(f"Exported: {path}")
        return 0

    if args.command == "run":
        inputs = {}
        for item in args.input:
            if "=" not in item:
                raise SystemExit(f"Invalid --input {item!r}; use KEY=VALUE")
            key, value = item.split("=", 1)
            if not key.strip():
                raise SystemExit("Input key cannot be empty")
            inputs[key.strip()] = value
        result = registry.run(args.name, inputs=inputs, timeout_seconds=args.timeout)
        print(result.get("stdout", "").rstrip())
        if result.get("stderr"):
            print(result["stderr"].rstrip(), file=sys.stderr)
        return 0

    manifests = registry.list_manifests()
    if not manifests:
        print("No tool manifests found.")
        return 0
    for manifest in manifests:
        status = "valid" if manifest.valid else "invalid"
        description = manifest.data.get("description", "")
        print(f"{manifest.name} | {status} | {description}")
        for error in manifest.errors:
            print(f"  - {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
