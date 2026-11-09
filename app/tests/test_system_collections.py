"""The built-in collections have a key, not a magic name.

NeXroll looked its trailer collections up by name ("NeX-Up Movie Trailers"),
so they could never be renamed. Now each carries ``system_key``; start-up
tags NeXroll's rows by their old names and gives them plain ones ("Movie
trailers"), without taking a name the person already uses. Old names in
backups and playlist files still find them.
"""
import io
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import main, models, system_collections as sc
from backend.database import SessionLocal
from backend.scheduler import ensure_trailer_prerolls


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    models.Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()
    engine.dispose()


def names(db):
    return {c.name: c.system_key for c in db.query(models.Category).order_by(models.Category.id)}


def test_nexroll_rows_are_tagged_and_renamed_once(db):
    db.add_all([
        models.Category(name="NeX-Up Movie Trailers", is_system=True,
                        description="System category for upcoming movie trailers from Radarr. Managed automatically by NeX-Up."),
        models.Category(name="NeX-Up TV Trailers", is_system=True),
        models.Category(name="NeX-Up Prerolls", is_system=True),
        models.Category(name="Coming Soon Lists", is_system=True),
        models.Category(name="Halloween"),
    ])
    db.commit()
    notes = sc.migrate(db)
    assert names(db) == {"Movie trailers": "movie_trailers", "TV trailers": "tv_trailers",
                         "Video maker": "video_maker", "Coming Soon Lists": "coming_soon_lists", "Halloween": None}
    assert 'Renamed the collection "NeX-Up Movie Trailers" to "Movie trailers".' in notes
    movies = sc.find(db, sc.MOVIE_TRAILERS)
    assert "NeX-Up" not in movies.description
    # Idempotent: a second start changes nothing.
    assert sc.migrate(db) == []
    assert names(db)["Movie trailers"] == "movie_trailers"


@pytest.mark.parametrize("mine, expected", [
    (["Movie trailers"], "Movie trailers (built-in)"),
    (["movie   TRAILERS"], "Movie trailers (built-in)"),
    (["Movie trailers", "Movie trailers (built-in)"], "Movie trailers (built-in) (2)"),
])
def test_a_name_the_person_already_uses_is_kept_for_them(db, mine, expected):
    db.add_all([models.Category(name=n) for n in mine] + [models.Category(name="NeX-Up Movie Trailers", is_system=True)])
    db.commit()
    sc.migrate(db)
    assert sc.find(db, sc.MOVIE_TRAILERS).name == expected
    for n in mine:
        row = db.query(models.Category).filter(models.Category.name == n).one()
        assert row.system_key is None and not row.is_system


def test_a_users_own_collection_is_never_taken_for_a_built_in_one(db):
    # No NeXroll row: "Movie trailers" and "Coming Soon Lists" here are the person's.
    db.add_all([models.Category(name="Movie trailers"), models.Category(name="Coming Soon Lists")])
    db.commit()
    assert sc.migrate(db) == []
    assert names(db) == {"Movie trailers": None, "Coming Soon Lists": None}


def test_a_renamed_built_in_collection_is_not_renamed_back(db):
    db.add(models.Category(name="Trailers we like", is_system=True, system_key="movie_trailers"))
    db.commit()
    sc.migrate(db)
    assert sc.find(db, sc.MOVIE_TRAILERS).name == "Trailers we like"


def test_get_or_create_makes_it_once_with_a_free_name(db):
    db.add(models.Category(name="TV trailers"))
    db.commit()
    first = sc.get_or_create(db, sc.TV_TRAILERS)
    assert (first.name, first.system_key, first.is_system) == ("TV trailers (built-in)", "tv_trailers", True)
    assert sc.get_or_create(db, sc.TV_TRAILERS).id == first.id


def test_trailers_find_their_collection_by_key_when_settings_lost_the_id(db, tmp_path):
    movies = sc.get_or_create(db, sc.MOVIE_TRAILERS)
    db.add(models.Setting())
    path = tmp_path / "Alpha.mp4"
    path.write_bytes(b"x")
    db.add(models.ComingSoonTrailer(radarr_movie_id=1, title="Alpha", local_path=str(path), status="downloaded",
                                    is_enabled=True))
    db.commit()
    assert ensure_trailer_prerolls(db) == 1
    assert db.query(models.Preroll).one().category_id == movies.id


def test_old_names_in_a_playlist_file_find_todays_collection(db):
    sc.migrate(db)  # nothing yet
    movies = sc.get_or_create(db, sc.MOVIE_TRAILERS)
    pattern = {"blocks": [{"type": "random", "category_name": "NeX-Up Movie Trailers"},
                          {"type": "random", "category_name": "Halloween"}],
               "sequences": [{"blocks": [{"type": "sequential", "category_name": "nex-up movie trailers",
                                          "category_names": ["NeX-Up TV Trailers"]}]}]}
    assert sc.upgrade_pattern_names(db, pattern) == 3
    assert pattern["blocks"][0]["category_name"] == movies.name
    assert pattern["blocks"][1]["category_name"] == "Halloween"
    assert pattern["sequences"][0]["blocks"][0]["category_name"] == "Movie trailers"
    assert pattern["sequences"][0]["blocks"][0]["category_names"] == ["TV trailers"]


# --- through the app ----------------------------------------------------------

@pytest.fixture
def admin():
    from tests.test_first_run_and_roles import _wipe_accounts
    _wipe_accounts()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    yield client
    session = SessionLocal()
    try:
        session.query(models.SavedSequence).filter(models.SavedSequence.name.like("Trailers before%")).delete(
            synchronize_session=False)
        session.commit()
    finally:
        session.close()
    _wipe_accounts()


def test_a_nexseq_naming_the_old_collection_matches_it(admin):
    session = SessionLocal()
    try:
        movies = sc.get_or_create(session, sc.MOVIE_TRAILERS)
        movies_id, movies_name = movies.id, movies.name
    finally:
        session.close()
    pattern = {"pattern_name": "Old trailers", "blocks": [
        {"type": "random", "category_name": "NeX-Up Movie Trailers", "count": 2}]}
    files = {"file": ("old.nexseq", io.BytesIO(json.dumps(pattern).encode()), "application/json")}
    r = admin.post("/sequences/import", files=files)
    assert r.status_code == 200, r.text
    block = r.json()["blocks"][0]
    assert (block["category_id"], block["category_name"]) == (movies_id, movies_name)


def test_a_trailer_playlist_template_never_takes_a_name_twice(admin):
    session = SessionLocal()
    try:
        sc.get_or_create(session, sc.MOVIE_TRAILERS)
    finally:
        session.close()
    url = "/nexup/sequence/create?preset_id=movie_trailers_only&include_preroll=false&name=Trailers%20before%20movies"
    first = admin.post(url)
    assert first.status_code == 200, first.text
    assert first.json()["sequence"]["name"] == "Trailers before movies"
    assert first.json()["renamed"] == []
    second = admin.post(url)
    assert second.status_code == 200, second.text
    assert second.json()["sequence"]["name"] == "Trailers before movies (2)"
    assert second.json()["renamed"] == ['The playlist "Trailers before movies" was saved as '
                                        '"Trailers before movies (2)", because another playlist already has that name.']
    assert "NeX-Up" not in second.json()["sequence"]["description"]


def test_a_trailer_playlist_without_trailers_says_what_to_do(admin):
    session = SessionLocal()
    try:
        row = sc.find(session, sc.TV_TRAILERS)
        if row is not None:
            session.delete(row)
            session.commit()
    finally:
        session.close()
    r = admin.post("/nexup/sequence/create?preset_id=tv_trailers_only")
    assert r.status_code == 400
    assert r.json()["error"]["message"] == "There's no TV trailers collection yet."
    assert "Sonarr" in r.json()["error"]["hint"]
