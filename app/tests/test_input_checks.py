"""Request checks and plain-language errors on the real app (CONTRACTS.md §1-2)."""
import pytest
from fastapi.testclient import TestClient

from backend import main, models
from backend.database import SessionLocal
from backend.errors import AppError
from fastapi import HTTPException

from tests.test_first_run_and_roles import _wipe_accounts


@pytest.fixture
def admin():
    _wipe_accounts()
    db = SessionLocal()
    try:
        db.query(models.Schedule).delete()
        db.query(models.Category).filter(models.Category.name.in_(
            ["Halloween", "Kids", "Night", "Dupes"])).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    client = TestClient(main.app, raise_server_exceptions=False)
    r = client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"})
    assert r.status_code == 200
    yield client
    _wipe_accounts()


def _error(r, status):
    assert r.status_code == status, r.text
    body = r.json()
    assert body["detail"] == body["error"]["message"]
    return body["error"]


def test_app_errors_pass_through_except_httpexception_blocks():
    assert isinstance(AppError("x"), HTTPException)
    err = main._failed(AppError("Plain.", status=409), "Other.")
    assert err.status_code == 409 and str(err) == "Plain."
    err = main._failed(KeyError("secret_column"), "That didn't save.")
    assert err.status_code == 500 and err.message == "That didn't save." and "secret" not in err.message


def test_collection_names_are_unique_ignoring_case(admin):
    assert admin.post("/categories", json={"name": "  Halloween  "}).json()["name"] == "Halloween"
    err = _error(admin.post("/categories", json={"name": "HALLOWEEN"}), 409)
    assert err["message"] == 'There is already a collection called "Halloween".'
    assert err["fields"]["name"]
    kids = admin.post("/categories", json={"name": "Kids"}).json()
    err = _error(admin.put(f"/categories/{kids['id']}", json={"name": "halloween"}), 409)
    assert "Halloween" in err["message"]
    _error(admin.post("/categories", json={"name": "   "}), 422)
    _error(admin.post("/categories", json={"name": "x" * 101}), 422)
    _error(admin.post("/categories", json={"name": "Night", "plex_mode": "loud"}), 422)
    assert admin.post("/categories", json={"name": "Night", "plex_mode": "Playlist"}).json()["plex_mode"] == "playlist"


def test_schedule_dates_are_checked_and_named(admin):
    cat = admin.post("/categories", json={"name": "Dupes"}).json()
    base = {"name": "Movie night", "type": "daily", "category_id": cat["id"]}
    err = _error(admin.post("/schedules", json={**base, "start_date": "2026-13-45"}), 422)
    assert "start_date" in err["fields"]
    err = _error(admin.post("/schedules", json={**base, "start_date": "2026-05-02T10:00",
                                                 "end_date": "2026-05-01T10:00"}), 422)
    assert err["fields"]["end_date"] == "The end must be after the start."
    err = _error(admin.post("/schedules", json={**base, "start_date": "2026-05-01", "type": "hourly"}), 422)
    assert "type" in err["fields"]
    err = _error(admin.post("/schedules", json={**base, "start_date": "2026-05-01", "priority": 11}), 422)
    assert err["fields"]["priority"] == "Use 10 or less."
    # A browser's zone suffix is dropped, not converted: times are on Prerolls Max's clock.
    r = admin.post("/schedules", json={**base, "start_date": "2026-05-01T18:30:00-07:00",
                                        "end_date": "2026-05-02T02:00:00Z"})
    assert r.status_code == 200, r.text
    assert r.json()["start_date"] == "2026-05-01T18:30:00"
    assert r.json()["end_date"] == "2026-05-02T02:00:00"
    # Yearly windows may wrap past New Year.
    r = admin.post("/schedules", json={**base, "name": "Winter", "type": "yearly", "start_date": "2026-12-15T00:00",
                                        "end_date": "2026-01-15T00:00"})
    assert r.status_code == 200, r.text
    err = _error(admin.post("/schedules", json={**base, "start_date": "2026-05-01", "category_id": 999999}), 422)
    assert "doesn't exist" in err["message"] and "999999" not in err["message"]


def test_generic_settings_only_take_known_keys(admin):
    _error(admin.put("/settings/auth_enabled", json=False), 422)  # not a dict/list body
    err = _error(admin.put("/settings/plex_token", json=["x"]), 404)
    assert err["code"] == "unknown_setting"
    _error(admin.get("/settings/plex_token"), 404)
    _error(admin.put("/settings/dashboard_tile_order", json=["ok", "<script>"]), 422)
    assert admin.put("/settings/dashboard_tile_order", json=["prerolls", "schedules", "prerolls"]).status_code == 200
    assert admin.get("/settings/dashboard_tile_order").json() == ["prerolls", "schedules"]


def test_external_register_needs_an_existing_video_file(admin, tmp_path):
    key = admin.post("/api/keys?name=automation").json()["key"]
    api = TestClient(main.app, raise_server_exceptions=False, headers={"X-Api-Key": key})
    err = _error(api.post("/external/prerolls/register", json={"path": "relative/clip.mp4"}), 422)
    assert "path" in err["fields"]
    err = _error(api.post("/external/prerolls/register", json={"path": "/etc/passwd"}), 422)
    assert "isn't a video file" in err["message"]
    err = _error(api.post("/external/prerolls/register", json={"path": str(tmp_path / "missing.mp4")}), 404)
    assert err["code"] == "file_not_found"
    folder = tmp_path / "folder.mp4"
    folder.mkdir()
    _error(api.post("/external/prerolls/register", json={"path": str(folder)}), 404)
    _error(api.post("/external/prerolls/register", json={"path": str(tmp_path / ".." / "x.mp4")}), 422)
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"\x00")
    r = api.post("/external/prerolls/register", json={"path": str(clip)})
    assert r.status_code == 200 and r.json()["preroll"]["filename"] == "clip.mp4"
    db = SessionLocal()
    try:
        db.query(models.Preroll).filter(models.Preroll.path == str(clip)).delete()
        db.commit()
    finally:
        db.close()


def test_plex_connect_checks_the_address_and_token(admin):
    err = _error(admin.post("/plex/connect", json={"url": "ftp://plex", "token": "abcdefghij"}), 422)
    assert err["fields"]["url"] == "The address must start with http:// or https://."
    err = _error(admin.post("/plex/connect", json={"url": "192.168.1.5:32400", "token": "ab cd"}), 422)
    assert "token" in err["fields"]


def test_unreachable_plex_says_so_in_plain_words(admin, monkeypatch):
    import requests

    def refuse(*a, **k):
        raise requests.exceptions.ConnectionError("Max retries exceeded with url: /identity")

    monkeypatch.setattr(main.requests, "get", refuse)
    monkeypatch.setattr(main.PlexConnector, "test_connection", lambda self: False)
    err = _error(admin.post("/plex/connect", json={"url": "http://10.9.8.7:32400", "token": "abcdefghij"}), 502)
    assert err["code"] == "plex_unreachable"
    assert err["message"] == "Plex didn't answer at http://10.9.8.7:32400."

    class Ok:
        status_code = 200
    monkeypatch.setattr(main.requests, "get", lambda *a, **k: Ok())
    err = _error(admin.post("/plex/connect", json={"url": "http://10.9.8.7:32400", "token": "abcdefghij"}), 502)
    assert err["code"] == "plex_auth_failed"


def test_restore_refuses_a_file_that_isnt_a_backup(admin):
    err = _error(admin.post("/restore/database", json={"hello": "world"}), 422)
    assert err["code"] == "not_a_backup"
    err = _error(admin.post("/restore/database", json={"categories": "nope"}), 422)
    assert "damaged" in err["message"]


def test_radarr_connect_checks_address_and_key_from_body_or_query(admin):
    err = _error(admin.post("/nexup/radarr/connect", json={"url": "javascript:alert(1)", "api_key": "short"}), 422)
    assert set(err["fields"]) == {"url", "api_key"}
    err = _error(admin.post("/nexup/sonarr/connect?url=ftp://x&api_key=0123456789abcdef0123"), 422)
    assert set(err["fields"]) == {"url"}


def test_log_settings_are_checked(admin):
    err = _error(admin.put("/logs/settings", json={"log_level": "LOUD"}), 422)
    assert "log_level" in err["fields"]
    _error(admin.put("/logs/settings", json={"log_retention_days": 0}), 422)
    assert admin.put("/logs/settings", json={"log_level": "warning"}).json()["log_level"] == "WARNING"
