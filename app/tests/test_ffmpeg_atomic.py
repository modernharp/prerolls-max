"""Generated videos appear only when complete (plugins used to cache half-written files)."""
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from backend import dynamic_preroll
from backend.dynamic_preroll import _run_ffmpeg_atomic


def test_the_output_is_written_elsewhere_and_renamed_into_place(tmp_path, monkeypatch):
    target = tmp_path / "coming_soon_grid.mp4"
    target.write_bytes(b"the old, complete video")
    seen = {}

    def fake_run(cmd, *a, **kw):
        seen["out"] = cmd[-1]
        # While ffmpeg works, the old file is still whole.
        assert target.read_bytes() == b"the old, complete video"
        with open(cmd[-1], "wb") as fh:
            fh.write(b"new video")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dynamic_preroll.subprocess, "run", fake_run)
    _run_ffmpeg_atomic(["ffmpeg", "-y", "-i", "x", str(target)], capture_output=True)
    assert seen["out"] != str(target) and seen["out"].endswith(".mp4")
    assert target.read_bytes() == b"new video" and sorted(os.listdir(tmp_path)) == ["coming_soon_grid.mp4"]


def test_a_failed_render_leaves_the_old_video_and_no_scraps(tmp_path, monkeypatch):
    target = tmp_path / "list.mp4"
    target.write_bytes(b"old")

    def failing(cmd, *a, **kw):
        with open(cmd[-1], "wb") as fh:
            fh.write(b"half")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(dynamic_preroll.subprocess, "run", failing)
    _run_ffmpeg_atomic(["ffmpeg", "-y", str(target)])
    assert target.read_bytes() == b"old" and os.listdir(tmp_path) == ["list.mp4"]


def test_other_commands_run_unchanged(monkeypatch):
    calls = []
    monkeypatch.setattr(dynamic_preroll.subprocess, "run", lambda cmd, *a, **kw: calls.append(cmd))
    _run_ffmpeg_atomic(["ffprobe", "-i", "/x/a.mp4"])
    _run_ffmpeg_atomic(["ffmpeg", "-i", "a.mp4", "-f", "null", "-"])
    assert calls == [["ffprobe", "-i", "/x/a.mp4"], ["ffmpeg", "-i", "a.mp4", "-f", "null", "-"]]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_with_real_ffmpeg(tmp_path):
    target = tmp_path / "blank.mp4"
    result = _run_ffmpeg_atomic(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                                 "color=c=black:s=64x64:d=0.2", str(target)], capture_output=True)
    assert result.returncode == 0 and target.stat().st_size > 0
    assert os.listdir(tmp_path) == ["blank.mp4"]
