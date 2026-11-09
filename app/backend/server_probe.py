"""Talking to one Plex, Jellyfin or Emby server: is it there, does it take the
key, what's in its movie library, and what would it play before a movie.

Every function takes a media_servers.Target and never raises for a server
problem; it answers in plain words instead. Tokens never appear in results.
"""
from __future__ import annotations

import logging
from typing import Optional

import requests

from backend.jellyfin_auth import jellyfin_auth_headers

logger = logging.getLogger("prerollsmax.servers")

TIMEOUT = (4, 8)
NAMES = {"plex": "Plex", "jellyfin": "Jellyfin", "emby": "Emby"}


def _verify(url: str) -> bool:
    from backend.plex_connector import _infer_tls_verify
    try:
        return _infer_tls_verify(url)
    except Exception:
        return True


def _base(target) -> str:
    base = str(target.url or "").rstrip("/")
    if target.type == "emby" and not base.lower().endswith("/emby"):
        base += "/emby"
    return base


def headers(target) -> dict:
    if target.type == "plex":
        return {"X-Plex-Token": target.token or "", "Accept": "application/json",
                "X-Plex-Client-Identifier": "prerolls-max", "X-Plex-Product": "Prerolls Max"}
    if target.type == "jellyfin":
        return {**jellyfin_auth_headers(target.token), "Accept": "application/json"}
    return {"X-Emby-Token": target.token or "", "Accept": "application/json"}


def request(target, method: str, path: str, **kw) -> requests.Response:
    kw.setdefault("timeout", TIMEOUT)
    kw.setdefault("verify", _verify(target.url))
    return requests.request(method, _base(target) + path, headers=headers(target), **kw)


def check(target) -> dict:
    """{reachable, signed_in, name, version, identifier, platform, message, hint}."""
    name = NAMES[target.type]
    out = {"reachable": False, "signed_in": False, "name": None, "version": None, "identifier": None,
           "platform": None, "message": None, "hint": None}
    public = "/identity" if target.type == "plex" else "/System/Info/Public"
    try:
        r = requests.get(_base(target) + public, headers={"Accept": "application/json"}, timeout=TIMEOUT,
                         verify=_verify(target.url))
    except requests.exceptions.SSLError:
        out.update(message=f"{name} at {target.url} didn't accept a secure connection.",
                   hint="Try the address with http:// instead of https://.")
        return out
    except requests.RequestException:
        out.update(message=f"{name} didn't answer at {target.url}.",
                   hint=f"Check that {name} is running and that the address and port are right. If Prerolls Max "
                        "runs in Docker, use the computer's IP address instead of localhost.")
        return out
    if r.status_code != 200 and not (target.type == "plex" and r.status_code == 401):
        out.update(message=f"Something answered at {target.url}, but it isn't {name}.",
                   hint=f"Check the port: {name} usually uses {32400 if target.type == 'plex' else 8096}.")
        return out
    out["reachable"] = True
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {}
    if target.type == "plex":
        mc = data.get("MediaContainer") or {}
        out.update(identifier=mc.get("machineIdentifier"), version=mc.get("version"))
        private = "/"
    else:
        out.update(name=data.get("ServerName"), version=data.get("Version"), identifier=data.get("Id"))
        private = "/System/Info"
    try:
        r = request(target, "GET", private)
    except requests.RequestException:
        out.update(message=f"{name} stopped answering while checking the key.", hint="Try again in a moment.")
        return out
    if r.status_code in (401, 403):
        what = "token" if target.type == "plex" else "API key"
        out.update(message=f"{name} turned down the {what}.",
                   hint=("Sign in with Plex again, or copy a fresh token." if target.type == "plex" else
                         f"Make a new key in {name} under API Keys and paste it in."))
        return out
    if r.status_code != 200:
        out.update(message=f"{name} couldn't check the key just now.", hint="Wait a moment and try again.")
        return out
    out["signed_in"] = True
    try:
        data = r.json() if r.content else {}
    except ValueError:
        data = {}
    if target.type == "plex":
        mc = data.get("MediaContainer") or {}
        out.update(name=mc.get("friendlyName"), platform=mc.get("platform"),
                   identifier=mc.get("machineIdentifier") or out["identifier"],
                   version=mc.get("version") or out["version"])
    else:
        out.update(platform=data.get("OperatingSystem"), name=data.get("ServerName") or out["name"])
    return out


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

def _admin_user(target) -> Optional[str]:
    """A Jellyfin/Emby user to ask as: the first administrator."""
    r = request(target, "GET", "/Users")
    if r.status_code != 200:
        return None
    users = r.json() if r.content else []
    admins = [u for u in users if (u.get("Policy") or {}).get("IsAdministrator")]
    pick = (admins or users or [None])[0]
    return pick.get("Id") if pick else None


def movies(target, query: str = "", limit: int = 40) -> list:
    """[{id, title, year}] from the server's movie libraries, best match first."""
    query = (query or "").strip()
    if target.type == "plex":
        r = request(target, "GET", "/library/sections")
        sections = ((r.json() if r.status_code == 200 else {}).get("MediaContainer") or {}).get("Directory") or []
        out = []
        for section in sections:
            if section.get("type") != "movie":
                continue
            params = {"type": 1, "X-Plex-Container-Start": 0, "X-Plex-Container-Size": limit}
            if query:
                params["title"] = query
            r = request(target, "GET", f"/library/sections/{section.get('key')}/all", params=params)
            items = ((r.json() if r.status_code == 200 else {}).get("MediaContainer") or {}).get("Metadata") or []
            out += [{"id": str(m.get("ratingKey")), "title": m.get("title"), "year": m.get("year")} for m in items]
        return out[:limit]
    user = _admin_user(target)
    params = {"IncludeItemTypes": "Movie", "Recursive": "true", "Limit": limit, "SortBy": "SortName",
              "Fields": "ProductionYear"}
    if query:
        params["SearchTerm"] = query
    path = f"/Users/{user}/Items" if user and target.type == "emby" else "/Items"
    if user and target.type == "jellyfin":
        params["userId"] = user
    r = request(target, "GET", path, params=params)
    items = (r.json() if r.status_code == 200 else {}).get("Items") or []
    return [{"id": str(m.get("Id")), "title": m.get("Name"), "year": m.get("ProductionYear")} for m in items]


def movie_title(target, item_id: str) -> Optional[str]:
    try:
        if target.type == "plex":
            r = request(target, "GET", f"/library/metadata/{item_id}")
            meta = ((r.json() if r.status_code == 200 else {}).get("MediaContainer") or {}).get("Metadata") or []
            return meta[0].get("title") if meta else None
        user = _admin_user(target)
        path = f"/Users/{user}/Items/{item_id}" if user else f"/Items/{item_id}"
        r = request(target, "GET", path)
        return (r.json() or {}).get("Name") if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


# ---------------------------------------------------------------------------
# What would play
# ---------------------------------------------------------------------------

def plex_intro_list(target) -> Optional[str]:
    r = request(target, "GET", "/:/prefs")
    if r.status_code != 200:
        return None
    for s in (r.json().get("MediaContainer") or {}).get("Setting") or []:
        if s.get("id") == "CinemaTrailersPrerollID":
            return s.get("value") or ""
    return ""


def intros(target, item_id: str) -> dict:
    """{ok, items: [{title, path}], user_id?, message?} as the server answers for this movie.

    Plex: a real play queue, like an app pressing Play (nothing starts
    playing). Jellyfin and Emby: the /Intros call their apps make."""
    name = NAMES[target.type]
    try:
        if target.type == "plex":
            r = request(target, "GET", "/")
            mid = ((r.json() if r.status_code == 200 else {}).get("MediaContainer") or {}).get("machineIdentifier")
            if not mid:
                return {"ok": False, "items": [], "message": f"{name} didn't say who it is."}
            uri = f"server://{mid}/com.plexapp.plugins.library/library/metadata/{item_id}"
            r = request(target, "POST", "/playQueues", params={"type": "video", "uri": uri, "extrasPrefixCount": 1,
                                                                "continuous": 0})
            if r.status_code != 200:
                return {"ok": False, "items": [], "message": f"{name} couldn't make a play queue ({r.status_code})."}
            queue = (r.json().get("MediaContainer") or {}).get("Metadata") or []
            items = []
            for it in queue:
                if str(it.get("ratingKey")) == str(item_id) or it.get("type") == "movie" and not it.get("extraType"):
                    break
                part = next((p for m in it.get("Media") or [] for p in m.get("Part") or []), {})
                items.append({"title": it.get("title"), "path": part.get("file")})
            return {"ok": True, "items": items}
        user = _admin_user(target)
        if not user:
            return {"ok": False, "items": [], "message": f"{name} didn't list any users to ask as."}
        path = (f"/Items/{item_id}/Intros" if target.type == "jellyfin" else f"/Users/{user}/Items/{item_id}/Intros")
        r = request(target, "GET", path, params={"userId": user} if target.type == "jellyfin" else None,
                    timeout=(4, 20))
        if r.status_code != 200:
            return {"ok": False, "items": [], "message": f"{name} couldn't list the intros ({r.status_code})."}
        found = (r.json() or {}).get("Items") or []
        return {"ok": True, "user_id": user,
                "items": [{"title": it.get("Name"), "path": it.get("Path")} for it in found]}
    except (requests.RequestException, ValueError) as exc:
        logger.info("Asking %s what it would play failed: %s", target.name, exc)
        return {"ok": False, "items": [], "message": f"{name} didn't answer at {target.url}."}


def plugin_info(target) -> dict:
    """{installed, version, configured, url} for the Prerolls Max Intros plugin on Jellyfin/Emby."""
    try:
        r = request(target, "GET", "/Plugins")
        plugins = r.json() if r.status_code == 200 and r.content else []
    except (requests.RequestException, ValueError):
        return {"installed": None}
    plugin = next((p for p in plugins if "prerolls max" in str(p.get("Name") or "").lower()), None)
    if plugin is None:
        return {"installed": False}
    out = {"installed": True, "version": plugin.get("Version"), "configured": None, "url": None}
    try:
        r = request(target, "GET", f"/Plugins/{plugin.get('Id')}/Configuration")
        config = r.json() if r.status_code == 200 and r.content else {}
        out["url"] = config.get("PrerollsMaxUrl") or config.get("NexrollUrl") or None
        out["configured"] = bool(out["url"])
    except (requests.RequestException, ValueError):
        pass
    return out
