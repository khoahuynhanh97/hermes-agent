### Task 5: Module 5 - Publisher (`tools/publisher.py`)

**Files:**
- Create: `tools/publisher.py`
- Create: `tests/tools/test_publisher.py`

**Interfaces:**
- Consumes: `project_dir` containing `final_video.mp4` and `script.json`
- Produces: Publish status (bool)

- [ ] **Step 1: Write the failing test**
```python
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/tools/test_publisher.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'tools.publisher'"

- [ ] **Step 3: Write minimal implementation**
```python
import os
import json

def publish_recycled_video(project_dir: str, platform: str) -> bool:
    """Publishes the finalized video to the target platform."""
    video_path = os.path.join(project_dir, "final_video.mp4")
    script_path = os.path.join(project_dir, "script.json")
    
    if not os.path.exists(video_path) or not os.path.exists(script_path):
        return False
        
    with open(script_path, "r", encoding="utf-8") as f:
        script = json.load(f)
        
    caption = script.get("caption", "")
    hashtags = script.get("hashtags", [])
    
    # In reality, API calls to TikTok/Youtube would go here
    print(f"Mock publishing to {platform}: {video_path}")
    print(f"Caption: {caption} {' '.join(hashtags)}")
    
    return True
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/tools/test_publisher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add tools/publisher.py tests/tools/test_publisher.py
git commit -m "feat: implement mock publisher module"
```
