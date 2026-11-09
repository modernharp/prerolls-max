"""Weighted random picks and "don't repeat within N hours".

Every intro has a weight from 1 (rarely) to 10 (often); 5 is normal. A
collection (or a rule) may have a cooldown: an intro that played within that
many hours is left out of random picks while anything else is available.

Weights ride on the shuffle bag (shuffle_bag.py): an intro goes into the bag
``weight / gcd(weights)`` times, so over one round of the bag a weight-10 intro
plays exactly twice as often as a weight-5 one, and the bag still spreads the
plays out instead of clumping them. When every weight is the same the bag holds
each intro once, exactly as before weights existed.

On Plex, which picks at random from one list itself, weights are written by
listing an intro more than once (weight 10 next to weight 5 is listed twice),
and intros in their cooldown are left out whenever Prerolls Max writes the
list.
"""
from __future__ import annotations

import datetime
import logging
import math
import os
from dataclasses import dataclass, field
from functools import reduce
from typing import Any, Callable, Hashable, Iterable, Optional

from backend.shuffle_bag import _default_item_key, shuffle_bag_sample
from backend.timeutil import utcnow

logger = logging.getLogger("prerollsmax.weighting")

DEFAULT_WEIGHT = 5
MIN_WEIGHT, MAX_WEIGHT = 1, 10
# Plex's intro list has to stay under about 8,000 characters.
PLEX_MAX_CHARS = 7000
# Most copies of all intros together in one weighted bag.
MAX_BAG_TOKENS = 400


def weight_of(item) -> int:
    try:
        value = int(getattr(item, "weight", None) or DEFAULT_WEIGHT)
    except (TypeError, ValueError):
        value = DEFAULT_WEIGHT
    return max(MIN_WEIGHT, min(MAX_WEIGHT, value))


def in_cooldown(last: Optional[datetime.datetime], hours: float, now: datetime.datetime) -> bool:
    return bool(hours and last and now - last < datetime.timedelta(hours=hours))


@dataclass(frozen=True)
class _Token:
    """One copy of an intro in a weighted bag."""
    key: Any
    item: Any = field(compare=False, hash=False)


def copies_for(weights: list, budget: int = MAX_BAG_TOKENS) -> list:
    """How many times each weight goes into a bag (or a Plex list)."""
    divisor = reduce(math.gcd, weights)
    copies = [w // divisor for w in weights]
    while sum(copies) > budget and max(copies) > 1:
        copies = [max(1, round(c / 2)) for c in copies]
    return copies


def pick(bag_key: Hashable, items: Iterable, count: int, *, weight: Callable = weight_of,
         last_played: Optional[dict] = None, cooldown_hours: float = 0,
         now: Optional[datetime.datetime] = None) -> list:
    """Pick ``count`` different items for one playback.

    ``last_played`` maps item ids to when they last played (for cooldowns).
    """
    pool, seen = [], set()
    for item in items or []:
        key = _default_item_key(item)
        if key not in seen:
            seen.add(key)
            pool.append(item)
    if not pool or count <= 0:
        return []
    count = min(int(count), len(pool))
    now = now or utcnow()
    last_played = last_played or {}

    eligible = pool
    if cooldown_hours:
        eligible = [i for i in pool if not in_cooldown(last_played.get(getattr(i, "id", None)), cooldown_hours, now)]
        if len(eligible) < count:
            # Everything is cooling down: play the ones that played longest ago.
            chosen_ids = {id(i) for i in eligible}
            resting = sorted((i for i in pool if id(i) not in chosen_ids),
                             key=lambda i: last_played.get(getattr(i, "id", None)) or datetime.datetime.min)
            eligible = eligible + resting[:count - len(eligible)]

    weights = [weight(i) for i in eligible]
    if len(set(weights)) <= 1:
        return shuffle_bag_sample(bag_key, eligible, count)

    tokens = [_Token((_default_item_key(item), n), item)
              for item, copies in zip(eligible, copies_for(weights)) for n in range(copies)]
    chosen, chosen_keys = [], set()
    attempts = 0
    while len(chosen) < count and attempts < count * 20:
        attempts += 1
        token = shuffle_bag_sample(("weighted", bag_key), tokens, 1, item_key=lambda t: t.key)[0]
        if token.key[0] not in chosen_keys:
            chosen_keys.add(token.key[0])
            chosen.append(token.item)
    if len(chosen) < count:
        chosen += [i for i in eligible if _default_item_key(i) not in chosen_keys][:count - len(chosen)]
    return chosen


def uses_weighting(items: Iterable, cooldown_hours: float = 0) -> bool:
    return bool(cooldown_hours) or len({weight_of(i) for i in items}) > 1


def category_cooldown(db, category_id) -> int:
    from backend import models
    try:
        category = db.query(models.Category).filter(models.Category.id == int(category_id)).first()
    except (TypeError, ValueError):
        return 0
    try:
        return max(0, int(getattr(category, "cooldown_hours", 0) or 0)) if category else 0
    except (TypeError, ValueError):
        return 0


def sample_prerolls(db, bag_key: Hashable, pool: list, count: int, *, category_id=None,
                    cooldown_hours: Optional[float] = None) -> list:
    """The random pick for a collection or rule, with weights and cooldowns.

    Falls back to the plain shuffle bag when nothing is weighted.
    """
    hours = cooldown_hours if cooldown_hours else (category_cooldown(db, category_id) if category_id else 0)
    if not uses_weighting(pool, hours):
        return shuffle_bag_sample(bag_key, pool, count)
    last = {}
    if hours:
        from backend.play_history import last_played
        try:
            last = last_played(db, [p.id for p in pool])
        except Exception:
            last = {}
    return pick(bag_key, pool, count, last_played=last, cooldown_hours=hours)


def sample_paths(bag_key: Hashable, paths: list, count: int, *, category_id=None) -> list:
    """Same as sample_prerolls for a list of file paths (the plugin's random
    category), looking the intros up by path. Unknown files weigh 5."""
    pool = list(dict.fromkeys(paths))
    try:
        from backend import models
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            rows = db.query(models.Preroll).filter(models.Preroll.path.in_(pool)).all()
            by_path = {os.path.abspath(r.path): r for r in rows if r.path}
            hours = category_cooldown(db, category_id) if category_id else 0
            items = [by_path.get(os.path.abspath(p)) for p in pool]
            if all(i is not None for i in items) and uses_weighting(items, hours):
                picked = sample_prerolls(db, bag_key, items, count, category_id=category_id)
                return [os.path.abspath(i.path) for i in picked]
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Weighted pick unavailable, using the plain rotation: %s", exc)
    return shuffle_bag_sample(bag_key, pool, count)


def plex_entries(prerolls: list, *, random_mode: bool, cooldown_hours: float = 0,
                 last_played: Optional[dict] = None, now: Optional[datetime.datetime] = None,
                 path_length: Callable = lambda p: len(p.path or "") + 1,
                 max_chars: int = PLEX_MAX_CHARS) -> list:
    """The intros to write into Plex's list, with weights and cooldowns applied.

    Only random lists (Plex picks one entry at random) are weighted: an intro
    appears ``weight / gcd(weights)`` times, scaled down until the list fits
    Plex's length limit. Intros in their cooldown are left out while at least
    one other can play. A list with nothing weighted comes back unchanged.
    """
    items = list(prerolls)
    if not random_mode or not items:
        return items
    now = now or utcnow()
    if cooldown_hours and last_played:
        resting = [p for p in items if in_cooldown(last_played.get(p.id), cooldown_hours, now)]
        if resting and len(resting) < len(items):
            items = [p for p in items if p not in resting]
    weights = [weight_of(p) for p in items]
    if len(set(weights)) <= 1:
        return items
    copies = copies_for(weights)
    top = max(copies)
    for scale in range(top, 0, -1):
        scaled = [max(1, round(c * scale / top)) for c in copies]
        total = sum(n * path_length(p) for n, p in zip(scaled, items))
        if total <= max_chars or scale == 1:
            copies = scaled
            break
    # Spread the copies through the list rather than in runs, so the list
    # reads sensibly to anyone who opens Plex's setting.
    out = []
    for round_index in range(max(copies)):
        out.extend(p for p, n in zip(items, copies) if n > round_index)
    return out
