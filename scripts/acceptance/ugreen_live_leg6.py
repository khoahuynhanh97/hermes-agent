"""UGREEN live run - Leg 6: final approve (authorized), export + voiceover mix,
verify final MP4 (video + audio streams), ready_to_publish."""
import os, sys, subprocess
from pathlib import Path
ROOT = Path(r"D:\work\hermes-agent"); sys.path.insert(0, str(ROOT))

DB_PATH = r"D:\work\hermes-agent-data\db\video_factory.sqlite"
WORKSPACE = Path(r"D:\work\hermes-agent-data\workspaces\video-factory")
VIDEO_DIR = WORKSPACE / "videos"
FFMPEG = os.environ.get("FFMPEG_PATH", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe")
FFPROBE = r"D:\HermesTools\ffmpeg\bin\ffprobe.exe"

os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = DB_PATH
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)
OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"

from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database

service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(DB_PATH))))
project = service.get_project(OWNER, PROJECT_ID)
if project.final_approval.value != "approved":
    project = service.approve_final_video(OWNER, PROJECT_ID, "approved via live run")
print("final_approval:", project.final_approval.value)

draft = VIDEO_DIR / "draft_video.mp4"
wav = WORKSPACE / "audio" / "ugreen_voiceover.wav"
assert draft.is_file(), "draft missing"
assert wav.is_file(), "wav missing"

# final MP4 with voiceover mixed (video + audio)
final = VIDEO_DIR / "ugreen-nexode-robot-uno-final.mp4"
r = subprocess.run([FFMPEG, "-y", "-i", str(draft), "-i", str(wav),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "23",
                    "-c:a", "aac", "-b:a", "128k", "-map", "0:v:0", "-map", "1:a:0", "-shortest",
                    str(final)], capture_output=True, timeout=300)
print("final mix returncode:", r.returncode, "err:", r.stderr.decode()[-200:] if r.returncode else "")
assert final.is_file() and final.stat().st_size > 0
print("final:", final, "size:", final.stat().st_size)

# domain: save final export -> ready_to_publish
service.save_final_export(OWNER, PROJECT_ID, "final_live_asset")
project = service.get_project(OWNER, PROJECT_ID)
print("status:", project.status.value, "| final_asset:", project.final_video_asset_id)

# ffprobe streams
print("--- video stream ---")
subprocess.run([FFPROBE, "-v", "error", "-select_streams", "v:0", "-show_entries",
                "stream=codec_type,codec_name,width,height", "-of", "default=noprint_wrappers=1", str(final)])
print("--- audio stream ---")
subprocess.run([FFPROBE, "-v", "error", "-select_streams", "a:0", "-show_entries",
                "stream=codec_type,codec_name,sample_rate,channels", "-of", "default=noprint_wrappers=1", str(final)])
print("--- duration ---")
subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1", str(final)])
print("PROJECT_ID:", PROJECT_ID)
print("FINAL:", final)
