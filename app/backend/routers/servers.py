"""Media servers: every Plex, Jellyfin and Emby server (media_servers.py).

    GET    /api/servers                 -> {servers: [Server]}
    POST   /api/servers                 {type, name?, url, token} -> Server
    GET    /api/servers/{id}            -> Server
    PUT    /api/servers/{id}            {name?, url?, token?, enabled?} -> Server
    DELETE /api/servers/{id}            -> {deleted: true, name}
    POST   /api/servers/{id}/test       -> {steps: [Step], server: Server}

The plugin, folder-mapping and "Play a test" routes are in server_tools.py.
Changing anything is admin only. Adding or changing an address or key first
checks that the server answers and takes the key.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from backend import coexist as _coexist, media_servers as ms, models, server_probe
from backend import validation as vld
from backend.admin_guard import admin
from backend.database import SessionLocal
from backend.errors import AppError, not_found, validation_summary

logger = logging.getLogger("prerollsmax.servers")
router = APIRouter(tags=["Media servers"])


@dataclass
class Deps:
    """What the plugin and folder routes need from main.py."""
    detect_plugin: dict
    configure_plugin: dict
    detect_mapping: Callable


deps: Optional[Deps] = None


def configure(d: Deps) -> None:
    global deps
    deps = d


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


ADMIN = [Depends(admin("change media servers"))]


# ---------------------------------------------------------------------------
# What the page sees
# ---------------------------------------------------------------------------

def server_out(db, row, status: Optional[dict] = None) -> dict:
    from backend.plex_fanout import FANOUT
    key = None
    if row.plugin_key_id:
        rec = db.query(models.APIKey).filter(models.APIKey.id == row.plugin_key_id).first()
        if rec is not None:
            key = {"id": rec.id, "name": rec.name, "active": bool(rec.is_active)}
    out = {
        "id": row.id, "type": row.type, "type_label": ms.LABELS[row.type], "name": ms.label(row),
        "url": row.url, "enabled": bool(row.enabled), "primary": bool(row.is_primary),
        "version": row.version, "has_key": bool(ms.get_secret(row)), "plugin_key": key,
        "created_at": row.created_at.isoformat() + "Z" if row.created_at else None,
        # Settings > Moving from NeXroll: "nexroll" when NeXroll keeps this server.
        "managed_by": "nexroll" if _coexist.nexroll_manages(row.id) else "prerollsmax",
    }
    if row.type == "plex":
        out["mappings"] = ms.mappings(row)
        out["last_apply"] = FANOUT.status(row.id)
    if status is not None:
        out["status"] = status
    return out


def _status(row) -> dict:
    if not row.enabled:
        return {"connected": False, "signed_in": False, "message": f"{ms.label(row)} is switched off.",
                "hint": "Switch it on to have Prerolls Max look after its intros again."}
    found = server_probe.check(ms.target(row))
    return {k: found.get(k) for k in ("reachable", "signed_in", "message", "hint", "version", "platform")} | {
        "connected": bool(found.get("signed_in")), "server_name": found.get("name")}


@router.get("/api/servers")
def list_servers(check: bool = False, db=Depends(get_db)):
    """``check=true`` asks each server whether it answers (a few seconds at most)."""
    ms.sync_from_settings(db)
    rows = ms.ordered(db)
    statuses = {}
    if check and rows:
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(8, len(rows))) as pool:
            statuses = dict(zip([r.id for r in rows], pool.map(_status, rows)))
    return {"servers": [server_out(db, r, statuses.get(r.id)) for r in rows]}


@router.get("/api/servers/{server_id}")
def get_server(server_id: int, check: bool = False, db=Depends(get_db)):
    row = _row(db, server_id)
    return server_out(db, row, _status(row) if check else None)


def _row(db, server_id: int):
    row = ms.find(db, server_id)
    if row is None:
        raise not_found("That media server")
    return row


# ---------------------------------------------------------------------------
# Adding and changing
# ---------------------------------------------------------------------------

class ServerIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type: Literal["plex", "jellyfin", "emby"]
    name: Optional[str] = Field(None, max_length=200)
    url: str = Field("", max_length=2100)
    token: str = Field("", max_length=600)


class ServerChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: Optional[str] = Field(None, max_length=200)
    url: Optional[str] = Field(None, max_length=2100)
    token: Optional[str] = Field(None, max_length=600)
    enabled: Optional[bool] = None


def _clean(kind: str, *, name=None, url=None, token=None) -> dict:
    """The cleaned fields, or a 422 naming each one to fix."""
    label = ms.LABELS[kind]
    fields, out = {}, {}
    if name is not None:
        try:
            out["name"] = vld.clean_name(name, what="server name", max_len=60)
        except ValueError as e:
            fields["name"] = str(e)
    if url is not None:
        try:
            out["url"] = vld.clean_server_url(url, service=label, default_port=ms.DEFAULT_PORT[kind])
        except ValueError as e:
            fields["url"] = str(e)
    if token is not None:
        try:
            out["token"] = (vld.clean_token(token, what="token") if kind == "plex"
                            else vld.clean_token(token, what="API key", min_len=16))
        except ValueError as e:
            fields["token"] = str(e)
    if fields:
        raise AppError(validation_summary(fields), status=422, code="invalid_input", fields=fields)
    return out


def _prove(kind: str, url: str, token: str, server_id: Optional[int] = None) -> dict:
    """Check the server answers and takes the key; 502 in plain words when not."""
    found = server_probe.check(ms.Target(id=server_id, type=kind, name=ms.LABELS[kind], url=url, token=token))
    if not found["reachable"]:
        raise AppError(found["message"], status=502, code=f"{kind}_unreachable", hint=found["hint"],
                       fields={"url": found["message"]})
    if not found["signed_in"]:
        raise AppError(found["message"], status=502, code=f"{kind}_auth_failed", hint=found["hint"],
                       fields={"token": found["message"]})
    return found


def _no_duplicate(db, kind: str, url: str, identifier: Optional[str], exclude_id: Optional[int] = None) -> None:
    for row in ms.ordered(db, kind):
        if row.id == exclude_id:
            continue
        same_url = ms.normalize_url(row.url) == ms.normalize_url(url)
        same_server = identifier and str(row.server_identifier or "").replace("-", "").lower() == \
            str(identifier).replace("-", "").lower()
        if same_url or same_server:
            message = f"This {ms.LABELS[kind]} is already on the list as \"{ms.label(row)}\"."
            raise AppError(message, status=409, code="server_already_added", fields={"url": message},
                           hint="Edit that one instead, or check the address.")


def _after_change(db, row, *, became_active: bool) -> None:
    """Hand a Plex that just joined (or came back) the current intro list."""
    if row.type != "plex" or not became_active:
        return
    server_id = row.id

    def run():
        from backend.plex_fanout import FANOUT
        from backend.scheduler import scheduler
        session = SessionLocal()
        try:
            again = ms.find(session, server_id)
            if again is not None and again.is_primary:
                scheduler._last_verification_time = None  # the first Plex: check its list now
                scheduler.trigger_immediate_check()
            else:
                FANOUT.seed_from_primary(scheduler, session)
                FANOUT.send_current(scheduler, session, server_id)
        except Exception as exc:
            logger.warning("Couldn't hand the intro list to the new Plex server: %s", exc)
        finally:
            session.close()

    threading.Thread(target=run, daemon=True, name="plex-new-server").start()


@router.post("/api/servers", dependencies=ADMIN)
def add_server(body: ServerIn, db=Depends(get_db)):
    ms.sync_from_settings(db)
    clean = _clean(body.type, name=body.name if body.name and body.name.strip() else None,
                   url=body.url, token=body.token)
    if clean.get("name"):
        ms.check_name(db, clean["name"])
    _no_duplicate(db, body.type, clean["url"], None)
    found = _prove(body.type, clean["url"], clean["token"])
    _no_duplicate(db, body.type, clean["url"], found.get("identifier"))
    row = models.MediaServer(type=body.type, name=clean.get("name") or ms.default_name(db, body.type),
                             url=clean["url"], enabled=True, server_identifier=found.get("identifier"),
                             version=found.get("version"))
    db.add(row)
    db.flush()
    if not ms.set_secret(row, clean["token"]):
        db.rollback()
        raise AppError("Prerolls Max couldn't save the key for this server.", status=500, code="token_not_saved",
                       hint="On Windows, check that Credential Manager is working; in Docker, that /data is writable.")
    ms.mirror(db)
    db.commit()
    logger.info("Added %s server %s", body.type, row.name)
    _after_change(db, row, became_active=True)
    return server_out(db, row, {"connected": True, "signed_in": True, "reachable": True, "message": None,
                                "hint": None, "version": found.get("version"), "server_name": found.get("name"),
                                "platform": found.get("platform")})


@router.put("/api/servers/{server_id}", dependencies=ADMIN)
def change_server(server_id: int, body: ServerChange, db=Depends(get_db)):
    ms.sync_from_settings(db)
    row = _row(db, server_id)
    clean = _clean(row.type, name=body.name, url=body.url, token=body.token)
    if "name" in clean:
        ms.check_name(db, clean["name"], exclude_id=row.id)
    url = clean.get("url", row.url)
    token = clean.get("token") or ms.get_secret(row)
    if "url" in clean or "token" in clean:
        _no_duplicate(db, row.type, url, None, exclude_id=row.id)
        found = _prove(row.type, url, token or "", row.id)
        _no_duplicate(db, row.type, url, found.get("identifier"), exclude_id=row.id)
        row.url, row.version = url, found.get("version") or row.version
        row.server_identifier = found.get("identifier") or row.server_identifier
        if "token" in clean and not ms.set_secret(row, clean["token"]):
            raise AppError("Prerolls Max couldn't save the new key.", status=500, code="token_not_saved")
    if "name" in clean:
        row.name = clean["name"]
    switched_on = body.enabled is True and not row.enabled
    if body.enabled is not None:
        row.enabled = body.enabled
    ms.mirror(db)
    db.commit()
    _after_change(db, row, became_active=switched_on or "url" in clean or "token" in clean)
    return server_out(db, row)


@router.delete("/api/servers/{server_id}", dependencies=ADMIN)
def delete_server(server_id: int, db=Depends(get_db)):
    from backend.plex_fanout import FANOUT
    ms.sync_from_settings(db)
    row = _row(db, server_id)
    name, key_id = ms.label(row), row.plugin_key_id
    ms.delete_secret(row)
    db.delete(row)
    db.flush()
    if key_id and not any(r.plugin_key_id == key_id for r in ms.ordered(db)):
        # The plugin's own key: nobody else uses it, so it stops working too.
        key = db.query(models.APIKey).filter(models.APIKey.id == key_id).first()
        if key is not None:
            key.is_active = False
    ms.mirror(db)
    db.commit()
    FANOUT.forget(server_id)
    logger.info("Removed media server %s", name)
    return {"deleted": True, "name": name}


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

def _step(sid: str, title: str, state: str, detail: Optional[str] = None, link: Optional[dict] = None) -> dict:
    return {"id": sid, "title": title, "state": state, "detail": detail, "link": link}


@router.post("/api/servers/{server_id}/test")
def test_server(server_id: int, db=Depends(get_db)):
    from backend.server_tools_checks import plex_files_step, plugin_steps
    row = _row(db, server_id)
    name = ms.label(row)
    target = ms.target(row)
    found = server_probe.check(target)
    steps = [_step("reach", f"Prerolls Max can reach {name}", "ok" if found["reachable"] else "fail",
                   None if found["reachable"] else f"{found['message']} {found['hint'] or ''}".strip())]
    if not found["reachable"]:
        steps.append(_step("key", f"Signed in to {name}", "skipped"))
    else:
        steps.append(_step("key", f"Signed in to {name}", "ok" if found["signed_in"] else "fail",
                           None if found["signed_in"] else f"{found['message']} {found['hint'] or ''}".strip()))
    ok = found["signed_in"]
    if ok:
        changed = False
        for attr, value in (("version", found.get("version")), ("server_identifier", found.get("identifier"))):
            if value and getattr(row, attr) != value:
                setattr(row, attr, value)
                changed = True
        if changed:
            db.commit()
    if row.type == "plex":
        steps.append(plex_files_step(db, row, target) if ok else _step("files", f"{name} can see your intro files",
                                                                       "skipped"))
    else:
        steps += plugin_steps(db, row, target, ok)
    if not row.enabled:
        steps.append(_step("enabled", f"{name} is switched on", "warn",
                           "It's switched off, so Prerolls Max leaves its intros alone. Switch it on to use it."))
    return {"steps": steps, "server": server_out(db, row)}


# ---------------------------------------------------------------------------
# Plugin requests (routers/plugin_v2.py)
# ---------------------------------------------------------------------------

def link_plugin_request(db, server_type: str, server_identifier: str, key_id: Optional[int],
                        address: str) -> Optional[dict]:
    row = ms.link_plugin(db, server_type, server_identifier, key_id, address)
    if row is None:
        return None
    return {"id": row.id, "name": ms.label(row), "enabled": bool(row.enabled),
            "nexroll_manages": _coexist.nexroll_manages(row.id)}
