import argparse
import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from core.prompt_library import list_prompt_templates, render_prompt_template


def parse_vars(items):
    values = {}
    for item in items or []:
        if "=" not in item:
            raise ValueError(f"Invalid --var value, expected key=value: {item}")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def main():
    parser = argparse.ArgumentParser(description="Render a local prompt template.")
    parser.add_argument("template_id", nargs="?", help="Template id, for example promptA")
    parser.add_argument("--var", action="append", default=[], help="Template variable as key=value")
    parser.add_argument("--json", dest="json_path", help="Load variables from JSON file")
    parser.add_argument("--list", action="store_true", help="List available prompt templates")
    parser.add_argument("--strict", action="store_true", help="Fail when a variable is missing")
    args = parser.parse_args()

    if args.list:
        print(json.dumps(list_prompt_templates(), ensure_ascii=False, indent=2))
        return 0

    if not args.template_id:
        parser.error("template_id is required unless --list is used")

    values = {}
    if args.json_path:
        with open(args.json_path, "r", encoding="utf-8") as f:
            values.update(json.load(f))
    values.update(parse_vars(args.var))

    rendered = render_prompt_template(args.template_id, values=values, strict=args.strict)
    if rendered["missing"]:
        print(f"[!] Missing variables: {', '.join(rendered['missing'])}", file=sys.stderr)
    print(rendered["text"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
