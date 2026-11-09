"""What every community library provides, and the pieces they share.

A library (a "source") lists intro videos as Items (see docs/dev/CONTRACTS.md
section 5), finds them, and downloads one to a local file it has checked.
Putting the file in the user's library is not its job: see library.py.

Items are plain dicts in the contract's shape. Keys starting with "_" are for
the source's own use (search text, sort keys, download addresses) and are
removed before an item leaves the API (:func:`public`).
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional

from backend.errors import AppError

MAX_DOWNLOAD_BYTES = 1024 ** 3   # the largest file in either library is far below this
CHUNK = 64 * 1024

DURATIONS = ("lt10", "10-20", "20-30", "30plus")
SORTS = ("newest", "popular", "shortest", "az")
PLATFORMS = ("plex", "jellyfin", "emby")


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


# Temporary files are created owner-only; a saved video must be readable by
# the media server, which often runs as another user (Docker PUID/PGID).
FILE_MODE = 0o666 & ~_umask()


@dataclass
class DownloadedFile:
    path: str
    size: int
    md5: str
    sha256: str
    content_type: str
    extension: str


class CommunitySource:
    id = ""
    name = ""
    site_url = ""
    description = ""
    needs_acceptance = False

    # --- listing ---------------------------------------------------------
    def status(self) -> dict:
        """{item_count, downloadable_count, last_refreshed, error}"""
        raise NotImplementedError

    def terms(self, accepted: bool) -> dict:
        raise NotImplementedError

    def search(self, *, q: str = "", category: str = "", tag: str = "", duration: str = "",
               downloadable: Optional[bool] = None, sort: str = "", platform: str = "",
               prefer: Iterable[str] = (), include_ai: bool = False) -> List[dict]:
        """Every matching item, in order. The caller pages them."""
        raise NotImplementedError

    def categories(self, *, include_ai: bool = False) -> List[dict]:
        raise NotImplementedError

    def item(self, key: str) -> Optional[dict]:
        raise NotImplementedError

    def has_data(self) -> bool:
        raise NotImplementedError

    # --- work --------------------------------------------------------------
    def refresh(self, ctx=None, *, force: bool = False) -> dict:
        raise NotImplementedError

    def download(self, item: dict, folder: str) -> DownloadedFile:
        raise NotImplementedError

    def wait_turn(self) -> float:
        """Sleep until this library's next download may start."""
        return 0.0


def public(item: dict) -> dict:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def duration_matches(seconds: Optional[float], bucket: str) -> bool:
    if not bucket:
        return True
    if seconds is None:
        return False
    if bucket == "lt10":
        return seconds < 10
    if bucket == "10-20":
        return 10 <= seconds < 20
    if bucket == "20-30":
        return 20 <= seconds < 30
    if bucket == "30plus":
        return seconds >= 30
    return True


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-") or "other"


def words(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", str(text or "").lower())


_EXT_BY_TYPE = {"video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
                "video/x-matroska": ".mkv", "video/x-m4v": ".m4v", "video/x-msvideo": ".avi"}
VIDEO_EXTENSIONS = (".mp4", ".m4v", ".mkv", ".mov", ".webm", ".avi")


def save_stream(resp, folder: str, *, site: str, expected_size: Optional[int] = None,
                expected_md5: Optional[str] = None, name_hint: str = "",
                accept_types: Iterable[str] = ("video/",)) -> DownloadedFile:
    """Write a streamed response to a temporary file in ``folder`` and check it.

    The response must be 200 with a video content type (``accept_types`` are
    prefixes), the size must match ``expected_size`` when known, and the MD5
    must match ``expected_md5`` when known. On any problem the partial file is
    removed and an AppError says what happened in plain words.
    """
    status = getattr(resp, "status_code", 0)
    if status == 404:
        raise AppError(f"{site} doesn't have this video anymore.", status=404, code="community_item_gone",
                       hint="Refresh the list to see what's there now.")
    if status in (429, 503):
        raise AppError(f"{site} is busy right now.", status=503, code="community_busy",
                       hint="Wait a few minutes and try again.")
    if status != 200:
        raise AppError(f"{site} couldn't send this video.", status=502, code="community_download_failed",
                       hint="Try again later.")
    ctype = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    if not any(ctype.startswith(t) for t in accept_types):
        raise AppError(f"{site} sent something that isn't a video, so it wasn't saved.", status=502,
                       code="community_not_a_video", hint="Try again later.")
    announced = str(resp.headers.get("Content-Length") or "")
    if announced.isdigit():
        if int(announced) > MAX_DOWNLOAD_BYTES:
            raise AppError("This video is too big to download (over 1 GB).", status=413, code="too_large")
        if expected_size and int(announced) != int(expected_size):
            raise AppError(f"{site} sent a file of the wrong size, so it wasn't saved.", status=502,
                           code="community_size_mismatch", hint="Try again later.")

    os.makedirs(folder, exist_ok=True)
    ext = os.path.splitext(name_hint)[1].lower()
    if ext not in VIDEO_EXTENSIONS:
        ext = _EXT_BY_TYPE.get(ctype, ".mp4")
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix=".community-", suffix=".part", dir=folder)
    md5, sha = hashlib.md5(), hashlib.sha256()
    written = 0
    try:
        with os.fdopen(fd, "wb") as f:
            for chunk in resp.iter_content(chunk_size=CHUNK):
                if not chunk:
                    continue
                written += len(chunk)
                if written > MAX_DOWNLOAD_BYTES:
                    raise AppError("This video is too big to download (over 1 GB).", status=413, code="too_large")
                md5.update(chunk)
                sha.update(chunk)
                f.write(chunk)
        if expected_size and written != int(expected_size):
            raise AppError(f"The download from {site} stopped part way.", status=502,
                           code="community_incomplete", hint="Try again.")
        if written == 0:
            raise AppError(f"{site} sent an empty file.", status=502, code="community_empty", hint="Try again later.")
        if expected_md5 and md5.hexdigest() != expected_md5.lower():
            raise AppError(f"The file from {site} didn't pass its check, so it wasn't saved.", status=502,
                           code="community_checksum_mismatch", hint="Try again.")
        try:
            os.chmod(tmp, FILE_MODE)
        except OSError:
            pass
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    finally:
        try:
            resp.close()
        except Exception:
            pass
    return DownloadedFile(path=tmp, size=written, md5=md5.hexdigest(), sha256=sha.hexdigest(),
                          content_type=ctype, extension=ext)


def etag_md5(resp) -> Optional[str]:
    """The MD5 an object store puts in a single-part upload's ETag, if that's what it is."""
    tag = str(resp.headers.get("ETag") or "").strip().strip('"').lower()
    if tag.startswith("w/"):
        return None
    return tag if re.fullmatch(r"[0-9a-f]{32}", tag) else None
