"""UGREEN live run - Leg 5: 1 Gemini TTS (authorized) + timeline + concat draft + mix voiceover."""
import os, sys, subprocess
from pathlib import Path
ROOT = Path(r"D:\work\hermes-agent"); sys.path.insert(0, str(ROOT))

DB_PATH = r"D:\work\hermes-agent-data\db\video_factory.sqlite"
WORKSPACE = Path(r"D:\work\hermes-agent-data\workspaces\video-factory")
VIDEO_DIR = WORKSPACE / "videos"

_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            k = k.strip(); v = v.strip().strip("'").strip('"')
            if k and not os.environ.get(k):
                os.environ[k] = v

os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = DB_PATH
os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(WORKSPACE)
os.environ["GOOGLE_CLOUD_PROJECT"] = "gen-lang-client-0816609628"
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["TTS_MODEL"] = "gemini-3.1-flash-tts-preview"

OWNER = "ninak"
PROJECT_ID = "ugreen-nexode-robot-uno-live"
FFMPEG = os.environ.get("FFMPEG_PATH", r"D:\HermesTools\ffmpeg\bin\ffmpeg.exe")

# ---- 1. Gemini TTS (exactly 1, authorized) ----
from hermes.ports.text_to_speech import TTSRequest
from providers.vertex_tts_provider import GoogleVertexTTSProvider
audio_dir = WORKSPACE / "audio"
audio_dir.mkdir(parents=True, exist_ok=True)
STYLE = ("Speak Vietnamese with a bright, clear, youthful and energetic short-video narration style. "
         "Use lively pitch variation and expressive intonation. Keep articulation crisp and natural. "
         "Use a brisk pace without sounding rushed.")
provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
tts = provider.synthesize(TTSRequest(
    request_id="ugreen_voiceover",
    text="Củ sạc GaN nhỏ gọn với mặt robot độc đáo. Sạc nhanh, tiện lợi, đáng để trang bị.",
    voice="Zephyr", language="vi-VN", style_prompt=STYLE,
))
print("TTS success:", tts.success, "| wav:", tts.wav_path, "| err:", (tts.error_message or "")[:150])
if not tts.success:
    raise SystemExit(2)
wav = Path(tts.wav_path)
print("WAV exists:", wav.is_file(), "size:", wav.stat().st_size if wav.is_file() else 0)

# ---- 2. Timeline (3 clips) + link audio track ----
from hermes.adapters.sqlite.video_factory_repository import SQLiteVideoFactoryRepository
from hermes.application.video_factory_service import VideoFactoryService
from hermes.db import Database
from hermes.domain.video_factory import Timeline, TimelineClip
service = VideoFactoryService(SQLiteVideoFactoryRepository(Database(Path(DB_PATH))))
project = service.get_project(OWNER, PROJECT_ID)
scene_list = project.scene_plan.scenes
clips = tuple(TimelineClip(clip_id=f"clip_{s.scene_id}", order=i + 1, source_asset_id=s.scene_id,
                           duration_seconds=float(s.duration_seconds)) for i, s in enumerate(scene_list))
timeline = Timeline(timeline_id="timeline_live", project_id=PROJECT_ID, clips=clips,
                    audio_track_asset_id="ugreen_voiceover")
project = service.save_timeline(OWNER, PROJECT_ID, timeline)
print("timeline saved, status:", project.status.value, "clips:", len(project.timeline.clips))

# ---- 3. Concat 3 scene videos -> draft (deterministic, no provider) ----
scene_files = []
for s in scene_list:
    f = VIDEO_DIR / f"scene_{s.scene_id}.mp4"
    if f.is_file():
        scene_files.append(f)
    else:
        print("MISSING scene file:", f)
        raise SystemExit(2)
print("scene files:", [f.name for f in scene_files])

concat_file = VIDEO_DIR / "concat_live.txt"
concat_file.write_text("\n".join(f"file {f.as_posix()!r}" for f in scene_files), encoding="utf-8")
draft_out = VIDEO_DIR / "draft_video.mp4"
subprocess.run([FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
                "-an", str(draft_out)], capture_output=True, timeout=300)
print("draft:", draft_out, "size:", draft_out.stat().st_size if draft_out.exists() else 0)

service.update_timeline_status(OWNER, PROJECT_ID, "completed")
service.save_draft_video(OWNER, PROJECT_ID, "draft_live")
print("draft video asset saved")
print("PROJECT_ID:", PROJECT_ID)
