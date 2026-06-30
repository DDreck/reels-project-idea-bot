import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "clip", Path(__file__).parent.parent / "tools" / "clip.py"
)
clip = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(clip)


def test_parse_time_seconds_and_mmss():
    assert clip._parse_time("12") == 12.0
    assert clip._parse_time("1:15") == 75.0
    assert clip._parse_time("1:02:03") == 3723.0


def test_make_clip_builds_ffmpeg_command(tmp_path):
    videos = tmp_path / "_videos"
    videos.mkdir()
    (videos / "sc1.mp4").write_bytes(b"x")
    calls = []

    def fake_runner(cmd, **kwargs):
        calls.append(cmd)

    out = clip.make_clip(tmp_path, "sc1", 5.0, 18.0, runner=fake_runner)
    assert out == tmp_path / "_clips" / "sc1_5-18.mp4"
    assert calls[0][0] == "ffmpeg"
    assert "-ss" in calls[0] and "5.0" in calls[0] and "18.0" in calls[0]


def test_make_clip_missing_video_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        clip.make_clip(tmp_path, "nope", 0.0, 5.0, runner=lambda *a, **k: None)


def test_make_clip_bad_range_raises(tmp_path):
    videos = tmp_path / "_videos"
    videos.mkdir()
    (videos / "sc1.mp4").write_bytes(b"x")
    with pytest.raises(ValueError):
        clip.make_clip(tmp_path, "sc1", 10.0, 5.0, runner=lambda *a, **k: None)
