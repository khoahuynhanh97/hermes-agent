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
