"""Tests for Video Factory PyAV composer module."""
from __future__ import annotations

import tempfile
from fractions import Fraction
from pathlib import Path

import av
import pytest

from hermes_personal.integrations.video_factory.composer import (
    concatenate_videos,
    get_video_info,
    compute_file_sha256,
)


def _create_synthetic_video(file_path: Path, width: int = 720, height: int = 1280, fps: int = 24, duration_frames: int = 24, with_audio: bool = False) -> Path:
    container = av.open(str(file_path), mode="w", format="mp4")
    stream = container.add_stream("libx264", rate=fps)
    stream.width = width
    stream.height = height
    stream.pix_fmt = "yuv420p"
    audio_stream = None
    if with_audio:
        audio_stream = container.add_stream("aac", rate=44100)
        audio_stream.layout = "mono"

    for i in range(duration_frames):
        frame = av.VideoFrame(width, height, "yuv420p")
        for plane in frame.planes:
            plane.update(bytes([128] * plane.buffer_size))
        frame.pts = i
        frame.time_base = Fraction(1, fps)
        for packet in stream.encode(frame):
            container.mux(packet)

    for packet in stream.encode():
        container.mux(packet)

    if audio_stream is not None:
        for i in range(44):
            audio_frame = av.AudioFrame(format="s16", layout="mono", samples=1024)
            audio_frame.sample_rate = 44100
            audio_frame.pts = i * 1024
            audio_frame.time_base = Fraction(1, 44100)
            audio_frame.planes[0].update(bytes(audio_frame.planes[0].buffer_size))
            for packet in audio_stream.encode(audio_frame):
                container.mux(packet)
        for packet in audio_stream.encode():
            container.mux(packet)

    container.close()
    return file_path


def test_get_video_info_nonexistent():
    with pytest.raises(FileNotFoundError):
        get_video_info("nonexistent_video.mp4")


def test_concatenate_videos_empty_list():
    with pytest.raises(ValueError):
        concatenate_videos([], "out.mp4")


def test_concatenate_synthetic_videos():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        clip1 = _create_synthetic_video(tmp_path / "clip1.mp4", duration_frames=24) # 1.0s
        clip2 = _create_synthetic_video(tmp_path / "clip2.mp4", duration_frames=24) # 1.0s

        out_file = tmp_path / "composite.mp4"
        info = concatenate_videos([clip1, clip2], out_file, target_width=720, target_height=1280, target_fps=24)

        assert out_file.is_file()
        assert out_file.stat().st_size > 0
        assert info["width"] == 720
        assert info["height"] == 1280
        assert info["fps"] == 24.0
        assert info["duration_seconds"] >= 1.9
        assert len(info["sha256"]) == 64


def test_mixed_audio_clips_export_silent_instead_of_shifting_voiceover(tmp_path: Path):
    voiced = _create_synthetic_video(tmp_path / "voiced.mp4", with_audio=True)
    silent = _create_synthetic_video(tmp_path / "silent.mp4")
    info = concatenate_videos([voiced, silent], tmp_path / "mixed.mp4")
    assert info["has_audio"] is False
