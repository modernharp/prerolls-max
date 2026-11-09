"""Settings > Moving from NeXroll.

    GET  /api/migrate/nexroll                 -> what's found here, the last import, port and who manages what
    POST /api/migrate/nexroll/scan            {path?}            -> {job_id}   a nexroll.db on this computer
    POST /api/migrate/nexroll/upload          (file .json|.zip)  -> {job_id}   a NeXroll backup file
    POST /api/migrate/nexroll/fetch           {url, api_key?}    -> {job_id}   a NeXroll that's running
         Each job's result: {source_id, preview} (nexroll_import.preview).
    POST /api/migrate/nexroll/import          {source_id, mode: replace|merge, include_keys, confirm_replace}
                                              -> {job_id}; result: the import report
    POST /api/migrate/nexroll/relink          {from_folder, to_folder} -> {relinked, still_missing, message}
    GET  /api/migrate/nexroll/detect?refresh= -> {alongside, summary, servers, warnings}
    POST /api/migrate/nexroll/detect/dismiss  {id}
    PUT  /api/migrate/nexroll/alongside       {mode?, nexroll_servers?, port?} -> as GET's "alongside"
    PUT  /api/servers/{id}/manager            {manager: prerollsmax|nexroll} -> {id, managed_by, alongside}

Everything that reads folders, fetches from another address or changes the
library is admin only. The detection banner (``detect``) is open to everyone
signed in, like the rest of Home.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from backend import coexist, jobs, media_servers, nexroll_detect, nexroll_import, nexroll_source, port_config
from backend.admin_guard import admin
from backend.database import SessionLocal
from backend.errors import AppError, bad_input, conflict, not_found

logger = logging.getLogger("prerollsmax.nexroll")
router = APIRouter(tags=["Moving from NeXroll"])

ADMIN = [Depends(admin("import from NeXroll"))]
SOURCE_KEEP_SECONDS = 3600
MAX_UPLOAD_BYTES = 50 * 1024 ** 3   # a full backup carries every video

_sources: dict = {}
_sources_lock = threading.Lock()


def _staging_root() -> str:
    # Next to the database, never inside the intro folder (the library scan
    # would pick the extracted videos up). The dot keeps scans out regardless.
    return os.path.join(os.path.dirname(_db_path()), ".nexroll-import")


def _prune_sources() -> None:
    now = time.time()
    with _sources_lock:
        old = [k for k, v in _sources.items() if now - v["at"] > SOURCE_KEEP_SECONDS]
        for key in old:
            entry = _sources.pop(key)
            if entry.get("staging"):
                shutil.rmtree(entry["staging"], ignore_errors=True)


def _keep_source(data: dict, staging: Optional[str]) -> str:
    _prune_sources()
    source_id = uuid.uuid4().hex[:16]
    with _sources_lock:
        _sources[source_id] = {"data": data, "staging": staging, "at": time.time()}
    return source_id


def _source(source_id: str) -> dict:
    with _sources_lock:
        entry = _sources.get(source_id)
    if entry is None:
        raise AppError("That NeXroll data isn't loaded anymore.", status=410, code="source_expired",
                       hint="It's kept for an hour. Load it again with one of the three ways above.")
    return entry


def _preview_job(load, staging: Optional[str] = None):
    def run(ctx: jobs.JobContext):
        ctx.report(progress=10, message="Reading NeXroll's data")
        try:
            data = load()
        except Exception:
            if staging:
                shutil.rmtree(staging, ignore_errors=True)
            raise
        ctx.report(progress=70, message="Checking which video files Prerolls Max can see")
        db = SessionLocal()
        try:
            preview = nexroll_import.preview(db, data)
        finally:
            db.close()
        return {"source_id": _keep_source(data, staging), "preview": preview}
    return run


def _in_docker() -> bool:
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "r", encoding="utf-8") as fh:
            return "docker" in fh.read()
    except OSError:
        return False


def _running_port(request: Request) -> int:
    server = request.scope.get("server") if request is not None else None
    try:
        return int(server[1])
    except (TypeError, ValueError, IndexError):
        return port_config.configured_port()[0]


def _alongside_state(db, request: Request) -> dict:
    split = coexist.split(db)
    running = _running_port(request)
    configured, source = port_config.configured_port()
    saved = port_config.saved_port()
    docker = _in_docker()
    conflicts = []
    if split["mode"] == "alongside":
        if running == port_config.NEXROLL_PORT and not docker:
            conflicts.append("Prerolls Max uses port 9393, NeXroll's port. Pick another port below.")
        if split["servers"] and all(s["manager"] == "prerollsmax" for s in split["servers"]):
            conflicts.append("Prerolls Max manages every server, so NeXroll has nothing to do. Stop NeXroll, "
                             "or hand it the servers it should keep.")
    return {
        "mode": split["mode"],
        "servers": split["servers"],
        "summary": split["summary"],
        "conflicts": conflicts,
        "port": {
            "running": running,
            "configured": configured,
            "source": source,
            "saved": saved,
            "in_docker": docker,
            "restart_needed": bool(source == "settings" and configured != running),
        },
    }


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

@router.get("/api/migrate/nexroll", dependencies=ADMIN)
def status(request: Request):
    deps = nexroll_import._need()
    db = SessionLocal()
    try:
        found = nexroll_source.find_databases(own_dir=os.path.dirname(_db_path()))
        return {
            "found": [{"path": f["path"], "folder": f["folder"],
                       "modified": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(f["modified"]))} for f in found],
            "platform": "windows" if os.name == "nt" else "docker" if _in_docker() else "other",
            "library_dir": deps.library_dir(),
            "import": nexroll_import.status(db),
            "alongside": _alongside_state(db, request),
        }
    finally:
        db.close()


def _db_path() -> str:
    from backend.database import DB_PATH
    return DB_PATH


# ---------------------------------------------------------------------------
# The three ways in
# ---------------------------------------------------------------------------

class ScanIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    path: Optional[str] = Field(default=None, max_length=4096)


@router.post("/api/migrate/nexroll/scan", dependencies=ADMIN)
def scan(body: ScanIn):
    if body.path and body.path.strip():
        path = nexroll_source.database_in(body.path)
    else:
        found = nexroll_source.find_databases(own_dir=os.path.dirname(_db_path()))
        if not found:
            raise AppError("Prerolls Max didn't find NeXroll's data on this computer.", status=404,
                           code="nexroll_not_found",
                           hint="Enter the folder NeXroll kept its data in (the one with nexroll.db), or use "
                                "one of the other two ways.")
        path = found[0]["path"]
    job = jobs.runner.submit("nexroll_scan", _preview_job(lambda: nexroll_source.backup_from_db(path)),
                             message="Reading NeXroll's database")
    return {"job_id": job.id, "path": path}


@router.post("/api/migrate/nexroll/upload", dependencies=ADMIN)
def upload(file: UploadFile = File(...)):
    name = os.path.basename(file.filename or "")
    if not name.lower().endswith((".json", ".zip")):
        raise bad_input("Pick the .json or .zip file NeXroll's Settings > Backup & Restore made.", field="file")
    root = _staging_root()
    os.makedirs(root, exist_ok=True)
    staging = tempfile.mkdtemp(prefix="upload-", dir=root)
    target = os.path.join(staging, "backup" + os.path.splitext(name)[1].lower())
    size = 0
    try:
        with open(target, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise AppError("That file is bigger than any NeXroll backup should be.", status=413,
                                   code="file_too_large")
                out.write(chunk)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if size == 0:
        shutil.rmtree(staging, ignore_errors=True)
        raise bad_input("That file is empty.", field="file")

    def load():
        try:
            return nexroll_source.backup_from_upload(target, name, staging)
        finally:
            try:
                os.unlink(target)
            except OSError:
                pass
    job = jobs.runner.submit("nexroll_upload", _preview_job(load, staging), message="Reading the backup")
    return {"job_id": job.id}


class FetchIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str = Field(max_length=2048)
    api_key: Optional[str] = Field(default=None, max_length=512)


@router.post("/api/migrate/nexroll/fetch", dependencies=ADMIN)
def fetch(body: FetchIn):
    # Check the address and the key now, so a problem shows next to its field
    # rather than as a failed job. The job then downloads the backup.
    nexroll_source.check_running(body.url, body.api_key)
    job = jobs.runner.submit("nexroll_fetch",
                             _preview_job(lambda: nexroll_source.fetch_backup(body.url, body.api_key)),
                             message="Asking NeXroll for a backup")
    return {"job_id": job.id}


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    source_id: str = Field(min_length=1, max_length=64)
    mode: Literal["replace", "merge"]
    include_keys: bool = True
    confirm_replace: bool = False


@router.post("/api/migrate/nexroll/import", dependencies=ADMIN)
def run_import(body: ImportIn):
    entry = _source(body.source_id)
    if body.mode == "replace" and not body.confirm_replace:
        raise AppError("Replacing removes the collections, videos and schedules you have now.", status=409,
                       code="confirm_replace", hint="Confirm that you want to replace them, or pick Merge.")

    def run(ctx: jobs.JobContext):
        report = nexroll_import.run_import(
            entry["data"], mode=body.mode, include_keys=body.include_keys,
            progress=lambda pct, msg: ctx.report(progress=pct, message=msg))
        with _sources_lock:
            gone = _sources.pop(body.source_id, None)
        if gone and gone.get("staging"):
            shutil.rmtree(gone["staging"], ignore_errors=True)
        return report
    job = jobs.runner.submit("nexroll_import", run, message="Bringing your NeXroll setup over",
                             key="nexroll_import")
    return {"job_id": job.id}


class RelinkIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_folder: str = Field(max_length=4096)
    to_folder: str = Field(max_length=4096)


@router.post("/api/migrate/nexroll/relink", dependencies=ADMIN)
def relink(body: RelinkIn):
    db = SessionLocal()
    try:
        return nexroll_import.relink(db, body.from_folder, body.to_folder)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Is NeXroll still running?
# ---------------------------------------------------------------------------

@router.get("/api/migrate/nexroll/detect")
def detect(request: Request, refresh: bool = False):
    db = SessionLocal()
    try:
        return nexroll_detect.report(db, _running_port(request), force=refresh)
    finally:
        db.close()


class DismissIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(min_length=1, max_length=100)


@router.post("/api/migrate/nexroll/detect/dismiss")
def dismiss(body: DismissIn):
    nexroll_detect.dismiss(body.id)
    return {"dismissed": True}


# ---------------------------------------------------------------------------
# Keep NeXroll running too
# ---------------------------------------------------------------------------

class AlongsideIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Optional[Literal["replace", "alongside"]] = None
    nexroll_servers: Optional[List[int]] = Field(default=None, max_length=100)
    port: Optional[int] = None
    clear_port: bool = False


@router.put("/api/migrate/nexroll/alongside", dependencies=ADMIN)
def save_alongside(body: AlongsideIn, request: Request):
    db = SessionLocal()
    try:
        mode = body.mode or coexist.load()["mode"]
        if body.nexroll_servers is not None:
            known = {r.id for r in media_servers.ordered(db)}
            unknown = [i for i in body.nexroll_servers if i not in known]
            if unknown:
                raise not_found("That media server")
        if body.port is not None or body.clear_port:
            _save_port(body.port if not body.clear_port else None, mode, request)
        coexist.save(mode=body.mode, nexroll_servers=body.nexroll_servers)
        return _alongside_state(db, request)
    finally:
        db.close()


def _save_port(port: Optional[int], mode: str, request: Request) -> None:
    if port_config.env_port() is not None:
        raise conflict("The port is set by PMAX_PORT, so it can't be changed here.", field="port",
                       code="port_from_environment",
                       hint="In Docker, change the port mapping instead (for example 9494:9393). Elsewhere, "
                            "change or remove PMAX_PORT where Prerolls Max is started.")
    if port is None:
        port_config.save_port(None)
        return
    if not (port_config.MIN_PORT <= port <= port_config.MAX_PORT):
        raise bad_input("Pick a port between 1024 and 65535.", field="port")
    if port == port_config.NEXROLL_PORT and mode == "alongside":
        raise bad_input("9393 is NeXroll's port. Pick another one, like 9494.", field="port")
    if port != _running_port(request) and not port_config.port_free(port):
        who = port_config.identify(port)
        raise bad_input(f"Port {port} is already in use" + (" by NeXroll." if who == "nexroll" else "."),
                        field="port", hint="Pick another port, like 9494.")
    port_config.save_port(port)


class ManagerIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    manager: Literal["prerollsmax", "nexroll"]


@router.put("/api/servers/{server_id}/manager", dependencies=[Depends(admin("change media servers"))])
def set_manager(server_id: int, body: ManagerIn):
    db = SessionLocal()
    try:
        row = media_servers.find(db, server_id)
        if row is None:
            raise not_found("That media server")
        data = coexist.load()
        ids = set(data["nexroll_servers"])
        if body.manager == "nexroll":
            ids.add(row.id)
        else:
            ids.discard(row.id)
        mode = "alongside" if body.manager == "nexroll" else data["mode"]
        coexist.save(mode=mode, nexroll_servers=sorted(ids))
        return {"id": row.id, "name": media_servers.label(row),
                "managed_by": "nexroll" if coexist.nexroll_manages(row.id) else "prerollsmax",
                "alongside": mode == "alongside"}
    finally:
        db.close()
