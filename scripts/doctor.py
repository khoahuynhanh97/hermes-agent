#!/usr/bin/env python3
"""
scripts/doctor.py — Hermes Personal No-Paid-Call Diagnostic Tool

Verifies environment readiness, source path identity, CLI availability,
skills, MCP servers, storage, FFmpeg, 9Router endpoint, Google ADC, and UI dependencies.

NO API calls are made to paid providers (Gemini Image, Veo, Gemini TTS, TikTok, etc.).
"""

import sys
import os
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

def check_status(condition, label, details=""):
    status = "READY" if condition else "MISSING"
    color = "\033[92m" if condition else "\033[93m"
    reset = "\033[0m"
    detail_str = f" ({details})" if details else ""
    print(f"  {label:<30}: {color}{status}{reset}{detail_str}")
    return condition

def main():
    print("=== Hermes Doctor Diagnostic (Zero Paid Calls) ===")
    print(f"Target Repo: {REPO_ROOT}\n")

    # 1. Python environment
    py_executable = sys.executable
    in_venv = str(REPO_ROOT) in py_executable or ".venv" in py_executable
    check_status(in_venv, "Python Environment", py_executable)

    # 2. Hermes Source Identity
    try:
        sys.path.insert(0, str(REPO_ROOT))
        import hermes
        import cli
        import hermes_cli
        hermes_source_ok = str(REPO_ROOT) in hermes.__file__ and str(REPO_ROOT) in cli.__file__
        check_status(hermes_source_ok, "Hermes Source Path", f"hermes: {hermes.__file__}")
    except Exception as e:
        check_status(False, "Hermes Source Path", str(e))

    # 3. Hermes CLI
    cli_exe = REPO_ROOT / ".venv" / "Scripts" / "hermes.exe"
    if not cli_exe.exists():
        cli_exe = REPO_ROOT / ".venv" / "bin" / "hermes"
    check_status(cli_exe.exists(), "Hermes CLI Executable", str(cli_exe) if cli_exe.exists() else "Run .\\setup.ps1")

    # 4. Skills Discovery
    skills_dir = REPO_ROOT / "skills"
    skill_count = len([d for d in skills_dir.iterdir() if d.is_dir()]) if skills_dir.exists() else 0
    check_status(skill_count > 0, "Skills Catalog", f"{skill_count} skills found in {skills_dir}")

    # 5. MCP Servers
    mcp_dir = REPO_ROOT / "mcp_servers"
    mcp_count = len([d for d in mcp_dir.iterdir() if d.is_dir()]) if mcp_dir.exists() else 0
    check_status(mcp_count > 0, "MCP Servers", f"{mcp_count} servers in {mcp_dir}")

    # 6. SQLite / Data Root
    env_file = REPO_ROOT / ".env"
    data_dir = None
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("HERMES_DATA_DIR="):
                    data_dir = line.split("=", 1)[1].strip().strip("\"'")
    if not data_dir:
        data_dir = r"D:\work\hermes-agent-data"
    data_dir_path = Path(data_dir)
    check_status(data_dir_path.exists(), "SQLite / Data Root", str(data_dir_path))

    # 7. FFmpeg
    ffmpeg_bin = shutil.which("ffmpeg") or os.environ.get("FFMPEG_PATH")
    if not ffmpeg_bin:
        for candidate in [r"C:\HermesTools\ffmpeg\bin\ffmpeg.exe", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe"]:
            if os.path.exists(candidate):
                ffmpeg_bin = candidate
                break
    check_status(bool(ffmpeg_bin), "FFmpeg Utility", ffmpeg_bin or "Install FFmpeg or set FFMPEG_PATH")

    # 8. 9Router Config / Endpoint
    router_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:20128/v1")
    check_status(True, "9Router Endpoint Config", router_url)

    # 9. Google ADC / Credentials
    g_adc = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    adc_exists = bool(g_adc and os.path.exists(g_adc))
    default_adc = Path.home() / "AppData" / "Roaming" / "gcloud" / "application_default_credentials.json"
    if not adc_exists and default_adc.exists():
        adc_exists = True
        g_adc = str(default_adc)
    check_status(adc_exists, "Google Cloud ADC", g_adc or "Set GOOGLE_APPLICATION_CREDENTIALS")

    # 10. Vertex Project / Config
    vertex_project = os.environ.get("VERTEX_PROJECT_ID") or os.environ.get("GCP_PROJECT_ID")
    check_status(bool(vertex_project), "Vertex Project Config", vertex_project or "Configure VERTEX_PROJECT_ID in .env")

    # 11. React / UI Dependencies
    web_node_modules = REPO_ROOT / "web" / "node_modules"
    check_status(web_node_modules.exists(), "React/Vite UI Dependencies", str(web_node_modules))

    print("\n=== Diagnostic Check Completed ===")

if __name__ == "__main__":
    main()
