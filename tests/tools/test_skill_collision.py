import json
import pytest
from pathlib import Path

from hermes.tools.skills_tool import skill_view
from hermes.agent.skill_utils import _external_dirs_cache_clear


@pytest.fixture
def mock_skills_dirs(tmp_path, monkeypatch):
    # Setup two mock skill directories
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    dir_a.mkdir()
    dir_b.mkdir()

    # Configure monkeypatch to return these roots
    monkeypatch.setattr("hermes.agent.skill_utils.get_all_skills_dirs", lambda: [dir_a, dir_b])
    
    # Clear the external dirs cache
    _external_dirs_cache_clear()

    return dir_a, dir_b


def test_skill_view_detects_collision_between_directories(mock_skills_dirs):
    dir_a, dir_b = mock_skills_dirs

    # Create same skill in both directories
    skill_a = dir_a / "my-test-skill"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("---\nname: my-test-skill\n---\nHello from A", encoding="utf-8")

    skill_b = dir_b / "my-test-skill"
    skill_b.mkdir()
    (skill_b / "SKILL.md").write_text("---\nname: my-test-skill\n---\nHello from B", encoding="utf-8")

    # Call skill_view
    res_str = skill_view("my-test-skill", preprocess=False)
    res = json.loads(res_str)

    assert res["success"] is False
    assert "Ambiguous skill name" in res["error"]
    assert len(res["matches"]) == 2


def test_skill_view_succeeds_when_no_collision(mock_skills_dirs):
    dir_a, dir_b = mock_skills_dirs

    # Create skill only in directory A
    skill_a = dir_a / "my-unique-skill"
    skill_a.mkdir()
    (skill_a / "SKILL.md").write_text("---\nname: my-unique-skill\n---\nUnique skill content", encoding="utf-8")

    # Call skill_view
    res_str = skill_view("my-unique-skill", preprocess=False)
    res = json.loads(res_str)

    assert res["success"] is True
    assert "Unique skill content" in res["content"]
