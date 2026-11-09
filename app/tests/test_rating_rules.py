"""Age-rating families, kids-safe titles and release years as Playlist (Advanced) conditions."""
import datetime

import pytest

from backend import ratings
from backend.sequence_conditions import (PlaybackContext, condition_holds, decade_of, describe_condition,
                                         evaluate_rule, year_matches)


# --- ratings -----------------------------------------------------------------

@pytest.mark.parametrize("value,key", [("pg 13", "PG-13"), ("US-PG-13", "PG-13"), ("TVY7", "TV-Y7"),
                                       ("tv_pg", "TV-PG"), ("DE-12", "12"), ("NC17", "NC-17"), ("", None)])
def test_rating_spellings(value, key):
    assert ratings.rating_key(value) == key


@pytest.mark.parametrize("value,safe", [("G", True), ("PG", True), ("TV-Y", True), ("TV-Y7", True),
                                        ("TV-G", True), ("TV-PG", True), ("U", True), ("PG-13", False),
                                        ("R", False), ("TV-14", False), ("TV-MA", False), ("NC-17", False)])
def test_kids_safe_ratings(value, safe):
    assert ratings.is_kids_safe(value) is safe


def test_unrated_is_not_kids_safe_unless_set():
    for value in (None, "", "NR", "Not Rated", "Unrated"):
        assert ratings.is_kids_safe(value) is False
        assert ratings.is_kids_safe(value, unrated_is_safe=True) is True


def test_families_for_pickers_mark_kids_safe():
    families = {f["id"]: f for f in ratings.families_for_ui()}
    us = {r["value"]: r["kids_safe"] for r in families["us_movies"]["ratings"]}
    assert us == {"G": True, "PG": True, "PG-13": False, "R": False, "NC-17": False}
    assert families["unrated"]["ratings"][0]["kids_safe"] is False
    assert ratings.family_of("TV-Y7") == "us_tv" and ratings.family_of("12A") == "uk"


# --- Playlist (Advanced) conditions -------------------------------------------

def ctx(**kw):
    return PlaybackContext(now=datetime.datetime(2026, 11, 8, 20, 0), **kw)


def test_kids_safe_condition_knows_unrated_from_unknown():
    rule = {"kind": "kids_safe"}
    assert evaluate_rule(rule, ctx(official_rating="PG", rating_known=True)) is True
    assert evaluate_rule(rule, ctx(official_rating="R", rating_known=True)) is False
    # The plugin said: no rating. Not kids-safe, so "not kids-safe" holds.
    assert evaluate_rule(rule, ctx(official_rating=None, rating_known=True)) is False
    assert evaluate_rule({**rule, "negate": True}, ctx(official_rating=None, rating_known=True)) is True
    assert evaluate_rule({**rule, "unrated_is_safe": True}, ctx(official_rating=None, rating_known=True)) is True
    # Plex with nothing playing: unknown, never met either way.
    assert evaluate_rule(rule, ctx()) is None
    assert not condition_holds({"rules": [{**rule, "negate": True}]}, ctx())


def test_year_condition_by_decade_and_range():
    assert evaluate_rule({"kind": "year", "decades": ["1980s"]}, ctx(year=1984)) is True
    assert evaluate_rule({"kind": "year", "decades": ["80s", 1990]}, ctx(year=1999)) is True
    assert evaluate_rule({"kind": "year", "decades": ["1980s"]}, ctx(year=2001)) is False
    assert evaluate_rule({"kind": "year", "from": 2000, "to": 2009}, ctx(year=2005)) is True
    assert evaluate_rule({"kind": "year", "decades": ["1980s"]}, ctx()) is None
    assert decade_of("70s") == 1970 and decade_of("2010s") == 2010 and decade_of("abc") is None
    assert year_matches(1975, [], None, None) is None


def test_new_conditions_read_plainly():
    text = describe_condition({"rules": [{"kind": "kids_safe"}, {"kind": "year", "decades": [1980, "1990s"]}]})
    assert text == "rated kids-safe and released in 1980s or 1990s"


def test_playback_context_carries_year_and_rating_known(monkeypatch):
    from backend import scheduler
    monkeypatch.setattr(scheduler, "_localized_now", lambda db: datetime.datetime(2026, 11, 8, 20, 0))
    known = scheduler.playback_context(None, media_type="Movie", genres=[], tags=[],
                                       facts={"official_rating": "", "year": 1985})
    assert known.rating_known is True and known.year == 1985 and known.official_rating is None
    plex = scheduler.playback_context(None, media_type="movie", server_type="plex")
    assert plex.rating_known is False and plex.year is None
