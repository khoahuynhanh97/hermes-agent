import os
import json
from tools.publisher import publish_recycled_video

def test_publish_recycled_video(tmp_path):
    project_dir = tmp_path / "project_x"
    project_dir.mkdir()
    
    script_data = {"caption": "Test video", "hashtags": ["#test"]}
    with open(project_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f)
        
    (project_dir / "final_video.mp4").write_text("mock video")
    
    result = publish_recycled_video(str(project_dir), "tiktok")
    
    assert result is True
