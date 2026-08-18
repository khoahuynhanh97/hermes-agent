"""Verify manifest validation and bounded local tool execution."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.append(str(Path(__file__).resolve().parent.parent))

from hermes.application.core.tool_exporter import ToolExporter
from hermes.application.core.tool_registry import ToolRegistry


def run_tests():
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        tool_dir = ToolExporter(root).scaffold("registry-smoke", "Registry execution fixture")
        registry = ToolRegistry(root)
        manifests = registry.list_manifests()
        assert any(item.name == "registry-smoke" and item.valid for item in manifests)
        result = registry.run("registry-smoke", timeout_seconds=5)
        report = tool_dir / "output" / "report.md"
        assert result["ok"] is True
        assert report.exists()
        try:
            registry.run("missing-tool")
        except ValueError as exc:
            assert "not found" in str(exc)
        else:
            raise AssertionError("missing tool should fail")
    print("tool registry execution tests: PASS")


if __name__ == "__main__":
    run_tests()
