"""Undo after deleting a video brings back its name, collections and "how
often", not only the file. Before, the scanner re-added the file as a new
video with the file name and default settings, so Undo looked like it failed."""
import uuid

from backend import main, models
from backend.database import SessionLocal


def test_trash_keeps_and_puts_back_the_videos_details(tmp_path):
    db = SessionLocal()
    path = str(tmp_path / f"undo-{uuid.uuid4().hex}.mp4")
    try:
        a = models.Category(name=f"Undo A {uuid.uuid4().hex[:6]}")
        b = models.Category(name=f"Undo B {uuid.uuid4().hex[:6]}")
        db.add_all([a, b])
        db.commit()
        p = models.Preroll(filename="file.mp4", path=path, display_name="Test Card Intro", weight=9,
                           description="made for the test", category_id=b.id, loudness_lufs=-23.4)
        p.categories = [a, b]
        db.add(p)
        db.commit()
        meta = main._trash_metadata(p)
        assert meta["display_name"] == "Test Card Intro" and meta["weight"] == 9
        assert sorted(meta["category_ids"]) == sorted([a.id, b.id])

        # Delete, then the scanner finds the restored file as a brand-new video.
        db.delete(p)
        db.commit()
        fresh = models.Preroll(filename="file.mp4", path=path)
        db.add(fresh)
        db.commit()

        assert main._apply_trash_metadata(db, {**meta, "restored_to": path}) is True
        db.refresh(fresh)
        assert fresh.display_name == "Test Card Intro"
        assert fresh.weight == 9 and fresh.description == "made for the test"
        assert fresh.loudness_lufs == -23.4
        assert sorted(c.id for c in fresh.categories) == sorted([a.id, b.id])
        assert fresh.category_id == b.id
        db.delete(fresh)
        db.delete(a)
        db.delete(b)
        db.commit()
    finally:
        db.close()


def test_nothing_to_put_back_when_the_video_is_not_found():
    db = SessionLocal()
    try:
        assert main._apply_trash_metadata(db, {"restored_to": "/nowhere/missing.mp4", "display_name": "x"}) is False
        assert main._apply_trash_metadata(db, {}) is False
    finally:
        db.close()
