"""Plex's /status/sessions is read in one place.

The scheduler's playback guard and play history used to poll Plex
separately, every 15 seconds each. Now the guard's probe is the only reader
and the smart-features loop uses its answers (plex_sessions.py).
"""
import datetime
from unittest import mock

import pytest

from backend import automation, plex_sessions
from backend.scheduler import Scheduler

PLAYING = (b'<MediaContainer size="1"><Video ratingKey="7" type="clip" title="Intro">'
           b'<Session id="s1"/><Player machineIdentifier="tv"/></Video></MediaContainer>')


class Response:
    status_code = 200
    content = PLAYING


class Setting:
    plex_url = "http://plex.local:32400"
    plex_token = "token"


@pytest.fixture
def wired(monkeypatch):
    plex_sessions.FEED.drain()
    scheduler = Scheduler()
    loop = automation.Automation()
    loop.plex_probe = scheduler.read_plex_sessions
    seen = []
    monkeypatch.setattr(loop, "observe_plex", lambda root, connector=None, now=None: seen.append(root))
    monkeypatch.setattr(loop, "poll_plugin_server", lambda kind, conf: None)
    monkeypatch.setattr(loop, "prune", lambda days: 0)
    requests_made = []

    def fake_get(url, **kw):
        requests_made.append(url)
        return Response()

    # Every Plex request anywhere in the app goes through requests.get.
    monkeypatch.setattr("requests.get", fake_get)
    yield scheduler, loop, seen, requests_made
    plex_sessions.FEED.drain()


def _age(scheduler, seconds):
    scheduler._session_probe_at = datetime.datetime.now() - datetime.timedelta(seconds=seconds)


def test_only_one_poller_asks_plex(wired, monkeypatch):
    scheduler, loop, seen, requests_made = wired
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {"url": Setting.plex_url, "token": "token"}})

    # The scheduler looks (a schedule change); play history records that same look.
    assert scheduler._plex_active_session_count(Setting()) == 1
    loop.tick(now=1_000)
    assert len(requests_made) == 1 and len(seen) == 1
    assert automation.watching_state()["plex"]["ok"] is True

    # 15 s on, the loop's turn: one fresh look, shared with the guard.
    _age(scheduler, 16)
    loop.tick(now=1_016)
    assert len(requests_made) == 2 and len(seen) == 2
    assert scheduler._plex_active_session_count(Setting()) == 1  # the guard reuses it
    assert len(requests_made) == 2

    # The loop ticks every 5 s; Plex is still asked at most once per 15 s.
    for step in range(1, 6):
        loop.tick(now=1_016 + step * 5)
    assert len(requests_made) == 2
    assert all(url == "http://plex.local:32400/status/sessions" for url in requests_made)


def test_the_loop_never_asks_plex_itself(wired, monkeypatch):
    _scheduler, loop, seen, requests_made = wired
    loop.plex_probe = None
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {"url": Setting.plex_url, "token": "token"}})
    loop.tick(now=2_000)
    assert requests_made == [] and seen == []


def test_nothing_is_asked_without_a_plex_server(wired, monkeypatch):
    scheduler, loop, seen, requests_made = wired
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {"url": None, "token": None}})
    for step in range(10):
        loop.tick(now=3_000 + step * 15)
    assert requests_made == [] and seen == []

    class NoPlex:
        plex_url = None
        plex_token = None

    assert scheduler._plex_active_session_count(NoPlex()) is None
    assert requests_made == []


def test_failures_are_shared_too(wired, monkeypatch):
    scheduler, loop, seen, _requests = wired
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {"url": Setting.plex_url, "token": "token"}})
    with mock.patch("requests.get", side_effect=OSError("no route")):
        loop.tick(now=4_000)
    assert seen == []
    assert automation.watching_state()["plex"]["ok"] is False
    assert automation.watching_state()["plex"]["message"] == "Plex didn't answer."


def test_turning_session_watching_off_stops_the_loop_asking(wired, monkeypatch):
    scheduler, loop, seen, requests_made = wired
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {"url": Setting.plex_url, "token": "token"}})
    monkeypatch.setattr(automation.smart_settings, "get_all", lambda db=None: {"watch_sessions": False})
    scheduler._plex_active_session_count(Setting())  # the guard still looks when it needs to
    loop.tick(now=5_000)
    assert len(requests_made) == 1 and seen == []
    assert plex_sessions.FEED.drain() == []  # and its answers aren't kept for later
