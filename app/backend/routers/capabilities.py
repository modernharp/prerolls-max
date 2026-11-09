"""What each media server can do with intros (CONTRACTS.md section 6).

    GET /api/capabilities

The interface puts a small badge on every option that depends on the media
server: "Works" (native), "Needs plugin" (plugin), "Next play only"
(emulated), "Not possible on Plex" (none). The notes are one plain sentence
each and say the honest version: Plex has one server-wide intro list chosen
before it knows the movie; Jellyfin and Emby ask per playback through the
Prerolls Max Intros plugin.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import requests
from fastapi import APIRouter

from backend.routers import plugin_v2

logger = logging.getLogger("prerollsmax.capabilities")

router = APIRouter(tags=["Media servers"])

FEATURES = ("random", "sequence", "random_in_groups", "folders", "genre_rules", "rating_rules", "per_user",
            "per_library", "episodes", "first_episode_only", "time_of_day", "dates", "trailers", "on_resume",
            "client_notes",
            # Smart features
            "rule_sets", "year_rules", "kids_safe", "exclude_titles", "weights_cooldowns", "play_history",
            "missed_intro_check", "combined_file", "loudness", "matching_versions", "watch_folders")

LEVELS = ("native", "plugin", "emulated", "none")


def _f(level: str, note: str) -> dict:
    assert level in LEVELS
    return {"level": level, "note": note}


PLEX_FEATURES = {
    "random": _f("native", "Plex picks one intro from the list at random each time a movie starts."),
    "sequence": _f("native", "Plex plays the whole list in order before each movie; a list longer than "
                             "about 7,500 characters is cut to its first entries."),
    "random_in_groups": _f("emulated", "Plex can't pick within groups, so Prerolls Max picks one per group and "
                                       "writes them in order; the picks change when it rewrites the list, "
                                       "not on every play."),
    "folders": _f("emulated", "Plex can't read a folder, so Prerolls Max lists its files for Plex; very large "
                              "folders are cut to fit Plex's limit."),
    "genre_rules": _f("emulated", "Plex picks the intro before it knows the movie, so genre rules apply from "
                                  "the next play, and only while one person is watching."),
    "rating_rules": _f("emulated", "Plex picks the intro before it knows the movie, so age-rating rules apply "
                                   "from the next play, and only while one person is watching."),
    "per_user": _f("emulated", "Plex has one intro list for everyone; Prerolls Max follows the one person "
                               "watching for their next play and leaves it alone when several are watching."),
    "per_library": _f("emulated", "Plex can only switch intros off for a whole library (in the library's "
                                  "settings); different intros per library work from the next play only."),
    "episodes": _f("none", "Plex only plays intros before movies."),
    "first_episode_only": _f("none", "Plex doesn't play intros before episodes."),
    "time_of_day": _f("emulated", "Prerolls Max rewrites Plex's list when the time comes, so a movie started "
                                  "just before keeps the earlier intro."),
    "dates": _f("native", "Prerolls Max changes Plex's list when a date or holiday schedule starts and ends."),
    "trailers": _f("native", "Plex can add trailers itself (new releases need Plex Pass), and Prerolls Max can "
                             "put trailers it downloaded into the list."),
    "on_resume": _f("none", "Plex doesn't play intros when a movie is resumed."),
    "client_notes": _f("emulated", "Plex's 2026 apps for iPhone, iPad, Apple TV, Android TV and Fire TV skip "
                                   "intros set to \"Play pre-roll only\"; set Cinema Trailers to \"1 before "
                                   "movie\" and turn Plex's own trailer sources off. Plex Web and the desktop "
                                   "app play them; Infuse, DLNA and downloads never do."),
    "rule_sets": _f("none", "Plex picks its intro before it knows the movie, so rule sets don't apply on Plex. "
                            "Playlist (Advanced) conditions can follow the one movie playing, for the next play."),
    "year_rules": _f("emulated", "Only in Playlist (Advanced) conditions, from the movie already playing, for "
                                 "the next play, and only while one person is watching."),
    "kids_safe": _f("emulated", "Only in Playlist (Advanced) conditions, for the next play while one movie plays. "
                                "For a children's library, the dependable way is turning Cinema Trailers off in "
                                "that library's settings in Plex."),
    "exclude_titles": _f("none", "Plex can't skip intros for one title. You can only turn intros off for a whole "
                                 "library (the library's Cinema Trailers setting in Plex)."),
    "weights_cooldowns": _f("emulated", "Plex picks at random from one list, so an intro with a higher weight is "
                                        "listed more than once; cooldowns leave recently played intros out whenever "
                                        "Prerolls Max writes the list."),
    "play_history": _f("emulated", "Counted from what Plex reports as playing, checked every 15 seconds, so very "
                                   "short intros can be missed."),
    "missed_intro_check": _f("emulated", "Prerolls Max watches what Plex plays and warns when a movie started "
                                         "without an intro, with a fix for that app."),
    "combined_file": _f("native", "A combined file is an ordinary video, so Plex plays it like any intro."),
    "loudness": _f("native", "Evened-out intros are ordinary video files; Plex plays them as they are."),
    "matching_versions": _f("native", "A 1080p SDR H.264 version plays on every Plex app without converting or "
                                      "switching the TV into HDR mode."),
    "watch_folders": _f("native", "New files are added to the collection and reach Plex the next time Prerolls "
                                  "Max writes its list."),
}


def _plugin_features(server: str) -> dict:
    name = "Jellyfin" if server == "jellyfin" else "Emby"
    episodes = ("Before episodes too, but only before the first one you start, not between auto-played "
                "episodes; the Android TV app plays intros before movies only."
                if server == "jellyfin" else
                "Before episodes too; Emby's Android TV and Fire TV apps play intros before movies only.")
    clients = ("The web app, Jellyfin Media Player, Android and Kodi play intros (Cinema mode must be on in the "
               "app, which it is by default). Swiftfin, Infuse and the MPV Shim don't play them, and the official "
               "Roku app plays only the first."
               if server == "jellyfin" else
               "Needs Emby Premiere, and Cinema Intros turned on in each app (Settings, Playback). Roku has it off "
               "by default; Samsung TVs and Infuse don't play intros.")
    trailers = (_f("plugin", "Jellyfin has no trailer feed of its own; trailers Prerolls Max downloads play "
                             "through the plugin.")
                if server == "jellyfin" else
                _f("native", "Emby can add trailers itself with Premiere, and trailers Prerolls Max downloads play "
                             "through the plugin."))
    return {
        "random": _f("plugin", "Prerolls Max picks for every play."),
        "sequence": _f("plugin", f"{name} plays them in order before each item."),
        "random_in_groups": _f("plugin", "Prerolls Max picks within each group for every play."),
        "folders": _f("plugin", "Prerolls Max picks from the folder's files for every play."),
        "genre_rules": _f("plugin", "Exact: the plugin tells Prerolls Max the genres of what is about to play."),
        "rating_rules": _f("plugin", "Exact: the plugin tells Prerolls Max the age rating of what is about to "
                                     "play."),
        "per_user": _f("plugin", "Exact: the plugin says who is watching."),
        "per_library": _f("plugin", "Exact: the plugin says which library the item is in."),
        "episodes": _f("plugin", episodes),
        "first_episode_only": _f("plugin", "The plugin says whether an episode is the first one someone starts "
                                           "after a break (4 hours by default, set on the plugin page)."),
        "time_of_day": _f("plugin", "Decided at the moment each play starts."),
        "dates": _f("plugin", "Decided at the moment each play starts."),
        "trailers": trailers,
        "on_resume": _f("none", f"{name} doesn't play intros when something is resumed."),
        "client_notes": _f("emulated", clients),
        "rule_sets": _f("plugin", "Exact: checked for every play with what the plugin says about the title. The "
                                  "first matching rule wins; otherwise your schedules decide."),
        "year_rules": _f("plugin", "Exact: the plugin sends the release year."),
        "kids_safe": _f("plugin", "Exact: the plugin sends the age rating (an episode without one uses its "
                                  "series' rating). Unrated titles don't count as kids-safe unless you say so."),
        "exclude_titles": _f("plugin", f"Exact: by item, title or tag. Items you tag no-intro in {name} never get "
                                       "intros."),
        "weights_cooldowns": _f("plugin", "Exact: Prerolls Max picks with the weights for every play and skips "
                                          "intros still in their cooldown."),
        "play_history": _f("plugin", f"Counted when {name} asks the plugin for intros, with who watched and on "
                                     "which app."),
        "missed_intro_check": _f("plugin", f"Prerolls Max compares {name}'s playing sessions with the plugin's "
                                           "requests and warns about apps that skip intros."),
        "combined_file": _f("plugin", "One file for apps that only play the first intro"
                                      + (" (the official Roku app)." if server == "jellyfin" else " (Roku).")),
        "loudness": _f("plugin", "Evened-out intros are ordinary video files the plugin hands out."),
        "matching_versions": _f("plugin", "A 1080p SDR H.264 version plays on every app without converting or "
                                          "switching the TV into HDR mode."),
        "watch_folders": _f("plugin", "New files can play from the next playback."),
    }


# ---------------------------------------------------------------------------
# Server versions (cached, short timeouts: this endpoint backs a badge)
# ---------------------------------------------------------------------------

_VERSION_TTL = 300
_version_lock = threading.Lock()
_version_cache: dict[tuple[str, str], tuple[float, Optional[str], bool]] = {}


def _fetch_version(kind: str, url: str, token: Optional[str]) -> tuple[Optional[str], bool]:
    """(version, reachable) for a configured server."""
    base = url.rstrip("/")
    try:
        if kind == "plex":
            from backend.plex_connector import PlexConnector
            info = PlexConnector(base, token).get_server_info() or {}
            version = info.get("version") or info.get("Version")
            return (str(version) if version and version != "Unknown" else None), bool(info)
        path = "/emby/System/Info/Public" if kind == "emby" else "/System/Info/Public"
        response = requests.get(base + path, timeout=3)
        if response.status_code == 200:
            return (response.json().get("Version") or None), True
        return None, False
    except Exception as exc:
        logger.debug("Version check for %s failed: %s", kind, exc)
        return None, False


def server_version(kind: str, url: str, token: Optional[str],
                   fetch: Callable[[str, str, Optional[str]], tuple] = _fetch_version) -> tuple[Optional[str], bool]:
    now = time.time()
    key = (kind, url)
    with _version_lock:
        cached = _version_cache.get(key)
        if cached and now - cached[0] < _VERSION_TTL:
            return cached[1], cached[2]
    version, reachable = fetch(kind, url, token)
    with _version_lock:
        _version_cache[key] = (now, version, reachable)
    return version, reachable


def clear_cache() -> None:
    with _version_lock:
        _version_cache.clear()


# ---------------------------------------------------------------------------
# The answer
# ---------------------------------------------------------------------------

def plugin_rows_for(kind: str, server_id: Optional[int], identifier: Optional[str], only_one: bool) -> list:
    """The plugins seen for one server: matched by the server it was linked to,
    or by the server id it sent; with one server of the type, every plugin of it."""
    rows = plugin_v2.seen_plugins(kind)
    ident = str(identifier or "").replace("-", "").lower()
    mine = [r for r in rows if (server_id and r.get("media_server_id") == server_id)
            or (ident and str(r.get("server_id") or "").replace("-", "").lower() == ident)]
    return mine if (mine or not only_one) else rows


def _plugin_state(kind: str, rows: Optional[list] = None) -> dict:
    rows = plugin_v2.seen_plugins(kind) if rows is None else rows
    if not rows:
        return {"connected": False, "version": None, "protocol": None, "last_seen_seconds_ago": None,
                "note": "The Prerolls Max Intros plugin hasn't asked for intros in the last week. Install it on "
                        "the server and point it at Prerolls Max."}
    row = rows[0]
    note = ("The plugin is connected." if row.get("protocol") == "v2" else
            "An older plugin is connected; it works, but update it so rules by genre, rating, person or library "
            "are exact and playback never waits on Prerolls Max.")
    return {"connected": True, "version": row.get("plugin_version") or None, "protocol": row.get("protocol"),
            "last_seen_seconds_ago": row.get("last_seen_seconds_ago"), "note": note}


def instance_entries(instances: list, *, version_of=server_version) -> list:
    """Each server (media_servers.Target-like dicts: id, type, name, url, token, enabled,
    identifier), with whether it answers, its version and, for Jellyfin/Emby, its plugin."""
    out = []
    counts = {}
    for inst in instances:
        counts[inst["type"]] = counts.get(inst["type"], 0) + 1
    for inst in instances:
        kind = inst["type"]
        version, reachable = (version_of(kind, inst["url"], inst.get("token")) if inst.get("enabled", True)
                              else (None, False))
        entry = {"id": inst["id"], "type": kind, "name": inst["name"], "enabled": inst.get("enabled", True),
                 "connected": bool(reachable), "version": version}
        if kind != "plex":
            entry["plugin"] = _plugin_state(kind, plugin_rows_for(kind, inst["id"], inst.get("identifier"),
                                                                  counts[kind] == 1))
        out.append(entry)
    return out


def build_capabilities(servers: dict, *, version_of=server_version, plex_state: Optional[dict] = None,
                       instances: Optional[list] = None) -> dict:
    """``servers`` maps "plex"/"jellyfin"/"emby" to {"url", "token"} (or None when not set up).
    ``instances``: every server when there are rows for them (see instance_entries)."""
    out = []
    per_server = instance_entries(instances, version_of=version_of) if instances else []
    for kind in ("plex", "jellyfin", "emby"):
        conf = servers.get(kind) or {}
        url = (conf.get("url") or "").strip()
        version, reachable = (version_of(kind, url, conf.get("token")) if url else (None, False))
        entry = {
            "type": kind,
            "configured": bool(url),
            "connected": bool(url) and reachable,
            "version": version,
            "features": PLEX_FEATURES if kind == "plex" else _plugin_features(kind),
        }
        if kind == "plex":
            entry["delivery"] = "server_list"
            entry["personalization"] = plex_state or {
                "applies": False,
                "reason": "Rules by genre, rating, library or person follow the one movie playing on Plex, "
                          "for the next play."}
        else:
            entry["delivery"] = "plugin"
            entry["plugin"] = _plugin_state(kind)
        mine = [i for i in per_server if i["type"] == kind]
        if mine:
            entry["instances"] = mine
            entry["configured"] = True
            entry["connected"] = any(i["connected"] for i in mine)
            plugged = [i["plugin"] for i in mine if i.get("plugin", {}).get("connected")]
            if kind != "plex" and plugged:
                entry["plugin"] = plugged[0]
        out.append(entry)
    return {"servers": out, "instances": per_server}


def _configured_servers() -> dict:
    from backend import models, secure_store
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        setting = db.query(models.Setting).first()
    finally:
        db.close()
    if setting is None:
        return {}

    def secret(getter, column):
        try:
            value = getter()
        except Exception:
            value = None
        return value or getattr(setting, column, None)

    return {
        "plex": {"url": getattr(setting, "plex_url", None),
                 "token": secret(secure_store.get_plex_token, "plex_token")},
        "jellyfin": {"url": getattr(setting, "jellyfin_url", None),
                     "token": secret(secure_store.get_jellyfin_api_key, "jellyfin_api_key")},
        "emby": {"url": getattr(setting, "emby_url", None),
                 "token": secret(secure_store.get_emby_api_key, "emby_api_key")},
    }


def _plex_state() -> Optional[dict]:
    try:
        from backend.scheduler import scheduler
        return scheduler.plex_personalization_state()
    except Exception:
        return None


def _instances() -> list:
    from backend import media_servers
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        return [{"id": r.id, "type": r.type, "name": media_servers.label(r), "url": r.url,
                 "token": media_servers.get_secret(r), "enabled": bool(r.enabled),
                 "identifier": r.server_identifier} for r in media_servers.ordered(db)]
    except Exception:
        return []
    finally:
        db.close()


@router.get("/api/capabilities")
def get_capabilities():
    """What each media server can do with intros, with a plain note for each."""
    return build_capabilities(_configured_servers(), plex_state=_plex_state(), instances=_instances())
