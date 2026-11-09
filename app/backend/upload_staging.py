"""Videos that turned out to be already in the library, waiting for a choice.

When an upload (or a video fetched from a web link) is the exact same file as
one in the library, it isn't added silently. It is parked here under a token,
and the page asks: Skip (the default) or Add anyway. "Add anyway" adds the
parked copy, so nothing is uploaded twice. Parked files are removed after
``KEEP_SECONDS`` whether anyone answers or not.

Each parked video is a folder ``<root>/<token>/`` with the file and a small
``staged.json`` (its name, what it was going to be added to, and the name of
the video it matches). Tokens are random, so they can't be guessed.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import shutil
import threading
import time
from typing import Optional

logger = logging.getLogger("prerollsmax.staging")

KEEP_SECONDS = 15 * 60
_META = "staged.json"
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
_lock = threading.Lock()


def _folder(root: str, token: str) -> Optional[str]:
    if not isinstance(token, str) or not _TOKEN.match(token):
        return None
    return os.path.join(root, token)


def stage(root: str, source, filename: str, *, meta: dict, existing_name: str, file_hash: str,
          move: bool = False) -> str:
    """Park a video and return its token.

    ``source`` is an open binary file (an upload, read from the start) or, with
    ``move=True``, the path of a finished download that is moved in.
    """
    sweep(root)
    token = secrets.token_urlsafe(18)
    folder = os.path.join(root, token)
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, os.path.basename(filename) or "video")
    try:
        if move:
            shutil.move(source, target)
        else:
            with open(target, "wb") as out:
                shutil.copyfileobj(source, out, 1024 * 1024)
        with open(os.path.join(folder, _META), "w", encoding="utf-8") as fh:
            json.dump({"filename": os.path.basename(target), "meta": meta, "existing_name": existing_name,
                       "file_hash": file_hash, "created": time.time()}, fh)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    # Removed on time even if nothing else happens in between.
    timer = threading.Timer(KEEP_SECONDS + 5, sweep, args=(root,))
    timer.daemon = True
    timer.start()
    return token


def get(root: str, token: str, *, now: Optional[float] = None) -> Optional[dict]:
    """The parked video for ``token`` ({path, filename, meta, existing_name,
    file_hash}), or None when it doesn't exist or has expired."""
    folder = _folder(root, token)
    if folder is None:
        return None
    try:
        with open(os.path.join(folder, _META), encoding="utf-8") as fh:
            info = json.load(fh)
    except (OSError, ValueError):
        return None
    if (now or time.time()) - float(info.get("created") or 0) > KEEP_SECONDS:
        discard(root, token)
        return None
    path = os.path.join(folder, os.path.basename(str(info.get("filename") or "")))
    if not os.path.isfile(path):
        return None
    return {"path": path, "filename": os.path.basename(path), "meta": info.get("meta") or {},
            "existing_name": info.get("existing_name") or "", "file_hash": info.get("file_hash") or ""}


def discard(root: str, token: str) -> bool:
    """Remove a parked video. True when there was one."""
    folder = _folder(root, token)
    if folder is None or not os.path.isdir(folder):
        return False
    with _lock:
        shutil.rmtree(folder, ignore_errors=True)
    return True


def sweep(root: str, *, now: Optional[float] = None) -> int:
    """Remove parked videos older than ``KEEP_SECONDS``. Returns how many."""
    if not os.path.isdir(root):
        return 0
    now = now or time.time()
    removed = 0
    for name in os.listdir(root):
        folder = os.path.join(root, name)
        if not os.path.isdir(folder):
            continue
        try:
            with open(os.path.join(folder, _META), encoding="utf-8") as fh:
                created = float(json.load(fh).get("created") or 0)
        except (OSError, ValueError):
            created = os.path.getmtime(folder)  # half-written: judge by the folder's age
        if now - created > KEEP_SECONDS:
            with _lock:
                shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    if removed:
        logger.info("Removed %d parked upload(s) nobody chose to add.", removed)
    return removed
