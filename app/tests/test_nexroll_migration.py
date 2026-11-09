"""Settings > Moving from NeXroll: the three ways in, the import, finding
videos again, "is NeXroll still running?", and keeping both.

The NeXroll database here is built from the schema real NeXroll 2.4.0
created (tests/fixtures/nexroll_2_4_0_schema.sql, dumped from a running
NeXroll), with rows shaped like the ones NeXroll's own API writes.
"""
import base64
import hashlib
import io
import json
import os
import socket
import sqlite3
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from backend import (coexist, jobs, main, media_servers, models, nexroll_detect, nexroll_import, nexroll_source,
                     port_config)
from backend.database import SessionLocal
from backend.errors import AppError
from tests.media_server_fixtures import secrets  # noqa: F401 (fixture)
from tests.test_first_run_and_roles import _wipe_accounts

SCHEMA = os.path.join(os.path.dirname(__file__), "fixtures", "nexroll_2_4_0_schema.sql")


def _video(path, seed):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = b"\x00\x00\x00\x18ftypmp42" + seed.encode() * 64
    with open(path, "wb") as fh:
        fh.write(data)
    return hashlib.sha256(data).hexdigest()


def make_nexroll(folder, videos_dir, *, missing_folder="D:\\Prerolls", plex_url="http://192.168.1.5:32400"):
    """A NeXroll 2.4.0 data folder: nexroll.db plus secrets.json."""
    os.makedirs(folder, exist_ok=True)
    db_path = os.path.join(folder, "nexroll.db")
    con = sqlite3.connect(db_path)
    con.executescript(open(SCHEMA, encoding="utf-8").read())
    con.execute("PRAGMA journal_mode=WAL")
    con.executemany("INSERT INTO categories (id, name, description, plex_mode, apply_to_plex, is_system) "
                    "VALUES (?, ?, ?, 'shuffle', 0, 0)",
                    [(1, "Halloween", "Spooky"), (2, "Christmas", "Holidays"), (3, "Everyday", "All year")])
    h1 = _video(os.path.join(videos_dir, "Halloween", "Ghost Walk.mp4"), "ghost")
    h2 = _video(os.path.join(videos_dir, "Everyday", "Popcorn Time.mp4"), "popcorn")
    rows = [
        (1, "Ghost Walk.mp4", os.path.join(videos_dir, "Halloween", "Ghost Walk.mp4"), 1, h1),
        (2, "Popcorn Time.mp4", os.path.join(videos_dir, "Everyday", "Popcorn Time.mp4"), 3, h2),
        (3, "Snow Globe.mp4", missing_folder + "\\Christmas\\Snow Globe.mp4", 2, None),
    ]
    con.executemany("INSERT INTO prerolls (id, filename, path, category_id, file_hash, tags, managed, enabled, "
                    "upload_date) VALUES (?, ?, ?, ?, ?, '[\"test\"]', 1, 1, '2026-11-08 20:23:48.566314')", rows)
    con.executemany("INSERT INTO preroll_categories (preroll_id, category_id) VALUES (?, ?)",
                    [(1, 1), (2, 3), (2, 1), (3, 2)])
    blocks = json.dumps([{"type": "random", "category_id": 3, "count": 1}, {"type": "fixed", "preroll_id": 2}])
    con.execute("INSERT INTO saved_sequences (id, name, description, blocks, created_at, updated_at) "
                "VALUES (1, 'Movie night', 'One random, then popcorn', ?, '2026-11-08 20:23:50', "
                "'2026-11-08 20:23:50')", (blocks,))
    con.executemany(
        "INSERT INTO schedules (id, name, type, start_date, end_date, category_id, playlist, is_active, priority, "
        "exclusive, blend_enabled, sequence, source_sequence_id, recurrence_pattern) "
        "VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, 0, ?, ?, ?)",
        [(1, "Halloween month", "monthly", "2026-10-01 00:00:00.000000", "2026-10-31 23:59:00.000000", 1, 7, 0,
          None, None, None),
         (2, "Christmas", "yearly", "2026-12-01 00:00:00.000000", "2026-12-26 23:59:00.000000", 2, 5, 1,
          None, None, None),
         (3, "Friday movie night", "weekly", "2026-01-01 00:00:00.000000", None, None, 5, 0, blocks, 1,
          json.dumps({"weekDays": ["friday"]}))])
    con.execute("INSERT INTO settings (plex_url, jellyfin_url, auth_enabled, timezone, path_mappings) "
                "VALUES (?, 'http://192.168.1.6:8096', 1, 'Europe/London', ?)",
                (plex_url, json.dumps([{"local": "D:\\Prerolls", "plex": "/media/prerolls"}])))
    con.execute("INSERT INTO users (username, password_hash, display_name, role, is_active, created_at) "
                "VALUES ('jf', 'x', 'JF', 'admin', 1, '2026-01-01')")
    con.executemany("INSERT INTO api_keys (name, key_hash, key_prefix, permissions, is_active, created_at) "
                    "VALUES (?, ?, 'nx_abc', 'read', 1, '2026-01-01')", [("Dashboard", "h1"), ("Plugin", "h2")])
    con.commit()
    con.close()
    with open(os.path.join(folder, "secrets.json"), "w") as fh:
        json.dump({"plex_token": base64.b64encode(b"plex-token-from-nexroll").decode(),
                   "jellyfin_api_key": {"b64": base64.b64encode(b"jf-key-from-nexroll").decode()}}, fh)
    return db_path


@pytest.fixture
def nexroll(tmp_path):
    folder = tmp_path / "NeXroll"
    videos = tmp_path / "nexroll-videos"
    return make_nexroll(str(folder), str(videos)), str(videos)


@pytest.fixture
def clean_library():
    """The shared test database without collections, videos, schedules or playlists."""
    def wipe():
        db = SessionLocal()
        try:
            for table in ("preroll_categories",):
                db.execute(models.Base.metadata.tables[table].delete())
            for col in ("active_category", "nexup_category_id", "nexup_tv_category_id", "filler_category_id",
                        "filler_sequence_id"):
                db.execute(models.Setting.__table__.update().values({col: None}))
            for model in (models.Schedule, models.SavedSequence, models.HolidayPreset, models.GenreMap,
                          models.Preroll, models.MediaServer):
                db.query(model).delete(synchronize_session=False)
            db.query(models.Category).filter(models.Category.is_system.isnot(True)).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()
    wipe()
    yield
    wipe()


@pytest.fixture
def admin(tmp_path, secrets, clean_library):  # noqa: F811
    _wipe_accounts()
    coexist.configure(str(tmp_path / "coexist"))
    nexroll_detect.reset()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    state = nexroll_import._state_path()
    yield client
    if state and os.path.exists(state):
        os.remove(state)
    coexist.configure(None)
    _wipe_accounts()


def wait(client, answer):
    assert answer.status_code == 200, answer.text
    job = jobs.runner.wait(answer.json()["job_id"], timeout=30)
    assert job["state"] == "done", job
    return job["result"]


# ---------------------------------------------------------------------------
# Reading NeXroll's data
# ---------------------------------------------------------------------------

def test_the_database_is_read_through_a_copy_and_never_changed(nexroll):
    path, videos = nexroll
    before = open(path, "rb").read()
    data = nexroll_source.backup_from_db(path)
    assert open(path, "rb").read() == before
    assert [c["name"] for c in data["categories"]] == ["Halloween", "Christmas", "Everyday"]
    popcorn = next(p for p in data["prerolls"] if p["filename"] == "Popcorn Time.mp4")
    assert sorted(c["name"] for c in popcorn["categories"]) == ["Everyday", "Halloween"]
    assert popcorn["managed"] is True and popcorn["enabled"] is True
    assert data["saved_sequences"][0]["blocks"][1] == {"type": "fixed", "preroll_id": 2}
    assert data["settings"]["plex_url"] == "http://192.168.1.5:32400"
    assert data["credentials"] == {"plex_token": "plex-token-from-nexroll", "jellyfin_api_key": "jf-key-from-nexroll"}
    assert data["_nexroll"] == {"users": 1, "api_keys": 2, "source": "database", "where": path}


def test_a_read_only_folder_still_works(nexroll, tmp_path):
    path, _ = nexroll
    os.chmod(os.path.dirname(path), 0o555)
    try:
        data = nexroll_source.backup_from_db(path)
    finally:
        os.chmod(os.path.dirname(path), 0o755)
    assert len(data["prerolls"]) == 3


def test_something_else_is_not_a_nexroll_database(tmp_path):
    other = tmp_path / "nexroll.db"
    con = sqlite3.connect(str(other))
    con.execute("CREATE TABLE notes (x)")
    con.close()
    with pytest.raises(AppError) as err:
        nexroll_source.backup_from_db(str(other))
    assert err.value.code == "not_nexroll"


def test_known_places_on_windows_and_a_typed_folder(tmp_path, nexroll):
    env = {"ProgramData": "C:\\ProgramData", "LOCALAPPDATA": "C:\\Users\\jf\\AppData\\Local"}
    places = nexroll_source.known_locations("win32", env)
    assert places[:2] == [os.path.join("C:\\ProgramData", "NeXroll"), os.path.join(env["LOCALAPPDATA"], "NeXroll")]
    path, _ = nexroll
    assert nexroll_source.database_in(os.path.dirname(path)) == path
    assert nexroll_source.database_in(path) == path  # the file itself is fine too
    for typed, words in (("data/nexroll", "full path"), (str(tmp_path / "nothing"), "can't see a folder"),
                         (str(tmp_path), "no nexroll.db"), ("/data/../etc", "..")):
        with pytest.raises(AppError) as err:
            nexroll_source.database_in(typed)
        assert err.value.fields and "path" in err.value.fields
        assert words in err.value.message


def _zip_backup(tmp_path, data, videos):
    target = tmp_path / "nexroll_system_backup.zip"
    with zipfile.ZipFile(target, "w") as zf:
        zf.writestr("database/nexroll_data.json", json.dumps(data))
        for rel, content in videos.items():
            zf.writestr("prerolls/" + rel, content)
        zf.writestr("../escape.mp4", b"nope")
        zf.writestr("/abs/escape.mp4", b"nope")
        zf.writestr("thumbnails/Halloween/1_Ghost.jpg", b"jpg")
    return str(target)


def test_a_full_backup_zip_brings_its_videos_and_nothing_escapes(tmp_path, nexroll):
    path, _ = nexroll
    data = nexroll_source.backup_from_db(path)
    data.pop("_nexroll")
    for row in data["prerolls"]:
        row["path"] = "C:\\ProgramData\\NeXroll\\Prerolls\\" + row["path"].replace("/", "\\").split("\\")[-2] + \
            "\\" + row["filename"]
    zpath = _zip_backup(tmp_path, data, {"Halloween/Ghost Walk.mp4": b"ghost", "Christmas/Snow Globe.mp4": b"snow"})
    staging = tmp_path / "staging"
    staging.mkdir()
    got = nexroll_source.backup_from_upload(zpath, "nexroll_system_backup.zip", str(staging))
    assert sorted(got["_nexroll"]["files"]) == ["Christmas/Snow Globe.mp4", "Halloween/Ghost Walk.mp4"]
    assert not (tmp_path / "escape.mp4").exists() and not os.path.exists("/abs/escape.mp4")
    found = [p for p in got["prerolls"] if nexroll_import.file_found(p, got["_nexroll"]["files"])]
    assert sorted(p["filename"] for p in found) == ["Ghost Walk.mp4", "Snow Globe.mp4"]


def test_files_that_arent_nexroll_backups_are_turned_down(tmp_path):
    bad = tmp_path / "notes.json"
    bad.write_text('{"hello": 1}')
    with pytest.raises(AppError) as err:
        nexroll_source.backup_from_upload(str(bad), "notes.json", str(tmp_path))
    assert err.value.code == "not_a_backup"
    z = tmp_path / "x.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("readme.txt", "hi")
    with pytest.raises(AppError):
        nexroll_source.backup_from_upload(str(z), "x.zip", str(tmp_path))


# ---------------------------------------------------------------------------
# From a running NeXroll
# ---------------------------------------------------------------------------

def _fake_nexroll(monkeypatch, *, page=b"<html><title>NeXroll</title></html>", key=None, backup=None):
    calls = []

    def fake_get(url, headers, timeout=None, max_bytes=None):
        calls.append((url, dict(headers)))
        if url.endswith("/health"):
            return 200, b'{"status":"healthy"}'
        if url.endswith("/"):
            return 200, page
        if url.endswith("/backup/status") and key and headers.get("X-Api-Key") != key:
            return 401, b'{"detail":"Authentication required"}'
        if key and headers.get("X-Api-Key") != key:
            return 401, b'{"detail":"Authentication required"}'
        return 200, json.dumps(backup or {"schema_version": 5, "categories": [], "prerolls": []}).encode()
    monkeypatch.setattr(nexroll_source, "_get", fake_get)
    return calls


def test_fetch_sends_the_key_in_a_header_and_explains_a_sign_in(monkeypatch):
    calls = _fake_nexroll(monkeypatch, key="nx_right")
    with pytest.raises(AppError) as err:
        nexroll_source.fetch_backup("192.168.1.9")
    assert err.value.code == "nexroll_key_required" and "api_key" in err.value.fields
    assert calls[0][0] == "http://192.168.1.9:9393/health"
    with pytest.raises(AppError) as err:
        nexroll_source.fetch_backup("http://192.168.1.9:9393", "nx_wrong")
    assert err.value.code == "nexroll_auth_failed" and "api_key" in err.value.fields
    data = nexroll_source.fetch_backup("http://192.168.1.9:9393", "nx_right")
    assert data["_nexroll"]["keys_left_out"] is True
    assert calls[-2][0] == "http://192.168.1.9:9393/backup/status"
    assert calls[-1] == ("http://192.168.1.9:9393/backup/database",
                         {"Accept": "application/json", "User-Agent": "Prerolls Max (moving from NeXroll)",
                          "X-Api-Key": "nx_right"})
    assert all("api_key=" not in url for url, _ in calls)


def test_the_fetch_route_puts_sign_in_problems_on_the_key_field(admin, monkeypatch):
    _fake_nexroll(monkeypatch, key="nx_right")
    answer = admin.post("/api/migrate/nexroll/fetch", json={"url": "http://192.168.1.9:9393"})
    assert answer.status_code == 422 and answer.json()["error"]["fields"] == {"api_key": "Enter a NeXroll API key."}
    wrong = admin.post("/api/migrate/nexroll/fetch", json={"url": "http://192.168.1.9:9393", "api_key": "nx_wrong"})
    assert wrong.status_code == 502 and "api_key" in wrong.json()["error"]["fields"]
    result = wait(admin, admin.post("/api/migrate/nexroll/fetch", json={"url": "192.168.1.9", "api_key": "nx_right"}))
    assert result["preview"]["source"] == {"kind": "running", "where": "http://192.168.1.9:9393",
                                           "exported_by": None, "keys_left_out": True}


@pytest.mark.parametrize("address,words", [
    ("file:///etc/passwd", "http:// or https://"),
    ("ftp://nexroll", "http:// or https://"),
    ("http://user:pw@nexroll", "user name and password"),
])
def test_fetch_only_takes_web_addresses(address, words):
    with pytest.raises(AppError) as err:
        nexroll_source.fetch_backup(address)
    assert words in err.value.message and "url" in err.value.fields


def test_fetch_tells_prerolls_max_and_other_apps_apart(monkeypatch):
    _fake_nexroll(monkeypatch, page=b"<title>Prerolls Max</title>")
    with pytest.raises(AppError) as err:
        nexroll_source.fetch_backup("http://127.0.0.1:9393")
    assert "That's Prerolls Max" in err.value.message
    _fake_nexroll(monkeypatch, page=b"<title>Sonarr</title>")
    with pytest.raises(AppError) as err:
        nexroll_source.fetch_backup("http://127.0.0.1:8989")
    assert "isn't NeXroll" in err.value.message


def test_fetch_stops_reading_a_reply_that_is_too_big(monkeypatch):
    class Big:
        status_code = 200

        def iter_content(self, size):
            while True:
                yield b"x" * size

        def close(self):
            pass
    monkeypatch.setattr(nexroll_source.requests, "get", lambda *a, **kw: Big())
    with pytest.raises(AppError) as err:
        nexroll_source._get("http://x/backup/database", {}, max_bytes=1024 * 1024)
    assert err.value.code == "nexroll_reply_too_large"


# ---------------------------------------------------------------------------
# Preview and import through the API
# ---------------------------------------------------------------------------

def test_preview_counts_and_what_stays_behind(admin, nexroll):
    path, _ = nexroll
    result = wait(admin, admin.post("/api/migrate/nexroll/scan", json={"path": os.path.dirname(path)}))
    p = result["preview"]
    assert p["counts"] | {} == p["counts"]
    assert {k: p["counts"][k] for k in ("collections", "intro_videos", "videos_found", "videos_missing",
                                        "schedules", "playlists", "api_keys", "users")} == {
        "collections": 3, "intro_videos": 3, "videos_found": 2, "videos_missing": 1, "schedules": 3,
        "playlists": 1, "api_keys": 2, "users": 1}
    assert p["missing"]["folder"] == "D:\\Prerolls\\Christmas" and p["missing"]["examples"] == ["Snow Globe"]
    assert {s["type"] for s in p["servers"]} == {"plex", "jellyfin"}
    assert "the Plex sign-in" in p["keys"] and p["suggested_mode"] == "replace"
    assert any("API key" in line for line in p["left_behind"])
    assert "plex-token" not in json.dumps(result)  # keys are never sent to the page


def test_merge_joins_collections_reuses_videos_and_numbers_clashing_names(admin, nexroll, tmp_path):
    path, videos = nexroll
    db = SessionLocal()
    try:
        mine = models.Category(name="halloween", description="mine")
        db.add(mine)
        db.flush()
        same_file = models.Preroll(filename="Ghost Walk.mp4", path=os.path.join(videos, "Halloween", "Ghost Walk.mp4"),
                                   category_id=mine.id)
        db.add(same_file)
        db.add(models.Schedule(name="Christmas", type="daily", start_date=None))
        db.commit()
        mine_id, ghost_id = mine.id, same_file.id
    finally:
        db.close()
    auth_before = admin.get("/auth/status").json()
    preview = wait(admin, admin.post("/api/migrate/nexroll/scan", json={"path": path}))
    assert preview["preview"]["names_taken"]["collections"] == ["Halloween"]
    report = wait(admin, admin.post("/api/migrate/nexroll/import",
                                    json={"source_id": preview["source_id"], "mode": "merge"}))
    assert report["added"]["collections"] == 2 and report["matched"]["collections"] == 1
    assert report["added"]["intro_videos"] == 2 and report["matched"]["intro_videos"] == 1
    assert report["added"]["schedules"] == 3 and report["added"]["playlists"] == 1
    assert any('"Christmas" was saved as "Christmas (2)"' in r for r in report["renamed"])
    assert report["settings"] == "kept" and report["missing"]["count"] == 1
    db = SessionLocal()
    try:
        names = sorted(c.name for c in db.query(models.Category).filter(models.Category.is_system.isnot(True)))
        assert names == ["Christmas", "Everyday", "halloween"]
        ghost = db.get(models.Preroll, ghost_id)
        assert [c.id for c in ghost.categories] == [mine_id]
        friday = db.query(models.Schedule).filter(models.Schedule.name == "Friday movie night").one()
        movie_night = db.query(models.SavedSequence).filter(models.SavedSequence.name == "Movie night").one()
        popcorn = db.query(models.Preroll).filter(models.Preroll.filename == "Popcorn Time.mp4").one()
        everyday = db.query(models.Category).filter(models.Category.name == "Everyday").one()
        assert friday.source_sequence_id == movie_night.id
        assert json.loads(friday.sequence) == [{"type": "random", "category_id": everyday.id, "count": 1},
                                               {"type": "fixed", "preroll_id": popcorn.id}]
        servers = {r.type: r for r in media_servers.ordered(db)}
        assert media_servers.get_secret(servers["plex"]) == "plex-token-from-nexroll"
        assert media_servers.mappings(servers["plex"]) == [{"local": "D:\\Prerolls", "plex": "/media/prerolls"}]
        assert media_servers.get_secret(servers["jellyfin"]) == "jf-key-from-nexroll"
        assert db.query(models.Setting).first().timezone != "Europe/London"  # merge keeps our settings
    finally:
        db.close()
    assert admin.get("/auth/status").json()["auth_enabled"] == auth_before["auth_enabled"]

    # Merging the same data again adds nothing.
    again = wait(admin, admin.post("/api/migrate/nexroll/scan", json={"path": path}))
    report = wait(admin, admin.post("/api/migrate/nexroll/import",
                                    json={"source_id": again["source_id"], "mode": "merge"}))
    assert report["added"] == {"collections": 0, "intro_videos": 0, "schedules": 0, "playlists": 0,
                               "holidays": 0, "servers": 0, "arr": 0}
    assert "Nothing new" in report["message"]


def test_replace_needs_a_clear_yes_and_keeps_our_sign_in(admin, nexroll):
    path, _ = nexroll
    preview = wait(admin, admin.post("/api/migrate/nexroll/scan", json={"path": path}))
    refused = admin.post("/api/migrate/nexroll/import", json={"source_id": preview["source_id"], "mode": "replace"})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "confirm_replace"
    report = wait(admin, admin.post("/api/migrate/nexroll/import", json={
        "source_id": preview["source_id"], "mode": "replace", "confirm_replace": True, "include_keys": False}))
    assert report["added"]["intro_videos"] == 3 and report["added"]["schedules"] == 3
    assert report["keys_imported"] == []
    db = SessionLocal()
    try:
        setting = db.query(models.Setting).first()
        assert setting.timezone == "Europe/London"
        assert setting.auth_enabled  # NeXroll's login setting didn't switch ours
        plex = media_servers.ordered(db, "plex")[0]
        assert media_servers.get_secret(plex) is None  # keys left out on request
    finally:
        db.close()
    # The source is used up.
    gone = admin.post("/api/migrate/nexroll/import", json={"source_id": preview["source_id"], "mode": "merge"})
    assert gone.status_code == 410


def test_missing_videos_wait_for_their_folder_and_relink_finds_them(admin, nexroll, tmp_path):
    path, _ = nexroll
    preview = wait(admin, admin.post("/api/migrate/nexroll/scan", json={"path": path}))
    report = wait(admin, admin.post("/api/migrate/nexroll/import",
                                    json={"source_id": preview["source_id"], "mode": "merge"}))
    held = nexroll_import.held_ids()
    assert len(held) == 1 and report["missing"]["ids"] == sorted(held)
    # The library clean-up leaves it alone while it waits.
    db = SessionLocal()
    try:
        from backend import scanner
        library = tmp_path / "lib"
        _video(str(library / "x.mp4"), "x")
        scanner.reconcile_prerolls(db, prerolls_dir=str(library), auto_prune_missing=True)
        assert db.get(models.Preroll, next(iter(held))) is not None
    finally:
        db.close()
    new_home = tmp_path / "moved"
    _video(str(new_home / "Christmas" / "Snow Globe.mp4"), "snow")
    bad = admin.post("/api/migrate/nexroll/relink", json={"from_folder": "D:\\Prerolls", "to_folder": "moved"})
    assert bad.status_code == 422 and "to_folder" in bad.json()["error"]["fields"]
    answer = admin.post("/api/migrate/nexroll/relink", json={"from_folder": "D:\\Prerolls",
                                                             "to_folder": str(new_home)})
    assert answer.status_code == 200, answer.text
    assert answer.json()["relinked"] == 1 and answer.json()["still_missing"] == 0
    assert nexroll_import.held_ids() == set()
    status = admin.get("/api/migrate/nexroll").json()
    assert status["import"]["waiting"]["count"] == 0 and status["import"]["last"]["mode"] == "merge"


def test_an_uploaded_full_backup_copies_its_videos_into_the_library(admin, nexroll, tmp_path):
    path, _ = nexroll
    data = nexroll_source.backup_from_db(path)
    data.pop("_nexroll")
    for row in data["prerolls"]:
        folder = {"Ghost Walk.mp4": "Halloween", "Popcorn Time.mp4": "Everyday", "Snow Globe.mp4": "Christmas"}
        row["path"] = f"C:\\ProgramData\\NeXroll\\Prerolls\\{folder[row['filename']]}\\{row['filename']}"
    zpath = _zip_backup(tmp_path, data, {"Halloween/Ghost Walk.mp4": b"ghost-zip", "Everyday/Popcorn Time.mp4": b"pop",
                                         "Christmas/Snow Globe.mp4": b"snow"})
    with open(zpath, "rb") as fh:
        result = wait(admin, admin.post("/api/migrate/nexroll/upload",
                                        files={"file": ("nexroll_system_backup.zip", fh, "application/zip")}))
    assert result["preview"]["counts"]["videos_in_zip"] == 3 and result["preview"]["counts"]["videos_missing"] == 0
    report = wait(admin, admin.post("/api/migrate/nexroll/import",
                                    json={"source_id": result["source_id"], "mode": "merge"}))
    assert report["videos_copied"] == 3 and report["missing"]["count"] == 0
    db = SessionLocal()
    try:
        for row in db.query(models.Preroll).all():
            assert os.path.isfile(row.path) and row.path.startswith(main.PREROLLS_DIR)
    finally:
        db.close()


def test_migration_routes_are_admin_only(nexroll):
    _wipe_accounts()
    client = TestClient(main.app, raise_server_exceptions=False)
    client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"})
    client.post("/auth/logout")
    for method, url in (("get", "/api/migrate/nexroll"), ("post", "/api/migrate/nexroll/scan"),
                        ("post", "/api/migrate/nexroll/fetch"), ("post", "/api/migrate/nexroll/relink"),
                        ("put", "/api/migrate/nexroll/alongside")):
        answer = client.request(method.upper(), url, json={} if method != "get" else None)
        assert answer.status_code in (401, 403), (url, answer.status_code)
    _wipe_accounts()


# ---------------------------------------------------------------------------
# Is NeXroll still running?
# ---------------------------------------------------------------------------

# GET /Plugins as Jellyfin 12 and Emby answer it (ids as each server writes them).
JELLYFIN_PLUGINS = [
    {"Name": "TMDb", "Id": "b8715ed16c4745289ad3f72deb539cd4", "Version": "12.4.0.0", "Status": "Active"},
    {"Name": "Prerolls Max Intros", "Id": "c0a6ea9477954b61b9644ddfb93ec8b0", "Version": "2.1.0.0",
     "Status": "Active"},
    {"Name": "NeXroll Intros", "Id": "a1b2c3d4e5f67890abcdae0c01100001", "Version": "1.15.2.0", "Status": "Active"},
]
EMBY_PLUGINS = [
    {"Name": "Backup & Restore", "Id": "e711475e-efad-431b-8527-033ba9873a34", "Version": "1.8.7.0", "Status": None},
    {"Name": "NeXroll Intros", "Id": "a1b2c3d4-e5f6-7890-abcd-ae0c01200002", "Version": "1.14.0.0", "Status": None},
]


def test_the_nexroll_plugin_is_recognised_on_jellyfin_and_emby():
    assert nexroll_detect.plugins_in(JELLYFIN_PLUGINS) == {"nexroll": True, "ours": True}
    assert nexroll_detect.plugins_in(EMBY_PLUGINS) == {"nexroll": True, "ours": False}
    disabled = [dict(JELLYFIN_PLUGINS[2], Status="Disabled")]
    assert nexroll_detect.plugins_in(disabled) == {"nexroll": False, "ours": False}
    renamed = [{"Name": "Intros", "Id": "a1b2c3d4-e5f6-7890-abcd-ae0c01100001"}]
    assert nexroll_detect.plugins_in(renamed)["nexroll"] is True


@pytest.fixture
def servers_here(tmp_path, secrets, clean_library):  # noqa: F811
    coexist.configure(str(tmp_path / "coexist"))
    nexroll_detect.reset()
    db = SessionLocal()
    rows = {}
    for kind, name, url in (("jellyfin", "Jellyfin 12", "http://jf12:8096"), ("emby", "Emby", "http://emby:8096"),
                            ("plex", "Living room Plex", "http://plex:32400")):
        row = models.MediaServer(type=kind, name=name, url=url, enabled=True)
        db.add(row)
        db.flush()
        media_servers.set_secret(row, "k" * 20)
        rows[kind] = row.id
    media_servers.mirror(db)
    db.commit()
    yield db, rows
    db.close()
    coexist.configure(None)
    nexroll_detect.reset()


def _answer_plugins(monkeypatch):
    from backend import server_probe

    class R:
        def __init__(self, data):
            self.status_code, self.content, self._data = 200, b"[]", data

        def json(self):
            return self._data
    monkeypatch.setattr(server_probe, "request", lambda target, method, path, **kw:
                        R(JELLYFIN_PLUGINS if target.type == "jellyfin" else EMBY_PLUGINS))


def test_home_says_intros_play_twice_and_how_to_fix_it(servers_here, monkeypatch):
    db, rows = servers_here
    _answer_plugins(monkeypatch)
    report = nexroll_detect.report(db, 9393, probe_port=False)
    by_server = {w["server"]: w for w in report["warnings"]}
    assert by_server["Jellyfin 12"]["title"] == "Jellyfin 12 still has the NeXroll Intros plugin."
    assert "Intros will play twice" in by_server["Jellyfin 12"]["message"]
    assert "Dashboard > Plugins" in by_server["Jellyfin 12"]["fix"]
    assert "play twice" not in by_server["Emby"]["message"]  # no Prerolls Max plugin there


def test_plex_list_changed_by_something_else_is_noticed(servers_here):
    db, rows = servers_here
    url = "http://plex:32400"
    assert nexroll_detect.note_plex_read(url, "/a.mp4") is False  # nothing written yet: no opinion
    nexroll_detect.note_plex_written(url, "/prerolls/a.mp4;/prerolls/b.mp4")
    assert nexroll_detect.note_plex_read(url, "/prerolls/a.mp4;/prerolls/b.mp4 ") is False
    assert nexroll_detect.note_plex_read(url + "/", "C:\\NeXroll\\x.mp4") is True
    assert nexroll_detect.note_plex_read(url, "C:\\NeXroll\\x.mp4") is False  # the same change counts once
    report = nexroll_detect.report(db, 9393, probe_port=False)
    plex = next(w for w in report["warnings"] if w["server"] == "Living room Plex")
    assert plex["title"] == "Something else changed Plex's intro list."
    assert "usually NeXroll still running" in plex["message"] and plex["fix"].startswith("Stop NeXroll")


def test_plex_connector_reports_its_writes_and_reads(monkeypatch):
    from backend import plex_connector
    seen = {}
    monkeypatch.setattr(nexroll_detect, "note_plex_written", lambda url, value: seen.__setitem__("w", value))
    monkeypatch.setattr(nexroll_detect, "note_plex_read", lambda url, value: seen.__setitem__("r", value))
    connector = plex_connector.PlexConnector("http://plex:32400", "t" * 20)
    monkeypatch.setattr(connector, "_try_set_preroll_value", lambda value: True)
    monkeypatch.setattr(plex_connector.plex_visibility, "gate_preroll_value",
                        lambda *a: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(connector, "_read_preroll_pref", lambda: "/other.mp4")
    assert connector.set_preroll("/prerolls/a.mp4") is True
    assert seen["w"] == "/prerolls/a.mp4"
    assert connector.get_preroll() == "/other.mp4" and seen["r"] == "/other.mp4"


def test_a_running_nexroll_on_its_port_is_recognised():
    class Page(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>NeXroll</title>")

        def log_message(self, *a):
            pass
    server = HTTPServer(("127.0.0.1", 0), Page)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert port_config.identify(port) == "nexroll"
        assert port_config.port_free(port, "127.0.0.1") is False
        message = port_config.check_before_start(port, "default", host="127.0.0.1")
        assert message.startswith(f"Port {port} is already in use, by NeXroll.")
        assert "PMAX_PORT" in message and "Traceback" not in message
    finally:
        server.shutdown()
        server.server_close()
    assert port_config.identify(port) is None


def test_port_9393_message_names_nexroll_and_pmax_port():
    text = port_config.in_use_message(9393, "other")
    assert text.startswith("Port 9393 is already in use, probably by NeXroll.")
    assert "Stop NeXroll" in text and "PMAX_PORT" in text


def test_the_port_comes_from_the_environment_then_settings(tmp_path):
    env = {"PMAX_DB_DIR": str(tmp_path)}
    assert port_config.configured_port(env) == (9393, "default")
    port_config.save_port(9494, env)
    assert json.load(open(tmp_path / "startup.json")) == {"port": 9494}
    assert port_config.configured_port(env) == (9494, "settings")
    assert port_config.configured_port(env | {"PMAX_PORT": "9500"}) == (9500, "environment")
    port_config.save_port(None, env)
    assert port_config.configured_port(env) == (9393, "default")


def test_startup_stops_with_a_plain_message_when_the_port_is_taken(monkeypatch, capsys):
    holder = socket.socket()
    holder.bind(("0.0.0.0", 0))
    holder.listen(1)
    port = holder.getsockname()[1]
    monkeypatch.setenv("PMAX_PORT", str(port))
    try:
        with pytest.raises(SystemExit) as stop:
            main._port_or_exit()
        assert stop.value.code == 1
        err = capsys.readouterr().err
        assert f"Port {port} is already in use" in err and "Traceback" not in err
    finally:
        holder.close()


# ---------------------------------------------------------------------------
# Keeping both
# ---------------------------------------------------------------------------

def test_servers_left_to_nexroll_are_left_alone(servers_here, monkeypatch):
    db, rows = servers_here
    from backend import plex_connector
    from backend.routers import servers as servers_router
    coexist.save(mode="alongside", nexroll_servers=[rows["plex"], rows["jellyfin"]])
    # Plex: the intro list isn't written at all.
    monkeypatch.setattr(plex_connector.requests, "put", lambda *a, **kw: pytest.fail("Plex was written"))
    connector = plex_connector.PlexConnector("http://plex:32400/", "t" * 20)
    assert connector.set_preroll("/prerolls/a.mp4") is True and connector.left_to_nexroll
    # Jellyfin: the plugin request is matched to the server and told NeXroll has it.
    linked = servers_router.link_plugin_request(db, "jellyfin", "", None, "jf12")
    assert linked["nexroll_manages"] is True
    assert servers_router.link_plugin_request(db, "emby", "", None, "emby")["nexroll_manages"] is False
    # Its NeXroll plugin is expected there; Emby's isn't.
    _answer_plugins(monkeypatch)
    report = nexroll_detect.report(db, 9494, probe_port=False)
    assert [w["server"] for w in report["warnings"]] == ["Emby"]
    assert report["summary"] == "NeXroll manages Jellyfin 12 and Living room Plex; Prerolls Max manages Emby."
    # Switching back to "replace" hands everything back to Prerolls Max.
    coexist.save(mode="replace")
    assert not coexist.nexroll_manages(rows["plex"])


def test_plugin_answer_is_empty_on_purpose_for_a_nexroll_server():
    from backend.routers import plugin_v2
    source = open(plugin_v2.__file__, encoding="utf-8").read()
    start = source.index('if linked and linked.get("nexroll_manages")')
    block = source[start:start + 600]
    assert '"items": []' in block and '"intentional_empty": not whole_pool' in block


def test_alongside_settings_and_the_server_switch(admin, servers_here, tmp_path, monkeypatch):
    db, rows = servers_here
    monkeypatch.delenv("PMAX_PORT", raising=False)
    monkeypatch.delenv("NEXROLL_PORT", raising=False)
    monkeypatch.setenv("PMAX_DB_DIR", str(tmp_path))
    monkeypatch.setattr(port_config, "data_folder", lambda environ=None: str(tmp_path))
    answer = admin.put(f"/api/servers/{rows['plex']}/manager", json={"manager": "nexroll"})
    assert answer.status_code == 200 and answer.json() == {
        "id": rows["plex"], "name": "Living room Plex", "managed_by": "nexroll", "alongside": True}
    listed = {s["id"]: s for s in admin.get("/api/servers").json()["servers"]}
    assert listed[rows["plex"]]["managed_by"] == "nexroll" and listed[rows["emby"]]["managed_by"] == "prerollsmax"

    taken = admin.put("/api/migrate/nexroll/alongside", json={"port": 9393})
    assert taken.status_code == 422 and "NeXroll's port" in taken.json()["error"]["fields"]["port"]
    low = admin.put("/api/migrate/nexroll/alongside", json={"port": 80})
    assert low.status_code == 422
    holder = socket.socket()
    holder.bind(("0.0.0.0", 0))
    holder.listen(1)
    try:
        busy = admin.put("/api/migrate/nexroll/alongside", json={"port": holder.getsockname()[1]})
        assert busy.status_code == 422 and "already in use" in busy.json()["error"]["message"]
    finally:
        holder.close()
    free = _free_port()
    saved = admin.put("/api/migrate/nexroll/alongside", json={"port": free})
    assert saved.status_code == 200, saved.text
    assert saved.json()["port"]["saved"] == free and saved.json()["port"]["restart_needed"] is True
    assert json.load(open(tmp_path / "startup.json")) == {"port": free}

    monkeypatch.setenv("PMAX_PORT", "9393")
    env = admin.put("/api/migrate/nexroll/alongside", json={"port": free})
    assert env.status_code == 409 and env.json()["error"]["code"] == "port_from_environment"
    assert "port mapping" in env.json()["error"]["hint"]

    extra = admin.put("/api/migrate/nexroll/alongside", json={"surprise": 1})
    assert extra.status_code == 422


def _free_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    port = s.getsockname()[1]
    s.close()
    return port
