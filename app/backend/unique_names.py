"""One name per schedule, playlist and rule.

Names are compared the way people read them: spaces at the ends and runs of
spaces don't count, and neither does upper or lower case ("halloween " is the
same as "Halloween").

- Saving a name another item already has is refused with a plain message.
- Imports and restores never refuse: a name that is taken gets " (2)", " (3)"
  added, the way file managers, Plex and Sonarr do it, and the caller reports
  the new name.
- Old databases (NeXroll) may already hold two items with one name. They keep
  working; ``shared_name_ids`` tells the list which ones to point out.
"""
from __future__ import annotations

from typing import Iterable, Optional

from backend import models
from backend.errors import AppError, conflict

# What each kind is called in messages, and its table.
KINDS = {
    "schedule": models.Schedule,
    "playlist": models.SavedSequence,
    "rule": models.IntroRule,
}


def name_key(name: Optional[str]) -> str:
    """The form two names are compared in."""
    return " ".join(str(name or "").split()).casefold()


def _rows(db, kind: str) -> list:
    model = KINDS[kind]
    return db.query(model.id, model.name).all()


def name_taken(db, kind: str, name: str, exclude_id: Optional[int] = None):
    """The (id, name) of another item of this kind with the same name, or None."""
    key = name_key(name)
    for row_id, row_name in _rows(db, kind):
        if row_id != exclude_id and name_key(row_name) == key:
            return row_id, row_name
    return None


def name_conflict(kind: str, existing_name: str) -> AppError:
    message = f"There's already a {kind} called '{' '.join(str(existing_name).split())}'. Pick another name."
    return conflict(message, field="name", code="name_taken")


def check_unique(db, kind: str, name: str, exclude_id: Optional[int] = None) -> None:
    """Raise the plain 409 when the name is taken by another item of this kind."""
    taken = name_taken(db, kind, name, exclude_id)
    if taken is not None:
        raise name_conflict(kind, taken[1])


def check_rename(db, kind: str, current: Optional[str], new: str, item_id: int) -> None:
    """Like ``check_unique``, for an edit: only a changed name is checked, so an
    item that already shares its name (an old database) can still be switched
    on or off and edited."""
    if name_key(current) != name_key(new):
        check_unique(db, kind, new, exclude_id=item_id)


def numbered(name: str, taken: Iterable[str], *, max_len: int = 200) -> str:
    """``name``, or ``name (2)``, ``name (3)``... whichever isn't in ``taken`` yet.

    The base is shortened when needed so the result stays within ``max_len``.
    """
    used = {name_key(n) for n in taken}
    base = " ".join(str(name or "").split()) or "Untitled"
    if name_key(base) not in used:
        return base[:max_len]
    counter = 2
    while True:
        suffix = f" ({counter})"
        candidate = base[: max_len - len(suffix)].rstrip() + suffix
        if name_key(candidate) not in used:
            return candidate
        counter += 1


def unique_name(db, kind: str, name: str, *, also_taken: Iterable[str] = (), max_len: int = 200) -> str:
    """A free name for an item being imported: the same name when it is free."""
    taken = [row_name for _id, row_name in _rows(db, kind)]
    return numbered(name, [*taken, *also_taken], max_len=max_len)


def renamed_note(kind: str, old: str, new: str) -> str:
    """The sentence an import or restore report shows for a renamed item."""
    return f"The {kind} \"{old}\" was saved as \"{new}\", because another {kind} already has that name."


def shared_name_ids(db, kind: str) -> set:
    """Ids of items whose name another item of the same kind also has."""
    groups: dict = {}
    for row_id, row_name in _rows(db, kind):
        groups.setdefault(name_key(row_name), []).append(row_id)
    return {i for ids in groups.values() if len(ids) > 1 for i in ids}
