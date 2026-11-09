"""Uploads are streamed to disk, size-limited and type-checked (backend/uploads.py)."""
import hashlib
import io
import os
from types import SimpleNamespace

import pytest

from backend import uploads
from backend.errors import AppError

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def upload(name, data):
    return SimpleNamespace(filename=name, file=io.BytesIO(data))


def test_a_file_is_streamed_into_place_with_its_hash(tmp_path):
    data = os.urandom(3 * uploads.CHUNK + 17)
    dest = tmp_path / "assets" / "clip.mp4"
    saved = uploads.save_upload(upload("clip.mp4", data), str(dest), max_bytes=10 * uploads.MB,
                                allowed=(".mp4",), what="video")
    assert dest.read_bytes() == data
    assert saved == {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    assert [p.name for p in dest.parent.iterdir()] == ["clip.mp4"]


def test_too_big_stops_and_leaves_nothing_behind(tmp_path):
    dest = tmp_path / "clip.mp4"
    dest.write_bytes(b"the old one")
    with pytest.raises(AppError) as err:
        uploads.save_upload(upload("clip.mp4", b"x" * (uploads.CHUNK + 1)), str(dest), max_bytes=uploads.CHUNK,
                            allowed=(".mp4",), what="video")
    assert err.value.status == 413 and err.value.message == "That video is too big. The limit is 1 MB."
    assert dest.read_bytes() == b"the old one"
    assert [p.name for p in tmp_path.iterdir()] == ["clip.mp4"]


def test_wrong_extension_and_renamed_files_are_refused(tmp_path):
    with pytest.raises(AppError) as err:
        uploads.save_upload(upload("logo.exe", PNG), str(tmp_path / "x.exe"), max_bytes=uploads.MB,
                            allowed=(".png", ".jpg"), what="logo")
    assert err.value.status == 422 and "exe" in err.value.message and "PNG" in err.value.fields["file"]
    with pytest.raises(AppError) as err:
        uploads.save_upload(upload("logo.png", b"GIF89a....."), str(tmp_path / "logo.png"), max_bytes=uploads.MB,
                            allowed=(".png",), what="logo")
    assert "doesn't look like a real .png" in err.value.message
    assert not (tmp_path / "logo.png").exists()
    saved = uploads.save_upload(upload("logo.png", PNG), str(tmp_path / "logo.png"), max_bytes=uploads.MB,
                                allowed=(".png",), what="logo")
    assert saved["size"] == len(PNG)


def test_empty_files_are_refused(tmp_path):
    with pytest.raises(AppError) as err:
        uploads.save_upload(upload("a.mp3", b""), str(tmp_path / "a.mp3"), max_bytes=uploads.MB,
                            allowed=(".mp3",), what="sound file")
    assert err.value.code == "empty_file"


def test_hash_upload_rewinds_and_limits():
    data = b"abc" * 1000
    up = upload("v.mp4", data)
    digest, size = uploads.hash_upload(up, max_bytes=10_000)
    assert (digest, size) == (hashlib.sha256(data).hexdigest(), len(data))
    assert up.file.read() == data
    with pytest.raises(AppError):
        uploads.hash_upload(upload("v.mp4", data), max_bytes=100)


def test_read_upload_never_reads_past_the_limit():
    class Counting(io.BytesIO):
        asked = 0

        def read(self, n=-1):
            Counting.asked = n
            return super().read(n)

    up = SimpleNamespace(filename="f.ttf", file=Counting(b"\x00\x01\x00\x00" + b"x" * 100))
    assert len(uploads.read_upload(up, max_bytes=200, allowed=(".ttf",), what="font")) == 104
    assert Counting.asked == 201
