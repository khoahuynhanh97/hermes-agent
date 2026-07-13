import os
import json
from editor.video_editor import build_content_video

def test_build_content_video(tmp_path):
    project_dir = tmp_path / "project_x"
    project_dir.mkdir()
    
    script_data = {"scenes": [{"scene_id": 1, "duration_hint": 3.0}]}
    mapping_data = {"1": "mock_asset_1.mp4"}
    
    with open(project_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f)
        
    with open(project_dir / "scene_mapping.json", "w", encoding="utf-8") as f:
        json.dump(mapping_data, f)
        
    result = build_content_video(str(project_dir))
    
    assert result is True
    assert (project_dir / "final_video.mp4").exists()
