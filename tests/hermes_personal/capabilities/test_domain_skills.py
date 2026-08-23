from __future__ import annotations

from pathlib import Path
import yaml

from hermes_personal.capabilities.manifest import INITIAL_CAPABILITIES

# Repository-relative path to .agents/skills/
SKILLS_DIR = Path(__file__).resolve().parents[3] / ".agents" / "skills"

SKILL_NAMES = [
    "hermes-personal-product-research",
    "hermes-personal-product-video-production",
    "hermes-personal-knowledge-learning",
]


def _parse_skill_file(skill_name: str) -> tuple[dict, str]:
    skill_path = SKILLS_DIR / skill_name / "SKILL.md"
    assert skill_path.exists(), f"Skill file does not exist: {skill_path}"

    content = skill_path.read_text(encoding="utf-8")
    assert content.startswith("---"), f"Skill file missing YAML frontmatter start: {skill_path}"

    parts = content.split("---", 2)
    assert len(parts) >= 3, f"Skill file malformed frontmatter: {skill_path}"

    frontmatter_raw = parts[1]
    body = parts[2]

    metadata = yaml.safe_load(frontmatter_raw)
    assert isinstance(metadata, dict), f"Frontmatter is not a dict: {skill_path}"

    return metadata, body


def test_domain_skills_exist_and_have_valid_frontmatter():
    for name in SKILL_NAMES:
        metadata, body = _parse_skill_file(name)
        assert metadata.get("name") == name
        assert metadata.get("description")
        assert isinstance(metadata.get("allowed-capabilities"), list)
        assert len(metadata["allowed-capabilities"]) > 0
        assert isinstance(metadata.get("allowed-tools"), list)
        assert len(metadata["allowed-tools"]) > 0


def test_domain_skill_capabilities_are_valid_manifest_entries_and_authorized():
    for skill_name in SKILL_NAMES:
        metadata, _ = _parse_skill_file(skill_name)
        for cap_id in metadata["allowed-capabilities"]:
            assert cap_id in INITIAL_CAPABILITIES, f"Skill {skill_name} references unknown capability {cap_id}"

            spec = INITIAL_CAPABILITIES[cap_id]
            assert skill_name in spec.allowed_skills, (
                f"Capability {cap_id} manifest allowed_skills {spec.allowed_skills} "
                f"does not include declaring skill {skill_name}"
            )


def test_domain_skills_reject_forbidden_or_unknown_capabilities():
    all_skill_caps: set[str] = set()
    for name in SKILL_NAMES:
        metadata, _ = _parse_skill_file(name)
        all_skill_caps.update(metadata["allowed-capabilities"])

    forbidden_caps = {"note.create", "unknown.cap", "system.shell", "admin.override"}
    assert not (all_skill_caps & forbidden_caps), (
        f"Forbidden capabilities found in skills: {all_skill_caps & forbidden_caps}"
    )


def test_domain_skill_instructions_assert_sole_brain_and_no_auto_approval():
    for name in SKILL_NAMES:
        _, body = _parse_skill_file(name)
        assert "sole brain" in body.lower(), f"Skill {name} body missing 'sole brain' architecture statement"

    _, know_body = _parse_skill_file("hermes-personal-knowledge-learning")
    assert "auto-approval" in know_body.lower() or "auto_approval" in know_body.lower(), (
        "Knowledge learning skill missing auto-approval prohibition"
    )
