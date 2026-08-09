"""Setup Vertex AI / Gemini Application Default Credentials.

Usage:
    python scripts/setup_vertex_auth.py [path\to\service-account.json]

Steps:
1. In GCP Console: IAM & Admin > Service Accounts > select/create a service
   account for project `gen-lang-client-0816609628`.
2. Keys > Add key > Create new key > JSON. Save the downloaded file.
3. Run this script with the file path. It validates the key (without printing
   its contents), tests google.auth.default(), and writes
   GOOGLE_APPLICATION_CREDENTIALS=<path> into .env (path only, never secrets).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _key_path_from_args() -> str | None:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    env = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    return env or None


def main() -> int:
    key_path = _key_path_from_args()
    if not key_path:
        print("Usage: python scripts/setup_vertex_auth.py <path-to-service-account.json>")
        print("Or set GOOGLE_APPLICATION_CREDENTIALS then run without arguments.")
        return 2

    p = Path(key_path).expanduser()
    if not p.is_file():
        print(f"[!] File not found: {p}")
        return 2

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"[!] Not a valid JSON file: {e}")
        return 2

    if data.get("type") != "service_account" or not data.get("client_email"):
        print("[!] Not a service-account key (missing type=service_account / client_email).")
        print("    Download a JSON service-account key from GCP Console.")
        return 2

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(p.resolve())

    try:
        from google.auth import default as google_auth_default
        creds, project = google_auth_default()
        print("[+] google.auth.default() OK")
        print(f"[+] project: {project or '(from key)'}")
        print(f"[+] account: {data['client_email']}")
        print(f"[+] scopes present: {bool(getattr(creds, 'scopes', None))}")
    except Exception as e:
        print(f"[!] google.auth.default() failed: {type(e).__name__}: {e}")
        return 1

    env_file = ROOT / ".env"
    line = f"GOOGLE_APPLICATION_CREDENTIALS={p.resolve()}"
    if env_file.exists():
        text = env_file.read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if not l.startswith("GOOGLE_APPLICATION_CREDENTIALS=")]
        lines.append(line)
        env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        env_file.write_text(line + "\n", encoding="utf-8")

    print(f"[+] Wrote GOOGLE_APPLICATION_CREDENTIALS path to {env_file.name}")
    print("[+] Ready. Run: python scripts/pimg1b_live_acceptance.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
