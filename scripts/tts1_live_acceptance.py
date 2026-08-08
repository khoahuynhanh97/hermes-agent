"""TTS1 live acceptance: ONE Vertex Gemini TTS generation + FFmpeg mix.

Authorized: voice Zephyr, vi-VN, exactly one live generation.
"""
import os, sys
from pathlib import Path
ROOT = Path(r'D:\work\hermes-agent'); sys.path.insert(0, str(ROOT))
env = ROOT / '.env'
for line in env.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, _, v = line.partition('=')
        k = k.strip(); v = v.strip().strip("'").strip('"')
        if k and not os.environ.get(k):
            os.environ[k] = v

os.environ['GOOGLE_CLOUD_PROJECT'] = 'gen-lang-client-0816609628'
os.environ['GOOGLE_CLOUD_LOCATION'] = 'global'
os.environ['TTS_MODEL'] = 'gemini-3.1-flash-tts-preview'
WS = Path(r'D:\work\hermes-agent-data\acceptance\vf-e2e\workspace')
os.environ['HERMES_TTS_OUTPUT_DIR'] = str(WS / 'audio')
(WS / 'audio').mkdir(parents=True, exist_ok=True)

from hermes.ports.text_to_speech import TTSRequest
from providers.vertex_tts_provider import GoogleVertexTTSProvider

STYLE = ("Speak Vietnamese with a bright, clear, youthful and energetic short-video narration style. "
         "Use lively pitch variation and expressive intonation. Keep articulation crisp and natural. "
         "Use a brisk pace without sounding rushed. Avoid excessive breathiness, heaviness, or overly theatrical delivery.")

provider = GoogleVertexTTSProvider(output_dir=str(WS / 'audio'))
res = provider.synthesize(TTSRequest(
    request_id='tts1_acceptance', text='Xin chào! Hôm nay tôi sẽ giới thiệu bình nước màu xanh này.',
    voice='Zephyr', language='vi-VN', style_prompt=STYLE,
))
print('success:', res.success)
print('error:', (res.error_message or '')[:300])
print('wav:', res.wav_path)
if res.wav_path:
    p = Path(res.wav_path)
    print('wav exists:', p.exists(), 'size:', p.stat().st_size)
    import wave
    with wave.open(str(p)) as w:
        print('channels:', w.getnchannels(), 'rate:', w.getframerate(), 'width:', w.getsampwidth(), 'frames:', w.getnframes())

    # mix into existing draft video
    from hermes.adapters.local.desktop_runtime import DesktopRuntime
    ff = os.environ.get('FFMPEG_PATH', 'D:\\HermesTools\\ffmpeg\\bin\\ffmpeg.exe')
    runtime = DesktopRuntime()
    runtime.ffmpeg.ffmpeg_path = ff
    draft = WS / 'videos' / 'draft_video.mp4'
    print('draft exists:', draft.is_file())
    if draft.is_file():
        out = WS / 'videos' / 'final_video_with_voiceover.mp4'
        r = runtime.ffmpeg.render_with_audio(str(draft), str(p), str(out))
        print('mix ok:', r.ok, '| msg:', (r.message or '')[:100])
        if r.ok and out.exists():
            print('final mp4:', out, 'size:', out.stat().st_size)
