"""The collections Prerolls Max fills itself (trailers, video maker output).

NeXroll found them by name ("NeX-Up Movie Trailers"), so renaming one broke
every lookup. Each now carries a stable ``Category.system_key`` and the code
looks it up by that key; the name is only what people see.

``migrate`` runs on every start and after a restore. It is idempotent:

1. A built-in collection without a key is found by its old NeXroll name and
   tagged with its key.
2. A tagged collection that still has an old name gets the new one, unless
   the person already has a collection called that (ignoring case); then it
   becomes "<new name> (built-in)" (numbered if even that is taken).

Old names keep working wherever a name comes from outside: backups, restores
and playlist (.nexseq) imports translate them with ``current_name``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

from backend import models
from backend.unique_names import name_key, numbered

logger = logging.getLogger("prerollsmax.system_collections")

MOVIE_TRAILERS = "movie_trailers"
TV_TRAILERS = "tv_trailers"
VIDEO_MAKER = "video_maker"
COMING_SOON_LISTS = "coming_soon_lists"


@dataclass(frozen=True)
class Spec:
    key: str
    name: str
    description: str
    old_names: tuple = ()


SPECS = {
    MOVIE_TRAILERS: Spec(
        MOVIE_TRAILERS, "Movie trailers",
        "Trailers for movies coming soon, from Radarr. Prerolls Max fills this collection itself.",
        ("NeX-Up Movie Trailers",),
    ),
    TV_TRAILERS: Spec(
        TV_TRAILERS, "TV trailers",
        "Trailers for TV seasons coming soon, from Sonarr. Prerolls Max fills this collection itself.",
        ("NeX-Up TV Trailers",),
    ),
    VIDEO_MAKER: Spec(
        VIDEO_MAKER, "Video maker",
        "Intro videos made with the video maker. Prerolls Max fills this collection itself.",
        ("NeX-Up Prerolls",),
    ),
    COMING_SOON_LISTS: Spec(
        COMING_SOON_LISTS, "Coming Soon Lists",
        "Coming soon videos listing upcoming releases. Prerolls Max fills this collection itself.",
        (),
    ),
}

# Old descriptions NeXroll wrote; replaced by the plain ones above.
_OLD_DESCRIPTION_MARKERS = ("NeX-Up",)

BUILT_IN_SUFFIX = " (built-in)"


def _old_keys(spec: Spec) -> set:
    return {name_key(n) for n in spec.old_names}


def key_for_name(name: Optional[str]) -> Optional[str]:
    """The key of a built-in collection called ``name`` now or in NeXroll."""
    wanted = name_key(name)
    if not wanted:
        return None
    for spec in SPECS.values():
        if wanted in _old_keys(spec):
            return spec.key
    return None


def find(db, key: str):
    """The collection with this key, or None."""
    return (db.query(models.Category)
            .filter(models.Category.system_key == key)
            .order_by(models.Category.id)
            .first())


def get_or_create(db, key: str, *, commit: bool = True):
    """The collection with this key, made (and named) when it doesn't exist yet."""
    category = find(db, key)
    if category is not None:
        return category
    spec = SPECS[key]
    category = models.Category(
        name=free_name(db, spec.name),
        description=spec.description,
        plex_mode="shuffle",
        apply_to_plex=False,
        is_system=True,
        system_key=key,
    )
    db.add(category)
    if commit:
        db.commit()
        db.refresh(category)
    else:
        db.flush()
    return category


def free_name(db, wanted: str, *, exclude_id: Optional[int] = None) -> str:
    """``wanted`` when no other collection has it (ignoring case), else
    "<wanted> (built-in)", numbered when even that is taken."""
    taken = [name for cid, name in db.query(models.Category.id, models.Category.name).all() if cid != exclude_id]
    if name_key(wanted) not in {name_key(n) for n in taken}:
        return wanted
    return numbered(wanted + BUILT_IN_SUFFIX, taken)


def current_name(db, name: Optional[str]) -> Optional[str]:
    """For a name from a backup or playlist file: the built-in collection's
    name today when ``name`` is one of its old names, otherwise ``name``."""
    key = key_for_name(name)
    if not key:
        return name
    category = find(db, key)
    return category.name if category is not None else SPECS[key].name


def upgrade_block_names(db, blocks: Iterable) -> int:
    """Rewrite old built-in collection names in playlist blocks (as found in
    .nexseq files) to today's names. Returns how many were changed."""
    changed = 0
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        name = block.get("category_name")
        if isinstance(name, str):
            new = current_name(db, name)
            if new != name:
                block["category_name"] = new
                changed += 1
        names = block.get("category_names")
        if isinstance(names, list):
            new_names = [current_name(db, n) if isinstance(n, str) else n for n in names]
            if new_names != names:
                block["category_names"] = new_names
                changed += 1
        for ref in block.get("prerolls") or []:
            if isinstance(ref, dict) and isinstance(ref.get("category_names"), list):
                ref["category_names"] = [current_name(db, n) if isinstance(n, str) else n
                                         for n in ref["category_names"]]
    return changed


def upgrade_pattern_names(db, pattern) -> int:
    """``upgrade_block_names`` for a whole .nexseq / .nexbundle document."""
    if not isinstance(pattern, dict):
        return 0
    changed = upgrade_block_names(db, pattern.get("blocks"))
    for seq in pattern.get("sequences") or []:
        if isinstance(seq, dict):
            changed += upgrade_block_names(db, seq.get("blocks"))
    return changed


def migrate(db) -> list:
    """Tag and rename the built-in collections. Returns plain sentences for
    what changed (for the log); safe to run any number of times."""
    notes = []
    rows = db.query(models.Category).all()
    for spec in SPECS.values():
        tagged = [c for c in rows if getattr(c, "system_key", None) == spec.key]
        category = tagged[0] if tagged else None
        if category is None:
            if spec.old_names:
                matches = [c for c in rows if not getattr(c, "system_key", None) and name_key(c.name) in _old_keys(spec)]
            else:
                # Never renamed, so only a row Prerolls Max made counts.
                matches = [c for c in rows if not getattr(c, "system_key", None) and getattr(c, "is_system", False)
                           and name_key(c.name) == name_key(spec.name)]
            # A NeXroll row is a system collection; prefer it over a look-alike.
            matches.sort(key=lambda c: (not getattr(c, "is_system", False), c.id))
            if not matches:
                continue
            category = matches[0]
            category.system_key = spec.key
            category.is_system = True
            notes.append(f'Marked "{category.name}" as the built-in "{spec.name}" collection.')
        if name_key(category.name) in _old_keys(spec):
            old_name = category.name
            category.name = free_name(db, spec.name, exclude_id=category.id)
            notes.append(f'Renamed the collection "{old_name}" to "{category.name}".')
        if not category.description or any(m in category.description for m in _OLD_DESCRIPTION_MARKERS):
            category.description = spec.description
    if db.dirty or db.new:
        db.commit()
    for note in notes:
        logger.info(note)
    return notes


def migrate_with(session_factory) -> list:
    """``migrate`` in a session of its own; never raises (start-up must go on)."""
    try:
        db = session_factory()
    except Exception as exc:
        logger.warning("Built-in collections not checked: %s", exc)
        return []
    try:
        return migrate(db)
    except Exception as exc:
        logger.warning("Built-in collections not checked: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
        return []
    finally:
        db.close()
