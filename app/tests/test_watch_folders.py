"""Watch folders: new files are added once they stop changing, and only once."""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import errors, models
from backend.automation import AUTOMATION
from backend.routers import automation as automation_routes
from backend.watch_folders import Deps, Watcher
from tests.smart_fixtures import collection, smart_db  # noqa: F401


@pytest.fixture
def setup(smart_db, tmp_path):
    library = tmp_path / "library"
    drop = tmp_path / "drop"
    library.mkdir()
    drop.mkdir()
    deps = Deps(library_dir=lambda: str(library),
                probe_seconds=lambda path: None if path.endswith("broken.mp4") else 12.5)
    yield smart_db, drop, library, deps
    smart_db.query(models.Preroll).filter(models.Preroll.description.like("Added from the watch folder%")).delete(
        synchronize_session=False)
    smart_db.commit()


def folder(db, path, mode="link", collection_id=None, recursive=True):
    row = models.WatchFolder(path=str(path), mode=mode, collection_id=collection_id, recursive=recursive,
                             enabled=True)
    db.add(row)
    db.commit()
    return row


def write(path, data=b"video"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_a_file_is_added_once_it_stops_changing(setup):
    db, drop, _library, deps = setup
    kids = collection(db, "T-Watch kids")
    watch = folder(db, drop, collection_id=kids.id)
    watcher = Watcher()
    clip = write(drop / "intro.mp4")
    first = watcher.scan(db, watch, deps, now=0)
    assert first["imported"] == [] and first["waiting"][0]["name"] == "intro.mp4"
    clip.write_bytes(b"video still copying")  # it grew
    assert watcher.scan(db, watch, deps, now=30)["imported"] == []
    assert watcher.scan(db, watch, deps, now=40)["imported"] == []  # only 10 s steady
    done = watcher.scan(db, watch, deps, now=60)
    assert [i["name"] for i in done["imported"]] == ["intro.mp4"]
    row = db.query(models.Preroll).filter(models.Preroll.path == str(clip)).one()
    assert row.managed is False and row.duration == 12.5 and [c.id for c in row.categories] == [kids.id]
    assert watch.imported_count == 1
    # Not again, even after it is removed from the library.
    db.delete(row)
    db.commit()
    assert watcher.scan(db, watch, deps, now=200)["imported"] == []


def test_partial_downloads_hidden_files_and_other_types_are_ignored(setup):
    db, drop, _library, deps = setup
    watch = folder(db, drop)
    for name in ("movie.mp4.part", "clip.crdownload", ".hidden.mp4", "notes.txt", "x.partial-ab12.mp4"):
        write(drop / name)
    watcher = Watcher()
    watcher.scan(db, watch, deps, now=0)
    assert watcher.scan(db, watch, deps, now=100) == {"imported": [], "duplicates": [], "waiting": [], "errors": []}


def test_copy_mode_copies_into_the_collection_folder_and_skips_duplicates(setup):
    db, drop, library, deps = setup
    trailers = collection(db, "T-Watch copies")
    watch = folder(db, drop, mode="copy", collection_id=trailers.id)
    write(drop / "sub" / "a.mp4", b"same bytes")
    write(drop / "b.mp4", b"same bytes")
    watcher = Watcher()
    watcher.scan(db, watch, deps, now=0)
    result = watcher.scan(db, watch, deps, now=60)
    assert len(result["imported"]) == 1  # the second file has the same contents
    row = db.query(models.Preroll).filter(models.Preroll.id == result["imported"][0]["preroll_id"]).one()
    # ...and is counted, by name, on the folder's card.
    first = os.path.splitext(result["imported"][0]["name"])[0]
    assert [d["existing"] for d in result["duplicates"]] == [first]
    assert watch.duplicate_count == 1
    assert row.managed is True and row.path.startswith(str(library / "T-Watch copies"))
    assert os.path.exists(row.path) and os.path.exists(drop / "b.mp4")  # the original stays
    assert not [n for n in os.listdir(library / "T-Watch copies") if n.startswith(".")]


def test_unreadable_files_are_given_up_on_with_a_plain_message(setup):
    db, drop, _library, deps = setup
    watch = folder(db, drop, recursive=False)
    write(drop / "broken.mp4")
    write(drop / "deep" / "skipped.mp4")
    watcher = Watcher()
    errors_seen = []
    for step in range(8):
        errors_seen += watcher.scan(db, watch, deps, now=step * 30)["errors"]
    assert errors_seen == ["'broken.mp4' can't be read as a video. It may be damaged; it was left alone."]
    assert db.query(models.Preroll).filter(models.Preroll.path.like(f"{drop}%")).count() == 0


def test_a_missing_folder_is_reported(setup, tmp_path):
    db, _drop, _library, deps = setup
    watch = folder(db, tmp_path / "gone")
    result = Watcher().scan(db, watch, deps, now=0)
    assert "isn't there" in result["errors"][0] and watch.last_error


def test_watch_folder_api(setup, monkeypatch):
    db, drop, library, deps = setup
    monkeypatch.setattr(AUTOMATION, "watch_deps", deps)
    app = FastAPI()
    errors.install(app)
    app.include_router(automation_routes.router)
    client = TestClient(app)
    group = collection(db, "T-Watch api")
    added = client.post("/api/watch-folders", json={"path": str(drop), "collection_id": group.id, "mode": "copy"})
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["collection_name"] == "T-Watch api" and body["exists"] is True and body["mode"] == "copy"
    overlap = client.post("/api/watch-folders", json={"path": str(drop / "inner")})
    assert overlap.status_code in (409, 422)
    (drop / "inner2").mkdir()
    nested = client.post("/api/watch-folders", json={"path": str(drop / "inner2")})
    assert nested.status_code == 409 and nested.json()["error"]["code"] == "already_watched"
    inside = client.post("/api/watch-folders", json={"path": str(library)})
    assert inside.status_code == 422 and "inside the Prerolls Max library" in inside.json()["detail"]
    missing = client.post("/api/watch-folders", json={"path": "/no/such/folder"})
    assert missing.status_code == 422 and "isn't there" in missing.json()["error"]["fields"]["path"]
    relative = client.post("/api/watch-folders", json={"path": "drop"})
    assert relative.status_code == 422 and "full path" in relative.json()["error"]["fields"]["path"]
    write(drop / "new.mp4")
    check = client.post(f"/api/watch-folders/{body['id']}/check").json()
    assert check["waiting"][0]["name"] == "new.mp4"
    listed = client.get("/api/watch-folders").json()
    assert listed[0]["waiting"][0]["name"] == "new.mp4"
    assert listed[0]["duplicate_count"] == 0
    assert client.put(f"/api/watch-folders/{body['id']}", json={"path": str(drop), "enabled": False}).json()["enabled"] is False
    assert client.delete(f"/api/watch-folders/{body['id']}").json()["deleted"] is True


def test_link_mode_leaves_out_a_video_already_in_the_library(setup):
    db, drop, _library, deps = setup
    watch = folder(db, drop)
    write(drop / "Pumpkin Intro.mp4", b"pumpkin bytes")
    watcher = Watcher()
    watcher.scan(db, watch, deps, now=0)
    assert [i["name"] for i in watcher.scan(db, watch, deps, now=60)["imported"]] == ["Pumpkin Intro.mp4"]
    write(drop / "copy of pumpkin.mp4", b"pumpkin bytes")
    watcher.scan(db, watch, deps, now=100)
    result = watcher.scan(db, watch, deps, now=200)
    assert result["imported"] == []
    assert result["duplicates"] == [{"name": "copy of pumpkin.mp4", "existing": "Pumpkin Intro"}]
    assert watch.duplicate_count == 1 and watch.imported_count == 1
    # Not counted again on the next check.
    assert watcher.scan(db, watch, deps, now=300)["duplicates"] == []
