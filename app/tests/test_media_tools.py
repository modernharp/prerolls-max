"""Media tools with real ffmpeg on tiny generated videos: loudness, versions, combine.

Originals are never changed in place: a new version is a new library item,
and "replace" moves the original to the Trash first.
"""
import os
import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, media_tools, models, preroll_trash
from backend.jobs import runner
from backend.routers import media_tools as media_routes
from tests.smart_fixtures import collection, make_video, preroll, smart_db  # noqa: F401

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")


@pytest.fixture
def media(smart_db, tmp_path):
    # Import the app first: its import configures the media routes with the
    # real folders, and the admin check imports it on the first request. If
    # that happened after the line below, it would replace the test folders.
    import backend.main  # noqa: F401
    library = tmp_path / "library"
    (library / "Kids").mkdir(parents=True)
    media_routes.configure(media_routes.Deps(library_dir=lambda: str(library), data_dir=lambda: str(tmp_path)))
    app = FastAPI()
    errors.install(app)
    app.include_router(media_routes.router)
    yield TestClient(app), smart_db, library
    media_routes.configure(None)


def run(client, url, body):
    started = client.post(url, json=body)
    assert started.status_code == 200, started.text
    state = runner.wait(started.json()["job_id"], timeout=120)
    assert state["state"] == "done", state
    return state


# --- the ffmpeg helpers ------------------------------------------------------

def test_measure_and_normalize_two_pass(tmp_path):
    loud = make_video(tmp_path / "loud.mp4", volume=6.0)
    before = media_tools.measure_loudness(loud)
    assert before["lufs"] > -15
    out = str(tmp_path / "even.mp4")
    after = media_tools.normalize_loudness(loud, out, target=-23)
    assert abs(after["lufs"] - (-23)) < 1.0 and after["peak"] <= -0.5
    assert media_tools.probe(out)["video_codec"] == "h264"  # the picture was copied, not re-encoded
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".")]


def test_silent_files_have_no_loudness(tmp_path):
    silent = make_video(tmp_path / "silent.mp4", audio=False)
    assert media_tools.measure_loudness(silent) is None
    with pytest.raises(errors.AppError) as caught:
        media_tools.normalize_loudness(silent, str(tmp_path / "x.mp4"))
    assert caught.value.code == "no_audio"


def test_loudness_status_words():
    assert media_tools.loudness_status(-14, -1.5, True, -23, 2) == ("loud", "9.0 LU louder than your target")
    assert media_tools.loudness_status(-30, -10, True, -23, 2)[0] == "quiet"
    assert media_tools.loudness_status(-23, 0.4, True, -23, 2)[0] == "peaks"
    assert media_tools.loudness_status(None, None, True, -23, 2) == ("silent", "No sound")
    assert media_tools.loudness_status(None, None, False, -23, 2)[0] == "unchecked"


def test_hdr_becomes_an_sdr_version(tmp_path):
    hdr = make_video(tmp_path / "hdr.mp4", hdr=True)
    if not media_tools.probe(hdr)["hdr"]:
        # Some FFmpeg builds can't write HDR tags, so there's no HDR sample to convert.
        pytest.skip("this FFmpeg can't make an HDR test video")
    info = media_tools.make_version(hdr, str(tmp_path / "sdr.mp4"), profile="720p")
    assert (info["width"], info["height"], info["hdr"], info["pix_fmt"]) == (1280, 720, False, "yuv420p")
    assert info["audio_codec"] == "aac" and info["channels"] == 2 and info["sample_rate"] == 48000
    assert media_tools.matches_profile(info, "720p") and not media_tools.matches_profile(info, "1080p")


def test_hdr_becomes_sdr_even_without_zscale(tmp_path, monkeypatch):
    """Some FFmpeg builds (Ubuntu's, for one) have no zscale filter."""
    monkeypatch.setattr(media_tools, "has_zscale", lambda: False)
    hdr = make_video(tmp_path / "hdr.mp4", hdr=True)
    info = media_tools.make_version(hdr, str(tmp_path / "sdr.mp4"), profile="720p")
    assert (info["width"], info["height"], info["hdr"], info["pix_fmt"]) == (1280, 720, False, "yuv420p")


def test_combine_mixes_sizes_rates_and_silent_parts(tmp_path):
    a = make_video(tmp_path / "a.mp4", seconds=1, size="320x240", rate=25)
    b = make_video(tmp_path / "b.mp4", seconds=1, size="640x360", rate=30, audio=False)
    info = media_tools.combine([a, b], str(tmp_path / "both.mp4"), profile="720p")
    assert abs(info["duration"] - 2.0) < 0.3 and (info["width"], info["height"]) == (1280, 720)
    assert info["has_audio"] and info["fps"] == 25.0


def test_transcode_endpoint_shares_the_encoder_settings():
    args = media_tools.h264_aac_args(preset="slow", crf=18, level="4.1", audio_bitrate="192k")
    assert args == ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "slow", "-crf", "18", "-profile:v", "high",
                    "-level", "4.1", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    assert media_tools.scale_pad_filter(1280, 720) == (
        "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black")


# --- the jobs ------------------------------------------------------------------

def test_loudness_check_flags_outliers(media):
    client, db, library = media
    kids = collection(db, "T-Media kids")
    loud = preroll(db, make_video(library / "Kids" / "loud.mp4", volume=6.0), kids)
    calm = preroll(db, make_video(library / "Kids" / "calm.mp4", volume=0.9), kids)
    state = run(client, "/api/media/loudness/check", {"preroll_ids": [loud.id, calm.id]})
    assert state["result"] == {"checked": 2} and state["progress"] == 100
    overview = client.get("/api/media/loudness").json()
    rows = {i["preroll_id"]: i for i in overview["items"]}
    assert rows[loud.id]["status"] == "loud" and rows[calm.id]["status"] == "ok"
    assert loud.id in [o["preroll_id"] for o in overview["outliers"]]
    assert overview["target_lufs"] == -23.0


def test_normalize_as_a_new_version_takes_the_originals_place(media):
    client, db, library = media
    kids = collection(db, "T-Media normalize")
    loud = preroll(db, make_video(library / "Kids" / "loud.mp4", volume=6.0), kids)
    state = run(client, "/api/media/loudness/normalize", {"preroll_ids": [loud.id]})
    item = state["result"]["items"][0]
    assert item["before_lufs"] > -15 and abs(item["after_lufs"] + 23) < 1
    new = db.query(models.Preroll).filter(models.Preroll.id == item["new_preroll_id"]).one()
    db.refresh(loud)
    assert new.version_of == loud.id and new.version_label == "Loudness -23 LUFS"
    assert [c.id for c in new.categories] == [kids.id] and loud.enabled is False
    assert os.path.exists(loud.path) and new.path.endswith("loud (normalized).mp4")
    db.created["prerolls"].append(new.id)


def test_normalize_replace_keeps_the_original_in_the_trash(media):
    client, db, library = media
    loud = preroll(db, make_video(library / "Kids" / "replace-me.mp4", volume=6.0))
    original_size = os.path.getsize(loud.path)
    state = run(client, "/api/media/loudness/normalize", {"preroll_ids": [loud.id], "mode": "replace",
                                                          "target_lufs": -20})
    assert state["result"]["items"][0]["original_in_trash"] is True
    db.refresh(loud)
    assert loud.path == str(library / "Kids" / "replace-me.mp4") and abs(loud.loudness_lufs + 20) < 1
    trashed = preroll_trash.list_trash(str(library), None)
    assert trashed and trashed[0]["filename"] == "replace-me.mp4" and trashed[0]["size_bytes"] == original_size


def test_matching_versions_skip_files_that_already_match(media):
    client, db, library = media
    kids = collection(db, "T-Media versions")
    small = preroll(db, make_video(library / "Kids" / "small.mp4", size="320x240"), kids)
    state = run(client, "/api/media/versions", {"preroll_ids": [small.id], "profiles": ["720p"]})
    made = state["result"]["made"][0]
    assert made["format"].startswith("1280x720, H264, SDR") and "note" in state["result"]
    new_id = made["new_preroll_id"]
    db.created["prerolls"].append(new_id)
    again = run(client, "/api/media/versions", {"preroll_ids": [new_id], "profiles": ["720p"], "use_instead": False})
    assert again["result"]["made"] == [] and again["result"]["skipped"][0]["why"].startswith("Already 720p SDR")
    info = client.get(f"/api/media/info/{small.id}").json()
    assert info["versions"][0]["id"] == new_id and info["matches_1080p_sdr"] is False
    two = client.post("/api/media/versions", json={"preroll_ids": [small.id], "profiles": ["720p", "1080p"]})
    assert two.status_code == 422 and "Only one size" in two.json()["detail"]


def test_combine_makes_a_library_item_in_the_collection(media):
    client, db, library = media
    roku = collection(db, "T-Roku")
    a = preroll(db, make_video(library / "Kids" / "a.mp4"))
    b = preroll(db, make_video(library / "Kids" / "b.mp4", audio=False))
    state = run(client, "/api/media/combine", {"preroll_ids": [a.id, b.id], "name": "Roku; all in one",
                                               "profile": "720p", "collection_id": roku.id})
    result = state["result"]
    assert result["parts"] == ["a", "b"] and abs(result["duration_seconds"] - 2) < 0.3
    row = db.query(models.Preroll).filter(models.Preroll.id == result["preroll_id"]).one()
    db.created["prerolls"].append(row.id)
    assert row.path == str(library / "T-Roku" / "Roku - all in one.mp4") and [c.id for c in row.categories] == [roku.id]
    one = client.post("/api/media/combine", json={"preroll_ids": [a.id], "name": "x"})
    assert one.status_code == 422 and "at least two" in one.json()["detail"]


def test_missing_files_and_ids_are_plain_errors(media):
    client, db, library = media
    ghost = preroll(db, str(library / "ghost.mp4"))
    os.remove(ghost.path)
    gone = client.post("/api/media/loudness/normalize", json={"preroll_ids": [ghost.id]})
    assert gone.status_code == 404 and gone.json()["detail"] == "The file for 'ghost' is missing."
    unknown = client.post("/api/media/versions", json={"preroll_ids": [999999]})
    assert unknown.status_code == 422 and unknown.json()["error"]["fields"]["preroll_ids"]
    assert client.get("/api/media/status").json()["ffmpeg"] is True
