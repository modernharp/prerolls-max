"""The media server list in a settings backup (``media_servers``).

Each server comes with its token or API key unless the backup was fetched
with an API key (then ``token`` is empty, as for the other credentials). On
restore, a server without a token keeps the one this install already has for
the same address; a server with no token either way is left out and named in
``skipped``. A backup without ``media_servers`` leaves the list alone (the
settings row's servers are adopted as on any start).
"""
from __future__ import annotations

import json
import logging

from backend import media_servers as ms, models, path_mapping
from backend import validation as vld

logger = logging.getLogger("prerollsmax.servers")


def export(db, with_keys: bool) -> list:
    out = []
    for row in ms.ordered(db):
        out.append({
            "type": row.type, "name": ms.label(row), "url": row.url, "enabled": bool(row.enabled),
            "server_identifier": row.server_identifier, "mappings": ms.mappings(row),
            "token": (ms.get_secret(row) or "") if with_keys else "",
        })
    return out


def restore(db, data: dict, skipped: list) -> int:
    """Replace the server list with the backup's. Returns how many came back."""
    rows = data.get("media_servers") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return 0  # an older backup, or one made before any server was added
    try:
        own = {(r.type, ms.normalize_url(r.url)): ms.get_secret(r) for r in ms.ordered(db)}
        old = ms.ordered(db)
        for row in old:
            db.delete(row)
        db.flush()
        restored = 0
        for entry in rows:
            if not isinstance(entry, dict) or entry.get("type") not in ms.TYPES:
                continue
            kind = entry["type"]
            try:
                url = vld.clean_server_url(str(entry.get("url") or ""), service=ms.LABELS[kind])
            except ValueError:
                skipped.append(f"a {ms.LABELS[kind]} server whose address isn't a web address")
                continue
            try:
                name = vld.clean_name(str(entry.get("name") or ""), what="server name", max_len=60)
            except ValueError:
                name = None
            if not name or ms.name_taken(db, name):
                name = ms.default_name(db, kind)
            token = str(entry.get("token") or "").strip() or own.get((kind, ms.normalize_url(url)))
            if not token:
                skipped.append(f"the {ms.LABELS[kind]} server \"{name}\": the backup has no key for it")
                continue
            row = models.MediaServer(type=kind, name=name, url=url, enabled=entry.get("enabled") is not False,
                                     server_identifier=str(entry.get("server_identifier") or "")[:100] or None,
                                     path_mappings=json.dumps(path_mapping.load_mappings(entry.get("mappings"))))
            db.add(row)
            db.flush()
            ms.set_secret(row, token)
            restored += 1
        if not restored:
            db.rollback()  # nothing usable: keep the servers this install has
            return 0
        ms.mirror(db)
        db.commit()
        for row in old:
            ms.delete_secret(row)
        return restored
    except Exception as exc:
        db.rollback()
        logger.warning("Restoring the media server list failed: %s", exc)
        skipped.append("the media server list: it couldn't be restored (see the log)")
        return 0
