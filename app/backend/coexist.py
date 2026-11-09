"""Running Prerolls Max beside NeXroll, for people who want to keep both.

Normally Prerolls Max replaces NeXroll. Both apps write Plex's one intro list
(they'd take turns overwriting it) and both Jellyfin/Emby plugins add intros
(intros would play twice), so running both only works when each media server
is managed by exactly one of them.

Saved in ``coexist.json`` next to the database:

    {"mode": "replace" | "alongside", "nexroll_servers": [media server ids]}

A server in ``nexroll_servers`` is left to NeXroll: Prerolls Max never writes
that Plex server's intro list, and its plugin on that Jellyfin/Emby server gets
an empty answer on purpose. Everything else is Prerolls Max's.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from typing import Optional

logger = logging.getLogger("prerollsmax.coexist")

FILE_NAME = "coexist.json"
_lock = threading.Lock()
_cache = {"at": 0.0, "data": None, "path": None}
_urls_cache = {"at": 0.0, "urls": None}
CACHE_SECONDS = 5.0
_folder_override: Optional[str] = None


def configure(folder: Optional[str]) -> None:
    """Tests point this at a temporary folder."""
    global _folder_override
    _folder_override = folder
    invalidate()


def _path() -> str:
    if _folder_override:
        return os.path.join(_folder_override, FILE_NAME)
    from backend.port_config import data_folder
    return os.path.join(data_folder(), FILE_NAME)


def invalidate() -> None:
    with _lock:
        _cache.update(at=0.0, data=None)
        _urls_cache.update(at=0.0, urls=None)


def load() -> dict:
    now = time.monotonic()
    path = _path()
    with _lock:
        if _cache["data"] is not None and _cache["path"] == path and now - _cache["at"] < CACHE_SECONDS:
            return dict(_cache["data"])
    data = {"mode": "replace", "nexroll_servers": []}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh) or {}
        if raw.get("mode") in ("replace", "alongside"):
            data["mode"] = raw["mode"]
        ids = raw.get("nexroll_servers") or []
        data["nexroll_servers"] = sorted({int(i) for i in ids if str(i).isdigit()})
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    with _lock:
        _cache.update(at=now, data=dict(data), path=path)
    return data


def save(mode: Optional[str] = None, nexroll_servers=None) -> dict:
    data = load()
    if mode is not None:
        data["mode"] = mode
    if nexroll_servers is not None:
        data["nexroll_servers"] = sorted({int(i) for i in nexroll_servers})
    path = _path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    os.replace(tmp, path)
    invalidate()
    return data


def alongside() -> bool:
    return load()["mode"] == "alongside"


def nexroll_manages(server_id) -> bool:
    """True when this media server is left to NeXroll (only in "alongside" mode)."""
    if server_id is None:
        return False
    data = load()
    return data["mode"] == "alongside" and int(server_id) in data["nexroll_servers"]


def _norm(url: Optional[str]) -> str:
    return str(url or "").strip().rstrip("/").lower()


def nexroll_plex_urls() -> set:
    """Addresses of the Plex servers left to NeXroll (cached a few seconds)."""
    now = time.monotonic()
    with _lock:
        if _urls_cache["urls"] is not None and now - _urls_cache["at"] < CACHE_SECONDS:
            return set(_urls_cache["urls"])
    urls = set()
    data = load()
    if data["mode"] == "alongside" and data["nexroll_servers"]:
        try:
            from backend import models
            from backend.database import SessionLocal
            db = SessionLocal()
            try:
                rows = db.query(models.MediaServer).filter(models.MediaServer.id.in_(data["nexroll_servers"]),
                                                           models.MediaServer.type == "plex").all()
                urls = {_norm(r.url) for r in rows}
            finally:
                db.close()
        except Exception as exc:
            logger.warning("Couldn't read which Plex servers NeXroll manages: %s", exc)
    with _lock:
        _urls_cache.update(at=now, urls=set(urls))
    return urls


def plex_url_left_to_nexroll(url: Optional[str]) -> bool:
    return bool(url) and _norm(url) in nexroll_plex_urls()


def split(db) -> dict:
    """Who manages each media server, and what's wrong with that split.

    {mode, servers: [{id, name, type, manager: "prerollsmax"|"nexroll",
                      nexroll_plugin: bool|None}], conflicts: [sentences],
     summary: sentence | None}
    """
    from backend import media_servers
    data = load()
    rows = []
    for row in media_servers.ordered(db):
        if not row.enabled:
            continue
        manager = "nexroll" if data["mode"] == "alongside" and row.id in data["nexroll_servers"] else "prerollsmax"
        rows.append({"id": row.id, "name": media_servers.label(row), "type": row.type, "manager": manager})
    nexroll_names = [r["name"] for r in rows if r["manager"] == "nexroll"]
    ours = [r["name"] for r in rows if r["manager"] == "prerollsmax"]
    summary = None
    if data["mode"] == "alongside":
        bits = []
        if nexroll_names:
            bits.append(f"NeXroll manages {_join(nexroll_names)}")
        if ours:
            bits.append(f"Prerolls Max manages {_join(ours)}")
        summary = ("; ".join(bits) + ".") if bits else None
        if summary:
            summary = summary[0].upper() + summary[1:]
    return {"mode": data["mode"], "servers": rows, "summary": summary}


def _join(names) -> str:
    names = list(names)
    if len(names) <= 1:
        return "".join(names)
    return ", ".join(names[:-1]) + " and " + names[-1]
