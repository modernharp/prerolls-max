"""What played, and whether intros played at all.

Two tables (models.py):

- ``intro_plays`` (PlayEvent): one row per intro. Jellyfin and Emby rows come
  from the plugin asking for intros (/plugin/v2/intros); Plex rows come from
  watching Plex's list of what is playing, the same request the scheduler's
  playback guard makes.
- ``playback_checks`` (PlaybackCheck): one row per movie or episode that
  started, saying whether intros came with it. The missed-intro check
  (GET /api/health/intros) reads these.

Everything here is best effort: a failure to record history must never get in
the way of playback, so callers wrap these in try/except.
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import threading
import time
from typing import Callable, Iterable, Optional

from sqlalchemy import func

from backend import models
from backend.timeutil import utcnow

logger = logging.getLogger("prerollsmax.history")

# A movie start whose first sighting was this far in (ms) still counts as seen
# from the beginning, so "no intro played" can be judged.
START_GRACE_MS = 45_000
# A Jellyfin/Emby playback counts as "the plugin was asked" when a plugin
# request for the same item came this recently.
PLUGIN_CALL_WINDOW = datetime.timedelta(minutes=20)
# Episodes that follow an earlier one of the same series this soon are
# auto-played; Jellyfin and Emby don't play intros between those.
SERIES_CONTINUE_WINDOW = datetime.timedelta(hours=8)


def iso(value: Optional[datetime.datetime]) -> Optional[str]:
    return value.replace(microsecond=0).isoformat() + "Z" if value else None


def _clip(value, limit: int = 200) -> Optional[str]:
    text = str(value or "").strip()
    return text[:limit] or None


# ---------------------------------------------------------------------------
# Recording
# ---------------------------------------------------------------------------

def record_plugin_answer(db, *, facts: dict, server_type: str, server_name: str, items: list,
                         reason: str = "", excluded: bool = False, rule_name: Optional[str] = None,
                         history: bool = True, now: Optional[datetime.datetime] = None) -> None:
    """A Jellyfin/Emby plugin asked for this playback's intros and got ``items``."""
    now = now or utcnow()
    common = dict(server_type=_clip(server_type, 20), user_name=_clip(facts.get("user_name") or facts.get("user_id")),
                  client=_clip(facts.get("client"), 100), device=_clip(facts.get("device_id"), 200),
                  item_id=_clip(facts.get("item_id"), 100), item_name=_clip(facts.get("item_name") or facts.get("series_name")),
                  item_type=_clip(facts.get("item_type"), 20))
    if history:
        for item in items:
            try:
                preroll_id = int(item.get("id"))
            except (TypeError, ValueError):
                preroll_id = None
            db.add(models.PlayEvent(played_at=now, preroll_id=preroll_id, name=_clip(item.get("name")),
                                    path=_clip(item.get("path"), 1000), server_name=_clip(server_name),
                                    source="plugin", rule_name=_clip(rule_name), **common))
    outcome = "intros" if items else ("excluded" if excluded else "nothing_set")
    db.add(models.PlaybackCheck(at=now, source="plugin", intro_count=len(items), outcome=outcome,
                                reason=_clip(reason, 300), series_id=_clip(facts.get("series_id"), 100),
                                server_name=_clip(server_name), **common))
    db.commit()


def record_play(db, *, preroll_id: Optional[int], name: str, path: str, server_type: str, user_name=None,
                client=None, device=None, item_name=None, source: str = "plex_sessions",
                server_name: Optional[str] = None, now: Optional[datetime.datetime] = None) -> None:
    db.add(models.PlayEvent(played_at=now or utcnow(), preroll_id=preroll_id, name=_clip(name),
                            path=_clip(path, 1000), server_type=server_type, server_name=_clip(server_name),
                            user_name=_clip(user_name),
                            client=_clip(client, 100), device=_clip(device, 200), item_name=_clip(item_name),
                            item_type="Movie", source=source))
    db.commit()


def record_check(db, **fields) -> None:
    fields.setdefault("at", utcnow())
    for key in ("user_name", "item_name", "reason"):
        if key in fields:
            fields[key] = _clip(fields[key], 300)
    db.add(models.PlaybackCheck(**fields))
    db.commit()


def prune(db, retention_days: int, now: Optional[datetime.datetime] = None) -> int:
    """Forget plays and checks older than the retention window."""
    cutoff = (now or utcnow()) - datetime.timedelta(days=max(1, int(retention_days)))
    removed = db.query(models.PlayEvent).filter(models.PlayEvent.played_at < cutoff).delete(synchronize_session=False)
    removed += db.query(models.PlaybackCheck).filter(models.PlaybackCheck.at < cutoff).delete(synchronize_session=False)
    db.commit()
    return removed


def last_played(db, preroll_ids: Iterable[int]) -> dict:
    """{preroll_id: datetime of its most recent play} for the ids that ever played."""
    ids = [int(i) for i in preroll_ids if i is not None]
    if not ids:
        return {}
    rows = (db.query(models.PlayEvent.preroll_id, func.max(models.PlayEvent.played_at))
            .filter(models.PlayEvent.preroll_id.in_(ids))
            .group_by(models.PlayEvent.preroll_id).all())
    return {pid: when for pid, when in rows if when is not None}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def _since(days: Optional[int], now=None):
    if not days:
        return None
    return (now or utcnow()) - datetime.timedelta(days=int(days))


def _filtered(query, model, *, since=None, server=None, user=None, client=None):
    column_at = model.played_at if model is models.PlayEvent else model.at
    if since is not None:
        query = query.filter(column_at >= since)
    if server:
        query = query.filter(model.server_type == server)
    if user:
        query = query.filter(func.lower(model.user_name) == user.lower())
    if client:
        query = query.filter(func.lower(model.client) == client.lower())
    return query


def play_row(row) -> dict:
    return {"id": row.id, "played_at": iso(row.played_at), "preroll_id": row.preroll_id, "name": row.name,
            "server_type": row.server_type, "server_name": row.server_name, "user_name": row.user_name,
            "client": row.client, "device": row.device, "item_name": row.item_name, "item_type": row.item_type,
            "source": row.source, "rule_name": row.rule_name}


def recent(db, *, limit: int = 50, server=None, user=None, client=None, days=None) -> list:
    query = _filtered(db.query(models.PlayEvent), models.PlayEvent, since=_since(days), server=server,
                      user=user, client=client)
    return [play_row(r) for r in query.order_by(models.PlayEvent.played_at.desc(), models.PlayEvent.id.desc())
            .limit(limit).all()]


def _library(db) -> dict:
    rows = db.query(models.Preroll).all()
    return {p.id: p for p in rows}


def _label(preroll) -> str:
    return (getattr(preroll, "display_name", None) or os.path.splitext(preroll.filename or "")[0]
            or f"Intro {preroll.id}")


def top(db, *, days: Optional[int] = 30, order: str = "most", limit: int = 20, server=None, user=None) -> list:
    """Most or least played intros. "least" lists intros that played at least
    once, fewest first; never_played lists the ones that didn't."""
    query = db.query(models.PlayEvent.preroll_id, func.count(models.PlayEvent.id), func.max(models.PlayEvent.played_at))
    query = _filtered(query, models.PlayEvent, since=_since(days), server=server, user=user)
    rows = query.filter(models.PlayEvent.preroll_id.isnot(None)).group_by(models.PlayEvent.preroll_id).all()
    library = _library(db)
    out = [{"preroll_id": pid, "name": _label(library[pid]), "plays": count, "last_played": iso(last)}
           for pid, count, last in rows if pid in library]
    out.sort(key=lambda r: (r["plays"], r["last_played"] or ""), reverse=(order != "least"))
    return out[:limit]


def never_played(db, *, days: Optional[int] = None, limit: int = 200) -> list:
    """Intros in the library with no play in the window (all of history when no window)."""
    query = db.query(models.PlayEvent.preroll_id).filter(models.PlayEvent.preroll_id.isnot(None))
    since = _since(days)
    if since is not None:
        query = query.filter(models.PlayEvent.played_at >= since)
    played = {pid for (pid,) in query.distinct().all()}
    rows = [p for p in db.query(models.Preroll).order_by(models.Preroll.id).all()
            if p.id not in played and getattr(p, "enabled", True) is not False]
    return [{"preroll_id": p.id, "name": _label(p),
             "collections": [c.name for c in (p.categories or [])] or ([p.category.name] if p.category else []),
             "added": iso(p.upload_date)} for p in rows[:limit]]


def summary(db, *, days: Optional[int] = 30) -> dict:
    since = _since(days)

    def grouped(column):
        query = db.query(column, func.count(models.PlayEvent.id))
        if since is not None:
            query = query.filter(models.PlayEvent.played_at >= since)
        rows = query.group_by(column).order_by(func.count(models.PlayEvent.id).desc()).limit(50).all()
        return [{"name": name or "Unknown", "plays": count} for name, count in rows]

    total = db.query(func.count(models.PlayEvent.id))
    if since is not None:
        total = total.filter(models.PlayEvent.played_at >= since)
    day = func.date(models.PlayEvent.played_at)
    per_day = db.query(day, func.count(models.PlayEvent.id))
    if since is not None:
        per_day = per_day.filter(models.PlayEvent.played_at >= since)
    return {
        "days": days,
        "total_plays": total.scalar() or 0,
        "by_user": grouped(models.PlayEvent.user_name),
        "by_server": grouped(models.PlayEvent.server_type),
        "by_client": grouped(models.PlayEvent.client),
        "by_day": [{"date": str(d), "plays": c} for d, c in per_day.group_by(day).order_by(day).all()],
    }


def clear(db) -> int:
    removed = db.query(models.PlayEvent).delete(synchronize_session=False)
    removed += db.query(models.PlaybackCheck).delete(synchronize_session=False)
    db.commit()
    return removed


# ---------------------------------------------------------------------------
# Watching Plex (what plays there)
# ---------------------------------------------------------------------------

class PrerollIndex:
    """Finds the library intro behind a path or title Plex reports."""

    def __init__(self, rows: list, translate: Callable[[str], str] = lambda p: p):
        self.by_path: dict = {}
        self.by_name: dict = {}
        for row in rows:
            path = getattr(row, "path", None)
            if not path:
                continue
            for candidate in {os.path.abspath(path), translate(os.path.abspath(path))}:
                self.by_path[_path_key(candidate)] = row
            base = os.path.basename(path)
            for name in {base.lower(), os.path.splitext(base)[0].lower(),
                         str(getattr(row, "display_name", "") or "").strip().lower()}:
                if name:
                    self.by_name.setdefault(name, row)

    def find(self, file_path: Optional[str], title: Optional[str]):
        if file_path:
            row = self.by_path.get(_path_key(file_path))
            if row is not None:
                return row
            base = file_path.replace("\\", "/").rsplit("/", 1)[-1].lower()
            row = self.by_name.get(base) or self.by_name.get(os.path.splitext(base)[0])
            if row is not None:
                return row
        if title:
            return self.by_name.get(str(title).strip().lower())
        return None


def _path_key(path: str) -> str:
    return str(path or "").replace("\\", "/").rstrip("/").lower()


class PlexWatcher:
    """Turns Plex's /status/sessions answers into play history and checks.

    Each preroll, trailer and the movie is its own item, but they share the
    playback's Session id and the player, so intros seen before a movie are
    remembered per player for a while.
    """

    CLIP_MEMORY_SECONDS = 15 * 60

    def __init__(self):
        self._lock = threading.Lock()
        self._recorded_clips: dict = {}   # (session, path) -> time
        self._player_clips: dict = {}     # player key -> [(time, preroll id)]
        self._movies: dict = {}           # (session, ratingKey) -> {"first_offset", "checked"}

    def observe(self, root, *, index: PrerollIndex, record_play: Callable[..., None],
                record_check: Callable[..., None], list_is_empty: Callable[[], Optional[bool]],
                now: Optional[float] = None) -> dict:
        now = time.time() if now is None else now
        seen = {"intros": 0, "movies": 0}
        with self._lock:
            for element in list(root):
                if element.tag != "Video":
                    continue
                kind = (element.get("type") or "").lower()
                session = element.find("Session")
                player = element.find("Player")
                user = element.find("User")
                session_id = (session.get("id") if session is not None else None) or element.get("sessionKey") or ""
                player_key = ((player.get("machineIdentifier") if player is not None else None)
                              or session_id or "?")
                product = ((player.get("product") if player is not None else None)
                           or (player.get("title") if player is not None else None) or "")
                device = (player.get("title") if player is not None else None) or ""
                user_name = (user.get("title") if user is not None else None) or ""
                part = element.find("Media/Part")
                file_path = part.get("file") if part is not None else None
                if kind == "clip" or element.get("extraType"):
                    row = index.find(file_path, element.get("title"))
                    if row is None:
                        continue
                    key = (session_id or player_key, row.id)
                    if key in self._recorded_clips:
                        continue
                    self._recorded_clips[key] = now
                    self._player_clips.setdefault(player_key, []).append((now, row.id))
                    seen["intros"] += 1
                    record_play(preroll_id=row.id, name=_label(row), path=row.path, server_type="plex",
                                user_name=user_name, client=product, device=device)
                elif kind == "movie":
                    key = (session_id or player_key, element.get("ratingKey") or "")
                    state = self._movies.get(key)
                    if state is None:
                        try:
                            offset = int(element.get("viewOffset") or 0)
                        except ValueError:
                            offset = 0
                        state = self._movies[key] = {"first_offset": offset, "checked": False, "at": now}
                    if state["checked"]:
                        continue
                    state["checked"] = True
                    seen["movies"] += 1
                    clips = [c for c in self._player_clips.get(player_key, [])
                             if now - c[0] <= self.CLIP_MEMORY_SECONDS]
                    title = element.get("title") or "a movie"
                    common = dict(server_type="plex", source="sessions", user_name=user_name, client=product,
                                  device=device, item_id=element.get("ratingKey"), item_name=title,
                                  item_type="Movie")
                    if clips:
                        record_check(intro_count=len(clips), outcome="intros", **common)
                        self._player_clips[player_key] = []
                    elif state["first_offset"] <= START_GRACE_MS:
                        empty = list_is_empty()
                        if empty:
                            record_check(intro_count=0, outcome="empty_list",
                                         reason="Plex had no intros set when the movie started.", **common)
                        else:
                            record_check(intro_count=0, outcome="not_played",
                                         reason="The movie started without an intro.", **common)
            self._forget(now)
        return seen

    def _forget(self, now: float) -> None:
        horizon = now - 6 * 3600
        for key in [k for k, t in self._recorded_clips.items() if t < horizon]:
            self._recorded_clips.pop(key, None)
        for key in [k for k, s in self._movies.items() if s["at"] < horizon]:
            self._movies.pop(key, None)
        for key in list(self._player_clips):
            self._player_clips[key] = [c for c in self._player_clips[key] if now - c[0] <= self.CLIP_MEMORY_SECONDS]
            if not self._player_clips[key]:
                self._player_clips.pop(key, None)


PLEX = PlexWatcher()


# ---------------------------------------------------------------------------
# Watching Jellyfin and Emby (did the plugin get asked?)
# ---------------------------------------------------------------------------

class PluginServerWatcher:
    """Spots Jellyfin/Emby playbacks that never asked the plugin for intros.

    The plugin is asked when an app plays from the start with intros turned on.
    A movie or first episode that appears in the server's sessions near its
    start with no plugin request for it means the app skipped intros (Swiftfin,
    Infuse, Roku with Cinema Mode off) or the plugin isn't running.
    """

    START_TICKS = 60 * 10_000_000  # 60 s

    def __init__(self):
        self._lock = threading.Lock()
        self._checked: dict = {}

    def observe(self, db, server_type: str, sessions: list, now: Optional[datetime.datetime] = None,
                server_name: Optional[str] = None) -> int:
        now = now or utcnow()
        flagged = 0
        with self._lock:
            for session in sessions or []:
                if not isinstance(session, dict):
                    continue
                item = session.get("NowPlayingItem") or {}
                kind = str(item.get("Type") or "")
                if kind not in ("Movie", "Episode"):
                    continue
                position = (session.get("PlayState") or {}).get("PositionTicks") or 0
                key = (server_type, server_name, session.get("Id"), item.get("Id"))
                if key in self._checked:
                    continue
                self._checked[key] = now
                try:
                    if int(position) > self.START_TICKS:
                        continue  # resumed or joined late: no intros expected
                except (TypeError, ValueError):
                    continue
                item_id = str(item.get("Id") or "")
                asked = (db.query(models.PlaybackCheck)
                         .filter(models.PlaybackCheck.source == "plugin",
                                 models.PlaybackCheck.item_id.in_(_id_forms(item_id)),
                                 models.PlaybackCheck.at >= now - PLUGIN_CALL_WINDOW).first())
                if asked is not None:
                    continue
                series_id = str(item.get("SeriesId") or "")
                if kind == "Episode" and series_id:
                    earlier = (db.query(models.PlaybackCheck)
                               .filter(models.PlaybackCheck.series_id.in_(_id_forms(series_id)),
                                       models.PlaybackCheck.at >= now - SERIES_CONTINUE_WINDOW).first())
                    if earlier is not None:
                        continue  # an auto-played next episode: no intros expected
                record_check(db, server_type=server_type, server_name=_clip(server_name), source="sessions",
                             user_name=session.get("UserName"),
                             client=_clip(session.get("Client"), 100), device=_clip(session.get("DeviceName"), 200),
                             item_id=item_id, item_name=item.get("SeriesName") or item.get("Name"), item_type=kind,
                             series_id=series_id or None, intro_count=0, outcome="no_plugin_call",
                             reason="This playback started without asking Prerolls Max for intros.", at=now)
                flagged += 1
            horizon = now - datetime.timedelta(hours=12)
            for key in [k for k, t in self._checked.items() if t < horizon]:
                self._checked.pop(key, None)
        return flagged


def _id_forms(value: str) -> list:
    """Jellyfin ids with and without dashes, as the API and plugin spell them."""
    text = str(value or "")
    plain = text.replace("-", "")
    forms = {text, plain, plain.lower()}
    if len(plain) == 32:
        dashed = f"{plain[:8]}-{plain[8:12]}-{plain[12:16]}-{plain[16:20]}-{plain[20:]}"
        forms |= {dashed, dashed.lower()}
    return [f for f in forms if f]


PLUGIN_SERVERS = PluginServerWatcher()


# ---------------------------------------------------------------------------
# Missed-intro check: plain warnings with fixes
# ---------------------------------------------------------------------------

_NEW_PLEX_APPS = ("apple tv", "tvos", "ios", "iphone", "ipad", "android tv", "androidtv", "fire tv", "firetv",
                  "android", "shield", "google tv")


def plex_fix(client: str) -> str:
    text = (client or "").lower()
    if "infuse" in text:
        return "Infuse never plays Plex intros. Use a Plex app on that device if you want them."
    if "plexamp" in text or "dlna" in text:
        return "This app doesn't play intros."
    if "web" in text or "htpc" in text or "desktop" in text or "windows" in text or "mac" in text:
        return ("Check Settings > Experience > Cinema Trailers in this app and choose at least 1 trailer before "
                "movies. Plex Web and the desktop app play intros once that is set.")
    if any(word in text for word in _NEW_PLEX_APPS):
        return (f"Your {client or 'device'} used the new Plex app, which skips intros set to \"Play pre-roll "
                "only\". In that app's settings, set Cinema Trailers to 1 before movies, and turn Plex's own "
                "trailer sources off in Plex's server settings so only your intro plays.")
    return ("In this app's settings, set Cinema Trailers to at least 1 before movies. Some Plex apps (Infuse, "
            "DLNA players, downloads) never play intros.")


def plugin_fix(server_type: str, client: str) -> str:
    text = (client or "").lower()
    name = "Jellyfin" if server_type == "jellyfin" else "Emby"
    if "swiftfin" in text:
        return "Swiftfin doesn't play intros. Use the Jellyfin web app or Jellyfin Media Player on that device."
    if "infuse" in text:
        return f"Infuse never plays {name} intros. Use the {name} app on that device if you want them."
    if "roku" in text:
        return (f"Turn on Cinema Mode (intros) in the {name} Roku app's settings; it is off by default. The Roku "
                "app plays only the first intro, so use one combined intro file (Media tools, Combine).")
    if "samsung" in text or "tizen" in text:
        return f"{name}'s Samsung TV app doesn't play intros."
    if "mpv" in text or "shim" in text:
        return "The MPV Shim doesn't play intros."
    if server_type == "emby":
        return ("Turn on Cinema Intros in this app (Settings, Playback), check that Emby Premiere is active and "
                "that the Prerolls Max Intros plugin is installed.")
    return ("Turn on Cinema mode (intros) in this app's playback settings, and check that the Prerolls Max "
            "Intros plugin is installed and enabled for this kind of item.")


_SERVER_NAMES = {"plex": "Plex", "jellyfin": "Jellyfin", "emby": "Emby"}


def intro_health(db, *, days: int = 7, configured: Optional[dict] = None, plugins_seen: Optional[dict] = None,
                 watching: Optional[dict] = None, now: Optional[datetime.datetime] = None,
                 servers: Optional[list] = None) -> dict:
    """Plain warnings about playbacks that started without intros.

    ``configured``: {"plex": bool, "jellyfin": bool, "emby": bool}.
    ``plugins_seen``: {"jellyfin": bool, "emby": bool} (a plugin asked in the last week).
    ``watching``: which servers' sessions are being watched right now.
    ``servers``: every connected server, [{name, type, plugin_seen}], when there
    may be several of a type; the plugin warning is then given per server.
    """
    now = now or utcnow()
    since = now - datetime.timedelta(days=days)
    configured = configured or {}
    plugins_seen = plugins_seen or {}
    rows = (db.query(models.PlaybackCheck).filter(models.PlaybackCheck.at >= since)
            .order_by(models.PlaybackCheck.at.desc()).all())
    warnings = []

    # Warnings name the server only when there are several of its type.
    several = {t for t in _SERVER_NAMES if sum(1 for s in servers or [] if s.get("type") == t) > 1}
    groups: dict = {}
    for row in rows:
        if row.outcome in ("intros", "excluded"):
            continue
        key = (row.server_type, (getattr(row, "server_name", None) or "") if row.server_type in several else "",
               row.outcome, row.client if row.outcome in ("not_played", "no_plugin_call") else "")
        groups.setdefault(key, []).append(row)

    for (server, server_name, outcome, client), items in groups.items():
        name = server_name or _SERVER_NAMES.get(server, server or "A media server")
        count = len(items)
        examples = [{"at": iso(r.at), "title": r.item_name, "user": r.user_name, "device": r.device}
                    for r in items[:5]]
        plays = "playback" if count == 1 else "playbacks"
        if outcome == "not_played":
            title = (f"{count} movie {plays} on {client or 'a Plex app'}"
                     f"{f' ({server_name})' if server_name else ''} started without an intro")
            reason = ("Plex had intros set, but this app went straight to the movie.")
            fix = plex_fix(client)
            severity = "warning"
        elif outcome == "no_plugin_call":
            title = f"{count} {plays} on {client or name} started without asking for intros"
            reason = (f"{name} started these from the beginning but never asked Prerolls Max for intros, so the "
                      "app skipped them or the plugin isn't running.")
            fix = plugin_fix(server, client)
            severity = "warning"
        elif outcome == "empty_list":
            title = f"{server_name or 'Plex'} had no intros set for {count} movie {plays}"
            reason = "Plex's intro list was empty when these movies started."
            fix = ("Turn on a schedule or set Default intros, so something is always set. If you clear the list "
                   "on purpose outside schedules, this is expected.")
            severity = "info"
        else:  # nothing_set
            title = f"{count} {name} {plays} got no intros"
            reason = "Prerolls Max had nothing set to play when these started."
            fix = ("Turn on a schedule, set Default intros, or add a rule that matches. Rules page: Preview shows "
                   "what would play for any title.")
            severity = "info"
        where = f"{server}:{server_name}" if server_name else f"{server}"
        warnings.append({"id": f"{where}:{outcome}:{(client or '').lower()}", "severity": severity,
                         "server": server, "server_name": server_name or None, "client": client or None,
                         "title": title, "reason": reason,
                         "fix": fix, "count": count, "last_seen": iso(items[0].at), "examples": examples})

    for entry in servers or []:
        if entry.get("type") in ("jellyfin", "emby") and not entry.get("plugin_seen"):
            name = entry.get("name") or _SERVER_NAMES[entry["type"]]
            warnings.append({
                "id": f"{entry['type']}:{name}:plugin_missing", "severity": "warning", "server": entry["type"],
                "server_name": name, "client": None,
                "title": f"The plugin on {name} hasn't asked for intros this week",
                "reason": f"{name} is connected, but its Prerolls Max Intros plugin hasn't been in touch.",
                "fix": f"Install the Prerolls Max Intros plugin on {name} and set it up under Media Servers.",
                "count": 0, "last_seen": None, "examples": []})
    for server in ("jellyfin", "emby"):
        if servers is not None:
            break
        if configured.get(server) and not plugins_seen.get(server):
            name = _SERVER_NAMES[server]
            warnings.append({
                "id": f"{server}:plugin_missing", "severity": "warning", "server": server, "client": None,
                "title": f"The {name} plugin hasn't asked for intros this week",
                "reason": f"{name} is connected, but the Prerolls Max Intros plugin hasn't been in touch.",
                "fix": f"Install the Prerolls Max Intros plugin on {name} and set it up under Media Servers.",
                "count": 0, "last_seen": None, "examples": []})

    order = {"warning": 0, "info": 1}
    warnings.sort(key=lambda w: (order.get(w["severity"], 2), -(w["count"] or 0)))
    with_intros = sum(1 for r in rows if r.outcome == "intros")
    total = len(rows)
    if warnings and any(w["severity"] == "warning" for w in warnings):
        status = "warning"
    elif warnings:
        status = "info"
    elif total:
        status = "ok"
    else:
        status = "unknown"
    messages = {
        "ok": "Every playback we saw in the last week had its intros.",
        "unknown": "No playbacks seen yet. Play something and check back.",
        "warning": "Some playbacks started without intros. Each warning says why and how to fix it.",
        "info": "Intros are playing; a few things are worth a look.",
    }
    return {"status": status, "message": messages[status], "days": days, "checked_at": iso(now),
            "watching": watching or {}, "playbacks": total, "with_intros": with_intros,
            "warnings": warnings}
