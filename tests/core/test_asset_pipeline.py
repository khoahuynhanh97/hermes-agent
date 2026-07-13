import os
import json
from core.asset_pipeline import match_assets_to_script

def test_match_assets_to_script_success(tmp_path):
    script_file = tmp_path / "script.json"
    script_data = {"scenes": [{"scene_id": 1, "visual_keywords": ["tech"]}]}
    script_file.write_text(json.dumps(script_data), encoding="utf-8")
    
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    
    assert result is True
    mapping_file = asset_dir / "scene_mapping.json"
    assert mapping_file.exists()
    
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    assert "1" in mapping
    assert "mock_asset_1.mp4" in mapping["1"]

def test_match_assets_to_script_invalid_file(tmp_path):
    script_file = tmp_path / "nonexistent.json"
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    assert result is False

def test_match_assets_to_script_invalid_json(tmp_path):
    script_file = tmp_path / "script.json"
    script_file.write_text("invalid json", encoding="utf-8")
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    assert result is False

def test_match_assets_to_script_root_list(tmp_path):
    script_file = tmp_path / "script.json"
    script_file.write_text(json.dumps([{"scene_id": 1}]), encoding="utf-8")
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    assert result is False

def test_match_assets_to_script_missing_scene_id(tmp_path):
    script_file = tmp_path / "script.json"
    script_data = {"scenes": [{"visual_keywords": ["tech"]}, {"scene_id": 2}]}
    script_file.write_text(json.dumps(script_data), encoding="utf-8")
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    assert result is True
    mapping_file = asset_dir / "scene_mapping.json"
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    assert "null" not in mapping
    assert "2" in mapping
