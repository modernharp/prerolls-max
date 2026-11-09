"""Per-server tools on the Media Servers page.

    GET  /api/servers/{id}/plugin                  -> as GET /jellyfin/plugin/detect, for this server
    POST /api/servers/{id}/plugin                  {nexroll_url} -> as POST /<type>/plugin/configure
    GET  /api/servers/{id}/folder-mapping          -> {mappings, primary}
    PUT  /api/servers/{id}/folder-mapping          {mappings: [{local, plex}]} -> {mappings}
    POST /api/servers/{id}/folder-mapping/detect   -> as POST /settings/path-mappings/detect
    GET  /api/servers/{id}/movies?q=               -> {items: [{id, title, year}]}
    POST /api/servers/{id}/play-test               {item_id} -> what the server would play first

The plugin and folder search reuse the routes in main.py, run for this server
(media_servers.acting_on). Folder mappings are Plex only: every Plex server
sees the intro files under its own paths.
"""
from __future__ import annotations

import json
import logging
import threading

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend import media_servers as ms
from backend import server_play_test, server_probe
from backend import validation as vld
from backend.database import SessionLocal
from backend.errors import AppError, bad_input, validation_summary
from backend.routers import servers as servers_router
from backend.routers.servers import ADMIN, _row, get_db

logger = logging.getLogger("prerollsmax.servers")
router = APIRouter(tags=["Media servers"])


def _plugin_row(db, server_id: int):
    row = _row(db, server_id)
    if row.type == "plex":
        raise AppError("Plex doesn't use the Prerolls Max plugin.", status=409, code="no_plugin_for_plex",
                       hint="Plex plays the intro list Prerolls Max writes into its settings.")
    if servers_router.deps is None:
        raise AppError("Prerolls Max is still starting.", status=503, code="starting", hint="Try again in a moment.")
    return row


@router.get("/api/servers/{server_id}/plugin")
def detect_plugin(server_id: int, request: Request, db=Depends(get_db)):
    row = _plugin_row(db, server_id)
    with ms.acting_on(ms.target(row)):
        return servers_router.deps.detect_plugin[row.type](request, db)


class PluginSetupIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    nexroll_url: str = Field("", max_length=2100)


@router.post("/api/servers/{server_id}/plugin", dependencies=ADMIN)
def setup_plugin(server_id: int, body: PluginSetupIn, db=Depends(get_db)):
    row = _plugin_row(db, server_id)
    try:
        url = vld.clean_server_url(body.nexroll_url, service="Prerolls Max")
    except ValueError as e:
        raise bad_input(str(e), field="nexroll_url")
    with ms.acting_on(ms.target(row)):
        return servers_router.deps.configure_plugin[row.type](url, db)


# ---------------------------------------------------------------------------
# Folder mapping (Plex)
# ---------------------------------------------------------------------------

def _plex_row(db, server_id: int):
    row = _row(db, server_id)
    if row.type != "plex":
        raise AppError(f"{ms.LABELS[row.type]} doesn't need a folder mapping.", status=409, code="plex_only",
                       hint="Its plugin downloads the intros from Prerolls Max, so file paths don't matter.")
    return row


@router.get("/api/servers/{server_id}/folder-mapping")
def get_mapping(server_id: int, db=Depends(get_db)):
    ms.sync_from_settings(db)
    row = _plex_row(db, server_id)
    return {"server": {"id": row.id, "name": ms.label(row)}, "primary": bool(row.is_primary),
            "mappings": ms.mappings(row)}


class MappingIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    local: str = Field("", max_length=4096)
    plex: str = Field("", max_length=4096)


class MappingsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    mappings: list[MappingIn] = Field(default_factory=list, max_length=50)


@router.put("/api/servers/{server_id}/folder-mapping", dependencies=ADMIN)
def put_mapping(server_id: int, body: MappingsIn, db=Depends(get_db)):
    ms.sync_from_settings(db)
    row = _plex_row(db, server_id)
    fields, out = {}, []
    for i, m in enumerate(body.mappings):
        try:
            local = vld.clean_folder_path(m.local, what="Prerolls Max folder")
        except ValueError as e:
            fields[f"mappings.{i}.local"] = str(e)
            local = None
        try:
            plex = vld.clean_folder_path(m.plex, what="media server folder")
        except ValueError as e:
            fields[f"mappings.{i}.plex"] = str(e)
            plex = None
        if local and plex:
            out.append({"local": local, "plex": plex})
    if fields:
        raise AppError(validation_summary(fields), status=422, code="invalid_input", fields=fields)
    row.path_mappings = json.dumps(out)
    ms.mirror(db)
    db.commit()
    _refresh_plex(row.id)
    return {"server": {"id": row.id, "name": ms.label(row)}, "primary": bool(row.is_primary), "mappings": out}


def _refresh_plex(server_id: int) -> None:
    """Send this server its list again with the new paths."""
    def run():
        from backend.plex_fanout import FANOUT
        from backend.scheduler import scheduler
        db = SessionLocal()
        try:
            row = ms.find(db, server_id)
            if row is None or not row.enabled:
                return
            if row.is_primary:
                scheduler._last_verification_time = None
                scheduler.trigger_immediate_check()
            else:
                FANOUT.seed_from_primary(scheduler, db)
                FANOUT.send_current(scheduler, db, server_id)
        except Exception as exc:
            logger.warning("Couldn't resend the intro list after a mapping change: %s", exc)
        finally:
            db.close()

    threading.Thread(target=run, daemon=True, name="plex-mapping").start()


@router.post("/api/servers/{server_id}/folder-mapping/detect")
def detect_mapping(server_id: int, db=Depends(get_db)):
    row = _plex_row(db, server_id)
    if servers_router.deps is None:
        raise AppError("Prerolls Max is still starting.", status=503, code="starting", hint="Try again in a moment.")
    with ms.acting_on(ms.target(row)):
        return servers_router.deps.detect_mapping(db)


# ---------------------------------------------------------------------------
# Play a test
# ---------------------------------------------------------------------------

@router.get("/api/servers/{server_id}/movies")
def list_movies(server_id: int, q: str = Query("", max_length=200), db=Depends(get_db)):
    row = _row(db, server_id)
    try:
        items = server_probe.movies(ms.target(row), q)
    except Exception as exc:
        logger.info("Listing movies on %s failed: %s", ms.label(row), exc)
        raise AppError(f"{ms.label(row)} didn't list its movies.", status=502, code="movies_unavailable",
                       hint="Check that the server is running (Test connection), then try again.")
    return {"items": items}


class PlayTestIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    item_id: str = Field(..., min_length=1, max_length=100, pattern=r"^[A-Za-z0-9-]+$")


@router.post("/api/servers/{server_id}/play-test")
def play_test(server_id: int, body: PlayTestIn, db=Depends(get_db)):
    row = _row(db, server_id)
    return server_play_test.run(db, row, body.item_id)
