"""Integration and discovery contracts for the bundled learning-from-video skill."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_DIR = REPO_ROOT / "skills" / "media" / "learning-from-video"
SKILL_MD = SKILL_DIR / "SKILL.md"
CONTRACT_MD = SKILL_DIR / "references" / "procedure-contract.md"


def _parse_frontmatter(content: str) -> dict:
    from agent.skill_utils import parse_frontmatter

    frontmatter, _ = parse_frontmatter(content)
    return frontmatter


@pytest.fixture(scope="module")
def skill_text() -> str:
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def frontmatter(skill_text: str) -> dict:
    return _parse_frontmatter(skill_text)


def test_skill_frontmatter_is_valid_and_discoverable(frontmatter: dict):
    assert frontmatter.get("name") == "learning-from-video"
    description = frontmatter.get("description")
    assert isinstance(description, str) and description.strip()
    assert len(description) <= 60, f"Description too long ({len(description)} chars): {description!r}"
    assert description.endswith(".")
    assert frontmatter.get("license") == "MIT"

    # Human contributor credited first per HARDLINE rules
    author = frontmatter.get("author", "")
    assert "Khoa Huynh" in author or "@khoahuynhanh97" in author, f"Human author not credited first: {author!r}"
    assert author.startswith("Khoa Huynh"), f"Human contributor should lead author line: {author!r}"

    platforms = frontmatter.get("platforms")
    assert isinstance(platforms, list)
    assert {"linux", "macos", "windows"}.issubset(platforms)


def test_bundled_skill_syncs_to_hermes_home(tmp_path: Path, monkeypatch):
    import tools.skills_sync as sync_mod

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setattr(sync_mod, "HERMES_HOME", tmp_path)
    monkeypatch.setattr(sync_mod, "SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr(sync_mod, "MANIFEST_FILE", tmp_path / "skills" / ".bundled_manifest")

    sync_mod.sync_skills(quiet=True)

    synced_skill = tmp_path / "skills" / "media" / "learning-from-video" / "SKILL.md"
    assert synced_skill.is_file()
    content = synced_skill.read_text(encoding="utf-8")
    assert "learning-from-video" in content


def test_skill_conforms_to_hardline_structure(skill_text: str):
    """Assert all mandatory HARDLINE sections are present per AGENTS.md spec:
    '# <Skill> Skill' title, When to Use, Prerequisites, How to Run,
    Quick Reference, Procedure, Pitfalls, Verification — in that exact order.
    """
    assert skill_text.startswith("---\n"), "SKILL.md must start with frontmatter"
    lines = skill_text.splitlines()

    # Find first h1 after frontmatter
    in_front = False
    h1 = None
    for line in lines:
        if line.strip() == "---":
            in_front = not in_front
            continue
        if not in_front and line.startswith("# "):
            h1 = line
            break
    assert h1 is not None, "Missing H1 title after frontmatter"
    assert h1 == "# Learning From Video Skill", f"H1 title must be '# Learning From Video Skill', got: {h1!r}"

    # Required sections in strict order
    required_sections = [
        "## When to Use",
        "## Prerequisites",
        "## How to Run",
        "## Quick Reference",
        "## Procedure",
        "## Pitfalls",
        "## Verification",
    ]
    positions = {}
    for sec in required_sections:
        idx = skill_text.find(sec)
        assert idx != -1, f"Missing mandatory HARDLINE section: {sec!r}"
        positions[sec] = idx

    # Check ordering (each section must appear after the previous)
    prev_name, prev_pos = None, -1
    for sec in required_sections:
        assert positions[sec] > prev_pos, (
            f"Section {sec!r} appears before {prev_name!r}"
        )
        prev_name, prev_pos = sec, positions[sec]

    # Must contain explicit skill_view command in Procedure section
    assert 'skill_view(name="learning-from-video", file_path="references/procedure-contract.md")' in skill_text

    # Prose must NOT contain raw third-party CLI tool names
    for banned in ("yt-dlp", "ffmpeg", "curl"):
        assert banned not in skill_text.lower(), f"SKILL.md prose should not mention raw third-party tool: {banned!r}"


def test_shared_contract_reference_exists():
    """The normative procedure contract must exist as a references file
    so both SKILL.md and the prompt engine consume the exact same source."""
    assert CONTRACT_MD.is_file(), (
        f"Missing shared contract reference: {CONTRACT_MD}"
    )
    contract_text = CONTRACT_MD.read_text(encoding="utf-8")
    for step_keyword in ("Step 1", "Step 2", "Step 3", "Step 4",
                         "Step 5", "Step 6", "Step 7", "Step 8"):
        assert step_keyword in contract_text, f"Contract missing {step_keyword!r}"
    assert "has_audio" in contract_text
    assert "MEMORY.md" in contract_text
    assert "pending_review" in contract_text

    # Prose must NOT contain raw third-party CLI tool names
    for banned in ("yt-dlp", "ffmpeg", "curl"):
        assert banned not in contract_text.lower(), f"procedure-contract.md prose should not mention raw third-party tool: {banned!r}"


def test_skill_md_does_not_duplicate_procedure_steps(skill_text: str):
    """Anti-drift: SKILL.md must NOT duplicate the 8-step summary or step headings.
    The 8 step headings (Step 1..Step 8) must reside ONLY in procedure-contract.md."""
    # Ensure no summary list of steps 1-8 in SKILL.md
    for duplicate_pattern in (
        "1. **Acquire**",
        "2. **Verify media**",
        "3. **Extract audio",
        "4. **Transcribe**",
        "5. **Analyse**",
        "6. **Manifest**",
        "7. **Propose candidate**",
        "8. **Verify & respond**",
    ):
        assert duplicate_pattern not in skill_text, (
            f"SKILL.md should not duplicate procedure step summary: {duplicate_pattern!r}"
        )

    # Ensure step headings are only in contract
    for step_num in range(1, 9):
        assert f"## Step {step_num}" not in skill_text, (
            f"Step heading '## Step {step_num}' must not appear in SKILL.md"
        )


def test_implicit_discovery_via_build_skills_system_prompt(tmp_path: Path, monkeypatch):
    """Verify that after syncing, the skill is rendered in the <available_skills> XML block
    of the system prompt via the production build_skills_system_prompt public path.

    Note: This test proves that the skill is visible and loadable to the model in the system prompt;
    it does not make assumptions about autonomous model decisions.
    """
    import tools.skills_sync as sync_mod
    from agent.prompt_builder import build_skills_system_prompt

    tmp_home = tmp_path / "hermes_home"
    tmp_skills = tmp_home / "skills"
    tmp_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HERMES_HOME", str(tmp_home))
    monkeypatch.setattr(sync_mod, "HERMES_HOME", tmp_home)
    monkeypatch.setattr(sync_mod, "SKILLS_DIR", tmp_skills)
    monkeypatch.setattr(sync_mod, "MANIFEST_FILE", tmp_skills / ".bundled_manifest")

    sync_mod.sync_skills(quiet=True)

    skills_prompt = build_skills_system_prompt(skills_dir_override=tmp_skills)

    assert "<available_skills>" in skills_prompt
    assert "</available_skills>" in skills_prompt
    assert "learning-from-video" in skills_prompt
    assert "Use when learning knowledge, hooks, or CTA from video." in skills_prompt


def test_skill_invocation_via_build_skill_invocation_message(tmp_path: Path, monkeypatch):
    """Verify that the skill can be loaded via the runtime invocation path
    build_skill_invocation_message() and returns SKILL.md instruction."""
    import tools.skills_sync as sync_mod
    import tools.skills_tool as skills_tool_mod
    from agent.skill_commands import build_skill_invocation_message, scan_skill_commands

    tmp_home = tmp_path / "hermes_home"
    tmp_skills = tmp_home / "skills"
    tmp_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HERMES_HOME", str(tmp_home))
    monkeypatch.setattr(sync_mod, "HERMES_HOME", tmp_home)
    monkeypatch.setattr(sync_mod, "SKILLS_DIR", tmp_skills)
    monkeypatch.setattr(sync_mod, "MANIFEST_FILE", tmp_skills / ".bundled_manifest")
    monkeypatch.setattr(skills_tool_mod, "HERMES_HOME", tmp_home)
    monkeypatch.setattr(skills_tool_mod, "SKILLS_DIR", tmp_skills)

    sync_mod.sync_skills(quiet=True)
    scan_skill_commands()

    user_instruction = "Xem video https://vt.tiktok.com/xyz/ và học quy trình"
    msg = build_skill_invocation_message("/learning-from-video", user_instruction)

    assert msg is not None
    assert "Learning From Video Skill" in msg
    assert user_instruction in msg
    assert "references/procedure-contract.md" in msg


def test_skill_reference_contract_loading_via_skill_view(tmp_path: Path, monkeypatch):
    """Verify that the normative contract file can be loaded dynamically via production skill_view()."""
    import tools.skills_sync as sync_mod
    import tools.skills_tool as skills_tool_mod

    tmp_home = tmp_path / "hermes_home"
    tmp_skills = tmp_home / "skills"
    tmp_home.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("HERMES_HOME", str(tmp_home))
    monkeypatch.setattr(sync_mod, "HERMES_HOME", tmp_home)
    monkeypatch.setattr(sync_mod, "SKILLS_DIR", tmp_skills)
    monkeypatch.setattr(sync_mod, "MANIFEST_FILE", tmp_skills / ".bundled_manifest")
    monkeypatch.setattr(skills_tool_mod, "HERMES_HOME", tmp_home)
    monkeypatch.setattr(skills_tool_mod, "SKILLS_DIR", tmp_skills)

    sync_mod.sync_skills(quiet=True)

    # Call production skill_view with file_path to reference contract
    raw_res = skills_tool_mod.skill_view("learning-from-video", file_path="references/procedure-contract.md")
    res = json.loads(raw_res)

    assert res.get("success") is True
    content = res.get("content", "")
    assert "Learning From Video — Procedure Contract" in content
    for step_num in range(1, 9):
        assert f"Step {step_num}" in content
    assert "has_audio" in content
    assert "pending_review" in content
