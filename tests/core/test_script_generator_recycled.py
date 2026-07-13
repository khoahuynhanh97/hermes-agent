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
