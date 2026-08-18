import ast
import os
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]


def test_hermes_does_not_import_product_intelligence_packages():
    production_roots = ("src/hermes", "apps")
    forbidden_roots = {"product_scout", "media"}
    violations = []
    unparseable = []
    for directory in production_roots:
        dir_path = ROOT / directory
        if not dir_path.exists():
            continue
        for path in dir_path.rglob("*.py"):
            if any(k in path.parts for k in [".venv", "__pycache__", "node_modules"]):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
            except SyntaxError as e:
                unparseable.append(f"{path.relative_to(ROOT)}: {e}")
                continue

            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                if any(name.split(".", 1)[0] in forbidden_roots for name in names):
                    violations.append(str(path.relative_to(ROOT)))

    assert unparseable == [], f"Found non-compiling production Python files: {unparseable}"
    assert violations == [], f"Found forbidden Product Intelligence imports: {violations}"


def test_workers_do_not_import_agent_or_channel_layers():
    violations = []
    workers_dir = ROOT / "src" / "hermes" / "workers"
    if workers_dir.exists():
        for path in workers_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8-sig")
            if "hermes.agent.conversation_loop" in text or "telegram_bot" in text:
                violations.append(str(path.relative_to(ROOT)))
    assert violations == [], f"Worker layer imports forbidden layers: {violations}"


def test_single_python_source_root_and_zero_root_py_files():
    root_py_files = list(ROOT.glob("*.py"))
    assert root_py_files == [], f"Root contains production Python files: {root_py_files}"
    assert (ROOT / "src" / "hermes").exists(), "Canonical package src/hermes must exist"


def test_runtime_data_path_resolution_uses_external_data_dir(monkeypatch):
    from hermes.config import get_data_root, get_data_path
    
    test_data_dir = ROOT.parent / "hermes-agent-data"
    resolved_root = get_data_root()
    assert str(resolved_root).lower() == str(test_data_dir.resolve()).lower()
    
    custom_target = Path("D:/custom-data-dir")
    monkeypatch.setenv("HERMES_DATA_DIR", str(custom_target))
    assert get_data_root() == custom_target.resolve()
    assert get_data_path("test", "file.txt") == custom_target.resolve() / "test" / "file.txt"


def test_current_adr_marks_adr_001_as_superseded():
    adr_file = ROOT / "docs/architecture-decisions/001-hermes-agent-migration-audit.md"
    assert adr_file.exists(), "ADR-001 does not exist"
    text = adr_file.read_text(encoding="utf-8-sig")
    assert "Status: Superseded" in text, "ADR-001 status is not marked as Superseded"
    assert "ADR-010" in text, "ADR-001 does not reference ADR-010"
