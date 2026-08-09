"""Tests for the shared Telegram learning attachment normalizer."""

from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from telegram_bot import extract_learning_attachment, extract_video_attachment


def run_tests():
    video = SimpleNamespace(video=SimpleNamespace(file_id="v1", file_unique_id="uv1"), audio=None, voice=None, photo=None, document=None)
    audio = SimpleNamespace(video=None, audio=SimpleNamespace(file_id="a1", file_unique_id="ua1"), voice=None, photo=None, document=None)
    voice = SimpleNamespace(video=None, audio=None, voice=SimpleNamespace(file_id="vo1", file_unique_id="uvo1"), photo=None, document=None)
    photo = SimpleNamespace(video=None, audio=None, voice=None, photo=[SimpleNamespace(file_id="p1", file_unique_id="up1")], document=None)
    document = SimpleNamespace(
        video=None,
        audio=None,
        voice=None,
        photo=None,
        document=SimpleNamespace(file_id="d1", file_unique_id="ud1", file_name="notes.md", mime_type="text/markdown"),
    )

    assert extract_learning_attachment(video)["source"] == "video"
    assert extract_learning_attachment(audio)["source"] == "audio"
    assert extract_learning_attachment(voice)["source"] == "voice"
    assert extract_learning_attachment(photo)["source"] == "photo"
    assert extract_learning_attachment(document)["source"] == "document"
    assert extract_video_attachment(audio) is None
    assert extract_video_attachment(video)["source"] == "video"
    print("telegram attachment normalization tests: PASS")


if __name__ == "__main__":
    run_tests()
