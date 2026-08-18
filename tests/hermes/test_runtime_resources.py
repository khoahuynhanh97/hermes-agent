import shutil
import pytest
from pathlib import Path

from hermes.runtime.resources import get_skills_dir, get_prompts_dir, get_locales_dir, _compute_package_digest


def test_bundled_resources_materialization(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    
    # Materialize skills, prompts, locales
    skills_dir = get_skills_dir()
    prompts_dir = get_prompts_dir()
    locales_dir = get_locales_dir()
    
    # Assert path is correct: caches/bundled-resources
    assert skills_dir == tmp_path / "caches" / "bundled-resources" / "skills"
    assert prompts_dir == tmp_path / "caches" / "bundled-resources" / "prompts"
    assert locales_dir == tmp_path / "caches" / "bundled-resources" / "locales"
    
    # Assert they exist and contain files
    assert skills_dir.exists()
    assert prompts_dir.exists()
    assert locales_dir.exists()
    
    # Assert digest file exists
    digest_file = tmp_path / "caches" / "bundled-resources" / ".digest"
    assert digest_file.exists()
    assert digest_file.read_text(encoding="utf-8").strip() == _compute_package_digest()


def test_bundled_resources_migration_from_old_cache(monkeypatch, tmp_path):
    # Simulate old cache existence
    old_root = tmp_path / "cache" / "bundled"
    old_skills = old_root / "skills"
    old_skills.mkdir(parents=True)
    (old_skills / "dummy.txt").write_text("old content", encoding="utf-8")
    
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    
    # Materializing should migrate old files to the new caches/bundled-resources path
    skills_dir = get_skills_dir()
    
    # New location should exist
    assert (skills_dir / "dummy.txt").exists()
    assert (skills_dir / "dummy.txt").read_text(encoding="utf-8") == "old content"
    
    # Old location should be removed
    assert not old_root.exists()
    assert not (tmp_path / "cache").exists()


def test_bundled_resources_migration_does_not_delete_unrelated_user_data(monkeypatch, tmp_path):
    # Simulate old cache existence
    old_root = tmp_path / "cache" / "bundled"
    old_skills = old_root / "skills"
    old_skills.mkdir(parents=True)
    (old_skills / "dummy.txt").write_text("old content", encoding="utf-8")
    
    # Create unrelated user file inside cache parent
    unrelated_file = tmp_path / "cache" / "unrelated-user-file.txt"
    unrelated_file.write_text("user private content", encoding="utf-8")
    
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    
    # Materializing should migrate old files to the new caches/bundled-resources path
    skills_dir = get_skills_dir()
    
    # New location should exist and contain the migrated dummy.txt
    assert (skills_dir / "dummy.txt").exists()
    assert (skills_dir / "dummy.txt").read_text(encoding="utf-8") == "old content"
    
    # Old location for bundled cache should be removed
    assert not old_root.exists()
    
    # The unrelated user file and the parent cache directory must still exist!
    assert unrelated_file.exists()
    assert unrelated_file.read_text(encoding="utf-8") == "user private content"
    assert (tmp_path / "cache").exists()

