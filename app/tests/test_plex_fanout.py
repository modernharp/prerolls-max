"""Schedules reach every enabled Plex server, each through its own folder
mapping, with failures reported per server; and Jellyfin/Emby plugin requests
are matched to their server."""
import json
import os
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from backend import errors, media_servers as ms, models, plex_fanout, plex_visibility
from backend import scheduler as scheduler_module
from backend.routers import plugin_v2
from tests.media_server_fixtures import secrets  # noqa: F401 (fixture)


class FakePlex:
    writes: dict = {}
    platform: dict = {}
    refuse: set = set()

    def __init__(self, url, token=None):
        self.url, self.token = url, token
        self.last_visibility = None
        self.last_error = None
        self.last_shortened = None

    def get_server_info(self):
        return {"connected": True, "platform": FakePlex.platform.get(self.url, "Linux")}

    def set_preroll(self, value):
        if self.url in FakePlex.refuse:
            paths = [p for p in value.split(";") if p]
            self.last_visibility = plex_visibility.GateResult(
                "withheld", value, [{"path": p, "status": plex_visibility.MISSING, "reason": "no"} for p in paths])
            return False
        FakePlex.writes.setdefault(self.url, []).append(value)
        return True

    def get_preroll(self):
        return (FakePlex.writes.get(self.url) or [""])[-1]

    get_current_preroll = get_preroll


@pytest.fixture
def world(secrets, tmp_path, monkeypatch):  # noqa: F811
    FakePlex.writes, FakePlex.platform, FakePlex.refuse = {}, {}, set()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    local = str(tmp_path / "intros")
    os.makedirs(local)
    category = models.Category(name="Halloween")
    db.add(category)
    db.flush()
    for name in ("Ghost.mp4", "Pumpkin.mp4"):
        path = os.path.join(local, name)
        open(path, "wb").write(b"x")
        db.add(models.Preroll(filename=name, path=path, category_id=category.id, enabled=True))
    db.add(models.Setting(timezone="UTC"))
    db.commit()
    for name, url, folder in (("Den", "http://p1:32400", "/prerolls"), ("Loft", "http://p2:32401", "/media/intros")):
        row = models.MediaServer(type="plex", name=name, url=url, enabled=True,
                                 path_mappings=json.dumps([{"local": local, "plex": folder}]))
        db.add(row)
        db.flush()
        ms.set_secret(row, "t" * 20)
    ms.mirror(db)
    db.commit()
    sched = scheduler_module.Scheduler()
    fanout = plex_fanout.PlexFanout()
    monkeypatch.setattr(plex_fanout, "FANOUT", fanout)
    monkeypatch.setattr(fanout, "busy", lambda *a: False)
    for name, value in (("PlexConnector", FakePlex), ("_scheduler_log", MagicMock()),
                        ("_scheduler_verbose", MagicMock()), ("SessionLocal", Session)):
        monkeypatch.setattr(scheduler_module, name, value)
    monkeypatch.setattr(sched, "_defer_preroll_write", lambda *a, **k: False)
    yield types.SimpleNamespace(db=db, sched=sched, fanout=fanout, category=category, local=local)
    db.close()
    engine.dispose()


def _rows(db):
    return {r.name: r for r in ms.ordered(db)}


def test_a_schedule_reaches_both_plex_servers_through_their_own_mappings(world):
    result = world.sched._apply_category_to_plex(world.category.id, world.db)
    assert result.plex is True
    assert FakePlex.writes["http://p1:32400"] == ["/prerolls/Ghost.mp4;/prerolls/Pumpkin.mp4"]
    assert FakePlex.writes["http://p2:32401"] == ["/media/intros/Ghost.mp4;/media/intros/Pumpkin.mp4"]
    rows = _rows(world.db)
    assert world.fanout.status(rows["Den"].id)["state"] == "ok"
    assert world.fanout.status(rows["Loft"].id)["state"] == "ok"


def test_a_switched_off_plex_is_left_alone(world):
    rows = _rows(world.db)
    rows["Loft"].enabled = False
    world.db.commit()
    world.sched._apply_category_to_plex(world.category.id, world.db)
    assert "http://p2:32401" not in FakePlex.writes


def test_a_server_that_cant_see_the_files_is_reported_by_name(world):
    FakePlex.refuse = {"http://p2:32401"}
    world.sched._apply_category_to_plex(world.category.id, world.db)
    status = world.fanout.status(_rows(world.db)["Loft"].id)
    assert status["state"] == "failed"
    assert status["message"] == ("Loft couldn't see any of the 2 intro files, so its list wasn't changed. "
                                 "Check its folder mapping.")
    assert FakePlex.writes["http://p1:32400"]  # the first one still got its list


def test_a_busy_server_waits_and_is_retried(world, monkeypatch):
    monkeypatch.setattr(world.fanout, "busy", lambda sched, db, target: target.name == "Loft")
    world.sched._apply_category_to_plex(world.category.id, world.db)
    loft = _rows(world.db)["Loft"].id
    assert world.fanout.status(loft)["state"] == "waiting"
    assert "playing intros right now" in world.fanout.status(loft)["message"]
    monkeypatch.setattr(world.fanout, "busy", lambda *a: False)
    world.fanout.tick(world.sched, world.db, now=10_000)
    assert world.fanout.status(loft)["state"] == "ok"
    assert FakePlex.writes["http://p2:32401"][-1].startswith("/media/intros/")


def test_a_windows_plex_without_a_mapping_is_told_why(world):
    FakePlex.platform = {"http://p2:32401": "Windows"}
    world.sched._apply_category_to_plex(world.category.id, world.db)
    status = world.fanout.status(_rows(world.db)["Loft"].id)
    assert status["state"] == "failed" and "folder mapping" in status["message"]


def test_a_list_changed_outside_prerolls_max_is_written_again(world):
    world.sched._apply_category_to_plex(world.category.id, world.db)
    FakePlex.writes["http://p2:32401"].append("/somewhere/else.mp4")
    world.fanout.tick(world.sched, world.db, now=10_000)
    assert FakePlex.writes["http://p2:32401"][-1] == "/media/intros/Ghost.mp4;/media/intros/Pumpkin.mp4"


def test_a_new_server_starts_from_the_first_ones_list(world):
    FakePlex.writes["http://p1:32400"] = ["/prerolls/Pumpkin.mp4,/prerolls/Ghost.mp4"]
    world.fanout.seed_from_primary(world.sched, world.db)
    assert world.fanout.last["delimiter"] == ","
    assert world.fanout.send_current(world.sched, world.db, _rows(world.db)["Loft"].id) is True
    assert FakePlex.writes["http://p2:32401"] == ["/media/intros/Pumpkin.mp4,/media/intros/Ghost.mp4"]


def test_unmap_reads_a_mapping_backwards():
    maps = [{"local": "/data/x", "plex": "/prerolls"}]
    assert plex_fanout.unmap("/prerolls/Halloween/a.mp4", maps) == os.path.join("/data/x", "Halloween", "a.mp4")
    assert plex_fanout.unmap("/prerollsX/a.mp4", maps) == "/prerollsX/a.mp4"


# -- Jellyfin / Emby plugins ------------------------------------------------------------

class Key:
    id = 5
    name = "Jellyfin Plugin (Auto) · Bedroom"


def _plugin_client(linked):
    answers = []
    db = types.SimpleNamespace(query=lambda model: types.SimpleNamespace(
        first=lambda: types.SimpleNamespace(auth_enabled=False, plugin_random_count=1),
        filter=lambda *a: types.SimpleNamespace(all=lambda: [])))

    def get_db():
        yield db

    plugin_v2.configure(plugin_v2.Deps(
        get_db=get_db, resolve_intros=lambda db_, **kw: answers.append(("resolve", kw)) or {"paths": ["/p/a.mp4"]},
        play_list=lambda setting, p, m, r: list(p), validate_api_key=lambda v, perm, db_: Key(),
        sign_stream_path=lambda path, expires: "sig", file_version=lambda path: "1", plugin_clients={},
        setting_model=object,
        on_answer=lambda db_, **kw: answers.append(("answer", kw)),
        link_server=lambda db_, kind, ident, key_id, address: linked(kind, ident, key_id),
        is_play_test=lambda facts: facts.get("item_id") == "testing"))
    app = FastAPI()
    errors.install(app)
    app.include_router(plugin_v2.router)
    return TestClient(app), answers


@pytest.fixture(autouse=False)
def reset_plugins():
    plugin_v2.reset_seen()
    yield
    plugin_v2.reset_seen()
    plugin_v2.configure(None)


def test_a_plugin_request_is_recorded_under_its_servers_name(reset_plugins):
    seen = []
    client, answers = _plugin_client(lambda kind, ident, key: seen.append((kind, ident, key)) or
                                     {"id": 9, "name": "Bedroom", "enabled": True})
    r = client.get("/plugin/v2/intros?item_id=m1&item_type=Movie&server_id=JF-2",
                   headers={"X-PrerollsMax-Plugin": "jellyfin/2.0.0.0", "X-Api-Key": "k"})
    assert r.status_code == 200 and r.json()["items"]
    assert seen == [("jellyfin", "JF-2", 5)]
    resolve = next(kw for what, kw in answers if what == "resolve")
    assert resolve["facts"]["media_server_id"] == 9
    answer = next(kw for what, kw in answers if what == "answer")
    assert answer["server_name"] == "Bedroom"
    assert plugin_v2.seen_plugins("jellyfin")[0]["media_server_id"] == 9


def test_a_switched_off_server_gets_no_intros(reset_plugins):
    client, answers = _plugin_client(lambda *a: {"id": 9, "name": "Bedroom", "enabled": False})
    body = client.get("/plugin/v2/intros?item_id=m1&item_type=Movie",
                      headers={"X-PrerollsMax-Plugin": "jellyfin/2.0.0.0", "X-Api-Key": "k"}).json()
    assert body["items"] == [] and body["reason"] == "Bedroom is switched off in Prerolls Max."
    assert body["intentional_empty"] is False and answers == []


def test_a_play_test_is_not_counted(reset_plugins):
    client, answers = _plugin_client(lambda *a: None)
    r = client.get("/plugin/v2/intros?item_id=testing&item_type=Movie",
                   headers={"X-PrerollsMax-Plugin": "emby/2.0.0.0", "X-Api-Key": "k"})
    assert r.json()["items"] and not [a for a in answers if a[0] == "answer"]
