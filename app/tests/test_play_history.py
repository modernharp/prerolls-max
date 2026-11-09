"""Play history, stats and the missed-intro check."""
import datetime
import xml.etree.ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, models, play_history
from backend.routers import plugin_v2, stats as stats_routes
from backend.timeutil import utcnow
from tests.smart_fixtures import collection, preroll, smart_db  # noqa: F401


@pytest.fixture
def client(smart_db):
    app = FastAPI()
    errors.install(app)
    app.include_router(stats_routes.router)
    return TestClient(app), smart_db


def answer(db, items, *, user="Kid", client="Jellyfin Web", item_id="m1", excluded=False, at=None, server="jellyfin"):
    play_history.record_plugin_answer(
        db, facts={"user_name": user, "client": client, "item_id": item_id, "item_name": "Film", "item_type": "Movie"},
        server_type=server, server_name="Home", items=items, reason="", excluded=excluded, now=at)


def test_plugin_answers_become_history_and_stats(client, tmp_path):
    api, db = client
    group = collection(db)
    a = preroll(db, str(tmp_path / "a.mp4"), group, display_name="Alpha")
    b = preroll(db, str(tmp_path / "b.mp4"), group, display_name="Beta")
    never = preroll(db, str(tmp_path / "never.mp4"), group, display_name="Never")
    answer(db, [{"id": str(a.id), "name": "Alpha", "path": a.path}])
    answer(db, [{"id": str(a.id), "name": "Alpha", "path": a.path}], user="Dad", client="Roku")
    answer(db, [{"id": str(b.id), "name": "Beta", "path": b.path}], server="emby")

    recent = api.get("/api/stats/recent?limit=2").json()
    assert len(recent["items"]) == 2 and recent["retention_days"] == 90
    assert api.get("/api/stats/recent?user=dad").json()["items"][0]["client"] == "Roku"
    assert [i["server_type"] for i in api.get("/api/stats/recent?server=emby").json()["items"]] == ["emby"]

    top = api.get("/api/stats/top").json()["items"]
    assert [(t["name"], t["plays"]) for t in top][:2] == [("Alpha", 2), ("Beta", 1)]
    least = api.get("/api/stats/top?order=least").json()["items"]
    assert least[0]["name"] == "Beta"
    never_ids = [i["preroll_id"] for i in api.get("/api/stats/never-played").json()["items"]]
    assert never.id in never_ids and a.id not in never_ids

    summary = api.get("/api/stats/summary").json()
    assert summary["total_plays"] == 3
    assert {r["name"]: r["plays"] for r in summary["by_user"]} == {"Kid": 2, "Dad": 1}
    assert {r["name"]: r["plays"] for r in summary["by_server"]} == {"jellyfin": 2, "emby": 1}
    assert summary["by_day"][0]["plays"] == 3

    assert api.get("/api/stats/top?order=sideways").status_code == 422
    assert api.delete("/api/stats").json()["removed"] == 6
    assert api.get("/api/stats/recent").json()["items"] == []


def test_old_history_is_forgotten(smart_db):
    old = utcnow() - datetime.timedelta(days=100)
    answer(smart_db, [{"id": "1", "name": "x", "path": "/x"}], at=old)
    answer(smart_db, [{"id": "1", "name": "x", "path": "/x"}])
    assert play_history.prune(smart_db, 90) == 2
    assert smart_db.query(models.PlayEvent).count() == 1


def test_last_played_feeds_cooldowns(smart_db):
    early, late = utcnow() - datetime.timedelta(hours=5), utcnow()
    answer(smart_db, [{"id": "7", "name": "x", "path": "/x"}], at=early)
    answer(smart_db, [{"id": "7", "name": "x", "path": "/x"}], at=late)
    assert play_history.last_played(smart_db, [7, 8]) == {7: late.replace(microsecond=late.microsecond)}


# --- Plex ---------------------------------------------------------------------

def sessions(*videos):
    return ET.fromstring("<MediaContainer>" + "".join(videos) + "</MediaContainer>")


def clip(path, session="s1", player="tv1"):
    return (f'<Video type="clip" title="intro" sessionKey="1"><Media><Part file="{path}"/></Media>'
            f'<Session id="{session}"/><Player machineIdentifier="{player}" product="Plex for Apple TV" title="Den"/>'
            f'<User title="sam"/></Video>')


def movie(offset=2000, session="s1", player="tv1", product="Plex for Apple TV", key="99"):
    return (f'<Video type="movie" title="Alien" ratingKey="{key}" viewOffset="{offset}"><Session id="{session}"/>'
            f'<Player machineIdentifier="{player}" product="{product}" title="Den"/><User title="sam"/></Video>')


class Recorder:
    def __init__(self):
        self.plays, self.checks = [], []

    def play(self, **fields):
        self.plays.append(fields)

    def check(self, **fields):
        self.checks.append(fields)


def observe(watcher, root, rec, index, empty=False, now=0.0):
    return watcher.observe(root, index=index, record_play=rec.play, record_check=rec.check,
                           list_is_empty=lambda: empty, now=now)


def test_plex_intro_then_movie_is_history_and_a_good_check(tmp_path):
    row = type("P", (), {"id": 5, "path": "/data/prerolls/Kids/a.mp4", "display_name": "Alpha", "filename": "a.mp4"})
    index = play_history.PrerollIndex([row], lambda p: p.replace("/data/prerolls", "/plex/prerolls"))
    watcher, rec = play_history.PlexWatcher(), Recorder()
    observe(watcher, sessions(clip("/plex/prerolls/Kids/a.mp4")), rec, index, now=0)
    observe(watcher, sessions(clip("/plex/prerolls/Kids/a.mp4")), rec, index, now=10)  # same clip again
    observe(watcher, sessions(movie()), rec, index, now=20)
    assert len(rec.plays) == 1 and rec.plays[0]["preroll_id"] == 5 and rec.plays[0]["client"] == "Plex for Apple TV"
    assert rec.checks == [{"intro_count": 1, "outcome": "intros", "server_type": "plex", "source": "sessions",
                           "user_name": "sam", "client": "Plex for Apple TV", "device": "Den", "item_id": "99",
                           "item_name": "Alien", "item_type": "Movie"}]


def test_plex_movie_from_the_start_without_an_intro_is_flagged():
    index = play_history.PrerollIndex([])
    watcher, rec = play_history.PlexWatcher(), Recorder()
    observe(watcher, sessions(movie(offset=3000)), rec, index)
    observe(watcher, sessions(movie(offset=600000, session="s2", key="5")), rec, index)  # joined late: unknown
    observe(watcher, sessions(movie(offset=1000, session="s3", key="6", player="web", product="Plex Web")),
            rec, index, empty=True)
    assert [c["outcome"] for c in rec.checks] == ["not_played", "empty_list"]


def test_plex_index_matches_by_file_name_and_title():
    row = type("P", (), {"id": 1, "path": "/library/Holiday Intro.mp4", "display_name": None,
                         "filename": "Holiday Intro.mp4"})
    index = play_history.PrerollIndex([row])
    assert index.find("D:\\Media\\Holiday Intro.mp4", None) is row
    assert index.find(None, "holiday intro") is row
    assert index.find("/other.mp4", "other") is None


# --- Jellyfin / Emby ------------------------------------------------------------

def session(item_id="i1", kind="Movie", ticks=0, client="Swiftfin", series=None, sid="sess1"):
    item = {"Id": item_id, "Type": kind, "Name": "Film"}
    if series:
        item["SeriesId"] = series
        item["SeriesName"] = "Show"
    return {"Id": sid, "UserName": "Kid", "Client": client, "DeviceName": "iPad", "NowPlayingItem": item,
            "PlayState": {"PositionTicks": ticks}}


def test_playbacks_that_never_asked_the_plugin_are_flagged(smart_db):
    watcher = play_history.PluginServerWatcher()
    # Asked: the plugin request for this item came in (with the plugin's id spelling).
    answer(smart_db, [], item_id="aaaaaaaabbbbccccddddeeeeeeeeeeee")
    flagged = watcher.observe(smart_db, "jellyfin", [
        session(item_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", sid="a"),
        session(item_id="never-asked", sid="b"),
        session(item_id="resumed", ticks=60 * 60 * 10_000_000, sid="c"),
        {"Id": "idle"},
    ])
    assert flagged == 1
    check = smart_db.query(models.PlaybackCheck).filter(models.PlaybackCheck.outcome == "no_plugin_call").one()
    assert check.client == "Swiftfin" and check.item_id == "never-asked" and check.user_name == "Kid"
    # Seen once per playback, not on every poll.
    assert watcher.observe(smart_db, "jellyfin", [session(item_id="never-asked", sid="b")]) == 0


def test_auto_played_next_episodes_are_not_flagged(smart_db):
    watcher = play_history.PluginServerWatcher()
    play_history.record_plugin_answer(smart_db, facts={"item_id": "e1", "series_id": "show1", "item_type": "Episode"},
                                      server_type="jellyfin", server_name="", items=[{"id": "1", "name": "x",
                                                                                      "path": "/x"}])
    assert watcher.observe(smart_db, "jellyfin", [session(item_id="e2", kind="Episode", series="show1")]) == 0
    assert watcher.observe(smart_db, "jellyfin", [session(item_id="e9", kind="Episode", series="other", sid="z")]) == 1


# --- the health answer -----------------------------------------------------------

def test_intro_health_turns_checks_into_plain_warnings(client):
    api, db = client
    now = utcnow()
    for _ in range(3):
        play_history.record_check(db, server_type="plex", source="sessions", client="Plex for Apple TV",
                                  item_name="Alien", outcome="not_played", intro_count=0, at=now)
    play_history.record_check(db, server_type="jellyfin", source="sessions", client="Swiftfin", item_name="Up",
                              outcome="no_plugin_call", intro_count=0, at=now)
    answer(db, [], item_id="q")  # Prerolls Max had nothing to play
    answer(db, [{"id": "1", "name": "x", "path": "/x"}], item_id="r")
    plugin_v2.reset_seen()
    body = api.get("/api/health/intros").json()
    assert body["status"] == "warning" and body["playbacks"] == 6 and body["with_intros"] == 1
    plex = next(w for w in body["warnings"] if w["server"] == "plex")
    assert plex["title"] == "3 movie playbacks on Plex for Apple TV started without an intro"
    assert plex["fix"].startswith("Your Plex for Apple TV used the new Plex app, which skips intros")
    assert "Cinema Trailers to 1 before movies" in plex["fix"]
    swiftfin = next(w for w in body["warnings"] if w["client"] == "Swiftfin")
    assert swiftfin["fix"].startswith("Swiftfin doesn't play intros")
    nothing = next(w for w in body["warnings"] if w["id"] == "jellyfin:nothing_set:")
    assert nothing["severity"] == "info" and "Turn on a schedule" in nothing["fix"]


def test_intro_health_with_no_data_and_a_missing_plugin(smart_db):
    empty = play_history.intro_health(smart_db, configured={"emby": True}, plugins_seen={"emby": False})
    assert empty["status"] == "warning"
    assert empty["warnings"][0]["title"] == "The Emby plugin hasn't asked for intros this week"
    assert play_history.intro_health(smart_db)["status"] == "unknown"


@pytest.mark.parametrize("client_name,start", [
    ("Infuse", "Infuse never plays"), ("Plex Web", "Check Settings > Experience"),
    ("Plex for Android (TV)", "Your Plex for Android (TV) used the new Plex app")])
def test_plex_fixes_per_app(client_name, start):
    assert play_history.plex_fix(client_name).startswith(start)


@pytest.mark.parametrize("server,client_name,words", [
    ("jellyfin", "Jellyfin Roku", "Cinema Mode"), ("emby", "Emby Theater", "Emby Premiere"),
    ("jellyfin", "Samsung Smart TV (Tizen)", "doesn't play intros")])
def test_plugin_fixes_per_app(server, client_name, words):
    assert words in play_history.plugin_fix(server, client_name)
