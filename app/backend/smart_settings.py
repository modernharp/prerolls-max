"""Settings for the smart features, kept in the ``feature_settings`` table.

    GET /api/smart-settings      -> every setting with its current value
    PUT /api/smart-settings      -> change some of them

Values are read often (every plugin request), so they are cached for a few
seconds; a save clears the cache.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.ratings import DEFAULT_KIDS_SAFE, rating_key

DEFAULT_NO_INTRO_TAGS = ["no-intro", "nointro", "no intro", "no-intros", "nointros"]

DEFAULTS: dict = {
    # Gap between episodes that still counts as one sitting, when the plugin
    # doesn't say itself (the plugin page has the same setting).
    "binge_window_hours": 4,
    # Kids-safe: which ratings count, and whether unrated titles do.
    "kids_safe_ratings": list(DEFAULT_KIDS_SAFE),
    "unrated_is_kids_safe": False,
    # "Never play an intro before this title": tags honoured automatically.
    "honor_no_intro_tags": True,
    "no_intro_tags": list(DEFAULT_NO_INTRO_TAGS),
    # Play history.
    "history_enabled": True,
    "history_retention_days": 90,
    # Backups carry play history only when asked: it names who watched what.
    "backup_includes_history": False,
    # Loudness: EBU R128 programme loudness (-23 LUFS), true peak -1 dBTP.
    "loudness_target_lufs": -23.0,
    "loudness_tolerance_lu": 2.0,
    # Missed-intro check: watch the media servers' sessions.
    "watch_sessions": True,
    # "Add from a web link" may fetch from this network (a NAS). Off: only
    # addresses on the internet, so a link can't reach into the home network.
    "links_allow_home_network": False,
}

_lock = threading.Lock()
_cache: dict = {"at": 0.0, "values": None}
CACHE_SECONDS = 5.0


class SmartSettingsUpdate(BaseModel):
    """PUT /api/smart-settings. Only the fields sent change."""

    model_config = ConfigDict(extra="forbid")

    binge_window_hours: Optional[int] = Field(None, ge=1, le=48)
    kids_safe_ratings: Optional[List[str]] = Field(None, max_length=60)
    unrated_is_kids_safe: Optional[bool] = None
    honor_no_intro_tags: Optional[bool] = None
    no_intro_tags: Optional[List[str]] = Field(None, max_length=30)
    history_enabled: Optional[bool] = None
    history_retention_days: Optional[int] = Field(None, ge=1, le=3650)
    backup_includes_history: Optional[bool] = None
    loudness_target_lufs: Optional[float] = Field(None, ge=-31, le=-10)
    loudness_tolerance_lu: Optional[float] = Field(None, ge=0.5, le=6)
    watch_sessions: Optional[bool] = None
    links_allow_home_network: Optional[bool] = None

    @field_validator("kids_safe_ratings")
    @classmethod
    def _ratings(cls, value):
        if value is None:
            return value
        out = []
        for item in value:
            key = rating_key(item)
            if not key or len(key) > 20:
                raise ValueError("Use age ratings like G, PG or TV-Y7.")
            if key not in out:
                out.append(key)
        return out

    @field_validator("no_intro_tags")
    @classmethod
    def _tags(cls, value):
        if value is None:
            return value
        out = []
        for item in value:
            text = str(item or "").strip()
            if not text or len(text) > 60:
                raise ValueError("Each tag needs 1 to 60 characters.")
            if text.lower() not in [t.lower() for t in out]:
                out.append(text)
        return out


def _read_all(db) -> dict:
    from backend import models
    values = dict(DEFAULTS)
    for row in db.query(models.FeatureSetting).all():
        if row.key in DEFAULTS:
            try:
                values[row.key] = json.loads(row.value) if row.value is not None else DEFAULTS[row.key]
            except ValueError:
                pass
    return values


def get_all(db=None) -> dict:
    """Every setting. Opens its own session when ``db`` is None."""
    now = time.monotonic()
    with _lock:
        if _cache["values"] is not None and now - _cache["at"] < CACHE_SECONDS:
            return dict(_cache["values"])
    own = db is None
    if own:
        from backend.database import SessionLocal
        db = SessionLocal()
    try:
        values = _read_all(db)
    except Exception:
        values = dict(DEFAULTS)
    finally:
        if own:
            db.close()
    with _lock:
        _cache.update(at=now, values=dict(values))
    return values


def get(key: str, db=None) -> Any:
    return get_all(db).get(key, DEFAULTS.get(key))


def save(db, changes: dict) -> dict:
    from backend import models
    for key, value in changes.items():
        if key not in DEFAULTS or value is None:
            continue
        row = db.query(models.FeatureSetting).filter(models.FeatureSetting.key == key).first()
        if row is None:
            row = models.FeatureSetting(key=key)
            db.add(row)
        row.value = json.dumps(value)
    db.commit()
    clear_cache()
    return get_all(db)


def clear_cache() -> None:
    with _lock:
        _cache.update(at=0.0, values=None)
