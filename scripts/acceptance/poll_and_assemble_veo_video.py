"""
scripts/poll_and_assemble_veo_video.py — Poll Google Cloud Veo 3.1 Operations and Assemble AI Video
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from hermes.integrations.providers.vertex_video_provider import GoogleVertexVideoProvider

ffmpeg = os.environ.get("FFMPEG_PATH", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe")
src_dir = Path(r"C:\Users\ninak\Downloads\sac-ugreen")
veo_out_dir = src_dir / "veo_ai_scenes"
veo_out_dir.mkdir(parents=True, exist_ok=True)

operations = [
    ("scene_1", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/e6f6655e-a693-4f0f-a551-c2d5ff68a990"),
    ("scene_2", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/14be6be5-f932-4264-bb75-625a392c8890"),
    ("scene_3", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/6d51c180-e2bf-4cae-80ed-e545065dd1d8"),
    ("scene_4", "projects/gen-lang-client-0816609628/locations/us-central1/publishers/google/models/veo-3.1-fast-generate-001/operations/2cb45989-e47e-4835-ac75-bf012b16073e")
]

def main():
    print("=== POLLING GOOGLE CLOUD VERTEX VEO 3.1 AI VIDEO GENERATION ===")
    provider = GoogleVertexVideoProvider()

    completed_files = {}

    for attempt in range(1, 15):
        print(f"\n--- [Attempt #{attempt}] Polling Google Cloud Operations ---")
        all_done = True
        
        for sc_id, op_id in operations:
            if sc_id in completed_files:
                continue
            
            res = provider.check_status(op_id)
            if res.success and res.video_path:
                print(f"  [SUCCESS] [{sc_id}] FINISHED! Downloaded: {res.video_path}")
                completed_files[sc_id] = res.video_path
            elif not res.success and "error" in res.metadata:
                print(f"  [ERROR] [{sc_id}] Error: {res.error_message}")
            else:
                print(f"  [PENDING] [{sc_id}] Rendering on Google GPU cluster...")
                all_done = False

        if len(completed_files) == len(operations):
            print("\nALL 4 GOOGLE VEO 3.1 AI SCENES HAVE FINISHED RENDERING!")
            break

            
        if not all_done:
            time.sleep(15)

    if len(completed_files) > 0:
        print("\n=== CONCATENATING DOWNLOADED AI VIDEO CLIPS ===")
        concat_list = veo_out_dir / "concat_veo.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for sc_id, op_id in operations:
                if sc_id in completed_files:
                    f.write(f"file '{Path(completed_files[sc_id]).resolve()}'\n")

        final_ai_video = src_dir / "ugreen_robot_uno_30s_veo_ai.mp4"
        cmd = [
            ffmpeg, "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(final_ai_video)
        ]
        subprocess.run(cmd, check=True)
        print(f"Final AI Motion Video Saved To: {final_ai_video} ({final_ai_video.stat().st_size} bytes)")
    else:
        print("\nOperations are still processing on Google Cloud servers. Check again shortly.")

if __name__ == "__main__":
    main()
