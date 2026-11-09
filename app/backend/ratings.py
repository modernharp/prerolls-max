"""Age ratings: families, spellings and "kids-safe".

Jellyfin and Emby store whatever rating the metadata provider gave ("PG-13",
"TV-Y7", "US-PG", "pg 13", "Unrated"...). Plex does the same in
``contentRating``. Rules compare ratings after :func:`rating_key` cleans them
up, so people can type them the way they read them.

Kids-safe means the US movie ratings G and PG and the US TV ratings TV-Y,
TV-Y7 (and TV-Y7-FV), TV-G and TV-PG, plus the UK's U and PG. A title with no
rating, or one marked "Not Rated"/"Unrated", is *not* kids-safe unless the
person says so in Settings: an unrated title is as likely to be a horror
festival cut as a home video, and a children's rule should rather miss a
cartoon than play before the wrong film.
"""
from __future__ import annotations

from typing import Iterable, Optional

# Country prefixes Jellyfin/Emby put in front of some ratings ("DE-12", "US-PG").
_COUNTRY_PREFIXES = ("US", "UK", "GB", "DE", "FR", "NL", "AU", "CA", "NZ", "IE", "ES", "IT", "SE", "NO",
                     "DK", "FI", "BR", "JP")

# Spellings that mean "no rating".
_UNRATED = {"NR", "NOT-RATED", "UNRATED", "UR", "NONE", "N/A", "NA", "APPROVED", "PASSED"}

FAMILIES = (
    {
        "id": "us_movies",
        "name": "US movies (MPAA)",
        "ratings": (
            ("G", "General audiences", True),
            ("PG", "Parental guidance suggested", True),
            ("PG-13", "Parents strongly cautioned", False),
            ("R", "Restricted", False),
            ("NC-17", "Adults only", False),
        ),
    },
    {
        "id": "us_tv",
        "name": "US TV",
        "ratings": (
            ("TV-Y", "All children", True),
            ("TV-Y7", "Older children", True),
            ("TV-Y7-FV", "Older children, fantasy violence", True),
            ("TV-G", "General audience", True),
            ("TV-PG", "Parental guidance suggested", True),
            ("TV-14", "Parents strongly cautioned", False),
            ("TV-MA", "Mature audiences only", False),
        ),
    },
    {
        "id": "uk",
        "name": "UK (BBFC)",
        "ratings": (
            ("U", "Universal", True),
            ("PG", "Parental guidance", True),
            ("12A", "12 and over, or with an adult", False),
            ("12", "12 and over", False),
            ("15", "15 and over", False),
            ("18", "Adults only", False),
        ),
    },
)

DEFAULT_KIDS_SAFE = ("G", "PG", "TV-Y", "TV-Y7", "TV-Y7-FV", "TV-G", "TV-PG", "U")


def rating_key(value) -> Optional[str]:
    """"PG-13", "pg 13" and "US-PG-13" all become "PG-13"; None when empty."""
    text = str(value or "").strip().upper().replace(" ", "-").replace("_", "-")
    while "--" in text:
        text = text.replace("--", "-")
    if not text:
        return None
    if len(text) > 3 and text[2] == "-" and text[:2] in _COUNTRY_PREFIXES and text[3:]:
        text = text[3:]
    if text in ("TVY", "TVY7", "TVG", "TVPG", "TV14", "TVMA"):
        text = "TV-" + text[2:]
    if text == "PG13":
        text = "PG-13"
    if text == "NC17":
        text = "NC-17"
    return text


def is_unrated(value) -> bool:
    key = rating_key(value)
    return key is None or key in _UNRATED


def is_kids_safe(value, *, unrated_is_safe: bool = False,
                 safe_ratings: Optional[Iterable[str]] = None) -> bool:
    """Whether a title with this rating may play before children's intros.

    ``safe_ratings`` replaces the default list when given (Settings lets
    people add their own country's ratings).
    """
    if is_unrated(value):
        return bool(unrated_is_safe)
    allowed = {rating_key(r) for r in (safe_ratings if safe_ratings is not None else DEFAULT_KIDS_SAFE)}
    return rating_key(value) in allowed


def family_of(value) -> Optional[str]:
    """The family id a rating belongs to ("us_movies", "us_tv", "uk"), or None."""
    key = rating_key(value)
    if key is None:
        return None
    for family in FAMILIES:
        if any(key == r[0] for r in family["ratings"]):
            return family["id"]
    return None


def families_for_ui(unrated_is_safe: bool = False, safe_ratings: Optional[Iterable[str]] = None) -> list:
    safe = {rating_key(r) for r in (safe_ratings if safe_ratings is not None else DEFAULT_KIDS_SAFE)}
    return [
        {"id": f["id"], "name": f["name"],
         "ratings": [{"value": value, "label": label, "kids_safe": value in safe}
                     for value, label, _default in f["ratings"]]}
        for f in FAMILIES
    ] + [{"id": "unrated", "name": "No rating",
          "ratings": [{"value": "Unrated", "label": "Not rated, or no rating at all",
                       "kids_safe": bool(unrated_is_safe)}]}]
