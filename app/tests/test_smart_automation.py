"""The smart-features background loop, the schema upgrade and the plugin push."""
import types

import pytest
from sqlalchemy import create_engine

from backend import automation, features_schema, models, plugin_push
from tests.smart_fixtures import smart_db  # noqa: F401


def test_old_databases_get_the_new_columns(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE prerolls (id INTEGER PRIMARY KEY, filename TEXT)")
        conn.exec_driver_sql("CREATE TABLE categories (id INTEGER PRIMARY KEY, name TEXT)")

    def has(table, column):
        with engine.connect() as conn:
            return column in [r[1] for r in conn.exec_driver_sql(f"PRAGMA table_info({table})")]

    def add(table, ddl):
        with engine.begin() as conn:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {ddl}")

    assert features_schema.upgrade(has, add) == len(features_schema.COLUMNS)
    assert features_schema.upgrade(has, add) == 0
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO prerolls (id, filename) VALUES (1, 'a.mp4')")
        assert conn.exec_driver_sql("SELECT weight FROM prerolls").scalar() == 5
        conn.exec_driver_sql("INSERT INTO categories (id, name) VALUES (1, 'c')")
        assert conn.exec_driver_sql("SELECT cooldown_hours FROM categories").scalar() == 0


class Response:
    def __init__(self, status=200, json_body=None, content=b"x"):
        self.status_code, self._json, self.content = status, json_body, content

    def json(self):
        return self._json


def test_jellyfin_sessions_are_read_with_the_api_key(smart_db, monkeypatch):
    seen = {}

    def fake_get(url, headers=None, timeout=None, **kw):
        seen["url"], seen["headers"] = url, headers
        return Response(json_body=[{"Id": "s", "Client": "Swiftfin", "UserName": "Kid",
                                    "NowPlayingItem": {"Id": "m1", "Type": "Movie", "Name": "Up"},
                                    "PlayState": {"PositionTicks": 0}}])

    monkeypatch.setattr(automation.requests, "get", fake_get)
    automation.Automation().poll_plugin_server("jellyfin", {"url": "http://jf:8096/", "token": "key"})
    assert seen["url"] == "http://jf:8096/Sessions?ActiveWithinSeconds=120"
    assert "key" in str(seen["headers"])
    assert smart_db.query(models.PlaybackCheck).one().outcome == "no_plugin_call"
    assert automation.watching_state()["jellyfin"]["ok"] is True


def test_emby_and_failures_are_noted(smart_db, monkeypatch):
    calls = []
    monkeypatch.setattr(automation.requests, "get",
                        lambda url, **kw: calls.append(url) or Response(status=401, json_body=None))
    automation.Automation().poll_plugin_server("emby", {"url": "http://emby:8096", "token": "key"})
    assert calls == ["http://emby:8096/emby/Sessions?ActiveWithinSeconds=120"]
    assert automation.watching_state()["emby"] == {"ok": False, "message": "Emby answered 401.", "seconds_ago": 0}


def test_tick_runs_each_job_on_its_own_schedule(monkeypatch):
    runs = []
    loop = automation.Automation()
    loop.watch_deps = object()
    monkeypatch.setattr(automation, "_servers", lambda: {"plex": {}, "jellyfin": {}, "emby": {}})
    monkeypatch.setattr(loop, "poll_plex", lambda conf, now: runs.append("plex"))
    monkeypatch.setattr(loop, "poll_plugin_server", lambda kind, conf: runs.append(kind))
    monkeypatch.setattr(loop, "scan_folders", lambda: runs.append("folders"))
    monkeypatch.setattr(loop, "prune", lambda days: runs.append(("prune", days)))
    loop.tick(now=100_000)
    assert runs == ["plex", "jellyfin", "emby", "folders", ("prune", 90)]
    runs.clear()
    loop.tick(now=100_016)  # 16 s later: only Plex is due again
    assert runs == ["plex"]


def test_a_failing_step_does_not_stop_the_others(monkeypatch):
    runs = []
    loop = automation.Automation()
    monkeypatch.setattr(automation, "_servers", lambda: {})

    def boom(conf, now):
        raise RuntimeError("plex exploded")

    monkeypatch.setattr(loop, "poll_plex", boom)
    monkeypatch.setattr(loop, "poll_plugin_server", lambda kind, conf: runs.append(kind))
    monkeypatch.setattr(loop, "prune", lambda days: runs.append("prune"))
    loop.tick(now=5_000_000)
    assert runs == ["jellyfin", "emby", "prune"]


def test_binge_gap_is_pushed_to_connected_plugins(monkeypatch):
    monkeypatch.setattr(plugin_push, "_servers", lambda: {"jellyfin": {"url": "http://jf", "token": "k"},
                                                          "emby": {"url": "http://emby", "token": "k"},
                                                          "plex": {"url": "http://plex", "token": "t"}})
    monkeypatch.setattr(plugin_push, "_push_jellyfin", lambda url, key, hours: hours == 6)

    def emby_down(url, key, hours):
        raise ConnectionError("down")

    monkeypatch.setattr(plugin_push, "_push_emby", emby_down)
    results = plugin_push.push_binge_window(6)
    assert results == [
        {"server": "jellyfin", "updated": True, "message": "The Jellyfin plugin now uses 6 hours too."},
        {"server": "emby", "updated": False,
         "message": "Couldn't update the Emby plugin. Set the same gap on its settings page."}]
