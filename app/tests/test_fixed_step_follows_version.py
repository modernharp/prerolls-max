"""A playlist step with chosen videos follows "Play the new version instead".

Making an evened-out or TV-friendly version with that option switches the
original off and puts the version in its collections. A playlist step that
named the original kept playing it, although the library showed it as Off."""
from backend import main, models, scheduler  # noqa: F401  (main creates the tables)
from backend.database import SessionLocal


def test_fixed_step_plays_the_version_that_replaced_the_original(tmp_path):
    original_file = tmp_path / "Welcome Intro.mp4"
    version_file = tmp_path / "Welcome Intro (normalized).mp4"
    other_file = tmp_path / "Popcorn Intro.mp4"
    for f in (original_file, version_file, other_file):
        f.write_bytes(b"x")
    db = SessionLocal()
    try:
        original = models.Preroll(filename=original_file.name, path=str(original_file), enabled=False)
        other = models.Preroll(filename=other_file.name, path=str(other_file), enabled=True)
        db.add_all([original, other])
        db.commit()
        version = models.Preroll(filename=version_file.name, path=str(version_file), enabled=True,
                                 version_of=original.id, version_label="Loudness -23 LUFS")
        db.add(version)
        db.commit()
        block = {"type": "fixed", "preroll_ids": [original.id, other.id]}
        assert scheduler.resolve_block_paths(block, db) == [str(version_file), str(other_file)]

        # Switched back on (the user prefers the original): the original plays.
        original.enabled = True
        db.commit()
        assert scheduler.resolve_block_paths(block, db) == [str(original_file), str(other_file)]
        for row in (version, original, other):
            db.delete(row)
        db.commit()
    finally:
        db.close()
