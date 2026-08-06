import os
import wave
from pathlib import Path
import pytest

from hermes.ports.text_to_speech import TTSRequest
from providers.tts_provider_factory import FakeTTSProvider, get_tts_provider


def test_fake_tts_provider_requires_allow_flag(tmp_path, monkeypatch):
    monkeypatch.delenv("HERMES_ALLOW_FAKE_PROVIDERS", raising=False)
    with pytest.raises(ValueError, match="HERMES_ALLOW_FAKE_PROVIDERS is not set"):
        FakeTTSProvider(output_dir=str(tmp_path))


def test_fake_tts_provider_synthesizes_silence_wav(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    provider = FakeTTSProvider(output_dir=str(tmp_path))
    result = provider.synthesize(TTSRequest(request_id="test_req", text="Hello world", voice="Zephyr"))

    assert result.success is True
    assert result.provider == "fake"
    assert Path(result.wav_path).is_file()

    with wave.open(result.wav_path, "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 24000


def test_get_tts_provider_factory_selects_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER", "fake")
    monkeypatch.setenv("HERMES_ALLOW_FAKE_PROVIDERS", "1")
    provider = get_tts_provider(output_dir=str(tmp_path))
    assert isinstance(provider, FakeTTSProvider)
