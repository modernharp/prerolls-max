"""Which community items are already in the library, and the id migration.

An item is "in the library" when a preroll carries its id (``pm:...`` /
``tn:...``, or one of the item's other copies or platform versions). Failing
that:

* Prerolls.me: a local file with exactly the item's byte size, and, when
  Prerolls Max knows the item's MD5 (from the storage ETag of an earlier
  download), the same MD5.
* Prerolls.uk: a local file with exactly the item's byte size (the rule
  community_match uses for "the same file").

Match Existing Prerolls and auto-match use :class:`SourceAwareMatcher`:
Prerolls.me by exact size first, then the Prerolls.uk matcher (size, or
title and length, see community_match), with every id tagged.
"""

from __future__ import annotations

import hashlib
import os
import threading
from typing import Iterable, List, Optional

from sqlalchemy import or_

from backend import models
from backend.community import ids

_md5_cache: dict = {}
_md5_lock = threading.Lock()


def local_md5(path: str) -> Optional[str]:
    """MD5 of a local file, cached by path, size and modification time."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (path, st.st_size, st.st_mtime_ns)
    with _md5_lock:
        if key in _md5_cache:
            return _md5_cache[key]
    digest = hashlib.md5()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    value = digest.hexdigest()
    with _md5_lock:
        if len(_md5_cache) > 2000:
            _md5_cache.clear()
        _md5_cache[key] = value
    return value


def _label(preroll) -> dict:
    return {"preroll_id": preroll.id, "name": preroll.display_name or preroll.filename}


def annotate(db, items: List[dict], known_md5=lambda item: None) -> List[dict]:
    """Fill in ``in_library`` on each item, in place. Returns the list."""
    if not items:
        return items
    wanted = {}
    for item in items:
        for item_id in [item["id"]] + [v["id"] for v in item.get("versions") or ()] + list(item.get("_also") or ()):
            wanted.setdefault(item_id, []).append(item)
    tagged = list(wanted)
    legacy = [i[3:] for i in tagged if i.startswith("tn:")]   # rows not migrated yet
    rows = db.query(models.Preroll).filter(
        or_(models.Preroll.community_preroll_id.in_(tagged), models.Preroll.community_preroll_id.in_(legacy))
    ).all() if tagged else []
    by_id = {}
    for row in rows:
        by_id.setdefault(ids.tag_legacy(row.community_preroll_id), row)
    for item_id, holders in wanted.items():
        row = by_id.get(item_id)
        if row:
            for item in holders:
                if not item.get("in_library"):
                    item["in_library"] = _label(row)

    sizes = {item["size_bytes"] for item in items
             if not item.get("in_library") and item.get("size_bytes") and item.get("downloadable")}
    if not sizes:
        return items
    local = db.query(models.Preroll).filter(models.Preroll.file_size.in_(sizes)).all()
    by_size: dict = {}
    for row in local:
        by_size.setdefault(int(row.file_size), []).append(row)
    for item in items:
        if item.get("in_library") or not item.get("size_bytes"):
            continue
        candidates = by_size.get(int(item["size_bytes"]), [])
        md5 = known_md5(item) if item.get("source") == "prerollsme" else None
        for row in candidates:
            if md5 and local_md5(row.path or "") != md5:
                continue
            item["in_library"] = _label(row)
            break
    return items


class SourceAwareMatcher:
    """community_match.Matcher with tagged ids and Prerolls.me tried first."""

    def __init__(self, uk_matcher=None, me_by_size: Optional[dict] = None, me_md5=lambda item: None):
        self.uk = uk_matcher
        self.me_by_size = me_by_size or {}
        self.me_md5 = me_md5

    def __len__(self):
        return (len(self.uk) if self.uk is not None else 0) + len(self.me_by_size)

    def match(self, names: Iterable[Optional[str]], size: Optional[int] = None, seconds=None,
              platform: Optional[str] = None, path: Optional[str] = None) -> dict:
        if size and int(size) in self.me_by_size:
            item = self.me_by_size[int(size)]
            md5 = self.me_md5(item)
            if not md5 or not path or local_md5(path) == md5:
                return {"entry": item, "id": item["id"], "title": item["title"], "how": "file",
                        "confidence": 100, "suggestions": []}
        if self.uk is None:
            return {"entry": None, "id": None, "title": None, "how": None, "confidence": 0, "suggestions": []}
        result = self.uk.match(names, size=size, seconds=seconds, platform=platform)
        result = dict(result)
        if result.get("id"):
            result["id"] = ids.tag_legacy(result["id"])
        result["suggestions"] = [dict(s, id=ids.tag_legacy(s.get("id"))) for s in result.get("suggestions") or ()]
        return result


def tag_legacy_ids(db) -> int:
    """Prefix bare Prerolls.uk paths with ``tn:``. Safe to run again: tagged
    ids (and the old unreadable ``_...`` form) are left alone."""
    rows = db.query(models.Preroll).filter(models.Preroll.community_preroll_id.like("/%")).all()
    changed = 0
    for row in rows:
        tagged = ids.tag_legacy(row.community_preroll_id)
        if tagged and tagged != row.community_preroll_id:
            row.community_preroll_id = tagged
            changed += 1
    if changed:
        db.commit()
    return changed
