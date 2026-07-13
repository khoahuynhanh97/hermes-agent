import os
import json
from core.asset_pipeline import match_assets_to_script

def test_match_assets_to_script(tmp_path):
    script_file = tmp_path / "script.json"
    script_data = {"scenes": [{"scene_id": 1, "visual_keywords": ["tech"]}]}
    script_file.write_text(json.dumps(script_data), encoding="utf-8")
    
    asset_dir = tmp_path / "assets"
    
    result = match_assets_to_script(str(script_file), str(asset_dir))
    
    assert result is True
    mapping_file = asset_dir / "scene_mapping.json"
    assert mapping_file.exists()
