"""Simple rule sets: "when this is about to play, play these intros".

A rule is::

    {"name": "Kids", "enabled": true,
     "when": {"genres": [], "ratings": [], "kids_safe": true, "decades": [],
              "year_from": null, "year_to": null, "libraries": [], "users": [],
              "media_type": "movie"|"episode"|"any", "first_episode_only": false},
     "play": {"collection_id": 4 | null, "preroll_ids": [..], "count": 1,
              "order": "random"|"in_order", "cooldown_hours": 0}}

Inside ``when`` every filled-in field must hold, and a list holds when any of
its values does ("Animation or Family"). An empty ``when`` matches everything.
Rules are checked in order; the first enabled one that matches decides, and
when none does the schedules decide as before.

Before any rule, the "never play an intro before this title" list is checked:
by item id, by title, or by tag, plus the tags people put on items in
Jellyfin/Emby (``no-intro`` / ``nointro``) when that setting is on.

Rules need to know what is about to play, which only the Jellyfin and Emby
plugin can say; Plex picks its intro before it knows the movie, so rule sets
don't apply there (capabilities: ``rule_sets``).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

from backend.ratings import is_kids_safe, is_unrated, rating_key
from backend.sequence_conditions import decade_of, year_matches
from backend.trailer_filters import genre_keys

logger = logging.getLogger("prerollsmax.rules")

MEDIA_TYPES = ("any", "movie", "episode")
ORDERS = ("random", "in_order")


# ---------------------------------------------------------------------------
# Reading rules
# ---------------------------------------------------------------------------

def _load(text, default):
    try:
        value = json.loads(text) if text else default
    except (TypeError, ValueError):
        return default
    return value if isinstance(value, type(default)) else default


def rule_dict(row) -> dict:
    return {"id": row.id, "name": row.name, "enabled": bool(row.enabled), "position": row.position or 0,
            "when": _load(row.when_json, {}), "play": _load(row.play_json, {})}


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


_YEAR_SUFFIX = re.compile(r"\s*\((?:18|19|20|21)\d\d\)$")


def _title_keys(value) -> set:
    """A title, with and without a year at the end: "Alien (1979)" also matches "Alien".

    Jellyfin and Emby show the folder name, year included, until metadata is
    fetched, and people type a title without the year (or the other way round).
    """
    text = _norm(value)
    if not text:
        return set()
    return {text, _YEAR_SUFFIX.sub("", text)}


def _tag_key(value) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _what(facts: dict) -> str:
    return "the episode" if facts.get("item_type") == "Episode" else "the movie"


def _join(words: list, conj: str = "or") -> str:
    words = [str(w) for w in words]
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + f" {conj} " + words[-1]


def match_when(when: dict, facts: dict, settings: dict) -> tuple:
    """(matched, because, why_not) for one rule's conditions.

    ``because`` lists plain phrases for every condition that held; ``why_not``
    is the first one that didn't, or None.
    """
    when = when or {}
    because: list = []
    what = _what(facts)
    item_type = facts.get("item_type") or "Movie"

    media = str(when.get("media_type") or "any").lower()
    if media in ("movie", "episode"):
        is_episode = item_type == "Episode"
        if (media == "episode") != is_episode:
            return False, because, (f"it's {'an episode' if is_episode else 'a movie'}, "
                                    f"not {'an episode' if media == 'episode' else 'a movie'}")
        because.append(f"it's {'an episode' if is_episode else 'a movie'}")

    if when.get("first_episode_only") and item_type == "Episode":
        first = facts.get("first_in_session")
        if first is None:
            return False, because, "nobody said whether this is the first episode of a sitting"
        if not first:
            return False, because, "it isn't the first episode of this sitting"
        because.append("it's the first episode of a sitting")

    genres = [g for g in (when.get("genres") or []) if str(g).strip()]
    if genres:
        have = genre_keys(facts.get("genres") or [])
        hits = [g for g in genres if genre_keys([g]) & have]
        if not hits:
            shown = _join(facts.get("genres") or [], "and") or "no genre"
            return False, because, f"{what} is {shown}, not {_join(genres)}"
        because.append(f"{what} is in the {_join(hits)} genre")

    rating = facts.get("official_rating") or ""
    ratings = [r for r in (when.get("ratings") or []) if str(r).strip()]
    if ratings:
        wanted = {rating_key(r) for r in ratings}
        if is_unrated(rating):
            if "UNRATED" not in wanted and "NR" not in wanted and "NOT-RATED" not in wanted:
                return False, because, f"{what} has no age rating"
            because.append(f"{what} isn't rated")
        elif rating_key(rating) not in wanted:
            return False, because, f"{what} is rated {rating}, not {_join(ratings)}"
        else:
            because.append(f"{what} is rated {rating}")

    if when.get("kids_safe"):
        safe = is_kids_safe(rating, unrated_is_safe=bool(settings.get("unrated_is_kids_safe")),
                            safe_ratings=settings.get("kids_safe_ratings"))
        if not safe:
            if is_unrated(rating):
                return False, because, f"{what} has no age rating, and unrated titles don't count as kids-safe"
            return False, because, f"{what} is rated {rating}, which isn't kids-safe"
        because.append(f"{what} is rated {rating or 'unrated'}, which is kids-safe" if not ratings else
                       "that rating is kids-safe")

    decades = [d for d in (when.get("decades") or []) if decade_of(d) is not None]
    year_from, year_to = when.get("year_from"), when.get("year_to")
    if decades or year_from or year_to:
        answer = year_matches(facts.get("year"), decades, year_from, year_to)
        if answer is None:
            return False, because, f"nobody said when {what} came out"
        if not answer:
            return False, because, f"{what} came out in {facts.get('year')}"
        because.append(f"{what} came out in {facts.get('year')}")

    libraries = [lib for lib in (when.get("libraries") or []) if str(lib).strip()]
    if libraries:
        have = {_norm(facts.get("library_name")), _norm(facts.get("library_id"))} - {""}
        if not have:
            return False, because, "nobody said which library it's in"
        hit = next((lib for lib in libraries if _norm(lib) in have), None)
        if hit is None:
            return False, because, f"it's in the {facts.get('library_name') or 'another'} library"
        because.append(f"it's in the {facts.get('library_name') or hit} library")

    users = [u for u in (when.get("users") or []) if str(u).strip()]
    if users:
        have = {_norm(facts.get("user_name")), _norm(facts.get("user_id"))} - {""}
        if not have:
            return False, because, "nobody said who is watching"
        hit = next((u for u in users if _norm(u) in have), None)
        if hit is None:
            return False, because, f"{facts.get('user_name') or 'someone else'} is watching"
        because.append(f"{facts.get('user_name') or hit} is watching")

    if not because:
        because.append("it has no conditions, so it matches everything")
    return True, because, None


def first_match(rules: list, facts: dict, settings: dict) -> tuple:
    """(rule or None, explanation, checks) for the first enabled matching rule."""
    checks = []
    for rule in rules:
        if not rule.get("enabled", True):
            checks.append({"rule_id": rule.get("id"), "name": rule.get("name"), "matched": False,
                           "why": "This rule is turned off."})
            continue
        matched, because, why_not = match_when(rule.get("when") or {}, facts, settings)
        if matched:
            text = f"Matches '{rule.get('name')}' because {_join(because, 'and')}."
            checks.append({"rule_id": rule.get("id"), "name": rule.get("name"), "matched": True, "why": text})
            return rule, text, checks
        checks.append({"rule_id": rule.get("id"), "name": rule.get("name"), "matched": False,
                       "why": f"Doesn't match: {why_not}."})
    return None, "No rule matches, so your schedules decide.", checks


# ---------------------------------------------------------------------------
# "Never play an intro before this title"
# ---------------------------------------------------------------------------

def exclusion_reason(exclusions: list, facts: dict, settings: dict) -> Optional[str]:
    """Why this playback gets no intros, or None when it may have them."""
    title = facts.get("item_name") or facts.get("series_name") or "This title"
    item_ids = {str(v).strip().lower().replace("-", "") for v in (facts.get("item_id"), facts.get("series_id")) if v}
    titles = set().union(*(_title_keys(v) for v in (facts.get("item_name"), facts.get("series_name")) if v))
    tags = {_tag_key(t): t for t in (facts.get("tags") or [])}
    for row in exclusions:
        kind, value = row.get("kind"), str(row.get("value") or "")
        if kind == "item" and value.strip().lower().replace("-", "") in item_ids:
            return f"No intros: '{title}' is on your never-play list."
        if kind == "title" and _title_keys(value) & titles:
            return f"No intros: '{title}' is on your never-play list."
        if kind == "tag" and _tag_key(value) in tags:
            return f"No intros: '{title}' has the tag '{tags[_tag_key(value)]}'."
    if settings.get("honor_no_intro_tags", True):
        auto = {_tag_key(t) for t in (settings.get("no_intro_tags") or [])}
        for key, tag in tags.items():
            if key in auto:
                return f"No intros: '{title}' has the tag '{tag}'."
    return None


# ---------------------------------------------------------------------------
# What a rule plays
# ---------------------------------------------------------------------------

def _label(preroll) -> str:
    return (getattr(preroll, "display_name", None) or os.path.splitext(preroll.filename or "")[0]
            or f"Intro {preroll.id}")


def candidates(db, play: dict) -> tuple:
    """(prerolls in play order, collection or None, problem or None)."""
    from backend import models
    from backend.scheduler import prerolls_for_category_query

    collection = None
    if play.get("collection_id"):
        collection = db.query(models.Category).filter(models.Category.id == int(play["collection_id"])).first()
        if collection is None:
            return [], None, "Its collection was deleted."
        rows = prerolls_for_category_query(db, collection.id).order_by(models.Preroll.id.asc()).all()
    else:
        ids = []
        for value in play.get("preroll_ids") or []:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        found = {p.id: p for p in db.query(models.Preroll).filter(models.Preroll.id.in_(ids)).all()} if ids else {}
        rows = [found[i] for i in ids if i in found and getattr(found[i], "enabled", True) is not False]
        if ids and not rows:
            return [], None, "Its intro videos were deleted or turned off."
    rows = [p for p in rows if p.path and os.path.isfile(p.path)]
    if not rows:
        what = f"'{collection.name}'" if collection is not None else "Its list"
        return [], collection, f"{what} has no intro videos whose files are there."
    return rows, collection, None


def choose(db, rule: dict, *, dry_run: bool = False) -> tuple:
    """(prerolls to play, problem or None). ``dry_run`` doesn't move rotations."""
    play = rule.get("play") or {}
    rows, collection, problem = candidates(db, play)
    if problem:
        return [], problem
    order = play.get("order") or "random"
    count = play.get("count")
    if order == "in_order":
        limit = int(count) if count else len(rows)
        return rows[:limit], None
    count = int(count or 1)
    if dry_run:
        return rows, None
    from backend import weighting
    hours = play.get("cooldown_hours") or None
    picked = weighting.sample_prerolls(db, ("rule", rule.get("id")), rows, count,
                                       category_id=collection.id if collection is not None else None,
                                       cooldown_hours=hours)
    return picked, None


def describe_play(play: dict, collection_name: Optional[str], prerolls: Optional[list] = None) -> str:
    order = play.get("order") or "random"
    count = play.get("count")
    source = f"'{collection_name}'" if collection_name else "the chosen intros"
    if order == "in_order":
        return f"Plays {('the first ' + str(count)) if count else 'all'} of {source} in order."
    n = int(count or 1)
    text = f"Plays {n} intro{'s' if n != 1 else ''} at random from {source}"
    if play.get("cooldown_hours"):
        text += f", not repeating one within {play['cooldown_hours']} hours"
    return text + "."


def describe_when(when: dict) -> str:
    when = when or {}
    parts = []
    media = when.get("media_type") or "any"
    if media == "movie":
        parts.append("a movie")
    elif media == "episode":
        parts.append("an episode")
    if when.get("first_episode_only"):
        parts.append("only the first episode of a sitting")
    if when.get("genres"):
        parts.append("genre " + _join(when["genres"]))
    if when.get("ratings"):
        parts.append("rated " + _join(when["ratings"]))
    if when.get("kids_safe"):
        parts.append("rated kids-safe")
    years = [f"{decade_of(d)}s" for d in (when.get("decades") or []) if decade_of(d) is not None]
    if when.get("year_from") or when.get("year_to"):
        years.append(f"{when.get('year_from') or '…'}–{when.get('year_to') or '…'}")
    if years:
        parts.append("from " + _join(years))
    if when.get("libraries"):
        parts.append("in the " + _join(when["libraries"]) + " library")
    if when.get("users"):
        parts.append("watched by " + _join(when["users"]))
    return ("When " + _join(parts, "and") + ".") if parts else "Always (no conditions)."


def resolve(db, facts: dict, settings: dict, *, rules: Optional[list] = None,
            exclusions: Optional[list] = None) -> Optional[dict]:
    """The rule-set answer for one playback, or None to let schedules decide.

    Returns ``{"paths", "mode": "sequential", "reason", "rule", "excluded"}``.
    """
    from backend import models

    if exclusions is None:
        exclusions = [{"kind": e.kind, "value": e.value} for e in db.query(models.IntroExclusion).all()]
    reason = exclusion_reason(exclusions, facts, settings)
    if reason:
        return {"paths": [], "mode": "sequential", "reason": reason, "rule": None, "excluded": True}
    if rules is None:
        rules = [rule_dict(r) for r in db.query(models.IntroRule).order_by(models.IntroRule.position,
                                                                            models.IntroRule.id).all()]
    if not rules:
        return None
    rule, explanation, _checks = first_match(rules, facts, settings)
    if rule is None:
        return None
    picked, problem = choose(db, rule)
    if problem:
        logger.warning("Rule '%s' matched but can't play anything: %s Falling back to schedules.",
                       rule.get("name"), problem)
        return None
    return {"paths": [os.path.abspath(p.path) for p in picked], "mode": "sequential",
            "reason": explanation, "rule": rule.get("name"), "excluded": False}


def pool_paths(db) -> list:
    """Every file an enabled rule could play (the plugin's download-ahead list)."""
    from backend import models
    paths = []
    for row in db.query(models.IntroRule).filter(models.IntroRule.enabled == True).all():  # noqa: E712
        rows, _collection, _problem = candidates(db, rule_dict(row).get("play") or {})
        paths.extend(os.path.abspath(p.path) for p in rows)
    return list(dict.fromkeys(paths))
