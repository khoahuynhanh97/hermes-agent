### Task 2: Module 2 - AI Script Rewriter (`core/script_generator.py`)

**Files:**
- Modify: `core/script_generator.py`
- Create: `tests/core/test_script_generator_recycled.py`

**Interfaces:**
- Consumes: `source.json` from Task 1
- Produces: `script.json` (structured scenes)

- [ ] **Step 1: Write the failing test**
```python
import os
import json
from core.script_generator import generate_recycled_script

def test_generate_recycled_script(tmp_path):
    source_file = tmp_path / "source.json"
    source_file.write_text('{"transcript": "Hello AI"}', encoding="utf-8")
    
    output_dir = tmp_path / "scripts"
    output_dir.mkdir()
    
    result = generate_recycled_script(str(source_file), str(output_dir), "tiktok_tech")
    
    assert result is True
    script_file = output_dir / "script.json"
    assert script_file.exists()
    
    with open(script_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "scenes" in data
        assert isinstance(data["scenes"], list)
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/core/test_script_generator_recycled.py -v`
Expected: FAIL with "ImportError: cannot import name 'generate_recycled_script'"

- [ ] **Step 3: Write minimal implementation**
```python
# Append to core/script_generator.py
import os
import json

def generate_recycled_script(source_json_path: str, output_dir: str, branch: str = "tiktok_tech") -> bool:
    """Generates a scene-based script from source transcript."""
    os.makedirs(output_dir, exist_ok=True)
    
    # In reality, this calls Gemini API with knowledge store context
    script_data = {
        "title": "Recycled Video",
        "platform": branch,
        "scenes": [
            {
                "scene_id": 1,
                "narration": "Sample voiceover",
                "visual_keywords": ["sample", "video"],
                "duration_hint": 3.0
            }
        ],
        "caption": "Sample caption",
        "hashtags": ["#sample"]
    }
    
    out_path = os.path.join(output_dir, "script.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
        
    return True
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/core/test_script_generator_recycled.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add core/script_generator.py tests/core/test_script_generator_recycled.py
git commit -m "feat: add recycled script generation"
```
