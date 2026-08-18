from pathlib import Path
import pytest
from hermes.tools.skills_guard import validate_bundled_skill_tools, runtime_tool_names

ROOT = Path(__file__).resolve().parents[2]


def test_bundled_skill_tool_references_resolve_to_canonical_names():
    skills_dir = ROOT / "skills"
    if skills_dir.exists():
        r_tools = runtime_tool_names()
        managed_mcp_tools = {
            "mcp__hermes_product__product_import_candidates",
            "mcp__hermes_product__product_score_shortlist",
            "mcp__hermes_product__product_get_run",
            "mcp__hermes_research__research_fetch",
            "mcp__hermes_research__research_extract",
            "mcp__hermes_research__research_get_source",
            "mcp__hermes_knowledge__knowledge_search",
            "mcp__hermes_knowledge__knowledge_get",
            "mcp__hermes_knowledge__knowledge_propose",
            "mcp__hermes_video__video_analyze",
            "mcp__hermes_video__video_create_job",
            "mcp__hermes_video__video_get_job",
            "mcp__hermes_video_factory__video_project_create",
            "mcp__hermes_video_factory__video_project_get",
            "mcp__hermes_video_factory__resource_pack_save",
            "mcp__hermes_video_factory__resource_pack_get",
            "mcp__hermes_video_factory__resource_pack_lock",
            "mcp__hermes_video_factory__resource_pack_unlock",
            "mcp__hermes_video_factory__raw_idea_save",
            "mcp__hermes_video_factory__creative_brief_save",
            "mcp__hermes_video_factory__creative_brief_get",
            "mcp__hermes_video_factory__creative_brief_approve",
            "mcp__hermes_video_factory__scene_plan_save",
            "mcp__hermes_video_factory__scene_plan_get",
            "mcp__hermes_video_factory__scene_plan_approve",
            "mcp__product_intelligence__research_product",
            "mcp__product_intelligence__get_product_research",
            "mcp__product_intelligence__build_resource_pack",
            "mcp__product_intelligence__get_resource_pack",
        }
        active_manifest = r_tools | managed_mcp_tools
        assert len(active_manifest) > 0
        errors = validate_bundled_skill_tools(skills_dir, active_tools=active_manifest)
        assert errors == []


def test_skill_contract_fixtures(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    # 1. Missing allowed-tools
    skill1 = skills_dir / "s1"
    skill1.mkdir()
    (skill1 / "SKILL.md").write_text("""---
name: s1
description: "no allowed-tools"
metadata:
  hermes:
    governed: true
---
# S1
""", encoding="utf-8")

    # 2. Unknown tool
    skill2 = skills_dir / "s2"
    skill2.mkdir()
    (skill2 / "SKILL.md").write_text("""---
name: s2
description: "unknown tool"
allowed-tools: [totally_nonexistent_tool_xyz]
---
# S2
""", encoding="utf-8")

    # 3. Ambiguous alias
    skill3 = skills_dir / "s3"
    skill3.mkdir()
    (skill3 / "SKILL.md").write_text("""---
name: s3
description: "ambiguous alias"
allowed-tools: [video_analyze]
---
# S3
""", encoding="utf-8")

    # 4. requires_tools not in allowlist
    skill4 = skills_dir / "s4"
    skill4.mkdir()
    (skill4 / "SKILL.md").write_text("""---
name: s4
description: "requires_tools mismatch"
allowed-tools: [mcp__hermes_research__research_fetch]
metadata:
  hermes:
    requires_tools: [mcp__hermes_product__product_import_candidates]
---
# S4
""", encoding="utf-8")

    # 5. Valid skill
    skill5 = skills_dir / "s5"
    skill5.mkdir()
    (skill5 / "SKILL.md").write_text("""---
name: s5
description: "valid skill"
allowed-tools: [mcp__hermes_research__research_fetch]
metadata:
  hermes:
    requires_tools: [mcp__hermes_research__research_fetch]
---
# S5
""", encoding="utf-8")

    # 6. Doc-only skill (exempt from allowed-tools)
    skill6 = skills_dir / "s6"
    skill6.mkdir()
    (skill6 / "SKILL.md").write_text("""---
name: s6
description: "doc only skill"
metadata:
  hermes:
    documentation_only: true
---
# S6
""", encoding="utf-8")

    active = {"mcp__hermes_research__research_fetch", "mcp__hermes_product__product_import_candidates"}
    errors = validate_bundled_skill_tools(skills_dir, active_tools=active)

    assert any("missing allowed-tools" in err for err in errors)
    assert any("unknown tool 'totally_nonexistent_tool_xyz'" in err for err in errors)
    assert any("ambiguous tool reference 'video_analyze'" in err for err in errors)
    assert any("requires_tools 'mcp__hermes_product__product_import_candidates' is not in allowed-tools" in err for err in errors)
    assert not any("s5" in err for err in errors)
    assert not any("s6" in err for err in errors)


def test_snapshot_unavailable_fails_explicitly(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    monkeypatch.setattr("hermes.tools.skills_guard.runtime_tool_names", lambda manifest=None: set())
    errors = validate_bundled_skill_tools(skills_dir)
    assert errors == ["Snapshot unavailable: runtime tool registry snapshot is empty or not initialized"]


def test_unknown_tool_fails_against_real_snapshot(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "test_sk"
    skill.mkdir()
    (skill / "SKILL.md").write_text("""---
name: test_sk
allowed-tools: [tool_not_in_active_snapshot]
metadata:
  hermes:
    governed: true
---
""", encoding="utf-8")
    errors = validate_bundled_skill_tools(skills_dir, active_tools={"real_tool_a"})
    assert any("unknown tool 'tool_not_in_active_snapshot'" in err for err in errors)


def test_requires_tools_must_be_allowed(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "sk_req"
    skill.mkdir()
    (skill / "SKILL.md").write_text("""---
name: sk_req
allowed-tools: [tool_a]
metadata:
  hermes:
    requires_tools: [tool_b]
---
""", encoding="utf-8")
    errors = validate_bundled_skill_tools(skills_dir, active_tools={"tool_a", "tool_b"})
    assert any("requires_tools 'tool_b' is not in allowed-tools" in err for err in errors)


def test_documentation_only_skill_is_exempt(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "sk_doc"
    skill.mkdir()
    (skill / "SKILL.md").write_text("""---
name: sk_doc
metadata:
  hermes:
    documentation_only: true
---
""", encoding="utf-8")
    errors = validate_bundled_skill_tools(skills_dir, active_tools={"tool_a"})
    assert errors == []


def test_valid_governed_skill_passes(tmp_path):
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    skill = skills_dir / "sk_gov"
    skill.mkdir()
    (skill / "SKILL.md").write_text("""---
name: sk_gov
allowed-tools: [tool_a, tool_b]
metadata:
  hermes:
    governed: true
    requires_tools: [tool_a]
---
""", encoding="utf-8")
    errors = validate_bundled_skill_tools(skills_dir, active_tools={"tool_a", "tool_b"})
    assert errors == []
