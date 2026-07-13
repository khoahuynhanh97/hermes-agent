import os
import json

def publish_recycled_video(project_dir: str, platform: str) -> bool:
    """Publishes the finalized video to the target platform."""
    video_path = os.path.join(project_dir, "final_video.mp4")
    script_path = os.path.join(project_dir, "script.json")
    
    if not os.path.exists(video_path) or not os.path.exists(script_path):
        return False
        
    with open(script_path, "r", encoding="utf-8") as f:
        try:
            script = json.load(f)
        except json.JSONDecodeError:
            return False
        
    caption = script.get("caption", "")
    hashtags = script.get("hashtags", [])
    
    # In reality, API calls to TikTok/Youtube would go here
    print(f"Mock publishing to {platform}: {video_path}")
    print(f"Caption: {caption} {' '.join(hashtags)}")
    
    return True
