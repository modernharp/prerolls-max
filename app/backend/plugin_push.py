"""Copy a Prerolls Max setting into the Prerolls Max Intros plugin's own settings.

The plugin decides "first episode of a sitting" itself, with the gap set on
its page (BingeWindowHours). When the gap changes in Prerolls Max, it is
written to the plugin on every connected Jellyfin and Emby server too, so the
two never disagree. Best effort: a server that is down is reported, not fatal.
"""
from __future__ import annotations

import logging
import threading

import requests

logger = logging.getLogger("prerollsmax.plugin_push")

PLUGIN_NAME = "Prerolls Max"


def _servers() -> dict:
    from backend.routers.capabilities import _configured_servers
    try:
        return _configured_servers()
    except Exception:
        return {}


def _push_jellyfin(url: str, key: str, hours: int) -> bool:
    from backend.jellyfin_connector import JellyfinConnector
    connector = JellyfinConnector(url, key)
    plugin = connector.find_plugin_by_name(PLUGIN_NAME)
    if not plugin:
        return False
    plugin_id = plugin.get("Id") or plugin.get("id")
    config = connector.get_plugin_configuration(plugin_id) or {}
    if "BingeWindowHours" not in config and "PrerollsMaxUrl" not in config:
        return False
    config["BingeWindowHours"] = hours
    return bool(connector.set_plugin_configuration(plugin_id, config).get("success"))


def _push_emby(url: str, key: str, hours: int) -> bool:
    base = url.rstrip("/")
    headers = {"X-Emby-Token": key}
    response = requests.get(f"{base}/emby/Plugins", headers=headers, timeout=5)
    if response.status_code != 200:
        return False
    plugin = next((p for p in response.json() or [] if PLUGIN_NAME.lower() in str(p.get("Name", "")).lower()), None)
    if not plugin:
        return False
    plugin_id = plugin.get("Id")
    current = requests.get(f"{base}/emby/Plugins/{plugin_id}/Configuration", headers=headers, timeout=5)
    config = current.json() if current.status_code == 200 else {}
    config["BingeWindowHours"] = hours
    saved = requests.post(f"{base}/emby/Plugins/{plugin_id}/Configuration", headers=headers, json=config, timeout=5)
    return saved.status_code in (200, 204)


def push_binge_window(hours: int) -> list:
    """[{server, updated: bool, message}] for each connected Jellyfin/Emby."""
    results = []
    servers = _servers()
    for kind, push in (("jellyfin", _push_jellyfin), ("emby", _push_emby)):
        conf = servers.get(kind) or {}
        if not conf.get("url") or not conf.get("token"):
            continue
        name = kind.capitalize()
        try:
            ok = push(conf["url"], conf["token"], hours)
        except Exception as exc:
            logger.info("Couldn't update the %s plugin's binge gap: %s", name, exc)
            ok = False
        results.append({"server": kind, "updated": ok,
                        "message": (f"The {name} plugin now uses {hours} hours too." if ok else
                                    f"Couldn't update the {name} plugin. Set the same gap on its settings page.")})
    return results


# ---------------------------------------------------------------------------
# "Get ready": ask the plugins to download what may play next
# ---------------------------------------------------------------------------
# The plugins keep a local copy of each intro and only hand ready copies to
# the media server. Emby also has to register a new copy before it plays it,
# which takes up to a minute. They refresh on their own every 30 minutes, so
# right after a schedule switched (or the user changed one) the first movies on
# Emby started with no intro at all. Asking the plugin's Prefetch endpoint as
# soon as the intros change closes that gap. Best effort and in the background.

PREFETCH_DELAY_SECONDS = 5.0
_prefetch_lock = threading.Lock()
_prefetch_timer = None


def _prefetch_jellyfin(url: str, key: str) -> bool:
    from backend.jellyfin_auth import jellyfin_auth_headers
    response = requests.post(f"{url.rstrip('/')}/PrerollsMax/Prefetch", headers=jellyfin_auth_headers(key),
                             json={}, timeout=120)
    return response.status_code in (200, 204)


def _prefetch_emby(url: str, key: str) -> bool:
    response = requests.post(f"{url.rstrip('/')}/emby/PrerollsMax/Prefetch", headers={"X-Emby-Token": key},
                             json={}, timeout=120)
    return response.status_code in (200, 204)


def prefetch_now() -> dict:
    """{server: True/False} for each connected Jellyfin/Emby. Never raises."""
    done = {}
    servers = _servers()
    for kind, call in (("jellyfin", _prefetch_jellyfin), ("emby", _prefetch_emby)):
        conf = servers.get(kind) or {}
        if not conf.get("url") or not conf.get("token"):
            continue
        try:
            done[kind] = call(conf["url"], conf["token"])
        except Exception as exc:  # an old plugin without the endpoint, or the server is down
            logger.info("Couldn't ask the %s plugin to get intros ready: %s", kind, exc)
            done[kind] = False
    return done


def _run_prefetch() -> None:
    global _prefetch_timer
    with _prefetch_lock:
        _prefetch_timer = None
    prefetch_now()


def request_prefetch(delay: float = PREFETCH_DELAY_SECONDS) -> bool:
    """Ask the plugins to get ready soon. Requests close together make one call."""
    global _prefetch_timer
    with _prefetch_lock:
        if _prefetch_timer is not None:
            return False
        timer = threading.Timer(delay, _run_prefetch)
        timer.daemon = True
        _prefetch_timer = timer
        timer.start()
        return True
