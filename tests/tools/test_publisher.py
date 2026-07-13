import json
from tools.publisher import publish_recycled_video

def test_publish_recycled_video(tmp_path):
    project_dir = tmp_path / "project_x"
    project_dir.mkdir()
    
    script_data = {"caption": "Test video", "hashtags": ["#test"]}
    with open(project_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f)
        
    (project_dir / "final_video.mp4").write_text("mock video", encoding="utf-8")
    
    result = publish_recycled_video(str(project_dir), "tiktok")
    
    assert result is True

def test_publish_recycled_video_missing_files(tmp_path):
    project_dir = tmp_path / "project_x"
    project_dir.mkdir()
    
    # Missing both
    assert publish_recycled_video(str(project_dir), "tiktok") is False
    
    # Missing video
    with open(project_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump({}, f)
    assert publish_recycled_video(str(project_dir), "tiktok") is False
    
    # Missing script (but video exists)
    (project_dir / "script.json").unlink()
    (project_dir / "final_video.mp4").write_text("mock video", encoding="utf-8")
    assert publish_recycled_video(str(project_dir), "tiktok") is False

def test_publish_recycled_video_malformed_json(tmp_path):
    project_dir = tmp_path / "project_x"
    project_dir.mkdir()
    
    (project_dir / "script.json").write_text("invalid json", encoding="utf-8")
    (project_dir / "final_video.mp4").write_text("mock video", encoding="utf-8")
    
    assert publish_recycled_video(str(project_dir), "tiktok") is False
