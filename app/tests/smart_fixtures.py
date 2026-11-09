"""Shared helpers for the smart-feature tests: tiny videos and clean tables."""
import os
import subprocess
import uuid

import pytest

from backend import models, smart_settings
from backend.database import SessionLocal, engine

# Without backend.main imported, nothing has created the tables yet.
models.Base.metadata.create_all(bind=engine)

SMART_TABLES = (models.IntroRule, models.IntroExclusion, models.FeatureSetting, models.PlayEvent,
                models.PlaybackCheck, models.WatchFolder)


def clean_smart_tables():
    db = SessionLocal()
    try:
        for model in SMART_TABLES:
            db.query(model).delete()
        db.commit()
    finally:
        db.close()
    smart_settings.clear_cache()


@pytest.fixture
def smart_db():
    """A session on the test database with the smart tables emptied before and after."""
    clean_smart_tables()
    db = SessionLocal()
    created = {"categories": [], "prerolls": []}
    db.created = created
    try:
        yield db
    finally:
        db.rollback()
        for preroll_id in created["prerolls"]:
            db.query(models.Preroll).filter(models.Preroll.id == preroll_id).delete()
        db.query(models.Preroll).filter(models.Preroll.description.like("%made by Prerolls Max%")).delete(
            synchronize_session=False)
        for category_id in created["categories"]:
            db.query(models.Category).filter(models.Category.id == category_id).delete()
        db.commit()
        db.close()
        clean_smart_tables()


def collection(db, name=None):
    row = models.Category(name=name or f"T-{uuid.uuid4().hex[:8]}")
    db.add(row)
    db.commit()
    db.refresh(row)
    db.created["categories"].append(row.id)
    return row


def preroll(db, path, category=None, **fields):
    if not os.path.exists(path):
        with open(path, "wb") as handle:
            handle.write(b"x")
    row = models.Preroll(filename=os.path.basename(path), path=str(path), enabled=True, **fields)
    if category is not None:
        row.categories = [category]
        row.category_id = category.id
    db.add(row)
    db.commit()
    db.refresh(row)
    db.created["prerolls"].append(row.id)
    return row


def make_video(path, seconds=1.0, size="320x240", rate=25, audio=True, volume=1.0, hdr=False):
    """A tiny real video made with ffmpeg's test sources."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
           "-i", f"testsrc=size={size}:rate={rate}:duration={seconds}"]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={seconds},volume={volume}"]
    if hdr:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020",
                "-color_trc", "smpte2084", "-colorspace", "bt2020nc"]
    else:
        cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    cmd += ["-preset", "ultrafast"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True)
    return str(path)
