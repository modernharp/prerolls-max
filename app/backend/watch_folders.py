"""Watch folders: new intro videos dropped into a folder are added on their own.

Each watch folder has a target collection and a mode:

- ``link``: the file is used where it is (like Library > Add > Map a folder).
- ``copy``: the file is copied into the Prerolls Max library, in the
  collection's folder. The original stays where it was.

A file is only added once it has stopped changing: same size and modification
time for ``STABLE_SECONDS``, readable, and ffprobe can read its length. That
covers files still being copied over the network or downloaded (partial
download names like ``.part`` and ``.crdownload`` are never looked at). A file
that is added once is remembered, so removing it from the library later
doesn't bring it back.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Optional

from backend import models
from backend.preroll_files import validate_storage_component
from backend.scanner import SKIP_DIRS, VALID_VIDEO_EXTENSIONS
from backend.timeutil import utcnow

logger = logging.getLogger("prerollsmax.watch_folders")

STABLE_SECONDS = 20
GIVE_UP_AFTER = 5           # unreadable checks of a file that stopped changing
MAX_REMEMBERED = 20000
PARTIAL_MARKERS = (".part", ".partial", ".crdownload", ".download", ".tmp", ".!qb", ".!ut", ".filepart",
                   ".opdownload", ".partial-")


@dataclass
class Deps:
    library_dir: Callable[[], str]
    probe_seconds: Callable[[str], Optional[float]]
    make_thumbnail: Optional[Callable] = None


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def inside(path: str, folder: str) -> bool:
    a, b = _norm(path), _norm(folder)
    return a == b or a.startswith(b + os.sep)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _candidates(folder: str, recursive: bool, library: Optional[str]):
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS
                   and not (library and inside(os.path.join(root, d), library))]
        for name in files:
            lower = name.lower()
            if name.startswith(".") or any(m in lower for m in PARTIAL_MARKERS):
                continue
            if os.path.splitext(lower)[1] not in VALID_VIDEO_EXTENSIONS or lower.endswith(".d.ts"):
                continue
            yield os.path.join(root, name)
        if not recursive:
            break


class Watcher:
    """Remembers files between checks to tell "still copying" from "done"."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state: dict = {}
        self.waiting: dict = {}  # folder id -> [{"name", "seconds"}]

    def scan(self, db, folder, deps: Deps, *, now: Optional[float] = None,
             stable_seconds: float = STABLE_SECONDS) -> dict:
        """Check one watch folder once. Returns {imported, duplicates, waiting, errors}."""
        now = time.time() if now is None else now
        result = {"imported": [], "duplicates": [], "waiting": [], "errors": []}
        with self._lock:
            path = folder.path
            if not os.path.isdir(path):
                folder.last_error = ("The folder isn't there. If Prerolls Max runs in Docker, mount the folder "
                                     "into the container and use the path inside it.")
                folder.last_checked_at = utcnow()
                db.commit()
                result["errors"].append(folder.last_error)
                return result
            library = deps.library_dir()
            try:
                remembered = set(json.loads(folder.imported_keys or "[]"))
            except ValueError:
                remembered = set()
            known_paths = {_norm(p) for (p,) in db.query(models.Preroll.path).filter(models.Preroll.path.isnot(None))}
            ignored = {k for (k,) in db.query(models.IgnoredPath.path_key).all()}
            collection = None
            if folder.collection_id:
                collection = db.query(models.Category).filter(models.Category.id == folder.collection_id).first()
            try:
                files = list(_candidates(path, bool(folder.recursive), library))
            except OSError:
                files = []
                result["errors"].append("Prerolls Max can't read that folder. Check its permissions.")
            for file_path in files:
                try:
                    stat = os.stat(file_path)
                except OSError:
                    continue
                signature = f"{file_path}|{stat.st_size}|{int(stat.st_mtime)}"
                if signature in remembered:
                    continue
                if folder.mode != "copy" and (_norm(file_path) in known_paths or _norm(file_path) in ignored):
                    remembered.add(signature)
                    continue
                state = self._state.get(file_path)
                sig = (stat.st_size, stat.st_mtime)
                if state is None or state["sig"] != sig:
                    self._state[file_path] = {"sig": sig, "since": now, "fails": 0}
                    result["waiting"].append({"name": os.path.basename(file_path), "seconds": 0,
                                              "why": "Waiting until it stops changing"})
                    continue
                steady = now - state["since"]
                if steady < stable_seconds or stat.st_size == 0:
                    result["waiting"].append({"name": os.path.basename(file_path), "seconds": int(steady),
                                              "why": "Waiting until it stops changing"})
                    continue
                try:
                    with open(file_path, "rb") as handle:
                        handle.read(1)
                    seconds = deps.probe_seconds(file_path)
                except OSError:
                    seconds = None
                if not seconds:
                    state["fails"] += 1
                    if state["fails"] >= GIVE_UP_AFTER:
                        result["errors"].append(f"'{os.path.basename(file_path)}' can't be read as a video. "
                                                "It may be damaged; it was left alone.")
                        remembered.add(signature)
                        self._state.pop(file_path, None)
                    else:
                        result["waiting"].append({"name": os.path.basename(file_path), "seconds": int(steady),
                                                  "why": "Waiting until it can be read"})
                    continue
                try:
                    row = self._import(db, folder, collection, file_path, seconds, deps)
                except OSError as exc:
                    logger.warning("Watch folder import of %s failed: %s", file_path, exc)
                    result["errors"].append(f"Couldn't add '{os.path.basename(file_path)}': Prerolls Max couldn't "
                                            "copy or read it.")
                    continue
                remembered.add(signature)
                self._state.pop(file_path, None)
                if isinstance(row, Duplicate):
                    result["duplicates"].append({"name": os.path.basename(file_path), "existing": row.name})
                elif row is not None:
                    result["imported"].append({"preroll_id": row.id, "name": os.path.basename(file_path)})
            folder.imported_keys = json.dumps(sorted(remembered)[-MAX_REMEMBERED:])
            folder.imported_count = (folder.imported_count or 0) + len(result["imported"])
            folder.duplicate_count = (folder.duplicate_count or 0) + len(result["duplicates"])
            folder.last_checked_at = utcnow()
            folder.last_error = result["errors"][-1] if result["errors"] else None
            db.commit()
            self.waiting[folder.id] = result["waiting"]
            for gone in [p for p in self._state if not os.path.exists(p)]:
                self._state.pop(gone, None)
        return result

    def _import(self, db, folder, collection, source: str, seconds: float, deps: Deps):
        size = os.path.getsize(source)
        description = f"Added from the watch folder {folder.path}."
        # The exact same video is already in the library (by content, not name):
        # left out, and counted on the folder's card.
        digest = _sha256(source)
        same = db.query(models.Preroll).filter(models.Preroll.file_hash == digest).first()
        if same is not None:
            logger.info("Watch folder: %s is already in the library as %s; left out.", source, _label(same))
            return Duplicate(_label(same))
        if folder.mode == "copy":
            library = deps.library_dir()
            sub = "Imported"
            if collection is not None:
                try:
                    sub = validate_storage_component(collection.name)
                except Exception:
                    sub = "Imported"
            target_dir = os.path.join(library, sub)
            os.makedirs(target_dir, exist_ok=True)
            name = os.path.basename(source)
            stem, ext = os.path.splitext(name)
            staged = os.path.join(target_dir, f".{stem}.partial-{uuid.uuid4().hex[:6]}{ext}")
            try:
                shutil.copy2(source, staged)
                final = os.path.join(target_dir, name)
                counter = 2
                while os.path.exists(final):
                    final = os.path.join(target_dir, f"{stem} ({counter}){ext}")
                    counter += 1
                os.replace(staged, final)
            finally:
                if os.path.exists(staged):
                    os.remove(staged)
            row = models.Preroll(filename=os.path.basename(final), path=final, managed=True, file_hash=digest,
                                 duration=seconds, file_size=size, description=description, enabled=True)
        else:
            row = models.Preroll(filename=os.path.basename(source), path=os.path.abspath(source), managed=False,
                                 duration=seconds, file_size=size, description=description, enabled=True,
                                 file_hash=digest)
        if collection is not None:
            row.categories = [collection]
            row.category_id = collection.id
        db.add(row)
        db.commit()
        db.refresh(row)
        if deps.make_thumbnail:
            try:
                thumb = deps.make_thumbnail(row, row.path, collection.name if collection is not None else None)
                if thumb:
                    row.thumbnail = thumb
                    db.commit()
            except Exception as exc:
                logger.info("No thumbnail for %s: %s", row.path, exc)
        logger.info("Watch folder: added %s", row.path)
        return row


class Duplicate:
    """What ``_import`` gives back for a file that's already in the library."""

    def __init__(self, name: str):
        self.name = name


def _label(preroll) -> str:
    return preroll.display_name or os.path.splitext(preroll.filename or "")[0] or "an intro video"


WATCHER = Watcher()
