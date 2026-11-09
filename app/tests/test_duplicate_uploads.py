"""The exact same video isn't added twice without asking.

An upload whose content matches a library video is parked for 15 minutes
(backend/upload_staging.py); the page offers Skip or Add anyway, and Add
anyway uses the parked copy. Older library videos get their fingerprint
filled in by a background job.
"""
import hashlib
import io
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from backend import main, models, upload_staging
from backend.database import SessionLocal
from backend.routers import library_add
from tests.test_first_run_and_roles import _wipe_accounts

MP4_HEAD = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


def video_bytes():
    return MP4_HEAD + uuid.uuid4().bytes * 8


@pytest.fixture
def admin():
    _wipe_accounts()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    created = []
    yield client, created
    db = SessionLocal()
    try:
        for row in db.query(models.Preroll).filter(models.Preroll.id.in_(created)).all():
            for path in (row.path,):
                if path and os.path.exists(path):
                    os.remove(path)
            db.delete(row)
        db.commit()
    finally:
        db.close()
    _wipe_accounts()


def upload(client, name, data, **form):
    return client.post("/prerolls/upload", files={"file": (name, io.BytesIO(data), "video/mp4")}, data=form)


# --- parking ---------------------------------------------------------------------

def test_a_parked_video_is_kept_for_15_minutes_then_removed(tmp_path):
    token = upload_staging.stage(str(tmp_path), io.BytesIO(b"bytes"), "Pumpkin.mp4", meta={"category_id": "3"},
                                 existing_name="Pumpkin Intro", file_hash="abc")
    found = upload_staging.get(str(tmp_path), token)
    assert found["filename"] == "Pumpkin.mp4" and found["meta"] == {"category_id": "3"}
    assert found["existing_name"] == "Pumpkin Intro" and open(found["path"], "rb").read() == b"bytes"
    later = os.path.getmtime(found["path"]) + upload_staging.KEEP_SECONDS + 1
    assert upload_staging.sweep(str(tmp_path), now=later - 60) == 0
    assert upload_staging.get(str(tmp_path), token, now=later) is None  # expired: gone
    assert not os.listdir(tmp_path)


def test_sweep_removes_old_parked_videos_and_keeps_new_ones(tmp_path):
    old = upload_staging.stage(str(tmp_path), io.BytesIO(b"a"), "a.mp4", meta={}, existing_name="A", file_hash="1")
    new = upload_staging.stage(str(tmp_path), io.BytesIO(b"b"), "b.mp4", meta={}, existing_name="B", file_hash="2")
    created = upload_staging.get(str(tmp_path), new)
    assert created is not None
    meta = os.path.join(tmp_path, old, "staged.json")
    import json
    data = json.load(open(meta))
    data["created"] -= upload_staging.KEEP_SECONDS + 5
    json.dump(data, open(meta, "w"))
    assert upload_staging.sweep(str(tmp_path)) == 1
    assert sorted(os.listdir(tmp_path)) == [new]


def test_tokens_cant_reach_outside_the_parking_folder(tmp_path):
    assert upload_staging.get(str(tmp_path), "../../etc") is None
    assert upload_staging.discard(str(tmp_path), "..") is False


# --- uploads -----------------------------------------------------------------------

def test_an_exact_copy_is_parked_and_named_and_skip_adds_nothing(admin):
    client, created = admin
    data = video_bytes()
    first = upload(client, "Pumpkin Intro.mp4", data, if_duplicate="ask")
    assert first.status_code == 200 and first.json()["uploaded"] is True, first.text
    created.append(first.json()["id"])

    again = upload(client, "pumpkin copy.mp4", data, if_duplicate="ask")
    body = again.json()
    assert again.status_code == 200 and body["duplicate"] is True and body["uploaded"] is False
    assert body["message"] == 'Already in your library as "Pumpkin Intro".'
    assert body["existing"]["name"] == "Pumpkin Intro" and body["keep_minutes"] == 15
    db = SessionLocal()
    try:
        same = db.query(models.Preroll).filter(models.Preroll.file_hash == hashlib.sha256(data).hexdigest()).count()
    finally:
        db.close()
    assert same == 1

    skipped = client.post(f"/prerolls/upload/staged/{body['token']}", json={"action": "skip"})
    assert skipped.status_code == 200 and skipped.json()["skipped"] is True
    gone = client.post(f"/prerolls/upload/staged/{body['token']}", json={"action": "add"})
    assert gone.status_code == 410 and gone.json()["error"]["code"] == "staged_expired"
    assert "15 minutes" in gone.json()["error"]["hint"]


def test_add_anyway_adds_the_parked_copy_to_the_chosen_collection(admin):
    client, created = admin
    collection = client.post("/categories", json={"name": f"Dup test {uuid.uuid4().hex[:6]}"}).json()
    data = video_bytes()
    created.append(upload(client, "Snow.mp4", data).json()["id"])
    parked = upload(client, "Snow again.mp4", data, if_duplicate="ask", category_id=str(collection["id"])).json()
    assert parked["duplicate"] is True

    added = client.post(f"/prerolls/upload/staged/{parked['token']}", json={"action": "add"})
    assert added.status_code == 200, added.text
    created.append(added.json()["id"])
    assert added.json()["uploaded"] is True and added.json()["category_id"] == collection["id"]
    assert added.json()["filename"].startswith("Snow again")
    # Used once: the parked copy is gone.
    assert client.post(f"/prerolls/upload/staged/{parked['token']}", json={"action": "add"}).status_code == 410


def test_without_asking_an_upload_still_works_as_before(admin):
    client, created = admin
    data = video_bytes()
    created.append(upload(client, "Plain.mp4", data).json()["id"])
    second = upload(client, "Plain 2.mp4", data)
    assert second.json()["uploaded"] is True
    created.append(second.json()["id"])


def test_a_bad_choice_is_refused(admin):
    client, _ = admin
    r = client.post("/prerolls/upload/staged/abcdefghijklmnopqrstuvwx", json={"action": "replace"})
    assert r.status_code == 422


# --- fingerprints for older videos -----------------------------------------------------

def test_the_backfill_fills_in_missing_fingerprints_and_skips_missing_files(tmp_path):
    clip = tmp_path / "old.mp4"
    clip.write_bytes(b"an old video")
    db = SessionLocal()
    try:
        have = models.Preroll(filename="old.mp4", path=str(clip), file_hash=None)
        gone = models.Preroll(filename="gone.mp4", path=str(tmp_path / "gone.mp4"), file_hash="")
        db.add_all([have, gone])
        db.commit()
        ids = (have.id, gone.id)
    finally:
        db.close()
    try:
        result = library_add.backfill_hashes(None, SessionLocal, batch=1, pause=0)
        assert result["hashed"] >= 1 and result["unreadable"] >= 1
        db = SessionLocal()
        try:
            rows = {r.id: r for r in db.query(models.Preroll).filter(models.Preroll.id.in_(ids))}
            assert rows[ids[0]].file_hash == hashlib.sha256(b"an old video").hexdigest()
            assert not rows[ids[1]].file_hash
        finally:
            db.close()
    finally:
        db = SessionLocal()
        db.query(models.Preroll).filter(models.Preroll.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()
