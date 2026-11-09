"""Backups carry the smart features, and restores put them back checked.

Rules (in their order), the never-play list, watch folders, smart settings,
per-intro weights and collection cooldowns go into every backup; play
history only when Settings says so. A restore points rules and watch folders
at the collections' and intros' new ids, and leaves out (and names) anything
it can't use. Runs main.py's own backup and restore, like test_backup_restore.py.
"""
import contextlib
import datetime
import io
import json
import sqlite3
import zipfile

from backend import models, smart_backup, smart_settings
from backend.database import SessionLocal
from tests.test_backup_restore import FakeSecrets, _close_databases, load, session  # noqa: F401
from tests.test_first_run_and_roles import _setup, fresh  # noqa: F401


def _rule(name, position, when, play, enabled=True):
    return models.IntroRule(name=name, enabled=enabled, position=position, when_json=json.dumps(when),
                            play_json=json.dumps(play))


def _source(tmp_path, *, history_in_backups):
    db = session(tmp_path / "source.db")
    # Ids with gaps, so the restored ones differ.
    db.add_all([models.Category(id=30, name="Halloween"), models.Category(id=40, name="Kids", cooldown_hours=12)])
    db.add_all([
        models.Preroll(id=70, filename="pumpkin.mp4", path="/media/intros/pumpkin.mp4", category_id=30, weight=9),
        models.Preroll(id=90, filename="cartoon.mp4", path="/media/intros/cartoon.mp4", category_id=40, weight=2),
    ])
    # Stored out of order: position decides.
    db.add(_rule("Spooky", 1, {"genres": ["Horror"]}, {"preroll_ids": [70], "order": "in_order"}))
    db.add(_rule("Kids", 0, {"kids_safe": True}, {"collection_id": 40, "count": 1, "order": "random"}))
    db.add_all([models.IntroExclusion(kind="title", value="Fight Club", note="no intros"),
                models.IntroExclusion(kind="tag", value="no-intro")])
    incoming = tmp_path / "incoming"
    incoming.mkdir()
    db.add(models.WatchFolder(path=str(incoming), collection_id=40, mode="copy", recursive=False, enabled=True,
                              imported_count=3, imported_keys=json.dumps(["a|1|2"])))
    db.add(models.WatchFolder(path="relative/folder", mode="link"))
    for key, value in (("binge_window_hours", 6), ("unrated_is_kids_safe", True),
                       ("backup_includes_history", history_in_backups)):
        db.add(models.FeatureSetting(key=key, value=json.dumps(value)))
    db.add(models.PlayEvent(played_at=datetime.datetime(2026, 10, 31, 20, 0), preroll_id=70, name="pumpkin",
                            server_type="jellyfin", user_name="Sam", client="Swiftfin", source="plugin"))
    db.commit()
    return db


def _target(tmp_path):
    db = session(tmp_path / "target.db")
    # Things already here that a restore replaces, using the ids the backup had.
    db.add(models.Category(id=40, name="Old"))
    db.add(models.Preroll(id=70, filename="old.mp4", path="/old/old.mp4"))
    db.add(_rule("Old rule", 0, {}, {"collection_id": 40}))
    db.add(models.PlayEvent(played_at=datetime.datetime(2026, 1, 1), preroll_id=70, name="old"))
    db.commit()
    return db


def _backup(db):
    smart_settings.clear_cache()
    return json.loads(json.dumps(load(FakeSecrets())["backup_database"](db=db), default=str))


def _restore(backup, db):
    smart_settings.clear_cache()
    try:
        return load(FakeSecrets())["restore_database"](backup, db=db)
    finally:
        smart_settings.clear_cache()


def test_a_json_backup_round_trips_the_smart_features(tmp_path):
    backup = _backup(_source(tmp_path, history_in_backups=True))
    assert backup["schema_version"] == 6
    assert [r["name"] for r in backup["intro_rules"]] == ["Kids", "Spooky"]
    assert backup["play_history_included"] is True and len(backup["play_history"]) == 1

    target = _target(tmp_path)
    result = _restore(backup, target)

    collections = {c.name: c for c in target.query(models.Category).all()}
    intros = {p.filename: p for p in target.query(models.Preroll).all()}
    assert collections["Kids"].id != 40 and intros["pumpkin.mp4"].id != 70  # new ids...
    rules = target.query(models.IntroRule).order_by(models.IntroRule.position).all()
    assert [(r.name, r.position) for r in rules] == [("Kids", 0), ("Spooky", 1)]
    assert json.loads(rules[0].play_json)["collection_id"] == collections["Kids"].id  # ...followed
    assert json.loads(rules[0].when_json)["kids_safe"] is True
    assert json.loads(rules[1].play_json)["preroll_ids"] == [intros["pumpkin.mp4"].id]
    assert sorted((e.kind, e.value, e.note) for e in target.query(models.IntroExclusion).all()) == [
        ("tag", "no-intro", None), ("title", "Fight Club", "no intros")]

    folders = target.query(models.WatchFolder).all()
    assert [(f.path, f.collection_id, f.mode, f.recursive, f.imported_count) for f in folders] == [
        (str(tmp_path / "incoming"), collections["Kids"].id, "copy", False, 3)]
    assert json.loads(folders[0].imported_keys) == ["a|1|2"]
    assert any("relative/folder" in note for note in result["skipped"]), result["skipped"]

    settings = smart_settings.get_all(target)
    assert settings["binge_window_hours"] == 6 and settings["unrated_is_kids_safe"] is True
    assert intros["pumpkin.mp4"].weight == 9 and intros["cartoon.mp4"].weight == 2
    assert collections["Kids"].cooldown_hours == 12 and collections["Halloween"].cooldown_hours == 0

    history = target.query(models.PlayEvent).all()
    assert [(h.preroll_id, h.name, h.user_name, h.played_at) for h in history] == [
        (intros["pumpkin.mp4"].id, "pumpkin", "Sam", datetime.datetime(2026, 10, 31, 20, 0))]
    assert result["smart_features"] == {"smart_settings": 3, "intro_rules": 2, "intro_exclusions": 2,
                                        "watch_folders": 1, "play_history": 1}


def test_play_history_stays_out_of_backups_unless_turned_on(tmp_path):
    backup = _backup(_source(tmp_path, history_in_backups=False))
    assert backup["play_history_included"] is False and "play_history" not in backup
    target = _target(tmp_path)
    _restore(backup, target)
    # This install's own history is left alone.
    assert [h.name for h in target.query(models.PlayEvent).all()] == ["old"]
    assert smart_settings.get_all(target)["backup_includes_history"] is False


def test_an_older_backup_leaves_the_smart_features_alone(tmp_path):
    backup = _backup(_source(tmp_path, history_in_backups=False))
    for key in ("intro_rules", "intro_exclusions", "watch_folders", "smart_settings", "play_history_included"):
        backup.pop(key)
    target = _target(tmp_path)
    result = _restore(backup, target)
    assert [r.name for r in target.query(models.IntroRule).all()] == ["Old rule"]
    assert result["smart_features"] == {}


def test_entries_that_cant_be_used_are_left_out_and_named(tmp_path):
    backup = _backup(_source(tmp_path, history_in_backups=True))
    backup["intro_rules"] += [
        {"name": "Gone", "position": 2, "when": {}, "play": {"collection_id": 999}},
        {"name": "Bad decade", "position": 3, "when": {"decades": ["soon"]}, "play": {"collection_id": 40}},
        {"name": "Nothing left", "position": 4, "when": {}, "play": {"preroll_ids": [12345]}},
    ]
    backup["intro_exclusions"] += [{"kind": "planet", "value": "Mars"}, {"kind": "title", "value": "fight club"}]
    backup["watch_folders"] += [{"path": "/srv/../etc", "mode": "link"}, {"path": "/srv/x", "mode": "teleport"},
                                {"path": str(tmp_path / "incoming" / "inner"), "mode": "link"}]
    backup["smart_settings"].update({"binge_window_hours": 500, "made_up": 1})
    backup["play_history"].append({"played_at": "yesterday", "name": "x"})
    backup["prerolls"][0]["weight"] = 99
    backup["categories"][0]["cooldown_hours"] = -4

    target = _target(tmp_path)
    result = _restore(backup, target)
    skipped = "\n".join(result["skipped"])
    for expected in ('the rule "Gone": its collection isn\'t in the backup',
                     'the rule "Bad decade"',
                     'the rule "Nothing left": none of its intro videos are in the backup',
                     'the never-play entry "Mars"',
                     "the watch folder /srv/../etc", "the watch folder /srv/x",
                     "it overlaps another watch folder",
                     'the setting "binge_window_hours"', 'the setting "made_up"',
                     "1 play history entries with no usable time",
                     "its weight wasn't 1 to 10", "its cooldown wasn't 0 to 720 hours"):
        assert expected in skipped, (expected, skipped)
    assert [r.name for r in target.query(models.IntroRule).order_by(models.IntroRule.position)] == ["Kids", "Spooky"]
    assert target.query(models.IntroExclusion).count() == 2  # the duplicate is folded in, not named
    assert target.query(models.WatchFolder).count() == 1
    assert smart_settings.get_all(target)["binge_window_hours"] == 4  # the bad value falls back to the default
    assert target.query(models.PlayEvent).count() == 1
    assert {p.weight for p in target.query(models.Preroll)} == {5, 2}


def test_the_database_file_in_a_system_backup_is_checked_too(tmp_path):
    db = _source(tmp_path, history_in_backups=False)
    db.add(models.PlaybackCheck(item_name="Up", outcome="intros"))
    db.commit()
    path = str(tmp_path / "source.db")
    smart_backup.strip_history_from_file(path)
    skipped = smart_backup.check_watch_folders_in_file(path, library_dir=str(tmp_path / "library"))
    with contextlib.closing(sqlite3.connect(path)) as con:
        assert con.execute("SELECT count(*) FROM intro_plays").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM playback_checks").fetchone() == (0,)
        assert con.execute("SELECT count(*) FROM intro_rules").fetchone() == (2,)
        assert con.execute("SELECT path FROM watch_folders").fetchall() == [(str(tmp_path / "incoming"),)]
    assert skipped and "relative/folder" in skipped[0]


def _db_in_zip(content: bytes, tmp_path) -> str:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        target = tmp_path / "from-zip.db"
        target.write_bytes(z.read("database/prerollsmax.db"))
        data = json.loads(z.read("database/nexroll_data.json"))
    return str(target), data


def test_the_system_backup_leaves_play_history_out_by_default(fresh, tmp_path):
    _setup(fresh, "admin", "admin pass 1")
    db = SessionLocal()
    try:
        db.add(models.PlayEvent(played_at=datetime.datetime(2026, 10, 1), name="a play"))
        db.commit()
        smart_settings.clear_cache()
        response = fresh.post("/backup/files")
        assert response.status_code == 200
        path, data = _db_in_zip(response.content, tmp_path)
        with contextlib.closing(sqlite3.connect(path)) as con:
            assert con.execute("SELECT count(*) FROM intro_plays").fetchone() == (0,)
        assert data["play_history_included"] is False and "intro_rules" in data

        assert fresh.put("/api/smart-settings", json={"backup_includes_history": True}).status_code == 200
        response = fresh.post("/backup/files")
        path, data = _db_in_zip(response.content, tmp_path)
        with contextlib.closing(sqlite3.connect(path)) as con:
            assert con.execute("SELECT count(*) FROM intro_plays").fetchone()[0] >= 1
        assert data["play_history_included"] is True and data["play_history"]
    finally:
        db.query(models.PlayEvent).delete()
        db.query(models.FeatureSetting).delete()
        db.commit()
        db.close()
        smart_settings.clear_cache()

