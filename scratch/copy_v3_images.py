import os
import shutil

def copy_v3_images():
    brain_dir = r"C:\Users\TeamSol\.gemini\antigravity\brain\7c33aa6b-94ec-4d67-8ea2-9489796d3dae"
    dest_dir = r"C:\Users\TeamSol\Downloads\TIKTOK\xe_may"
    
    files = os.listdir(brain_dir)
    for f in files:
        if f.startswith("storyboard_scene_") and "v3" in f and f.endswith(".png"):
            src_path = os.path.join(brain_dir, f)
            dest_path = os.path.join(dest_dir, f)
            shutil.copy(src_path, dest_path)
            print(f"Copied {f} to {dest_dir}")

if __name__ == "__main__":
    copy_v3_images()
