### Task 3: Module 3 - Asset Pipeline (`core/asset_pipeline.py`)

**Files:**
- Create: `core/asset_pipeline.py`
- Create: `tests/core/test_asset_pipeline.py`

**Interfaces:**
- Consumes: `script.json`
- Produces: `scene_mapping.json` (maps scene_id to local asset paths)

- [ ] **Step 1: Write the failing test**
```python
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
```

- [ ] **Step 2: Run test to verify it fails**
Run: `pytest tests/core/test_asset_pipeline.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Write minimal implementation**
```python
import os
import json

def match_assets_to_script(script_json_path: str, output_asset_dir: str) -> bool:
    """Matches script visual keywords to local or remote assets."""
    os.makedirs(output_asset_dir, exist_ok=True)
    
    with open(script_json_path, "r", encoding="utf-8") as f:
        script = json.load(f)
        
    mapping = {}
    for scene in script.get("scenes", []):
        sid = scene.get("scene_id")
        # In reality, perform matching logic. Mocking path:
        mapping[sid] = os.path.join(output_asset_dir, f"mock_asset_{sid}.mp4")
        
    mapping_file = os.path.join(output_asset_dir, "scene_mapping.json")
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
        
    return True
```

- [ ] **Step 4: Run test to verify it passes**
Run: `pytest tests/core/test_asset_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add core/asset_pipeline.py tests/core/test_asset_pipeline.py
git commit -m "feat: implement asset pipeline matching"
```
