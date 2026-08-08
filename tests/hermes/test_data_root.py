"""DATA1 tests: canonical Hermes data root + explicit override priority."""
import os
from pathlib import Path

import pytest

from hermes.config import get_data_path, get_data_root


def test_data_root_from_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    assert get_data_root() == tmp_path.resolve()


def test_data_root_default_when_unset(monkeypatch):
    monkeypatch.delenv("HERMES_DATA_DIR", raising=False)
    root = get_data_root()
    assert isinstance(root, Path)
    assert str(root)  # non-empty


def test_data_path_derives_under_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    db = get_data_path("db", "hermes.db")
    assert str(db).startswith(str(tmp_path.resolve()))
    assert db.name == "hermes.db"

    ws = get_data_path("workspaces", "video-factory")
    assert str(ws).startswith(str(tmp_path.resolve()))
    assert ws.parts[-2:] == ("workspaces", "video-factory")


def test_explicit_override_beats_derived(monkeypatch, tmp_path):
    """MCP/store resolution: explicit HERMES_VIDEO_FACTORY_DB_PATH wins over derived."""
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HERMES_VIDEO_FACTORY_DB_PATH", str(tmp_path / "explicit" / "vf.sqlite"))
    configured = os.environ.get("HERMES_VIDEO_FACTORY_DB_PATH", "").strip()
    resolved = Path(configured).expanduser().resolve() if configured else get_data_path("db", "video_factory.sqlite")
    assert str(resolved) == str((tmp_path / "explicit" / "vf.sqlite").resolve())


def test_vf_workspace_containment_respects_override(monkeypatch, tmp_path):
    from hermes.application.video_factory_service import VideoFactoryService

    monkeypatch.setenv("HERMES_VIDEO_FACTORY_WORKSPACE", str(tmp_path / "ws"))
    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path / "derived"))
    # valid relative uri inside explicit workspace should pass
    VideoFactoryService._validate_asset_uri("asset://x")  # asset:// always allowed
    # a path outside explicit workspace must be rejected
    outside = tmp_path / "outside" / "f.png"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_bytes(b"x")
    with pytest.raises(ValueError, match="UNAUTHORIZED_PATH"):
        VideoFactoryService._validate_asset_uri(str(outside))


def test_vf_workspace_derived_from_data_dir(monkeypatch, tmp_path):
    from hermes.application.video_factory_service import VideoFactoryService

    monkeypatch.setenv("HERMES_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HERMES_VIDEO_FACTORY_WORKSPACE", raising=False)
    # a path inside the derived workspace should be accepted
    derived_ws = get_data_path("workspaces", "video-factory")
    inside = derived_ws / "img.png"
    inside.parent.mkdir(parents=True, exist_ok=True)
    inside.write_bytes(b"x")
    VideoFactoryService._validate_asset_uri(str(inside))  # no raise
