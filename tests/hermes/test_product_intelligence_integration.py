from __future__ import annotations

import json
from pathlib import Path

from hermes.runtime.constants import reset_hermes_home_override, set_hermes_home_override


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_product_intelligence_mcp_namespace_is_distinct():
    from hermes.tools.mcp_tool import mcp_prefixed_tool_name

    assert (
        mcp_prefixed_tool_name("product_intelligence", "research_product")
        == "mcp__product_intelligence__research_product"
    )

    namespaces = {
        mcp_prefixed_tool_name(server, "research_product").split("__")[1]
        for server in ("hermes_product", "hermes_research", "product_intelligence")
    }
    assert namespaces == {"hermes_product", "hermes_research", "product_intelligence"}


def test_product_research_skill_is_discoverable_from_project_external_dir(tmp_path):
    token = set_hermes_home_override(tmp_path / "hermes-home")
    try:
        hermes_home = tmp_path / "hermes-home"
        hermes_home.mkdir(parents=True)
        (hermes_home / "skills").mkdir()
        (hermes_home / "config.yaml").write_text(
            "skills:\n"
            "  external_dirs:\n"
            f"    - {json.dumps(str((REPO_ROOT / 'skills').resolve()))}\n",
            encoding="utf-8",
        )

        from hermes.agent.skill_utils import _external_dirs_cache_clear
        from hermes.tools import skills_tool

        _external_dirs_cache_clear()
        skills_tool._SKILLS_CACHE.clear()

        payload = json.loads(skills_tool.skills_list())
        names = {skill["name"] for skill in payload["skills"]}
        assert "product-research" in names
    finally:
        reset_hermes_home_override(token)


def test_hermes_has_no_direct_product_intelligence_imports():
    forbidden_prefixes = ("from media", "import media", "from product_scout", "import product_scout")
    source_roots = [
        REPO_ROOT / "agent",
        REPO_ROOT / "core",
        REPO_ROOT / "hermes",
        REPO_ROOT / "hermes_cli",
        REPO_ROOT / "mcp_servers",
        REPO_ROOT / "tools",
    ]

    offenders: list[str] = []
    for root in source_roots:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line_no, line in enumerate(text.splitlines(), start=1):
                stripped = line.strip()
                if any(stripped.startswith(prefix) for prefix in forbidden_prefixes):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_no}:{stripped}")

    assert offenders == []
