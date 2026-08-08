"""TTS1 tests: Vertex TTS provider + FFmpeg audio mix (no paid calls)."""
import base64
import os
import wave
from pathlib import Path
from unittest import mock

import pytest

from hermes.ports.text_to_speech import TTSRequest
from providers.vertex_tts_provider import GoogleVertexTTSProvider


@pytest.fixture(autouse=True)
def _no_live_vertex(monkeypatch):
    """Block any real Vertex call from tests. Tests must mock HTTP/auth explicitly."""
    def _block(*a, **k):
        raise RuntimeError("live Vertex call blocked: tests must mock HTTP/auth")
    monkeypatch.setattr("providers.vertex_tts_provider.requests.post", _block)
    monkeypatch.setattr("providers.vertex_tts_provider.get_access_token", _block)


@pytest.fixture
def audio_dir(tmp_path):
    return tmp_path / "audio"


def _pcm_bytes():
    # 1 second of 24kHz 16-bit mono silence
    frames = b"\x00\x00" * 24000
    return frames


def test_request_mapping_and_wav_output(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0816609628")
    monkeypatch.setattr("providers.vertex_tts_provider.get_access_token", lambda: "tok")

    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return mock.Mock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{
                "inlineData": {"mimeType": "audio/pcm", "data": base64.b64encode(_pcm_bytes()).decode()},
            }]}}]
        })

    with mock.patch("providers.vertex_tts_provider.requests.post", side_effect=fake_post):
        res = provider.synthesize(TTSRequest(
            request_id="tts_test", text="Xin chao",
            voice="Zephyr", language="vi-VN", style_prompt="energetic",
        ))

    assert res.success is True
    assert res.wav_path and Path(res.wav_path).exists()
    assert res.voice == "Zephyr"
    # request mapping
    sc = captured["json"]["generationConfig"]["speechConfig"]
    assert sc["languageCode"] == "vi-VN"
    assert sc["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Zephyr"
    assert "gemini-3.1-flash-tts-preview" in captured["url"]
    # style prompt combined into contents text, no systemInstruction
    contents_text = captured["json"]["contents"][0]["parts"][0]["text"]
    assert "energetic" in contents_text
    assert "Xin chao" in contents_text
    assert "Say the following:" in contents_text
    assert "systemInstruction" not in captured["json"]

    # WAV is 24kHz/16-bit/mono
    with wave.open(res.wav_path) as w:
        assert w.getframerate() == 24000
        assert w.getsampwidth() == 2
        assert w.getnchannels() == 1
        assert w.getnframes() == 24000


def test_pcm_to_wav_write(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    out = audio_dir / "x.wav"
    provider._write_wav("audio/pcm", _pcm_bytes(), out)
    assert out.exists() and out.stat().st_size > 0
    with wave.open(str(out)) as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2


def test_build_text_empty_style(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    # empty style -> minimal instruction + text, no crash, no default style
    from providers.vertex_tts_provider import GoogleVertexTTSProvider as P
    text = P._build_text(TTSRequest(request_id="r", text="Xin chao", voice="Zephyr", style_prompt=""))
    assert text == "Say the following:\nXin chao"
    assert "bright" not in text  # no provider-injected creative default


def test_build_text_with_style(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    from providers.vertex_tts_provider import GoogleVertexTTSProvider as P
    text = P._build_text(TTSRequest(
        request_id="r", text="Xin chao", voice="Zephyr",
        style_prompt="Speak energetically",
    ))
    assert text == "Speak energetically\n\nSay the following:\nXin chao"


def test_wav_passthrough(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    out = audio_dir / "x.wav"
    provider._write_wav("audio/wav", b"\x52\x49\x46\x46", out)
    assert out.read_bytes() == b"\x52\x49\x46\x46"


def test_workspace_containment(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setattr("providers.vertex_tts_provider.get_access_token", lambda: "tok")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))
    # no real API call: mocked; assert filename sanitization keeps output inside audio_dir
    def fake_post(url, headers=None, json=None, timeout=None):
        return mock.Mock(status_code=200, json=lambda: {
            "candidates": [{"content": {"parts": [{
                "inlineData": {"mimeType": "audio/pcm", "data": base64.b64encode(_pcm_bytes()).decode()},
            }]}}]
        })
    with mock.patch("providers.vertex_tts_provider.requests.post", side_effect=fake_post):
        res = provider.synthesize(TTSRequest(request_id="../../escape", text="x", voice="Zephyr"))
    assert res.success is True
    if res.wav_path:
        assert str(Path(res.wav_path).resolve()).startswith(str(audio_dir.resolve()))


def test_provider_error_normalized(audio_dir, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "proj")
    monkeypatch.setattr("providers.vertex_tts_provider.get_access_token", lambda: "tok")
    provider = GoogleVertexTTSProvider(output_dir=str(audio_dir))

    with mock.patch(
        "providers.vertex_tts_provider.requests.post",
        return_value=mock.Mock(status_code=400, json=lambda: {"error": {"message": "bad voice"}}),
    ):
        res = provider.synthesize(TTSRequest(request_id="r", text="x", voice="Nope"))
    assert res.success is False
    assert "400" in res.error_message
    assert "bad voice" in res.error_message


def test_render_with_audio_mix(tmp_path, monkeypatch):
    """FFmpeg render_with_audio: mocked, verifies command construction."""
    from hermes.adapters.local.desktop_runtime import DesktopRuntime
    from hermes.domain.results import Result

    runtime = DesktopRuntime()
    called = {}

    def fake_run(cmd, capture_output=None, text=None, timeout=None):
        called["cmd"] = cmd
        m = mock.Mock()
        m.returncode = 0
        m.stderr = ""
        return m

    with mock.patch("subprocess.run", side_effect=fake_run):
        res = runtime.ffmpeg.render_with_audio("/v/a.mp4", "/a/b.wav", "/v/out.mp4")

    assert res.ok is True
    cmd = called["cmd"]
    assert "-i" in cmd and "/v/a.mp4" in cmd and "/a/b.wav" in cmd
    assert "-map" in cmd
    assert "1:a:0" in cmd  # audio stream mapped
    assert "-shortest" in cmd


# UI/API: generation is explicit only
def test_tts_endpoint_requires_text(tmp_path):
    import asyncio
    import os
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from video_factory_api import build_routes

    os.environ["HERMES_VIDEO_FACTORY_DB_PATH"] = str(tmp_path / "t.db")
    os.environ["HERMES_VIDEO_FACTORY_WORKSPACE"] = str(tmp_path / "ws")
    app = web.Application()
    app.add_routes(build_routes())

    async def flow(c):
        async with c.post("/api/vf/projects?owner_user_id=web_owner", json={"project_id": "t1"}) as r:
            assert r.status == 201
        # missing text -> 400, no generation
        async with c.post("/api/vf/projects/t1/tts?owner_user_id=web_owner", json={}) as r:
            assert r.status == 400

    async def runner():
        s = TestServer(app)
        await s.start_server()
        c = TestClient(s)
        await c.start_server()
        try:
            await flow(c)
        finally:
            await c.close()
            await s.close()

    asyncio.run(runner())
