from __future__ import annotations

import ast
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
ADAPTER_FILES = {
    PROJECT_ROOT / "hermes_personal" / "gateway" / "__init__.py",
    PROJECT_ROOT / "hermes_personal" / "gateway" / "normalizers.py",
    PROJECT_ROOT / "hermes_personal" / "gateway" / "plugin.py",
    PROJECT_ROOT / "plugins" / "hermes_personal" / "__init__.py",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "providers",
    "agent.video_gen",
    "plugins.video_gen",
    "tools.video_generation",
    "product_intelligence",
    "video_factory",
)
WORKFLOW_MUTATION_CALLS = {
    "create_handoff",
    "link_workflow",
    "set_active_workflow",
    "update_workflow_state",
}


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _target_names(node: ast.AST) -> set[str]:
    if isinstance(node, (ast.Name, ast.Attribute)):
        return {_qualified_name(node)}
    if isinstance(node, (ast.Tuple, ast.List)):
        return {name for item in node.elts for name in _target_names(item)}
    return set()


def _string_literals(node: ast.AST) -> set[str]:
    return {
        item.value.lower()
        for item in ast.walk(node)
        if isinstance(item, ast.Constant) and isinstance(item.value, str)
    }


def boundary_violations(source: str) -> list[str]:
    tree = ast.parse(source)
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            modules = [node.module or ""]
        else:
            modules = []
        for module in modules:
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"forbidden import: {module}")

        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            target_names = {
                name.lower() for target in targets for name in _target_names(target)
            }
            value = node.value
            if any(
                token in name
                for name in target_names
                for token in ("route", "router", "routing", "keyword", "intent")
            ) and _string_literals(value) & {"product", "video"}:
                violations.append("product/video semantic routing table")
            if any(
                name.endswith((".active_workflow_id", ".workflow_state"))
                for name in target_names
            ):
                violations.append("workflow state mutation")

        if isinstance(node, ast.Call):
            call_name = _qualified_name(node.func)
            normalized = call_name.replace("_", "").lower()
            if call_name.rsplit(".", 1)[-1] in WORKFLOW_MUTATION_CALLS:
                violations.append(f"workflow state mutation call: {call_name}")
            if "productintelligence" in normalized or "videofactory" in normalized:
                violations.append(f"direct intelligence/factory call: {call_name}")
    return violations


def test_exact_project_adapter_packages_have_no_semantic_router_or_direct_calls():
    discovered = {
        *list((PROJECT_ROOT / "hermes_personal" / "gateway").rglob("*.py")),
        *list((PROJECT_ROOT / "plugins" / "hermes_personal").rglob("*.py")),
    }
    assert discovered == ADAPTER_FILES

    violations = {
        str(path.relative_to(PROJECT_ROOT)): boundary_violations(
            path.read_text(encoding="utf-8")
        )
        for path in sorted(ADAPTER_FILES)
    }
    assert {path: found for path, found in violations.items() if found} == {}


@pytest.mark.parametrize(
    "source",
    (
        "PRODUCT_VIDEO_ROUTES = {'product': 'pi', 'video': 'vf'}",
        "from providers.openai import Client",
        "from agent.video_gen_provider import VideoGenProvider",
        "session.active_workflow_id = 'wf_7'",
        "sessions.link_workflow('session_7', 'wf_7')",
        "ProductIntelligence().research()",
        "video_factory.run()",
    ),
)
def test_boundary_scan_rejects_forbidden_adapter_shapes(source):
    assert boundary_violations(source)


def test_boundary_scan_does_not_flag_neutral_words_in_docs_or_regular_copy():
    source = '''
"""Document product and video behavior without routing it."""
product_copy = "product"
video_copy = "video"

def describe_workflow(workflow_id):
    return f"Workflow {workflow_id} remains outside the adapter."
'''

    assert boundary_violations(source) == []
