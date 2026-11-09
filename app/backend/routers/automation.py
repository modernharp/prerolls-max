"""Weights, cooldowns and watch folders.

    GET  /api/weights?collection_id=          -> {items: [{preroll_id, name, weight, last_played,
                                                   resting_until}], cooldown_hours, collection}
    PUT  /api/weights                         {items: [{preroll_id, weight 1-10}]} -> {updated}
    PUT  /api/collections/{id}/cooldown       {cooldown_hours 0-720} -> {collection_id, name, cooldown_hours}

    GET    /api/watch-folders                 -> [WatchFolder]
    POST   /api/watch-folders                 {path, collection_id?, mode: link|copy, recursive, enabled}
    PUT    /api/watch-folders/{id}            same body
    DELETE /api/watch-folders/{id}            -> {deleted: true}  (files are left alone)
    POST   /api/watch-folders/{id}/check      -> {imported, waiting, errors}

Adding, changing, removing and checking watch folders is for admins: a watch
folder reads whatever server folder it names.
"""
from __future__ import annotations

import datetime
import os
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field

from backend import models, play_history
from backend.admin_guard import admin
from backend.automation import AUTOMATION
from backend.database import SessionLocal
from backend.errors import AppError, bad_input, not_found
from backend.timeutil import utcnow
from backend.validation import FolderPath
from backend.watch_folders import WATCHER, inside

router = APIRouter(tags=["Automation"])

MAX_WATCH_FOLDERS = 20


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _label(p) -> str:
    return getattr(p, "display_name", None) or os.path.splitext(p.filename or "")[0] or f"Intro {p.id}"


# ---------------------------------------------------------------------------
# Weights and cooldowns
# ---------------------------------------------------------------------------

class WeightItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_id: int = Field(..., ge=1)
    weight: int = Field(..., ge=1, le=10)


class WeightsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    items: List[WeightItem] = Field(..., min_length=1, max_length=5000)


class CooldownIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    cooldown_hours: int = Field(..., ge=0, le=720)


@router.get("/api/weights")
def list_weights(collection_id: Optional[int] = Query(None, ge=1), db=Depends(get_db)):
    from backend.scheduler import prerolls_for_category_query
    collection = None
    if collection_id:
        collection = db.query(models.Category).filter(models.Category.id == collection_id).first()
        if collection is None:
            raise not_found("That collection")
        rows = prerolls_for_category_query(db, collection_id).order_by(models.Preroll.id).all()
    else:
        rows = db.query(models.Preroll).order_by(models.Preroll.id).all()
    hours = int(getattr(collection, "cooldown_hours", 0) or 0) if collection else 0
    last = play_history.last_played(db, [r.id for r in rows])
    items = []
    for r in rows:
        when = last.get(r.id)
        resting = when + datetime.timedelta(hours=hours) if (hours and when) else None
        if resting is not None and resting <= utcnow():
            resting = None
        items.append({"preroll_id": r.id, "name": _label(r), "weight": int(r.weight or 5),
                      "last_played": play_history.iso(when), "resting_until": play_history.iso(resting)})
    return {"items": items, "cooldown_hours": hours,
            "collection": {"id": collection.id, "name": collection.name} if collection else None,
            "note": "Weight 1 plays rarely, 10 often, 5 is normal. On Plex an intro with a higher weight is "
                    "listed more than once, so Plex's own random pick favours it."}


@router.put("/api/weights")
def put_weights(body: WeightsIn, db=Depends(get_db)):
    wanted = {i.preroll_id: i.weight for i in body.items}
    rows = db.query(models.Preroll).filter(models.Preroll.id.in_(list(wanted))).all()
    if len(rows) != len(wanted):
        raise bad_input("Some of those intro videos don't exist anymore.", field="items",
                        hint="Refresh the page and try again.")
    for row in rows:
        row.weight = wanted[row.id]
    db.commit()
    return {"updated": len(rows)}


@router.put("/api/collections/{collection_id}/cooldown")
def put_cooldown(collection_id: int, body: CooldownIn, db=Depends(get_db)):
    collection = db.query(models.Category).filter(models.Category.id == collection_id).first()
    if collection is None:
        raise not_found("That collection")
    collection.cooldown_hours = body.cooldown_hours
    db.commit()
    hours = f"{body.cooldown_hours} hour" + ("" if body.cooldown_hours == 1 else "s")
    text = (f"An intro from '{collection.name}' won't play again within {hours} while "
            "another one can." if body.cooldown_hours else f"Intros from '{collection.name}' can repeat any time.")
    return {"collection_id": collection.id, "name": collection.name, "cooldown_hours": body.cooldown_hours,
            "summary": text}


# ---------------------------------------------------------------------------
# Watch folders
# ---------------------------------------------------------------------------

class WatchFolderIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: FolderPath
    collection_id: Optional[int] = Field(None, ge=1)
    mode: Literal["link", "copy"] = "link"
    recursive: bool = True
    enabled: bool = True


def _library_dir() -> Optional[str]:
    deps = AUTOMATION.watch_deps
    try:
        return deps.library_dir() if deps else None
    except Exception:
        return None


def _present(db, folder) -> dict:
    collection = None
    if folder.collection_id:
        collection = db.query(models.Category).filter(models.Category.id == folder.collection_id).first()
    problem = folder.last_error
    if folder.collection_id and collection is None:
        problem = "Its collection was deleted; new files are added without a collection."
    return {"id": folder.id, "path": folder.path, "collection_id": folder.collection_id,
            "collection_name": collection.name if collection else None, "mode": folder.mode,
            "recursive": bool(folder.recursive), "enabled": bool(folder.enabled),
            "exists": os.path.isdir(folder.path), "imported_count": folder.imported_count or 0,
            "duplicate_count": folder.duplicate_count or 0,
            "last_checked_at": play_history.iso(folder.last_checked_at), "problem": problem,
            "waiting": WATCHER.waiting.get(folder.id, [])}


def _check_folder(db, body: WatchFolderIn, folder_id: Optional[int] = None) -> None:
    if not os.path.isdir(body.path):
        raise bad_input("That folder isn't there. If Prerolls Max runs in Docker, mount the folder into the "
                        "container and use the path inside it.", field="path")
    if not os.access(body.path, os.R_OK):
        raise bad_input("Prerolls Max isn't allowed to read that folder.", field="path",
                        hint="Check the folder's permissions.")
    library = _library_dir()
    if library and inside(body.path, library):
        raise bad_input("That folder is inside the Prerolls Max library, which is already checked for new files "
                        "on its own.", field="path", hint="Pick a folder outside the library.")
    if body.collection_id and db.query(models.Category).filter(models.Category.id == body.collection_id).first() is None:
        raise bad_input("That collection doesn't exist anymore.", field="collection_id")
    for other in db.query(models.WatchFolder).all():
        if other.id != folder_id and (inside(body.path, other.path) or inside(other.path, body.path)):
            raise AppError("That folder is already watched, or overlaps one that is.", status=409,
                           code="already_watched", fields={"path": f"Overlaps {other.path}."})


@router.get("/api/watch-folders")
def list_watch_folders(db=Depends(get_db)):
    return [_present(db, f) for f in db.query(models.WatchFolder).order_by(models.WatchFolder.id).all()]


@router.post("/api/watch-folders", dependencies=[Depends(admin("add watch folders"))])
def add_watch_folder(body: WatchFolderIn, db=Depends(get_db)):
    if db.query(models.WatchFolder).count() >= MAX_WATCH_FOLDERS:
        raise AppError(f"You can watch up to {MAX_WATCH_FOLDERS} folders.", status=409, code="too_many_folders")
    _check_folder(db, body)
    folder = models.WatchFolder(path=body.path, collection_id=body.collection_id, mode=body.mode,
                                recursive=body.recursive, enabled=body.enabled)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _present(db, folder)


def _folder(db, folder_id: int):
    folder = db.query(models.WatchFolder).filter(models.WatchFolder.id == folder_id).first()
    if folder is None:
        raise not_found("That watch folder")
    return folder


@router.put("/api/watch-folders/{folder_id}", dependencies=[Depends(admin("change watch folders"))])
def update_watch_folder(folder_id: int, body: WatchFolderIn, db=Depends(get_db)):
    folder = _folder(db, folder_id)
    _check_folder(db, body, folder_id)
    folder.path, folder.collection_id, folder.mode = body.path, body.collection_id, body.mode
    folder.recursive, folder.enabled = body.recursive, body.enabled
    db.commit()
    return _present(db, folder)


@router.delete("/api/watch-folders/{folder_id}", dependencies=[Depends(admin("remove watch folders"))])
def delete_watch_folder(folder_id: int, db=Depends(get_db)):
    folder = _folder(db, folder_id)
    db.delete(folder)
    db.commit()
    WATCHER.waiting.pop(folder_id, None)
    return {"deleted": True, "note": "The folder and the intros already added from it are left as they are."}


@router.post("/api/watch-folders/{folder_id}/check", dependencies=[Depends(admin("check watch folders"))])
def check_watch_folder(folder_id: int, db=Depends(get_db)):
    folder = _folder(db, folder_id)
    if AUTOMATION.watch_deps is None:
        raise AppError("Prerolls Max is still starting.", status=503, code="starting", hint="Try again in a moment.")
    result = WATCHER.scan(db, folder, AUTOMATION.watch_deps)
    result["note"] = ("New files are added once they have stopped changing for about 20 seconds; Prerolls Max "
                      "checks every 30 seconds.")
    return result
