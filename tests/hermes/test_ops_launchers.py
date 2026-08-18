from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_windows_telegram_launchers_resolve_repo_root_and_module_entrypoint():
    ps1 = (REPO_ROOT / "scripts" / "ops" / "start_bot.ps1").read_text(encoding="utf-8")
    bat = (REPO_ROOT / "scripts" / "ops" / "start_telegram_and_worker.bat").read_text(encoding="utf-8")

    assert "$RepoRoot = Resolve-Path" in ps1
    assert "-m hermes.channels.gateway.platforms.telegram.bot" in ps1
    assert "telegram_bot.py" not in ps1

    assert "%~dp0..\\.." in bat
    assert "REPO_ROOT=%%~fI" in bat
    assert "-m hermes.channels.gateway.platforms.telegram.bot" in bat
    assert "telegram_bot.py" not in bat


def test_telegram_auto_start_includes_knowledge_worker_and_review_watcher():
    ps1 = (REPO_ROOT / "scripts" / "ops" / "start_bot.ps1").read_text(encoding="utf-8")
    bat = (REPO_ROOT / "scripts" / "ops" / "start_telegram_and_worker.bat").read_text(encoding="utf-8")

    assert "run_job_worker.py" in ps1
    assert "telegram_review_watcher.py" in ps1
    assert "run_job_worker.py" in bat
    assert "telegram_review_watcher.py" in bat
