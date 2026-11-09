"""Play history, stats and the missed-intro check.

    GET    /api/stats/recent?limit=50&server=&user=&client=&days=
    GET    /api/stats/top?days=30&order=most|least&limit=20&server=&user=
    GET    /api/stats/never-played?days=
    GET    /api/stats/summary?days=30
    DELETE /api/stats                       -> {removed}  (admins)
    GET    /api/health/intros?days=7        -> {status, message, warnings: [{title, reason, fix, ...}], ...}
"""
from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query

from backend import play_history, smart_settings
from backend.admin_guard import admin
from backend.database import SessionLocal

router = APIRouter(tags=["Stats"])

Server = Optional[Literal["plex", "jellyfin", "emby"]]


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _history_note(db) -> dict:
    settings = smart_settings.get_all(db)
    return {"history_enabled": bool(settings.get("history_enabled", True)),
            "retention_days": int(settings.get("history_retention_days") or 90),
            "note": "Jellyfin and Emby plays are counted when the media server asks for intros; Plex plays when "
                    "Plex reports them playing (checked every 15 seconds, so very short intros can be missed)."}


@router.get("/api/stats/recent")
def stats_recent(limit: int = Query(50, ge=1, le=500), server: Server = None,
                 user: Optional[str] = Query(None, max_length=200), client: Optional[str] = Query(None, max_length=100),
                 days: Optional[int] = Query(None, ge=1, le=3650), db=Depends(get_db)):
    return {"items": play_history.recent(db, limit=limit, server=server, user=user, client=client, days=days),
            **_history_note(db)}


@router.get("/api/stats/top")
def stats_top(days: Optional[int] = Query(30, ge=1, le=3650), order: Literal["most", "least"] = "most",
              limit: int = Query(20, ge=1, le=200), server: Server = None,
              user: Optional[str] = Query(None, max_length=200), db=Depends(get_db)):
    return {"order": order, "days": days,
            "items": play_history.top(db, days=days, order=order, limit=limit, server=server, user=user)}


@router.get("/api/stats/never-played")
def stats_never_played(days: Optional[int] = Query(None, ge=1, le=3650), limit: int = Query(200, ge=1, le=1000),
                       db=Depends(get_db)):
    items = play_history.never_played(db, days=days, limit=limit)
    return {"days": days, "items": items,
            "note": "Intros with no play recorded" + (f" in the last {days} days." if days else " since history began.")}


@router.get("/api/stats/summary")
def stats_summary(days: Optional[int] = Query(30, ge=1, le=3650), db=Depends(get_db)):
    return {**play_history.summary(db, days=days), **_history_note(db)}


@router.delete("/api/stats", dependencies=[Depends(admin("clear the play history"))])
def stats_clear(db=Depends(get_db)):
    return {"removed": play_history.clear(db)}


@router.get("/api/health/intros")
def health_intros(days: int = Query(7, ge=1, le=90), db=Depends(get_db)):
    from backend.automation import watching_state
    from backend.routers import plugin_v2
    from backend.routers.capabilities import _configured_servers

    try:
        servers = _configured_servers()
    except Exception:
        servers = {}
    configured = {k: bool((v or {}).get("url")) for k, v in servers.items()}
    plugins_seen = {k: bool(plugin_v2.seen_plugins(k)) for k in ("jellyfin", "emby")}
    servers = None
    try:
        from backend.routers.capabilities import _instances, plugin_rows_for
        found = [i for i in _instances() if i["enabled"]]
        if found:
            counts = {k: sum(1 for i in found if i["type"] == k) for k in ("plex", "jellyfin", "emby")}
            servers = [{"name": i["name"], "type": i["type"],
                        "plugin_seen": bool(plugin_rows_for(i["type"], i["id"], i["identifier"],
                                                             counts[i["type"]] == 1))} for i in found]
    except Exception:
        servers = None
    return play_history.intro_health(db, days=days, configured=configured, plugins_seen=plugins_seen,
                                     watching=watching_state(), servers=servers)
