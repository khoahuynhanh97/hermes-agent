"""Hermes Personal doctor — no-paid-call verification.

Checks: source resolution, python env, imports, skills/MCP discovery,
SQLite/data root, FFmpeg, Vertex credentials detect, 9Router config detect.

No Gemini/Veo/TTS generation. Resource checks report READY/MISSING only.
"""
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

# load .env if present (no secrets printed)
try:
    from dotenv import load_dotenv
    load_dotenv(REPO / ".env")
except Exception:
    pass

def ok(label, detail=""):
    print(f"  [READY ] {label} {detail}")

def missing(label, detail=""):
    print(f"  [MISSING] {label} {detail}")

def main() -> int:
    print("=== Hermes Personal doctor ===")

    # source resolution
    import hermes
    src_ok = str(Path(hermes.__file__).resolve()).startswith(str(REPO.resolve()))
    if src_ok:
        ok("source", hermes.__file__)
    else:
        missing("source resolves elsewhere", hermes.__file__)

    # python env
    print(f"  [INFO ] python {sys.version.split()[0]} at {sys.executable}")

    # core imports (no paid calls)
    try:
        import hermes.db, hermes.config, hermes.jobs
        import providers.vertex_auth, providers.image_provider_factory
        import mcp_servers.video_factory.server
        import workers.job_worker
        ok("imports (hermes/providers/mcp/workers)")
    except Exception as e:
        missing("imports", str(e)[:160])

    # skills discovery
    skills_dir = REPO / "skills"
    skill_files = list(skills_dir.glob("*/SKILL.md")) if skills_dir.is_dir() else []
    if skill_files:
        ok("skills", f"{len(skill_files)} skill(s)")
    else:
        missing("skills directory")

    # MCP discovery
    mcp_dir = REPO / "mcp_servers"
    mcp_count = len([d for d in mcp_dir.iterdir() if d.is_dir() and (d / "server.py").is_file()]) if mcp_dir.is_dir() else 0
    if mcp_count:
        ok("mcp servers", f"{mcp_count} server(s)")
    else:
        missing("mcp servers")

    # SQLite / data root
    from hermes.config import get_data_path, get_data_root
    root = get_data_root()
    print(f"  [INFO ] HERMES_DATA_DIR -> {root}")
    db = get_data_path("db", "hermes.db")
    try:
        db.parent.mkdir(parents=True, exist_ok=True)
        ok("data root writable", str(root))
    except OSError as e:
        missing("data root writable", str(e))

    # FFmpeg
    ffmpeg = os.environ.get("HERMES_FFMPEG_PATH") or os.environ.get("FFMPEG_PATH") or ""
    if not ffmpeg and Path("C:/HermesTools/ffmpeg/bin/ffmpeg.exe").is_file():
        ffmpeg = "C:/HermesTools/ffmpeg/bin/ffmpeg.exe"
    if not ffmpeg and Path("D:/HermesTools/ffmpeg/bin/ffmpeg.exe").is_file():
        ffmpeg = "D:/HermesTools/ffmpeg/bin/ffmpeg.exe"
    if ffmpeg and Path(ffmpeg).is_file():
        ok("ffmpeg", ffmpeg)
    else:
        missing("ffmpeg", "set HERMES_FFMPEG_PATH or install ffmpeg")

    # Vertex credentials (detect only, no calls)
    adc = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    if adc and Path(adc).is_file():
        ok("vertex ADC", f"GOOGLE_APPLICATION_CREDENTIALS set ({Path(adc).name})")
    elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        missing("vertex ADC file", adc)
    else:
        missing("vertex ADC", "set GOOGLE_APPLICATION_CREDENTIALS (service account key) or run gcloud auth application-default login")
    if project:
        ok("vertex project", project)
    else:
        missing("vertex project", "set GOOGLE_CLOUD_PROJECT")

    # providers config
    img = os.environ.get("IMAGE_PROVIDER", "")
    vid = os.environ.get("VIDEO_PROVIDER", "")
    print(f"  [INFO ] IMAGE_PROVIDER={img or '(unset)'} VIDEO_PROVIDER={vid or '(unset)'}")
    if (img or "").lower() == "fake" and os.environ.get("HERMES_ALLOW_FAKE_PROVIDERS") != "1":
        missing("fake provider guard", "HERMES_ALLOW_FAKE_PROVIDERS not set; fake providers will fail")

    # 9Router / reasoning endpoint (config detect only)
    llm_url = os.environ.get("LLM_ROUTER_BASE_URL") or os.environ.get("LLM_BASE_URL") or ""
    print(f"  [INFO ] LLM router: {llm_url or '(unset - external 9Router)'}")
    if llm_url:
        ok("9Router configured", llm_url)
    else:
        missing("9Router", "set LLM_ROUTER_BASE_URL (external dependency, no bundled runtime)")

    print("=== done (no paid calls made) ===")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
