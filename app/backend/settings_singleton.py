"""Collapsing duplicate Setting rows.

`Setting` is a singleton - every read is `db.query(models.Setting).first()`. But
roughly twenty places create one with the `if not setting: create` pattern, and
on a fresh database a first page load fires a dozen endpoints at once. Two of
them can both see no row and both insert, and from then on the app has two
settings rows and reads whichever `.first()` returns.

That is not a cosmetic duplicate. On a real install the startup hook adopted the
container's `TZ` into one row while the scheduler read the other, which still
held the `UTC` column default - so every time-of-day schedule was evaluated
hours away from the time the user typed in. A "kids' prerolls before 8pm" rule
stayed active all evening, and the rule meant to replace it never started.

The merge decision lives here, free of the database, so it can be tested.
"""
from __future__ import annotations

import re
from typing import Any, Optional, Sequence

# Flags that only ever go from off to on through a deliberate act: accepting
# terms, finishing onboarding, turning login on. If any duplicate row has one
# on, the merged row keeps it on: dropping it would ask the user again, or (for
# auth_enabled) silently turn login off.
_ONE_WAY_FLAG = re.compile(r"(^|_)(accepted|agreed|acknowledged|complete|completed|seen)$")
ONE_WAY_FLAGS = frozenset({"auth_enabled"})


def is_one_way_flag(column: str) -> bool:
    return column in ONE_WAY_FLAGS or bool(_ONE_WAY_FLAG.search(column))


def choose_survivor(rows: Sequence[Any]) -> Optional[Any]:
    """Which duplicate row to keep.

    The most recently updated one: that is the row the app has actually been
    writing to, so keeping it preserves the newest configuration. Rows without
    an `updated_at` sort oldest, and a tie goes to the highest id, which is the
    later insert.
    """
    if not rows:
        return None

    def key(row):
        updated = getattr(row, "updated_at", None)
        return (updated is not None, updated, getattr(row, "id", 0) or 0)

    return max(rows, key=key)


def fields_to_backfill(survivor: Any, others: Sequence[Any],
                       columns: Sequence[str]) -> dict:
    """Values the survivor is missing that a discarded row can supply.

    Only fills columns that are None or empty on the survivor, so a real choice
    is never overwritten by a stale duplicate. Where several discarded rows have
    a value, the most recently updated wins - same rule as the survivor itself.

    One-way flags (``is_one_way_flag``: terms accepted, onboarding complete,
    login on) are the exception: a False on the survivor is usually just the
    column default, so a True on any discarded row wins.
    """
    filled = {}
    ranked = sorted(
        others,
        key=lambda r: (getattr(r, "updated_at", None) is not None,
                       getattr(r, "updated_at", None),
                       getattr(r, "id", 0) or 0),
        reverse=True,
    )
    for column in columns:
        current = getattr(survivor, column, None)
        if is_one_way_flag(column) and current is not True:
            if any(getattr(row, column, None) is True for row in ranked):
                filled[column] = True
            continue
        if current is not None and current != "":
            continue
        for row in ranked:
            candidate = getattr(row, column, None)
            if candidate is not None and candidate != "":
                filled[column] = candidate
                break
    return filled
