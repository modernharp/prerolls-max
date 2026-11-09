"""A schedule set to "Play them all, one after another" plays every intro in
order on Jellyfin and Emby too. Plex read the schedule's choice, but the
plugins only read the collection's, so they played one intro where Plex
played them all."""
import datetime
import uuid

import pytest

from backend import main, models
from backend.database import SessionLocal


@pytest.fixture
def halloween():
    db = SessionLocal()
    cat = models.Category(name=f"In order {uuid.uuid4().hex[:6]}", plex_mode="shuffle")
    db.add(cat)
    db.commit()
    rolls = []
    for n in ("Ghost", "Pumpkin"):
        p = models.Preroll(filename=f"{n}.mp4", path=f"/tmp/in-order-{uuid.uuid4().hex}/{n}.mp4",
                           category_id=cat.id, enabled=True)
        p.categories = [cat]
        db.add(p)
        rolls.append(p)
    sched = models.Schedule(name="Halloween night", type="daily", category_id=cat.id, is_active=True,
                            start_date=datetime.datetime(2026, 1, 1), playlist=True)
    db.add(sched)
    db.commit()
    setting = db.query(models.Setting).first()
    saved = (setting.active_category, setting.active_schedule_id, setting.filler_enabled)
    setting.active_category, setting.active_schedule_id, setting.filler_enabled = cat.id, sched.id, False
    db.commit()
    yield db, cat, sched
    setting = db.query(models.Setting).first()
    setting.active_category, setting.active_schedule_id, setting.filler_enabled = saved
    for p in rolls:
        db.delete(p)
    db.delete(sched)
    db.delete(cat)
    db.commit()
    db.close()


def test_in_order_schedule_plays_all_in_order_for_plugins(halloween):
    db, cat, sched = halloween
    result = main._resolve_current_intros(db)
    assert result["mode"] == "sequential"
    assert [p.rsplit("/", 1)[-1] for p in result["paths"]] == ["Ghost.mp4", "Pumpkin.mp4"]


def test_random_schedule_wins_over_an_in_order_collection(halloween):
    db, cat, sched = halloween
    sched.playlist = False

    cat.plex_mode = "playlist"
    db.commit()
    assert main._resolve_current_intros(db)["mode"] == "shuffle"
