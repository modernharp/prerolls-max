"""Plugin protocol v2: what the Jellyfin and Emby plugins ask at playback time.

    GET /plugin/v2/intros   (CONTRACTS.md section 7)

The plugin sends everything it knows about what is about to play (type,
genres, tags, rating, user, library, series, audio, path...), so Prerolls Max
never calls back into Jellyfin or Emby while the player waits. In v1 those
callbacks took up to six seconds against a five second plugin timeout, and
the movie started without intros.

Also here, shared with the v1 routes in main.py:

- ``check_plugin_key``: the plugin's API key, from the X-Api-Key header only,
  required whenever login is on (CONTRACTS.md section 4).
- the list of plugins seen recently, for /api/capabilities.
- ``BingeSessions``: "first episode of a sitting" when a plugin can't tell.

main.py wires this module up with ``configure`` (the functions it needs live
there) and includes ``router`` before the static files are mounted.
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Request

from backend.errors import AppError

logger = logging.getLogger("prerollsmax.plugin")

router = APIRouter(tags=["Plugins"])

# How long a download link in a v2 answer works. The plugin downloads right
# away (or within its prefetch run), so an hour is plenty; a leaked link stops
# working soon after.
STREAM_LINK_SECONDS = 3600
# How long a plugin may keep an "everything that could play" list.
POOL_CACHE_SECONDS = 1800
# Gap between episodes that still counts as one sitting, when the plugin doesn't say.
DEFAULT_BINGE_HOURS = 4


@dataclass
class Deps:
    """What this module needs from main.py."""

    get_db: Callable[..., Any]
    resolve_intros: Callable[..., dict]
    play_list: Callable[..., list]
    validate_api_key: Callable[..., Any]
    sign_stream_path: Callable[[str, int], str]
    file_version: Callable[[str], str]
    plugin_clients: dict
    setting_model: Any
    preroll_model: Any = None
    note_playback: Optional[Callable[[], None]] = None
    keyless_note: Optional[Callable[..., Any]] = None
    keyless_forget: Optional[Callable[..., Any]] = None
    # Smart features (features.py): the rule set and never-play list, decided
    # before schedules; every file a rule could play (for pool requests); what
    # to record once an answer is sent; the "one sitting" gap in hours.
    smart_intros: Optional[Callable[..., Optional[dict]]] = None
    rule_pool: Optional[Callable[..., list]] = None
    on_answer: Optional[Callable[..., None]] = None
    binge_hours: Optional[Callable[[], int]] = None
    # Several servers of one type (media_servers.py): which one is asking,
    # as {id, name, enabled} or None; and whether this request is Prerolls
    # Max's own "Play a test" (not a real playback, so not recorded).
    link_server: Optional[Callable[..., Optional[dict]]] = None
    is_play_test: Optional[Callable[[dict], bool]] = None


_deps: Optional[Deps] = None


def configure(deps: Deps) -> None:
    global _deps
    _deps = deps


def _get_db():
    if _deps is None:
        yield None
        return
    yield from _deps.get_db()


# ---------------------------------------------------------------------------
# API key
# ---------------------------------------------------------------------------

def login_enabled(db, setting_model) -> bool:
    try:
        setting = db.query(setting_model).first()
    except Exception:
        return False
    return bool(getattr(setting, "auth_enabled", False))


def check_plugin_key(request: Request, db, *, validate_api_key, setting_model,
                     keyless_note=None, keyless_forget=None):
    """The plugin's key record, or None when login is off and no key was sent.

    Raises a plain-language 401 when the key is wrong, or missing while login
    is on. A key in the address (``?api_key=``) is refused: addresses end up
    in proxy and server logs.
    """
    server_type, server_name, version = plugin_identity(request)
    address = request.client.host if request.client else ""
    if "api_key" in request.query_params:
        raise AppError(
            "Prerolls Max no longer accepts the API key in the address.",
            status=400, code="api_key_in_url",
            hint="Update the plugin; current versions send the key in the X-Api-Key header.")
    key = (request.headers.get("X-Api-Key") or "").strip()
    if key:
        record = validate_api_key(key, "read", db)
        if not record:
            raise AppError(
                "Prerolls Max didn't accept the plugin's API key.",
                status=401, code="plugin_key_rejected",
                hint="The key may have been deleted or expired. In Prerolls Max, open Media Servers and "
                     "press \"Set up the plugin for me\", or make a key under Settings, Advanced, API keys "
                     "and paste it into the plugin's settings.")
        if keyless_forget:
            keyless_forget(server_type, server_name, address)
        return record
    if keyless_note:
        keyless_note(server_type, server_name, version, address)
    if login_enabled(db, setting_model):
        raise AppError(
            "Prerolls Max needs an API key from this plugin because login is on.",
            status=401, code="plugin_key_required",
            hint="In Prerolls Max, open Media Servers and press \"Set up the plugin for me\". Or make a "
                 "key under Settings, Advanced, API keys and paste it into the plugin's settings.")
    return None


def plugin_identity(request: Request) -> tuple[str, str, str]:
    """(server type, server name, plugin version) from the plugin's headers."""
    header = (request.headers.get("X-PrerollsMax-Plugin") or "").strip()
    kind, _, version = header.partition("/")
    kind = kind.strip().lower()
    if kind not in ("jellyfin", "emby"):
        kind = (request.headers.get("X-Plugin-Server-Type") or "").strip().lower() or "unknown"
    version = version.strip() or (request.headers.get("X-Plugin-Server-Version") or "").strip()
    name = (request.headers.get("X-Plugin-Server-Name") or "").strip()
    return kind[:20], name[:120], version[:40]


# ---------------------------------------------------------------------------
# Plugins seen recently (for /api/capabilities and the Connect page)
# ---------------------------------------------------------------------------

_SEEN_LOCK = threading.Lock()
_SEEN: dict[tuple[str, str], dict] = {}
SEEN_FOR_SECONDS = 7 * 86400
# The list is kept in a small file next to the database. Held only in memory,
# every restart (an update, a reboot) made working plugins show "Needs setting
# up" until someone played a movie again.
SEEN_FILE_NAME = "plugins-seen.json"
_SEEN_SAVE_EVERY = 300  # seconds between saves when only the time changed
_seen_state = {"loaded": False, "saved_at": 0.0, "path": None}


def _seen_path() -> Optional[str]:
    if _seen_state["path"] is None:
        try:
            from backend.database import DB_PATH
            _seen_state["path"] = os.path.join(os.path.dirname(DB_PATH), SEEN_FILE_NAME)
        except Exception:
            _seen_state["path"] = ""
    return _seen_state["path"] or None


def _load_seen_locked() -> None:
    if _seen_state["loaded"]:
        return
    _seen_state["loaded"] = True
    path = _seen_path()
    if not path or not os.path.isfile(path):
        return
    try:
        import json
        with open(path, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
        for row in rows if isinstance(rows, list) else []:
            kind, who = str(row.get("server_type") or ""), str(row.get("who") or "")
            if kind in ("jellyfin", "emby") and who and isinstance(row.get("last_seen"), (int, float)):
                entry = {k: v for k, v in row.items() if k != "who"}
                _SEEN.setdefault((kind, who), entry)
    except Exception as exc:  # a damaged file only costs the list
        logger.warning("Couldn't read the list of plugins seen: %s", exc)


def _save_seen_locked(now: float) -> None:
    path = _seen_path()
    if not path:
        return
    try:
        import json
        rows = [{**v, "who": who} for (kind, who), v in _SEEN.items()]
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rows, fh)
        os.replace(tmp, path)
        _seen_state["saved_at"] = now
    except Exception as exc:
        logger.warning("Couldn't save the list of plugins seen: %s", exc)


def note_plugin(server_type: str, *, version: str = "", protocol: str = "v1", server_id: str = "",
                server_name: str = "", key_name: Optional[str] = None, address: str = "",
                media_server_id: Optional[int] = None, now: Optional[float] = None) -> None:
    kind = (server_type or "unknown").strip().lower()
    if kind not in ("jellyfin", "emby"):
        return
    now = time.time() if now is None else now
    who = server_id or server_name or address or "?"
    with _SEEN_LOCK:
        _load_seen_locked()
        entry = _SEEN.setdefault((kind, who), {"server_type": kind, "first_seen": now})
        before = {k: entry.get(k) for k in ("plugin_version", "protocol", "server_name", "key_name")}
        entry.update({
            "plugin_version": version or entry.get("plugin_version", ""),
            "protocol": protocol,
            "server_id": server_id or entry.get("server_id", ""),
            "server_name": server_name or entry.get("server_name", ""),
            "key_name": key_name or entry.get("key_name"),
            "media_server_id": media_server_id or entry.get("media_server_id"),
            "last_seen": now,
        })
        changed = before != {k: entry.get(k) for k in before}
        if changed or now - _seen_state["saved_at"] >= _SEEN_SAVE_EVERY:
            _save_seen_locked(now)


def seen_plugins(server_type: Optional[str] = None, now: Optional[float] = None) -> list[dict]:
    """Plugins that asked for intros in the last week, newest first."""
    now = time.time() if now is None else now
    with _SEEN_LOCK:
        _load_seen_locked()
        for key in [k for k, v in _SEEN.items() if now - v["last_seen"] > SEEN_FOR_SECONDS]:
            _SEEN.pop(key, None)
        rows = [dict(v) for (kind, _), v in _SEEN.items() if server_type is None or kind == server_type]
    rows.sort(key=lambda r: r["last_seen"], reverse=True)
    for row in rows:
        row["last_seen_seconds_ago"] = int(now - row["last_seen"])
    return rows


def reset_seen() -> None:
    with _SEEN_LOCK:
        _SEEN.clear()
        _seen_state["loaded"] = True
        path = _seen_path()
        if path and os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass


def reload_seen_for_tests(path: Optional[str]) -> None:
    """Forget what is in memory and read `path` again, as after a restart."""
    with _SEEN_LOCK:
        _SEEN.clear()
        _seen_state.update({"loaded": False, "saved_at": 0.0, "path": path or ""})


# ---------------------------------------------------------------------------
# "First episode of a sitting", when the plugin can't tell
# ---------------------------------------------------------------------------

class BingeSessions:
    """Whether an episode starts a sitting for one person and series.

    Same rule as the plugins': first if this person started no other episode
    of the series within the window. The same episode asked about again
    within the window keeps its answer (clients sometimes ask twice).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen: dict[tuple[str, str], tuple[float, str]] = {}

    def is_first(self, user: str, series: str, episode: str, window_seconds: float,
                 now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        key = (user, series)
        with self._lock:
            last = self._seen.get(key)
            if last is None or now - last[0] >= window_seconds:
                self._seen[key] = (now, episode)
                first = True
            else:
                first = last[1] == episode
                self._seen[key] = (now, last[1])
            if len(self._seen) > 5000:
                for k in [k for k, v in self._seen.items() if now - v[0] > window_seconds]:
                    self._seen.pop(k, None)
        return first


BINGES = BingeSessions()


# ---------------------------------------------------------------------------
# The request
# ---------------------------------------------------------------------------

def _split(value: Optional[str]) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()][:100]


def _int(value: Optional[str]) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _flag(value: Optional[str]) -> Optional[bool]:
    text = (value or "").strip().lower()
    if text in ("1", "true", "yes"):
        return True
    if text in ("0", "false", "no"):
        return False
    return None


def _clip(value: Optional[str], limit: int = 300) -> str:
    return (value or "").strip()[:limit]


def read_facts(params) -> dict:
    """The playback facts from the v2 query string, cleaned up."""
    from backend.media_audio import codec_format

    item_type = _clip(params.get("item_type"), 20).lower()
    item_type = {"movie": "Movie", "episode": "Episode"}.get(item_type, "Movie")
    codecs = [c for c in (codec_format(v) for v in _split(params.get("audio_codecs"))) if c]
    default_codec = codec_format(params.get("audio_default"))
    audio = None
    if codecs or default_codec:
        audio = {"default": default_codec, "formats": sorted(set(codecs) | ({default_codec} if default_codec else set())),
                 "complete": bool(codecs)}
    return {
        "item_id": _clip(params.get("item_id"), 100),
        "item_type": item_type,
        "item_name": _clip(params.get("item_name")),
        "user_id": _clip(params.get("user_id"), 100),
        "user_name": _clip(params.get("user_name"), 200),
        "library_id": _clip(params.get("library_id"), 100),
        "library_name": _clip(params.get("library_name"), 200),
        "genres": _split(params.get("genres")),
        "tags": _split(params.get("tags")),
        "official_rating": _clip(params.get("official_rating"), 40),
        "year": _int(params.get("year")),
        "series_id": _clip(params.get("series_id"), 100),
        "series_name": _clip(params.get("series_name")),
        "season": _int(params.get("season")),
        "episode": _int(params.get("episode")),
        "first_in_session": _flag(params.get("is_first_in_session")),
        "client": _clip(params.get("client"), 100),
        "device_id": _clip(params.get("device_id"), 200),
        "server_id": _clip(params.get("server_id"), 100),
        "audio_text": _clip(params.get("audio"), 100),
        "audio": audio,
        "video": _clip(params.get("video"), 100),
        "path": _clip(params.get("path"), 1000),
        "tmdb_id": _clip(params.get("tmdb_id"), 40),
    }


def _stream_url(sign: Callable[[str, int], str], path: str, lifetime: int = STREAM_LINK_SECONDS) -> str:
    """A signed download link, relative to Prerolls Max's address.

    Relative so the plugin joins it to the address it was configured with:
    behind a reverse proxy with a path prefix, an absolute link built from the
    address the request arrived on pointed at the wrong place.
    """
    expires = int(time.time()) + lifetime
    encoded = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii")
    return f"/plugin/stream?p={encoded}&e={expires}&t={sign(path, expires)}"


def _reason(result: dict, count: int, whole_pool: bool, facts: dict) -> str:
    if result.get("reason"):
        return str(result["reason"])
    if whole_pool:
        return f"{count} intro(s) could play right now."
    if count == 0:
        return "Nothing is set to play right now, so no intros."
    kind = "episode" if facts.get("item_type") == "Episode" else "movie"
    order = " in order" if result.get("mode") in ("sequential", "single") else ""
    return f"Playing {count} intro(s){order} before this {kind}."


@router.get("/plugin/v2/intros")
def plugin_v2_intros(request: Request, db=Depends(_get_db)):
    """The intros for one playback (or, with ``all=1``, everything that could play)."""
    if _deps is None:
        raise AppError("Prerolls Max is still starting.", status=503, code="starting",
                       hint="Try again in a few seconds.")
    deps = _deps
    record = check_plugin_key(request, db, validate_api_key=deps.validate_api_key,
                              setting_model=deps.setting_model,
                              keyless_note=deps.keyless_note, keyless_forget=deps.keyless_forget)
    server_type, server_name, version = plugin_identity(request)
    params = request.query_params
    facts = read_facts(params)
    whole_pool = _flag(params.get("all")) is True
    address = request.client.host if request.client else ""
    linked = None
    if deps.link_server is not None and db is not None:
        try:
            linked = deps.link_server(db, server_type, facts["server_id"], getattr(record, "id", None), address)
        except Exception:
            logger.exception("Matching a %s plugin to its server failed", server_type)
    if linked:
        facts["media_server_id"] = linked["id"]
        server_name = linked["name"]
    note_plugin(server_type, version=version, protocol="v2", server_id=facts["server_id"],
                server_name=server_name, key_name=getattr(record, "name", None), address=address,
                media_server_id=linked["id"] if linked else None)
    if record is not None:
        deps.plugin_clients[record.name] = {
            "api_key_name": record.name,
            "api_key_id": getattr(record, "id", None),
            "server_type": server_type.capitalize(),
            "server_name": server_name,
            "server_version": version,
            "protocol": "v2",
            "last_seen": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()),
        }

    if (not whole_pool and facts["item_type"] == "Episode" and facts["first_in_session"] is None
            and facts["user_id"] and facts["series_id"]):
        hours = DEFAULT_BINGE_HOURS
        if deps.binge_hours:
            try:
                hours = int(deps.binge_hours()) or DEFAULT_BINGE_HOURS
            except Exception:
                hours = DEFAULT_BINGE_HOURS
        facts["first_in_session"] = BINGES.is_first(
            facts["user_id"], facts["series_id"], facts["item_id"], hours * 3600)

    if linked and not linked.get("enabled", True):
        # Switched off on the Media Servers page: nothing plays from Prerolls Max.
        return {"mode": "pool" if whole_pool else "exact", "items": [],
                "reason": f"{server_name} is switched off in Prerolls Max.", "intentional_empty": False,
                "cache_seconds": POOL_CACHE_SECONDS if whole_pool else 0}

    if linked and linked.get("nexroll_manages"):
        # Settings > Moving from NeXroll: NeXroll's plugin adds the intros on
        # this server. Nothing from Prerolls Max, on purpose, so they never play twice.
        return {"mode": "pool" if whole_pool else "exact", "items": [],
                "reason": f"NeXroll manages intros on {server_name}, so Prerolls Max adds none.",
                "intentional_empty": not whole_pool,
                "cache_seconds": POOL_CACHE_SECONDS if whole_pool else 0}

    testing = bool(deps.is_play_test and not whole_pool and deps.is_play_test(facts))
    if not whole_pool and deps.note_playback and not testing:
        deps.note_playback()

    result = None
    if not whole_pool and deps.smart_intros is not None:
        # Never-play list and rule set first; None lets the schedules decide.
        try:
            result = deps.smart_intros(db, facts=facts, server_type=server_type)
        except Exception:
            logger.exception("Checking the rule set for a %s plugin failed; using schedules", server_type)
            result = None

    try:
        if result is None:
            result = deps.resolve_intros(
                db, media_type=facts["item_type"], item_id=facts["item_id"] or None,
                server_type=server_type, genres=facts["genres"], whole_pool=whole_pool, facts=facts)
    except AppError:
        raise
    except Exception:
        logger.exception("Choosing intros for a %s plugin failed", server_type)
        raise AppError("Prerolls Max couldn't choose the intros for this playback.", status=500,
                       code="intros_failed", hint="Its log has the details. The plugin plays the intros "
                                                  "it was given last time meanwhile.")

    paths = list(result.get("paths") or [])
    if whole_pool and deps.rule_pool is not None:
        try:
            paths = list(dict.fromkeys(paths + list(deps.rule_pool(db))))
        except Exception:
            logger.exception("Listing the rule set's intros failed")
    mode = result.get("mode", "shuffle")
    if not whole_pool:
        setting = db.query(deps.setting_model).first() if db is not None else None
        paths = deps.play_list(setting, paths, mode, result.get("rotation"))

    known = {}
    if deps.preroll_model is not None and paths and db is not None:
        try:
            for row in db.query(deps.preroll_model).filter(deps.preroll_model.path.in_(paths)).all():
                known[os.path.abspath(row.path)] = row
        except Exception:
            known = {}

    items = []
    for path in paths:
        row = known.get(os.path.abspath(path))
        name = (getattr(row, "display_name", None) or os.path.splitext(os.path.basename(path))[0])
        duration = getattr(row, "duration", None)
        items.append({
            "id": str(row.id) if row is not None else hashlib.sha256(path.encode("utf-8")).hexdigest()[:16],
            "name": name,
            "path": path,
            "stream_url": _stream_url(deps.sign_stream_path, path),
            "version": deps.file_version(path),
            "duration_seconds": float(duration) if isinstance(duration, (int, float)) else None,
        })

    logger.debug("v2 intros for %s %s: %d item(s)", server_type, facts["item_type"], len(items))
    reason = _reason({**result, "mode": mode}, len(items), whole_pool, facts)
    if not whole_pool and deps.on_answer is not None and not testing:
        try:
            deps.on_answer(db, facts=facts, server_type=server_type, server_name=server_name, items=items,
                           reason=reason, excluded=bool(result.get("excluded")), rule_name=result.get("rule"))
        except Exception:
            logger.exception("Recording play history failed")
    # No intros on purpose (never-play list, a no-intro tag): the plugin plays
    # nothing and keeps its last list for when Prerolls Max is unreachable.
    intentional_empty = (not whole_pool and not items
                         and bool(result.get("excluded") or result.get("intentional_empty")))
    return {
        "mode": "pool" if whole_pool else "exact",
        "items": items,
        "reason": reason,
        "intentional_empty": intentional_empty,
        "cache_seconds": POOL_CACHE_SECONDS if whole_pool else 0,
    }
