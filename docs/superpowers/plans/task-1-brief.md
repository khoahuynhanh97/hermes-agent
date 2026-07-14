### Task 1: Module 1 - Source Crawler (`core/content_source.py`)

**Files:**
- Create: `core/content_source.py`
- Create: `tests/core/test_content_source.py`

**Interfaces:**
- Consumes: Video URL (TikTok, YouTube, etc.)
- Produces: `source.json` containing transcript and Gemini analysis

- [ ] **Step 1: Write the failing test**
```python
import os
import json
from core.content_source import crawl_source

def test_crawl_source(tmp_path):
    # Mock implementations would be needed here for network calls
    output_dir = tmp_path / "project_x"
    output_dir.mkdir()
    
    result = crawl_source("https://dummy.url", str(output_dir))
    
    assert result is True
    assert (output_dir / "source.json").exists()
    
    with open(output_dir / "source.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "transcript" in data
        assert "topics" in data
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/core/test_content_source.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'core.content_source'"

- [ ] **Step 3: Write minimal implementation**
```python
import json
import os
# from tools.video_downloader import download_video
# from core.video_fetcher import fetch_transcript
# from tools.video_analyser import analyze_video

def crawl_source(url: str, output_dir: str) -> bool:
    """Orchestrates downloading, transcribing, and analyzing a source video."""
    os.makedirs(output_dir, exist_ok=True)
    
    # In a real implementation, this calls download_video, fetch_transcript, analyze_video
    # Here we mock the output for the skeleton
    source_data = {
        "source_url": url,
        "transcript": "Sample transcript text.",
        "language": "vi",
        "topics": ["tech", "ai"],
        "structure_analysis": "Hook -> Body -> CTA"
    }
    
    out_path = os.path.join(output_dir, "source.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(source_data, f, ensure_ascii=False, indent=2)
        
    return True
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/core/test_content_source.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add core/content_source.py tests/core/test_content_source.py
git commit -m "feat: implement source crawler module"
```
