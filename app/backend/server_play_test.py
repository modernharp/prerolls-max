"""'Play a test': ask a media server what it would play before a movie.

Plex builds a real play queue (what an app does when you press Play, though
nothing starts playing); Jellyfin and Emby answer their /Intros call, which
makes the plugin ask Prerolls Max just as a real playback would. That request
is marked as a test so it isn't counted in What Played.

When the answer is empty, :func:`why_empty` says why in plain words.
"""
from __future__ import annotations

import hashlib
import os
import threading
import time
from typing import Optional

from backend import media_servers as ms, models, server_probe

_TESTS: dict = {}
_lock = threading.Lock()
TEST_SECONDS = 90


def _forms(item_id) -> set:
    text = str(item_id or "").strip().lower()
    return {text, text.replace("-", "")} - {""}


def mark(item_id) -> None:
    with _lock:
        until = time.time() + TEST_SECONDS
        for form in _forms(item_id):
            _TESTS[form] = until


def is_test(facts: dict) -> bool:
    now = time.time()
    with _lock:
        for key in [k for k, t in _TESTS.items() if t < now]:
            _TESTS.pop(key, None)
        return any(f in _TESTS for f in _forms((facts or {}).get("item_id")))


def _preroll_names(db, row, items: list) -> list:
    """Each intro by its name in Prerolls Max when it can be matched, else the server's title."""
    from backend.plex_fanout import unmap
    rows = db.query(models.Preroll).all()
    by_path = {os.path.normcase(os.path.abspath(p.path)): p for p in rows if p.path}
    by_hash = {hashlib.sha256(p.path.encode("utf-8")).hexdigest()[:24]: p for p in rows if p.path}
    by_name = {}
    for p in rows:
        for key in (p.display_name, os.path.splitext(p.filename or "")[0]):
            if key:
                by_name.setdefault(key.casefold(), p)
    out = []
    for item in items:
        match = None
        path = item.get("path")
        if path and row.type == "plex":
            local = unmap(path, ms.mappings(row))
            match = by_path.get(os.path.normcase(os.path.abspath(local)))
        title = str(item.get("title") or "")
        if match is None and title:
            match = by_name.get(title.casefold())
        if match is None and path:
            match = by_name.get(os.path.splitext(os.path.basename(path))[0].casefold())
        if match is None:
            # The plugin's cache names a file by a hash of the intro's path (IntroCache.Key).
            stem = os.path.splitext(os.path.basename(str(path or title)))[0].split("-")[0].lower()
            match = by_hash.get(stem)
        out.append({"title": (match.display_name or match.filename) if match else (title or "An intro"),
                    "preroll_id": match.id if match else None})
    return out


def _reason(title: str, detail: str, link: Optional[dict] = None) -> dict:
    return {"title": title, "detail": detail, "link": link}


def _prerolls_max_answer(db, row, item_id: str, movie: str) -> Optional[dict]:
    """What Prerolls Max itself would hand this server's plugin for this movie."""
    from backend.routers import plugin_v2
    deps = plugin_v2._deps
    if deps is None:
        return None
    facts = plugin_v2.read_facts({"item_id": item_id, "item_type": "Movie", "item_name": movie,
                                  "server_id": row.server_identifier or ""})
    facts["media_server_id"] = row.id
    try:
        result = deps.smart_intros(db, facts=facts, server_type=row.type) if deps.smart_intros else None
        if result is None:
            result = deps.resolve_intros(db, media_type="Movie", item_id=item_id, server_type=row.type,
                                         genres=[], whole_pool=False, facts=facts)
    except Exception:
        return None
    return result


def why_empty(db, row, target, item_id: str, movie: str) -> list:
    name = ms.label(row)
    if not row.enabled:
        return [_reason(f"{name} is switched off", "Prerolls Max leaves its intros alone. Switch it on to use it.")]
    reasons = []
    if row.type == "plex":
        from backend.plex_fanout import FANOUT
        value = server_probe.plex_intro_list(target)
        if value is not None and not value.strip():
            reasons.append(_reason("Nothing is set to play",
                                   f"{name} has no intros set right now. Turn on a schedule, or set Default intros.",
                                   {"to": "/schedules", "label": "Schedules"}))
        status = FANOUT.status(row.id) or {}
        if status.get("state") in ("failed", "waiting") and status.get("message"):
            reasons.append(_reason("The last change didn't reach it", status["message"]))
        if not reasons:
            reasons.append(_reason("Plex skipped them for this movie",
                                   f"{name} has intros set but put none before this movie. The movie's library may "
                                   "have Cinema Trailers turned off (in Plex: the library's Edit, then Advanced), or "
                                   "Plex can't see the files. Test connection checks the files."))
        return reasons
    info = server_probe.plugin_info(target)
    if info.get("installed") is False:
        return [_reason("The plugin isn't installed", f"{name} doesn't have the Prerolls Max Intros plugin, so it "
                        "never asks for intros. Follow the plugin steps on this server's card.",
                        {"to": "/servers", "label": "Media Servers"})]
    if info.get("installed") and info.get("configured") is False:
        return [_reason("The plugin isn't set up", "The plugin doesn't know where Prerolls Max is. Press \"Set up "
                        "the plugin for me\" on this server's card.", {"to": "/servers", "label": "Media Servers"})]
    answer = _prerolls_max_answer(db, row, item_id, movie)
    if answer is not None and answer.get("excluded"):
        return [_reason("This movie never gets intros", "It's on the never-play list, or it has a no-intro tag in "
                        f"{name}.", {"to": "/schedules/never-play", "label": "Never-play list"})]
    if answer is not None and not answer.get("paths"):
        return [_reason("Nothing is set to play", "No schedule is on and there are no Default intros, so Prerolls "
                        "Max has nothing to hand out.", {"to": "/schedules", "label": "Schedules"})]
    if row.type == "emby":
        return [_reason("Emby is still getting them ready", "Emby only plays intros the plugin has downloaded and "
                        "registered. New ones take a minute or two; try again shortly."),
                _reason("Emby Premiere", "Emby plays intros only with Emby Premiere.")]
    return [_reason("The plugin didn't hear back", f"The plugin on {name} may not reach Prerolls Max. Press \"Set up "
                    "the plugin for me\" on this server's card to check its address.",
                    {"to": "/servers", "label": "Media Servers"})]


def run(db, row, item_id: str) -> dict:
    target = ms.target(row)
    name = ms.label(row)
    movie = server_probe.movie_title(target, item_id) or "this movie"
    server = {"id": row.id, "name": name, "type": row.type}
    if not row.enabled:
        return {"server": server, "movie": {"id": item_id, "title": movie}, "ok": True, "items": [],
                "summary": f"{name} is switched off, so Prerolls Max gives it no intros.",
                "reasons": why_empty(db, row, target, item_id, movie)}
    if row.type != "plex":
        mark(item_id)
    answer = server_probe.intros(target, item_id)
    if not answer.get("ok"):
        return {"server": server, "movie": {"id": item_id, "title": movie}, "ok": False, "items": [],
                "summary": answer.get("message") or f"{name} didn't answer.", "reasons": []}
    items = _preroll_names(db, row, answer["items"])
    if items:
        summary = f"Before \"{movie}\", {name} will play: " + ", ".join(i["title"] for i in items)
        if row.type == "plex" and (server_probe.plex_intro_list(target) or "").count(";"):
            summary += ". Plex picks at random each time, so another test may show a different one."
        return {"server": server, "movie": {"id": item_id, "title": movie}, "ok": True, "items": items,
                "summary": summary, "reasons": []}
    return {"server": server, "movie": {"id": item_id, "title": movie}, "ok": True, "items": [],
            "summary": f"Before \"{movie}\", {name} would play no intro.",
            "reasons": why_empty(db, row, target, item_id, movie)}
