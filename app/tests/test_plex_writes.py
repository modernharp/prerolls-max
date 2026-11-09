"""How Prerolls Max writes Plex's intro list (CinemaTrailersPrerollID).

One PUT of the one real preference and one read back; a list too long for
Plex keeps its order when it is a playlist; the random-subset cache is shared
safely; certificates are checked unless turned off; names with , or ; are
kept out; and on a shared server one viewer's movie never steers everyone.
"""
import threading
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
import requests

from backend import plex_connector
from backend.plex_connector import PlexConnector, tls_error_message, unsafe_for_plex
from backend.scheduler import plex_next_play_facts


class FakePlex:
    """Answers PUT/GET /:/prefs like Plex, recording every request."""

    def __init__(self, put_status=200, keep_old=False):
        self.value = "old.mp4"
        self.put_status = put_status
        self.keep_old = keep_old
        self.calls = []

    def put(self, url, **kw):
        self.calls.append(("PUT", url))
        name, _, encoded = url.partition("?")[2].partition("=")
        assert name == "CinemaTrailersPrerollID"
        if self.put_status == 200 and not self.keep_old:
            self.value = requests.utils.unquote(encoded)
        return SimpleNamespace(status_code=self.put_status)

    def get(self, url, **kw):
        self.calls.append(("GET", url))
        xml = f'<MediaContainer><Setting id="CinemaTrailersPrerollID" value="{self.value}"/></MediaContainer>'
        return SimpleNamespace(status_code=200, content=xml.encode())


@pytest.fixture
def plex(monkeypatch):
    fake = FakePlex()
    monkeypatch.setattr(plex_connector.requests, "put", fake.put)
    monkeypatch.setattr(plex_connector.requests, "get", fake.get)
    # The visibility gate has its own tests; here it can't run (no Plex), which writes unchecked.
    monkeypatch.setattr(plex_connector.plex_visibility, "gate_preroll_value", Mock(side_effect=RuntimeError("off")))
    return fake


def connector():
    return PlexConnector("http://plex:32400", "token")


def test_one_put_of_the_real_preference_and_one_read_back(plex):
    c = connector()
    assert c.set_preroll("/p/a.mp4;/p/b.mp4") is True
    assert [m for m, _ in plex.calls] == ["PUT", "GET"]
    assert plex.value == "/p/a.mp4;/p/b.mp4" and c.last_error is None


def test_a_refused_token_is_reported_plainly_and_nothing_else_is_tried(plex):
    plex.put_status = 401
    c = connector()
    assert c.set_preroll("/p/a.mp4") is False
    assert [m for m, _ in plex.calls] == ["PUT"]
    assert "turned down the token" in c.last_error


def test_a_value_plex_did_not_keep_is_a_failure_with_a_reason(plex):
    plex.keep_old = True
    c = connector()
    assert c.set_preroll("/p/a.mp4") is False
    assert "still shows a different intro list" in c.last_error


def test_a_long_playlist_keeps_its_order(plex):
    paths = [f"/prerolls/{i:03d}-{'x' * 80}.mp4" for i in range(150)]
    c = connector()
    assert c.set_preroll(",".join(paths)) is True
    written = plex.value.split(",")
    assert written == paths[:len(written)] and 0 < len(written) < len(paths)
    assert "only the first" in c.last_shortened


def test_a_long_random_pool_uses_one_shared_subset(plex):
    PlexConnector._chunk_cache_value = None
    paths = [f"/prerolls/{i:03d}-{'y' * 80}.mp4" for i in range(150)]
    value = ";".join(paths)
    results = []
    threads = [threading.Thread(target=lambda: results.append(connector()._build_chunked_subset(value, ";")))
               for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(results)) == 1
    subset = results[0].split(";")
    assert set(subset) <= set(paths) and len(subset) < len(paths)


def test_certificates_are_checked_unless_turned_off(monkeypatch):
    monkeypatch.delenv("PMAX_PLEX_TLS_VERIFY", raising=False)
    assert PlexConnector("https://192.168.1.5:32400", "t")._verify is True
    monkeypatch.setenv("PMAX_PLEX_TLS_VERIFY", "0")
    assert PlexConnector("https://192.168.1.5:32400", "t")._verify is False


def test_a_certificate_problem_says_what_to_do(monkeypatch):
    def broken(*a, **kw):
        raise requests.exceptions.SSLError("hostname mismatch")

    monkeypatch.setattr(plex_connector.requests, "put", broken)
    monkeypatch.setattr(plex_connector.plex_visibility, "gate_preroll_value", Mock(side_effect=RuntimeError("off")))
    c = PlexConnector("https://192.168.1.5:32400", "t")
    assert c.set_preroll("/p/a.mp4") is False
    assert c.last_error == tls_error_message("https://192.168.1.5:32400")
    assert "PMAX_PLEX_TLS_VERIFY=0" in c.last_error


def test_names_with_commas_or_semicolons_are_kept_out_of_plex():
    assert unsafe_for_plex("/p/Hello, World.mp4") and unsafe_for_plex("/p;x/a.mp4")
    assert not unsafe_for_plex("/p/Hello - World.mp4")
    from backend.scheduler import Scheduler
    sched = Scheduler.__new__(Scheduler)
    with patch("backend.scheduler._scheduler_log") as log:
        joined = sched._join_for_plex(["/p/a.mp4", "/p/Hello, World.mp4", "/p/b.mp4"], ",")
    assert joined == "/p/a.mp4,/p/b.mp4"
    assert "comma or semicolon" in log.call_args.args[0]


def sessions(*videos):
    return ET.fromstring("<MediaContainer>" + "".join(videos) + "</MediaContainer>")


MOVIE = ('<Video type="movie" title="Alien" contentRating="R" librarySectionID="1" librarySectionTitle="Movies">'
         '<Genre tag="Horror"/><Genre tag="Science Fiction"/><User id="7" title="sam"/></Video>')


def test_one_movie_playing_steers_the_next_play():
    facts, reason = plex_next_play_facts(sessions(MOVIE))
    assert facts == {"genres": ["Horror", "Science Fiction"], "official_rating": "R", "library_id": "1",
                     "library_name": "Movies", "user_id": "7", "user_name": "sam", "year": None}
    assert "next play" in reason


def test_two_viewers_leave_personal_rules_alone():
    facts, reason = plex_next_play_facts(sessions(MOVIE, MOVIE.replace("sam", "alex")))
    assert facts is None and "2 people are watching" in reason and "Schedules still change" in reason


def test_nothing_playing_or_an_episode_gives_no_facts():
    assert plex_next_play_facts(sessions())[0] is None
    facts, reason = plex_next_play_facts(sessions('<Video type="episode" title="Pilot"/>'))
    assert facts is None and "only plays intros before movies" in reason
