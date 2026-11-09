"""One name per schedule, playlist and rule (case and spaces don't count).

Saving a taken name is refused in plain words; imports and restores add
" (2)", " (3)" instead and say so; schedules an old database already holds
twice keep working.
"""
import datetime
import io
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, models, unique_names
from backend.database import SessionLocal
from tests.test_first_run_and_roles import _wipe_accounts


def _clear(db):
    db.query(models.Setting).update({models.Setting.active_schedule_id: None,
                                     models.Setting.filler_sequence_id: None},
                                    synchronize_session=False)
    db.query(models.Schedule).delete(synchronize_session=False)
    db.query(models.SavedSequence).delete(synchronize_session=False)
    db.query(models.IntroRule).delete(synchronize_session=False)
    db.commit()


@pytest.fixture
def admin():
    _wipe_accounts()
    db = SessionLocal()
    try:
        _clear(db)
    finally:
        db.close()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    yield client
    db = SessionLocal()
    try:
        _clear(db)
    finally:
        db.close()
    _wipe_accounts()


@pytest.fixture
def collection(admin):
    db = SessionLocal()
    try:
        row = db.query(models.Category).filter(models.Category.name == "Names test").first()
        if row is not None:
            return {"id": row.id, "name": row.name}
    finally:
        db.close()
    return admin.post("/categories", json={"name": "Names test"}).json()


def _schedule(collection, name):
    return {"name": name, "type": "daily", "category_id": collection["id"], "start_date": "2026-05-01T00:00"}


def _playlist(collection, name):
    return {"name": name, "blocks": [{"type": "random", "category_id": collection["id"], "count": 1}]}


def _rule(collection, name):
    return {"name": name, "when": {"genres": ["Horror"]}, "play": {"collection_id": collection["id"]}}


def _conflict(r):
    assert r.status_code == 409, r.text
    error = r.json()["error"]
    assert error["code"] == "name_taken"
    assert error["fields"]["name"] == error["message"]
    return error["message"]


# --- the helpers -------------------------------------------------------------

def test_names_compare_without_case_or_extra_spaces():
    assert unique_names.name_key("  Hallo   ween ") == unique_names.name_key("hallo ween")
    assert unique_names.numbered("Halloween", []) == "Halloween"
    assert unique_names.numbered("Halloween", ["halloween"]) == "Halloween (2)"
    assert unique_names.numbered("Halloween", ["Halloween", "Halloween (2)"]) == "Halloween (3)"


def test_a_numbered_name_stays_within_the_length_limit():
    long = "x" * 100
    assert unique_names.numbered(long, [long], max_len=100) == "x" * 96 + " (2)"


# --- saving --------------------------------------------------------------------

def test_a_second_schedule_with_the_same_name_is_refused(admin, collection):
    assert admin.post("/schedules", json=_schedule(collection, "Halloween")).status_code == 200
    message = _conflict(admin.post("/schedules", json=_schedule(collection, "  halloween ")))
    assert message == "There's already a schedule called 'Halloween'. Pick another name."


def test_renaming_a_schedule_to_a_taken_name_is_refused(admin, collection):
    admin.post("/schedules", json=_schedule(collection, "Halloween"))
    other = admin.post("/schedules", json=_schedule(collection, "Christmas")).json()
    _conflict(admin.put(f"/schedules/{other['id']}", json={"name": "HALLOWEEN"}))
    # Its own name, in another case, is fine.
    r = admin.put(f"/schedules/{other['id']}", json={"name": "christmas"})
    assert r.status_code == 200, r.text


def test_schedules_an_old_database_holds_twice_keep_working(admin, collection):
    first = admin.post("/schedules", json=_schedule(collection, "Halloween")).json()
    db = SessionLocal()
    try:  # what a NeXroll database can hold: two schedules with one name
        twin = models.Schedule(name="Halloween", type="daily", category_id=collection["id"],
                               start_date=datetime.datetime(2026, 5, 1))
        db.add(twin)
        db.commit()
        twin_id = twin.id
    finally:
        db.close()
    db = SessionLocal()
    try:
        assert unique_names.shared_name_ids(db, "schedule") == {first["id"], twin_id}
    finally:
        db.close()
    # Switching it off and saving it under its own name still work.
    assert admin.put(f"/schedules/{twin_id}", json={"is_active": False}).status_code == 200
    assert admin.put(f"/schedules/{twin_id}", json={"name": "Halloween", "priority": 7}).status_code == 200
    # Renaming it to a free name clears the clash.
    assert admin.put(f"/schedules/{twin_id}", json={"name": "Halloween late"}).status_code == 200


def test_playlist_names_are_unique(admin, collection):
    first = admin.post("/sequences", json=_playlist(collection, "Movie night"))
    assert first.status_code == 200, first.text
    message = _conflict(admin.post("/sequences", json=_playlist(collection, "MOVIE NIGHT")))
    assert message == "There's already a playlist called 'Movie night'. Pick another name."
    other = admin.post("/sequences", json=_playlist(collection, "Kids")).json()
    _conflict(admin.put(f"/sequences/{other['id']}", json={"name": "movie night"}))
    assert admin.put(f"/sequences/{other['id']}", json={"name": "Kids", "description": "x"}).status_code == 200


def test_an_empty_playlist_name_is_refused_in_plain_words(admin, collection):
    r = admin.post("/sequences", json=_playlist(collection, "   "))
    assert r.status_code == 422
    assert r.json()["error"]["fields"]["name"] == "Enter a playlist name."


def test_rule_names_are_unique(admin, collection):
    first = admin.post("/api/rules", json=_rule(collection, "Kids"))
    assert first.status_code == 200, first.text
    message = _conflict(admin.post("/api/rules", json=_rule(collection, "kids")))
    assert message == "There's already a rule called 'Kids'. Pick another name."
    other = admin.post("/api/rules", json=_rule(collection, "Horror")).json()
    _conflict(admin.put(f"/api/rules/{other['id']}", json=_rule(collection, "KIDS")))
    # Switching a rule on or off sends its own name back; that's fine.
    assert admin.put(f"/api/rules/{other['id']}", json={**_rule(collection, "Horror"), "enabled": False}).status_code == 200


# --- imports and restores ------------------------------------------------------

def test_a_nexseq_import_offers_a_numbered_name_when_the_name_is_taken(admin, collection):
    admin.post("/sequences", json=_playlist(collection, "Movie night"))
    pattern = {"pattern_name": "Movie night", "blocks": [{"type": "random", "category_id": collection["id"]}]}
    files = {"file": ("movie-night.nexseq", io.BytesIO(json.dumps(pattern).encode()), "application/json")}
    r = admin.post("/sequences/import", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggested_name"] == "Movie night (2)"
    assert body["renamed"] == ['The playlist "Movie night" was saved as "Movie night (2)", because another '
                               'playlist already has that name.']


def test_a_bundle_import_numbers_taken_names_and_says_so(admin, collection):
    admin.post("/sequences", json=_playlist(collection, "Movie night"))
    blocks = [{"type": "random", "category_id": collection["id"], "count": 1}]
    r = admin.post("/sequences/import-bundle-confirm", json={"sequences": [
        {"name": "Movie night", "blocks": blocks}, {"name": "movie night", "blocks": blocks}]})
    assert r.status_code == 200, r.text
    assert [s["name"] for s in r.json()["sequences"]] == ["Movie night (2)", "movie night (3)"]
    assert len(r.json()["renamed"]) == 2


def test_a_restore_numbers_schedules_and_playlists_that_share_a_name():
    used = {"schedule": [], "playlist": []}
    renamed = []
    assert main._restored_name("schedule", "Halloween", used, renamed) == "Halloween"
    assert main._restored_name("schedule", " halloween ", used, renamed) == "halloween (2)"
    assert main._restored_name("playlist", "Halloween", used, renamed) == "Halloween"
    assert renamed == ['The schedule "halloween" was saved as "halloween (2)", because another schedule '
                       'already has that name.']
    # restore_database itself: tests/test_backup_restore.py


def test_a_restore_numbers_rules_that_share_a_name(collection):
    from backend import smart_backup
    rows = [
        {"name": "Kids", "when": {"genres": ["Family"]}, "play": {"collection_id": 1}, "position": 0},
        {"name": "kids", "when": {"genres": ["Kids"]}, "play": {"collection_id": 1}, "position": 1},
    ]
    db = SessionLocal()
    try:
        report = smart_backup.restore(db, {"intro_rules": rows}, category_ids={1: collection["id"]}, preroll_ids={})
        names = sorted(r.name for r in db.query(models.IntroRule).all())
    finally:
        db.close()
    assert report["restored"]["intro_rules"] == 2
    assert names == ["Kids", "kids (2)"]
    assert report["renamed"] == ['The rule "kids" was saved as "kids (2)", because another rule already has that name.']
