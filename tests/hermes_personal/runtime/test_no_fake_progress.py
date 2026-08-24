from __future__ import annotations

import re
from pathlib import Path
import pytest


def test_no_fake_progress_timers_in_web_and_adapters():
    """Verify that Web and application sources do not use timers to simulate progress."""
    repo_root = Path(__file__).resolve().parents[3]
    web_src = repo_root / "web" / "src"
    app_src = repo_root / "hermes_personal"

    fake_progress_pattern = re.compile(
        r"(set(?:Interval|Timeout)\s*\(\s*(?:.*?\+\+|.*?progress\s*\+=|.*?setProgress\(prev\s*=>\s*prev\s*\+))",
        re.IGNORECASE,
    )

    violations = []
    for base_dir in (web_src, app_src):
        if not base_dir.exists():
            continue
        for file_path in base_dir.rglob("*"):
            if file_path.suffix in (".ts", ".tsx", ".js", ".jsx", ".py"):
                # Skip test files
                if "test" in file_path.name or "mock" in file_path.name:
                    continue
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                matches = fake_progress_pattern.findall(content)
                if matches:
                    violations.append(f"{file_path}: found fake progress timer: {matches}")

    assert not violations, f"Found fake progress timers in production code:\n" + "\n".join(violations)


def test_no_mock_or_demo_artifact_ids_in_production_runtime():
    """Verify that production runtime code does not emit mock/demo/fake artifact IDs."""
    repo_root = Path(__file__).resolve().parents[3]
    app_src = repo_root / "hermes_personal"

    prohibited_artifact_patterns = [
        re.compile(r"""['"]art_(?:mock|demo|fake)_[a-zA-Z0-9_\-]+['"]""", re.IGNORECASE),
        re.compile(r"""artifact_id\s*=\s*['"](?:mock|demo|fake)""", re.IGNORECASE),
    ]

    violations = []
    for file_path in app_src.rglob("*.py"):
        if "test" in file_path.name or "fake" in file_path.name:
            continue
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        for pat in prohibited_artifact_patterns:
            matches = pat.findall(content)
            if matches:
                violations.append(f"{file_path}: prohibited mock artifact ID: {matches}")

    assert not violations, f"Found mock artifact IDs in production runtime:\n" + "\n".join(violations)


def test_no_direct_provider_calls_from_web_or_omni():
    """Verify that Web/Omni surfaces do not call OpenAI/Anthropic/OpenRouter directly."""
    repo_root = Path(__file__).resolve().parents[3]
    web_src = repo_root / "web" / "src"

    prohibited_endpoints = [
        "api.openai.com",
        "api.anthropic.com",
        "openrouter.ai/api",
        "generativelanguage.googleapis.com",
    ]

    violations = []
    if web_src.exists():
        for file_path in web_src.rglob("*"):
            if file_path.suffix in (".ts", ".tsx", ".js", ".jsx"):
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for ep in prohibited_endpoints:
                    if ep in content:
                        violations.append(f"{file_path}: found direct provider endpoint '{ep}'")

    assert not violations, f"Found prohibited direct provider calls in Web/Omni:\n" + "\n".join(violations)
