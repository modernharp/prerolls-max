"""Small backend gaps the new web interface ran into (second pass).

Each test names what the interface needs: a JSON body where only the query
string worked, a partial schedule update, a server-side check that an upload
is a video, and plain errors (CONTRACTS.md section 1) when Jellyfin or Emby
can't be reached.
"""
import io
import uuid

import pytest
import requests
from fastapi.testclient import TestClient

from backend import main, models, uploads
from backend.database import SessionLocal
from tests.test_first_run_and_roles import _wipe_accounts

MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.fixture
def admin():
    _wipe_accounts()
    db = SessionLocal()
    try:
        db.query(models.Schedule).delete()
        setting = db.query(models.Setting).first()
        if setting:
            setting.filler_category_id = None
            setting.filler_enabled = False
        db.commit()
    finally:
        db.close()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    yield client
    _wipe_accounts()


def _error(r, status):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["detail"] == body["error"]["message"]
    return body["error"]


# --- uploads ----------------------------------------------------------------

@pytest.mark.parametrize("ext,head,ok", [
    (".mp4", MP4_HEAD, True),
    (".mov", b"\x00\x00\x00\x14ftypqt  ", True),
    (".mkv", b"\x1a\x45\xdf\xa3\x01\x00", True),
    (".webm", b"\x1a\x45\xdf\xa3\x01\x00", True),
    (".avi", b"RIFF\x00\x00\x00\x00AVI LIST", True),
    (".mpg", b"\x00\x00\x01\xba\x44", True),
    (".mp4", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, False),
    (".mp4", b"<!doctype html><html>", False),
    (".mkv", b"%PDF-1.7", False),
])
def test_looks_like_video(ext, head, ok):
    assert uploads.looks_like_video(head, ext) is ok


def test_upload_refuses_a_picture_renamed_to_mp4(admin):
    fake = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    r = admin.post("/prerolls/upload", files={"file": ("holiday.mp4", fake, "video/mp4")})
    err = _error(r, 422)
    assert err["code"] == "not_a_video"
    assert err["fields"]["file"]


def test_upload_multiple_reports_the_non_video_and_carries_on(admin):
    r = admin.post("/prerolls/upload-multiple",
                   files=[("files", ("notes.mp4", io.BytesIO(b"just some text" * 20), "video/mp4"))])
    assert r.status_code == 200, r.text
    result = r.json()["results"][0]
    assert result["uploaded"] is False
    assert "isn't a video" in result["error"]


# --- JSON bodies --------------------------------------------------------------

def test_api_keys_take_a_json_body_and_still_the_query_string(admin):
    r = admin.post("/api/keys", json={"name": "From JSON", "permissions": "read"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "From JSON" and r.json()["permissions"] == "read"
    key_id = r.json()["id"]
    r = admin.put(f"/api/keys/{key_id}", json={"name": "Renamed", "is_active": False})
    assert r.status_code == 200, r.text
    keys = {k["id"]: k for k in admin.get("/api/keys").json()["keys"]}
    assert keys[key_id]["name"] == "Renamed" and keys[key_id]["is_active"] is False
    assert admin.post("/api/keys?name=From%20query").status_code == 200
    err = _error(admin.post("/api/keys", json={"name": "  "}), 422)
    assert "name" in err["fields"]


def test_default_intros_take_a_json_body(admin):
    db = SessionLocal()
    try:
        cat = models.Category(name=f"Gaps {uuid.uuid4().hex[:8]}")
        db.add(cat)
        db.commit()
        cat_id = cat.id
    finally:
        db.close()
    r = admin.put("/settings/filler", json={"enabled": True, "type": "category", "category_id": cat_id})
    assert r.status_code == 200, r.text
    got = admin.get("/settings/filler").json()
    assert got["enabled"] is True and got["category_id"] == cat_id
    assert admin.put("/settings/filler?enabled=false").status_code == 200
    assert admin.get("/settings/filler").json()["enabled"] is False
    err = _error(admin.put("/settings/filler", json={"category_id": 999999}), 422)
    assert "category_id" in err["fields"]


# --- partial schedule updates -----------------------------------------------

def test_schedule_put_changes_only_the_fields_sent(admin):
    cat = admin.post("/categories", json={"name": f"Gaps {uuid.uuid4().hex[:8]}"}).json()
    created = admin.post("/schedules", json={
        "name": "Spooky", "type": "yearly", "start_date": "2000-10-01T00:00", "end_date": "2000-10-31T23:59",
        "category_id": cat["id"], "priority": 7, "exclusive": True,
        "recurrence_pattern": '{"timeRange": {"start": "18:00", "end": "23:00"}}',
    })
    assert created.status_code == 200, created.text
    sid = created.json()["id"]
    r = admin.put(f"/schedules/{sid}", json={"is_active": False})
    assert r.status_code == 200, r.text
    saved = next(s for s in admin.get("/schedules").json() if s["id"] == sid)
    assert saved["is_active"] is False
    assert saved["name"] == "Spooky" and saved["priority"] == 7 and saved["exclusive"] is True
    assert saved["start_date"].startswith("2000-10-01") and saved["end_date"].startswith("2000-10-31")
    assert "18:00" in saved["recurrence_pattern"]
    err = _error(admin.put(f"/schedules/{sid}", json={"priority": 42}), 422)
    assert "priority" in err["fields"]


# --- Jellyfin and Emby: plain errors ------------------------------------------

def test_jellyfin_that_doesnt_answer_is_a_502_with_a_hint(admin, monkeypatch):
    from backend import jellyfin_connector
    monkeypatch.setattr(jellyfin_connector.JellyfinConnector, "test_connection", lambda self: False)
    err = _error(admin.post("/jellyfin/connect", json={"url": "192.168.1.9", "api_key": "a" * 32}), 502)
    assert err["code"] == "jellyfin_unreachable"
    assert "http://192.168.1.9:8096" in err["message"] and err["hint"]


def test_jellyfin_that_refuses_the_key_says_so(admin, monkeypatch):
    from backend import jellyfin_connector
    monkeypatch.setattr(jellyfin_connector.JellyfinConnector, "test_connection", lambda self: True)
    monkeypatch.setattr(jellyfin_connector.JellyfinConnector, "test_api_key", lambda self: False)
    err = _error(admin.post("/jellyfin/connect", json={"url": "http://jf:8096", "api_key": "b" * 32}), 502)
    assert err["code"] == "jellyfin_auth_failed" and "API key" in err["message"]


def test_emby_that_doesnt_answer_is_a_502(admin, monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(main.requests, "get", boom)
    err = _error(admin.post("/emby/connect", json={"url": "http://emby:8096", "api_key": "c" * 32}), 502)
    assert err["code"] == "emby_unreachable"
    assert "refused" not in err["message"]


def test_connect_checks_the_form_fields(admin):
    err = _error(admin.post("/jellyfin/connect", json={"url": "ftp://x", "api_key": "short"}), 422)
    assert set(err["fields"]) == {"url", "api_key"}


def test_plugin_setup_before_connecting_explains_what_to_do(admin):
    db = SessionLocal()
    try:
        setting = db.query(models.Setting).first()
        if setting:
            setting.jellyfin_url = None
            db.commit()
    finally:
        db.close()
    err = _error(admin.post("/jellyfin/plugin/configure", json={"nexroll_url": "http://pmax:9393"}), 409)
    assert err["code"] == "server_not_connected" and "Media Servers" in err["hint"]

