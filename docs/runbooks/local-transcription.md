# Local Audio Transcription

Hermes uses `faster-whisper==1.2.1` with the multilingual `base` model on CPU
`int8`. The model cache is stored at `D:\HermesData\models\whisper`.

The complete FFmpeg 8.1.2 Windows distribution is installed under
`D:\HermesTools\ffmpeg\bin`. Both `ffmpeg.exe` and `ffprobe.exe` are required by
`yt-dlp`; the single executable shipped by `imageio-ffmpeg` is only a fallback.

Relevant `.env` values:

```dotenv
FFMPEG_PATH=D:\HermesTools\ffmpeg\bin\ffmpeg.exe
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
WHISPER_COMPUTE_TYPE=int8
WHISPER_MODEL_DIR=D:\HermesData\models\whisper
YTDLP_IMPERSONATE_TARGET=Chrome-131:Android-14
```

`curl-cffi` supplies the browser fingerprint used by `yt-dlp` for TikTok's public
JavaScript challenge. TikTok audio uses the `download` format first because some
high-bitrate URLs are video-only even when the extractor labels them as AAC.

## Verify

```powershell
cd D:\work\hermes-agent
& D:\HermesTools\ffmpeg\bin\ffmpeg.exe -version
& D:\HermesTools\ffmpeg\bin\ffprobe.exe -version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m unittest tests.hermes.test_video_fetcher -v
```

The first transcription process loads the cached model and is slower than later
jobs in the same worker process. A missing backend or inaccessible source returns
`needs_source`; metadata alone never becomes reusable knowledge.
