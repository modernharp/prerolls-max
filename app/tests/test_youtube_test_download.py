""""Try a test download" against the real YouTube: the control video came
back with formats while every trailer came back as a title with no formats
("Sign in to confirm you're not a bot"). The probe counted a title as a pass,
so the page said "YouTube authentication is working via no authentication"
while every download failed."""

import yt_dlp

from backend import main
from backend.radarr_connector import probe_youtube


class FakeYDL:
    info = {}

    def __init__(self, opts):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        return dict(self.info)


def probe_with(monkeypatch, info):
    FakeYDL.info = info
    monkeypatch.setattr(yt_dlp, "YoutubeDL", FakeYDL)
    return probe_youtube("https://www.youtube.com/watch?v=x")


def test_title_without_formats_is_the_bot_wall(monkeypatch):
    r = probe_with(monkeypatch, {"title": "Dune: Part Three | Final Trailer", "formats": []})
    assert not r["ok"] and r["category"] == "auth"
    assert "isn't a robot" in r["reason"]


def test_formats_mean_it_works(monkeypatch):
    r = probe_with(monkeypatch, {"title": "Trailer", "duration": 120, "formats": [{"format_id": "18"}]})
    assert r["ok"] and r["title"] == "Trailer"


def test_control_works_but_trailers_are_walled():
    control = {"ok": True, "title": "Music video"}
    target = {"ok": False, "category": "auth", "reason": "YouTube asked this server to prove it isn't a robot."}
    r = main._youtube_test_answer(control, target, have_cookies=False)
    assert r["success"] is False
    assert r["error"] == target["reason"]
    assert "Upload cookies.txt" in r["hint"]


def test_stale_cookies_hint():
    r = main._youtube_test_answer({"ok": False, "category": "auth", "reason": "x"}, None, have_cookies=True)
    assert not r["success"] and "export the cookies again" in r["hint"]


def test_gone_trailer_is_not_a_setup_problem():
    r = main._youtube_test_answer({"ok": True}, {"ok": False, "category": "video_unavailable", "reason": "gone"}, False)
    assert not r["success"] and r["auth_ok"] and "gone from YouTube" in r["error"]


def test_all_good_says_so_plainly():
    r = main._youtube_test_answer({"ok": True}, {"ok": True, "title": "Hexed - Trailer"}, have_cookies=False)
    assert r["success"]
    assert r["message"].startswith("YouTube hands videos to this server without signing in")
    assert "Hexed - Trailer" in r["message"]
    assert "no authentication" not in r["message"]
