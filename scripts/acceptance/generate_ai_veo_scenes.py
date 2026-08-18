"""
scripts/generate_ai_veo_scenes.py — Generate Real AI Motion Video Clips via Google Cloud Vertex Veo 3.1
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from hermes.integrations.providers.vertex_video_provider import GoogleVertexVideoProvider
from hermes.ports.video_generation import VideoGenerationRequest

def main():
    print("=== INITIATING REAL AI VIDEO GENERATION VIA GOOGLE CLOUD VERTEX VEO 3.1 ===")
    
    provider = GoogleVertexVideoProvider()
    print(f"  GCP Project : {provider.project}")
    print(f"  GCP Location: {provider.location}")
    print(f"  Veo AI Model: {provider.model}")

    scene_prompts = [
        ("scene_1", "3D animation of a cute white UGREEN Robot UNO 65W GaN charger standing on a modern desk, glowing blue LED smile face expression, smooth 9:16 vertical camera pan"),
        ("scene_2", "Dynamic close-up video of UGREEN Nexode Robot UNO charger showing 65W fast power surge with futuristic blue lighting energy particles, vertical 9:16"),
        ("scene_3", "Macro high tech video of UGREEN Robot UNO LED screen changing expressions showing charging battery level status, vertical 9:16"),
        ("scene_4", "Cinematic product shot of UGREEN Robot UNO charger next to an iPhone 16 charging rapidly, glowing LED smile face, vertical 9:16")
    ]

    active_operations = []

    for sc_id, prompt_text in scene_prompts:
        print(f"\nSubmitting Scene [{sc_id}] to Google Vertex Veo 3.1 API...")
        print(f"  Prompt: {prompt_text}")
        
        req = VideoGenerationRequest(
            request_id=f"veo_scene_{sc_id}",
            owner_user_id="ninak",
            scene_id=sc_id,
            prompt=prompt_text,
            duration_seconds=5.0,
            aspect_ratio="9:16"
        )
        res = provider.generate(req)
        print(f"  -> Result Success: {res.success}")
        if res.success:
            print(f"  -> Google Operation ID: {res.provider_operation_id}")
            active_operations.append((sc_id, res.provider_operation_id))
        else:
            print(f"  -> Error: {res.error_message}")

    print(f"\n=== SUBMITTED {len(active_operations)} AI SCENE GENERATION JOBS TO GOOGLE CLOUD ===")
    print("Google Cloud GPU servers are now processing the AI video scenes.")

if __name__ == "__main__":
    main()
