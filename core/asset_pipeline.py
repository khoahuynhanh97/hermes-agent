import os
import json

def match_assets_to_script(script_json_path: str, output_asset_dir: str) -> bool:
    """Matches script visual keywords to local or remote assets."""
    os.makedirs(output_asset_dir, exist_ok=True)
    
    try:
        with open(script_json_path, "r", encoding="utf-8") as f:
            script = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return False
        
    if not isinstance(script, dict):
        script = {}
        
    mapping = {}
    for scene in script.get("scenes", []):
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        if sid is None:
            continue
        # In reality, perform matching logic. Mocking path:
        mapping[sid] = os.path.join(output_asset_dir, f"mock_asset_{sid}.mp4")
        
    mapping_file = os.path.join(output_asset_dir, "scene_mapping.json")
    with open(mapping_file, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2)
        
    return True
