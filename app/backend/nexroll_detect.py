"""Is NeXroll still running next to Prerolls Max? Say so plainly when it is.

Three signs, each cheap to check:

* A connected Jellyfin or Emby server still has the **NeXroll Intros** plugin
  (its plugin list, ``GET /Plugins``). With the Prerolls Max plugin there too,
  intros play twice.
* Plex's intro list changed after Prerolls Max wrote it. Plex has one list per
  server; NeXroll writes the same setting, so the two take turns. Every write
  and every read of the list goes through ``note_plex_written`` and
  ``note_plex_read`` (plex_connector.py), which compare the two.
* Something answers as NeXroll on port 9393 while Prerolls Max runs on another
  port.

Servers left to NeXroll on purpose (coexist.py) are never flagged.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from backend import coexist

logger = logging.getLogger("prerollsmax.nexroll")

# NeXroll's plugin ids (upstream Plugins/NeXroll.*/Plugin.cs). Jellyfin lists
# ids without dashes, Emby with them; compare without.
NEXROLL_PLUGIN_IDS = {
    "a1b2c3d4e5f67890abcdae0c01100001",  # NeXroll Intros for Jellyfin (10.11 and 12)
    "a1b2c3d4e5f67890abcdae0c01200002",  # NeXroll Intros for Emby
}
OUR_PLUGIN_IDS = {
    "c0a6ea9477954b61b9644ddfb93ec8b0",  # Prerolls Max Intros for Jellyfin
    "2fea54cd3c4a4307ab535e25a07a24ec",  # Prerolls Max Intros for Emby
}
PLUGIN_CACHE_SECONDS = 600
PLEX_CHANGE_WINDOW = 24 * 3600

_lock = threading.Lock()
_plex_written: dict = {}      # normalized url -> (value, time)
_plex_changes: dict = {}      # normalized url -> {"count", "first_at", "last_at"}
_plugin_cache = {"at": 0.0, "key": None, "found": None}
_dismissed: dict = {}         # warning id -> time


def _norm_url(url) -> str:
    return str(url or "").strip().rstrip("/").lower()


def _norm_value(value) -> str:
    return str(value or "").strip()


def _norm_id(value) -> str:
    return str(value or "").replace("-", "").replace("{", "").replace("}", "").strip().lower()


# ---------------------------------------------------------------------------
# Plex: did someone else change the list we wrote?
# ---------------------------------------------------------------------------

def note_plex_written(url, value, now: Optional[float] = None) -> None:
    """Prerolls Max just wrote this list to this Plex server."""
    if not url:
        return
    with _lock:
        _plex_written[_norm_url(url)] = (_norm_value(value), time.time() if now is None else now)


def note_plex_read(url, value, now: Optional[float] = None) -> bool:
    """Prerolls Max just read this Plex server's list. True when it differs
    from what Prerolls Max wrote last: something else changed it."""
    if not url or value is None:
        return False
    key = _norm_url(url)
    now = time.time() if now is None else now
    with _lock:
        written = _plex_written.get(key)
        if written is None or written[0] == _norm_value(value):
            return False
        # Count each new value once: the next read of the same value isn't news.
        _plex_written[key] = (_norm_value(value), now)
        entry = _plex_changes.setdefault(key, {"count": 0, "first_at": now, "last_at": now})
        if now - entry["last_at"] > PLEX_CHANGE_WINDOW:
            entry.update(count=0, first_at=now)
        entry["count"] += 1
        entry["last_at"] = now
    logger.warning("Plex's intro list at %s was changed outside Prerolls Max (usually NeXroll still running)", url)
    return True


def plex_changes(now: Optional[float] = None) -> dict:
    """{normalized url: {count, first_at, last_at}} for changes in the last day."""
    now = time.time() if now is None else now
    with _lock:
        return {k: dict(v) for k, v in _plex_changes.items() if now - v["last_at"] <= PLEX_CHANGE_WINDOW}


def reset() -> None:
    """Tests start clean."""
    with _lock:
        _plex_written.clear()
        _plex_changes.clear()
        _plugin_cache.update(at=0.0, key=None, found=None)
        _dismissed.clear()


# ---------------------------------------------------------------------------
# Jellyfin and Emby: is the NeXroll Intros plugin still there?
# ---------------------------------------------------------------------------

def plugins_in(listing) -> dict:
    """{nexroll: bool, ours: bool} from a /Plugins answer. Disabled plugins don't count."""
    out = {"nexroll": False, "ours": False}
    for plugin in listing if isinstance(listing, list) else []:
        if not isinstance(plugin, dict):
            continue
        status = str(plugin.get("Status") or "").lower()
        if status in ("disabled", "deleted", "notsupported", "malfunctioned", "superceded", "superseded"):
            continue
        pid = _norm_id(plugin.get("Id"))
        name = str(plugin.get("Name") or "").lower()
        if pid in NEXROLL_PLUGIN_IDS or "nexroll" in name:
            out["nexroll"] = True
        if pid in OUR_PLUGIN_IDS or "prerolls max" in name:
            out["ours"] = True
    return out


def _check_one(target) -> dict:
    from backend import server_probe
    out = {"id": target.id, "name": target.name, "type": target.type, "nexroll": None, "ours": None}
    try:
        r = server_probe.request(target, "GET", "/Plugins")
        if r.status_code == 200 and r.content:
            out.update(plugins_in(r.json()))
    except Exception as exc:  # a server that's down just isn't checked this time
        logger.info("Couldn't list %s's plugins: %s", target.name, exc)
    return out


def plugin_report(db, force: bool = False) -> list:
    """Per Jellyfin/Emby server: {id, name, type, nexroll, ours}. Cached ten minutes."""
    from backend import media_servers
    targets = [media_servers.target(r) for r in media_servers.enabled(db) if r.type in ("jellyfin", "emby")]
    key = tuple((t.id, t.url) for t in targets)
    now = time.monotonic()
    with _lock:
        if (not force and _plugin_cache["found"] is not None and _plugin_cache["key"] == key
                and now - _plugin_cache["at"] < PLUGIN_CACHE_SECONDS):
            return [dict(x) for x in _plugin_cache["found"]]
    if not targets:
        found = []
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
            found = list(pool.map(_check_one, targets))
    with _lock:
        _plugin_cache.update(at=now, key=key, found=[dict(x) for x in found])
    return found


# ---------------------------------------------------------------------------
# Port 9393
# ---------------------------------------------------------------------------

def nexroll_on_its_port(our_port: int) -> bool:
    from backend import port_config
    if int(our_port) == port_config.NEXROLL_PORT:
        return False  # we hold that port, so NeXroll can't
    return port_config.identify(port_config.NEXROLL_PORT, timeout=1.0) == "nexroll"


# ---------------------------------------------------------------------------
# Everything together, as the Home and Media Servers pages show it
# ---------------------------------------------------------------------------

HELP = "/help/moving-from-nexroll"


def dismiss(warning_id: str) -> None:
    with _lock:
        _dismissed[warning_id] = time.time()


def _plural_times(count: int) -> str:
    return "once" if count == 1 else "twice" if count == 2 else f"{count} times"


def report(db, our_port: int, force: bool = False, probe_port: bool = True) -> dict:
    """{alongside, summary, warnings: [{id, severity, server, title, message, fix, help}]}"""
    from backend import media_servers
    split = coexist.split(db)
    alongside = split["mode"] == "alongside"
    manager = {s["id"]: s["manager"] for s in split["servers"]}
    warnings = []

    for found in plugin_report(db, force=force):
        if not found.get("nexroll"):
            continue
        if manager.get(found["id"]) == "nexroll":
            continue  # left to NeXroll on purpose: its plugin belongs there
        twice = bool(found.get("ours"))
        warnings.append({
            "id": f"plugin-{found['id']}",
            "severity": "warning",
            "server": found["name"],
            "title": f"{found['name']} still has the NeXroll Intros plugin.",
            "message": ("Intros will play twice: once from NeXroll, once from Prerolls Max." if twice else
                        "It can still add NeXroll's intros on its own."),
            "fix": (f"Remove it in Jellyfin: Dashboard > Plugins > NeXroll Intros > Uninstall, then restart Jellyfin."
                    if found["type"] == "jellyfin" else
                    "Remove it in Emby: open Plugins in the server dashboard, uninstall NeXroll Intros, then restart Emby."),
            "help": HELP + "#help-remove-the-nexroll-plugin",
        })

    names = {_norm_url(r.url): media_servers.label(r) for r in media_servers.ordered(db, "plex")}
    ids = {_norm_url(r.url): r.id for r in media_servers.ordered(db, "plex")}
    for url, change in plex_changes().items():
        server_id = ids.get(url)
        if server_id is not None and manager.get(server_id) == "nexroll":
            continue
        name = names.get(url, "Plex")
        warnings.append({
            "id": f"plex-{server_id or url}",
            "severity": "warning",
            "server": name,
            "title": "Something else changed Plex's intro list.",
            "message": (f"{name}'s intro list was changed outside Prerolls Max {_plural_times(change['count'])} "
                        "in the last day. That's usually NeXroll still running. Prerolls Max puts its list back, "
                        "so the two take turns and you can't tell which intros will play."),
            "fix": "Stop NeXroll so only one app manages Plex.",
            "help": HELP + "#help-stop-nexroll",
        })

    if probe_port:
        try:
            if nexroll_on_its_port(our_port):
                warnings.append({
                    "id": "port-9393",
                    "severity": "info" if alongside else "warning",
                    "server": None,
                    "title": "NeXroll is still running on this computer.",
                    "message": "It answers on port 9393." + (
                        "" if alongside else " Both apps manage the same media servers unless you stop it."),
                    "fix": "Stop NeXroll and turn off its automatic start." if not alongside else
                           "That's expected while you keep both. Settings > Moving from NeXroll shows who manages "
                           "each server.",
                    "help": HELP + ("#help-running-both" if alongside else "#help-stop-nexroll"),
                })
        except Exception as exc:
            logger.info("Checking port 9393 failed: %s", exc)

    with _lock:
        hidden = {k for k, at in _dismissed.items() if time.time() - at < 24 * 3600}
    warnings = [w for w in warnings if w["id"] not in hidden]
    return {"alongside": alongside, "summary": split["summary"], "servers": split["servers"],
            "warnings": warnings}
