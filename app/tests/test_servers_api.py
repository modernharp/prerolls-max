"""/api/servers: adding, changing and removing servers in plain words, the
connection test, and "Play a test" (servers are faked; no network)."""
import types

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, media_servers as ms, models, server_play_test, server_probe
from backend.routers import server_tools, servers
from tests.media_server_fixtures import add, as_admin, secrets, server_db  # noqa: F401 (fixtures)

GOOD = {"reachable": True, "signed_in": True, "name": "Box", "version": "12.4.0", "identifier": None,
        "platform": "Linux", "message": None, "hint": None}


@pytest.fixture
def api(server_db, as_admin, monkeypatch):  # noqa: F811
    answers = {}

    def check(target):
        found = answers.get(target.url, GOOD)
        return {**found, "identifier": found.get("identifier") or target.url}

    monkeypatch.setattr(server_probe, "check", check)
    monkeypatch.setattr(servers, "_after_change", lambda *a, **k: None)
    app = FastAPI()
    errors.install(app)
    app.include_router(servers.router)
    app.include_router(server_tools.router)
    return types.SimpleNamespace(client=TestClient(app), db=server_db, answers=answers)


def test_adding_servers_names_them_and_keeps_the_key_secret(api):
    r = api.client.post("/api/servers", json={"type": "jellyfin", "url": "jf1", "token": "k" * 32})
    assert r.status_code == 200, r.text
    first = r.json()
    assert first["name"] == "Jellyfin" and first["url"] == "http://jf1:8096" and first["primary"] is True
    assert "k" * 32 not in r.text and first["has_key"] is True
    second = api.client.post("/api/servers", json={"type": "jellyfin", "url": "http://jf2:8096", "token": "m" * 32})
    assert second.json()["name"] == "Jellyfin 2" and second.json()["primary"] is False
    setting = api.db.query(models.Setting).first()
    api.db.refresh(setting)
    assert setting.jellyfin_url == "http://jf1:8096"  # the first one stays where old pages look
    listed = api.client.get("/api/servers").json()["servers"]
    assert [s["name"] for s in listed] == ["Jellyfin", "Jellyfin 2"]


@pytest.mark.parametrize("body, field, words", [
    ({"type": "plex", "url": "ftp://nope", "token": "t" * 20}, "url", "http://"),
    ({"type": "plex", "url": "", "token": "t" * 20}, "url", "Enter the address"),
    ({"type": "jellyfin", "url": "http://jf:8096", "token": "short"}, "token", "too short"),
    ({"type": "emby", "url": "http://e:8096", "token": "has space in it here"}, "token", "spaces"),
])
def test_bad_input_is_named_per_field(api, body, field, words):
    r = api.client.post("/api/servers", json=body)
    assert r.status_code == 422
    assert words in r.json()["error"]["fields"][field]


def test_a_server_that_doesnt_answer_or_refuses_the_key_is_not_added(api):
    api.answers["http://down:32400"] = {**GOOD, "reachable": False, "signed_in": False,
                                        "message": "Plex didn't answer at http://down:32400.", "hint": "Check it."}
    r = api.client.post("/api/servers", json={"type": "plex", "url": "http://down:32400", "token": "t" * 20})
    assert r.status_code == 502 and r.json()["error"]["fields"]["url"].startswith("Plex didn't answer")
    api.answers["http://locked:32400"] = {**GOOD, "signed_in": False, "message": "Plex turned down the token."}
    r = api.client.post("/api/servers", json={"type": "plex", "url": "http://locked:32400", "token": "t" * 20})
    assert r.status_code == 502 and r.json()["error"]["code"] == "plex_auth_failed"
    assert "token" in r.json()["error"]["fields"]
    assert ms.ordered(api.db) == []


def test_duplicate_names_and_servers_are_refused(api):
    add(api.db, "plex", "Living room", "http://p1:32400")
    r = api.client.post("/api/servers", json={"type": "plex", "name": "living ROOM", "url": "http://p2:32400",
                                              "token": "t" * 20})
    assert r.status_code == 409 and r.json()["error"]["fields"]["name"] == \
        "There's already a media server called \"living ROOM\"."
    r = api.client.post("/api/servers", json={"type": "plex", "url": "http://p1:32400/", "token": "t" * 20})
    assert r.status_code == 409 and "already on the list as \"Living room\"" in r.json()["detail"]


def test_rename_switch_off_and_remove(api):
    jf = add(api.db, "jellyfin", "Jellyfin", "http://jf1:8096", plugin_key_id=None)
    key = models.APIKey(name="Jellyfin Plugin (Auto) · Jellyfin", key_hash="h", key_prefix="p", permissions="read",
                        is_active=True)
    api.db.add(key)
    api.db.commit()
    jf.plugin_key_id = key.id
    api.db.commit()
    r = api.client.put(f"/api/servers/{jf.id}", json={"name": "  Living   room "})
    assert r.json()["name"] == "Living room"
    add(api.db, "emby", "Emby", "http://e:8096")
    assert api.client.put(f"/api/servers/{jf.id}", json={"name": "emby"}).status_code == 409
    assert api.client.put(f"/api/servers/{jf.id}", json={"name": ""}).status_code == 422
    r = api.client.put(f"/api/servers/{jf.id}", json={"enabled": False})
    assert r.json()["enabled"] is False and r.json()["primary"] is False
    jf_id, key_id = jf.id, key.id
    r = api.client.delete(f"/api/servers/{jf_id}")
    assert r.json() == {"deleted": True, "name": "Living room"}
    api.db.expire_all()
    assert api.db.get(models.APIKey, key_id).is_active is False  # its plugin key stops working
    assert f"media_server_{jf_id}" not in api.db.secrets
    assert api.client.get(f"/api/servers/{jf_id}").status_code == 404


def test_a_new_address_is_checked_before_it_is_saved(api):
    plex = add(api.db, "plex", "Den", "http://p1:32400")
    api.answers["http://p9:32400"] = {**GOOD, "reachable": False, "message": "Plex didn't answer.", "hint": None}
    r = api.client.put(f"/api/servers/{plex.id}", json={"url": "http://p9:32400"})
    assert r.status_code == 502
    api.db.refresh(plex)
    assert plex.url == "http://p1:32400"


def test_the_connection_test_lists_plain_steps(api, monkeypatch):
    jf = add(api.db, "jellyfin", "Bedroom", "http://jf1:8096")
    monkeypatch.setattr(server_probe, "plugin_info", lambda target: {"installed": False})
    body = api.client.post(f"/api/servers/{jf.id}/test").json()
    states = {s["id"]: s["state"] for s in body["steps"]}
    assert states == {"reach": "ok", "key": "ok", "plugin": "fail", "asked": "skipped"}
    plugin = next(s for s in body["steps"] if s["id"] == "plugin")
    assert plugin["title"] == "The Prerolls Max plugin is installed in Bedroom"
    api.answers["http://jf1:8096"] = {**GOOD, "reachable": False, "signed_in": False,
                                      "message": "Jellyfin didn't answer at http://jf1:8096.", "hint": "Check it."}
    body = api.client.post(f"/api/servers/{jf.id}/test").json()
    assert [s["state"] for s in body["steps"]][:2] == ["fail", "skipped"]


def test_folder_mapping_is_per_plex_server(api):
    den = add(api.db, "plex", "Den", "http://p1:32400")
    loft = add(api.db, "plex", "Loft", "http://p2:32401")
    r = api.client.put(f"/api/servers/{loft.id}/folder-mapping",
                       json={"mappings": [{"local": "/data/prerolls", "plex": "/media/intros"}]})
    assert r.status_code == 200 and r.json()["primary"] is False
    r = api.client.put(f"/api/servers/{loft.id}/folder-mapping", json={"mappings": [{"local": "data", "plex": "/x"}]})
    assert r.status_code == 422 and "mappings.0.local" in r.json()["error"]["fields"]
    assert api.client.get(f"/api/servers/{den.id}/folder-mapping").json()["mappings"] == []
    jf = add(api.db, "jellyfin", "JF", "http://jf:8096")
    assert api.client.get(f"/api/servers/{jf.id}/folder-mapping").status_code == 409


# -- Play a test -----------------------------------------------------------------------

def test_play_test_names_what_the_server_would_play(api, monkeypatch):
    plex = add(api.db, "plex", "Den", "http://p1:32400")
    monkeypatch.setattr(server_probe, "movie_title", lambda t, i: "Night of the Test")
    monkeypatch.setattr(server_probe, "intros", lambda t, i: {"ok": True, "items": [
        {"title": "Pumpkin Intro", "path": "/prerolls/Pumpkin Intro.mp4"},
        {"title": "Ghost Intro", "path": "/prerolls/Ghost Intro.mp4"}]})
    monkeypatch.setattr(server_probe, "plex_intro_list", lambda t: "/a.mp4,/b.mp4")
    body = api.client.post(f"/api/servers/{plex.id}/play-test", json={"item_id": "12"}).json()
    assert body["summary"] == "Before \"Night of the Test\", Den will play: Pumpkin Intro, Ghost Intro"
    assert body["reasons"] == []


def test_play_test_explains_an_empty_answer(api, monkeypatch):
    plex = add(api.db, "plex", "Den", "http://p1:32400")
    jf = add(api.db, "jellyfin", "Bedroom", "http://jf:8096")
    monkeypatch.setattr(server_probe, "movie_title", lambda t, i: "Sandbox Story")
    monkeypatch.setattr(server_probe, "intros", lambda t, i: {"ok": True, "items": []})
    monkeypatch.setattr(server_probe, "plex_intro_list", lambda t: "")
    body = api.client.post(f"/api/servers/{plex.id}/play-test", json={"item_id": "12"}).json()
    assert body["summary"] == "Before \"Sandbox Story\", Den would play no intro."
    assert body["reasons"][0]["title"] == "Nothing is set to play"
    monkeypatch.setattr(server_probe, "plugin_info", lambda t: {"installed": False})
    body = api.client.post(f"/api/servers/{jf.id}/play-test", json={"item_id": "abc"}).json()
    assert body["reasons"][0]["title"] == "The plugin isn't installed"
    assert server_play_test.is_test({"item_id": "ABC"})  # the plugin's own request isn't counted


def test_play_test_refuses_a_strange_item_id(api):
    plex = add(api.db, "plex", "Den", "http://p1:32400")
    assert api.client.post(f"/api/servers/{plex.id}/play-test", json={"item_id": "../x"}).status_code == 422


def test_emby_cache_names_are_turned_back_into_intro_names(api, monkeypatch, tmp_path):
    import hashlib
    path = str(tmp_path / "Pumpkin Intro.mp4")
    row = models.Preroll(filename="Pumpkin Intro.mp4", display_name="Pumpkin Intro", path=path, enabled=True)
    api.db.add(row)
    api.db.commit()
    try:
        emby = add(api.db, "emby", "Den Emby", "http://e:8096")
        cached = hashlib.sha256(path.encode()).hexdigest()[:24] + "-0a1b2c3d4e5f"
        monkeypatch.setattr(server_probe, "movie_title", lambda t, i: "Night of the Test")
        monkeypatch.setattr(server_probe, "intros", lambda t, i: {"ok": True, "items": [
            {"title": cached, "path": f"/config/cache/{cached}.mp4"}]})
        body = api.client.post(f"/api/servers/{emby.id}/play-test", json={"item_id": "123"}).json()
        assert body["summary"] == "Before \"Night of the Test\", Den Emby will play: Pumpkin Intro"
    finally:
        api.db.delete(row)
        api.db.commit()
