# Hermes Agent Source and Runtime Layout Runbook

## Canonical Source Root
`D:\work\hermes-agent` is the canonical source root.
No production imports should ever point to `%APPDATA%`, `Downloads/`, or external cache paths.

## Canonical Launchers
- **Full Stack / Background**: `.\start.ps1` or `start_full_bg.vbs`
- **Interactive CLI**: `.\.venv\Scripts\python.exe run_agent.py`
- **FastAPI Backend (Port 8000)**: `.\.venv\Scripts\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8000`
- **Web Studio (Port 3000)**: `npm run dev --prefix web`
- **Telegram Bot**: `.\.venv\Scripts\python.exe telegram_bot.py` or `start_telegram_bg.vbs`

## Runtime Data Isolation
All persistent databases (`hermes.db`, `video_factory.sqlite`), generated videos, and job traces must be stored under:
`D:\work\hermes-agent-data`

## Generated Artifacts Policy
- Never commit `*.pyc`, `__pycache__`, `.pytest_cache`, `.audit-pytest-*`, or temporary test folders.
- Clean them up with `scripts/ops/clean_generated.py`.
