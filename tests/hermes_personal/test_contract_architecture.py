import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_ROOT = ROOT / "hermes_personal" / "contracts"
FORBIDDEN_ROOTS = {
    "fastapi",
    "gateway",
    "telegram",
    "product_intelligence",
    "video_factory",
    "run_agent",
    "tools",
}


def test_contracts_do_not_import_transport_provider_or_upstream_runtime():
    violations = []
    for path in CONTRACT_ROOT.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN_ROOTS:
                    violations.append(f"{path.name}: {name}")
    assert violations == []
