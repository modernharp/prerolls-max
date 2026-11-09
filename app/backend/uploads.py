"""Saving uploaded files: streamed to disk, size-limited, type-checked.

Uploads used to be read whole into memory (``file.file.read()``), so a large
or endless upload could exhaust RAM on a small NAS before any limit applied,
and backdrop/font/logo uploads had no limit at all. These helpers copy in
chunks, stop at the limit, and only move the file into place once it is
complete, so a failed upload never leaves a half-written file behind.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from typing import Iterable, Optional

from backend.errors import AppError

CHUNK = 1024 * 1024

MB = 1024 * 1024
IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
FONT_EXTENSIONS = frozenset({".ttf", ".otf"})
AUDIO_EXTENSIONS = frozenset({".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".opus"})

# First bytes of each type, so a renamed file is caught before ffmpeg sees it.
_MAGIC = {
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".ttf": (b"\x00\x01\x00\x00", b"true", b"OTTO"),
    ".otf": (b"OTTO", b"\x00\x01\x00\x00"),
}


def human_size(limit: int) -> str:
    if limit >= 1024 * MB:
        return f"{limit / (1024 * MB):g} GB"
    return f"{limit // MB} MB"


def extension_of(filename: Optional[str], allowed: Iterable[str], *, what: str = "file") -> str:
    """The lower-case extension of ``filename`` if allowed, else a 422."""
    name = os.path.basename(str(filename or "").replace("\\", "/"))
    ext = os.path.splitext(name)[1].lower()
    allowed = sorted(set(allowed))
    if ext not in allowed:
        kind = f"{ext} files" if ext else "files without an extension"
        raise AppError(f"That {what} can't be used: Prerolls Max doesn't take {kind} here.", status=422,
                       code="wrong_file_type", hint="Use one of: " + ", ".join(allowed) + ".",
                       fields={"file": "Pick a " + "/".join(e.lstrip(".").upper() for e in allowed) + " file."})
    return ext


def _too_big(limit: int, what: str) -> AppError:
    return AppError(f"That {what} is too big. The limit is {human_size(limit)}.", status=413, code="too_large",
                    hint="Pick a smaller file, or make it smaller first.")


def _check_magic(head: bytes, ext: str, what: str) -> None:
    if ext == ".webp":
        ok = head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    else:
        signatures = _MAGIC.get(ext)
        if not signatures:
            return
        ok = any(head.startswith(sig) for sig in signatures)
    if not ok:
        raise AppError(f"That file doesn't look like a real {ext} {what}.", status=422, code="wrong_file_type",
                       hint="It may be damaged or renamed from another type. Save it again as the right type.")


def looks_like_video(head: bytes, ext: str) -> bool:
    """Whether the first bytes of a file match a video container for ``ext``.

    Only the container is checked, not every frame, so this is cheap. It
    catches the common mistakes: a photo, a document or a web page saved
    with a video extension.
    """
    ext = (ext or "").lower()
    if ext in (".mp4", ".m4v", ".mov"):
        # ISO media: a box size, then a box type such as ftyp, moov or mdat.
        return head[4:8] in (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")
    if ext in (".mkv", ".webm"):
        return head.startswith(b"\x1a\x45\xdf\xa3")
    if ext == ".avi":
        return head[:4] == b"RIFF" and head[8:12] == b"AVI "
    if ext == ".wmv":
        return head.startswith(b"\x30\x26\xb2\x75\x8e\x66\xcf\x11")
    if ext == ".flv":
        return head.startswith(b"FLV")
    if ext == ".ts":
        # MPEG transport stream: a 0x47 sync byte every 188 bytes (192 for M2TS).
        return (len(head) > 188 and head[0] == 0x47 and head[188] == 0x47) or \
               (len(head) > 196 and head[4] == 0x47 and head[196] == 0x47)
    if ext in (".mpg", ".mpeg"):
        return head.startswith(b"\x00\x00\x01\xba") or head.startswith(b"\x00\x00\x01\xb3")
    return True


def check_video_upload(upload, ext: str) -> None:
    """Refuse an upload whose content isn't a video, then rewind it."""
    head = upload.file.read(512)
    try:
        upload.file.seek(0)
    except Exception:
        pass
    if not head:
        raise AppError("That video is empty.", status=422, code="empty_file",
                       hint="Pick the file again; it may not have finished copying.",
                       fields={"file": "This file is empty."})
    if not looks_like_video(head, ext):
        raise AppError(f"That file isn't a video, even though its name ends in {ext}.", status=422,
                       code="not_a_video",
                       hint="It may be a picture or a document that was renamed. Pick the video file itself.",
                       fields={"file": "This file isn't a video."})


def save_upload(upload, dest_path: str, *, max_bytes: int, allowed: Optional[Iterable[str]] = None,
                what: str = "file", check_content: bool = True) -> dict:
    """Stream ``upload`` (a FastAPI UploadFile) to ``dest_path``.

    Returns ``{"size": bytes, "sha256": hex}``. Raises AppError for a wrong
    type (422) or a file over ``max_bytes`` (413); nothing is left on disk then.
    """
    ext = extension_of(upload.filename, allowed, what=what) if allowed is not None else \
        os.path.splitext(str(upload.filename or ""))[1].lower()
    folder = os.path.dirname(os.path.abspath(dest_path)) or "."
    os.makedirs(folder, exist_ok=True)
    digest = hashlib.sha256()
    size = 0
    fd, tmp = tempfile.mkstemp(prefix=".upload-", suffix=ext, dir=folder)
    try:
        with os.fdopen(fd, "wb") as out:
            first = True
            while True:
                chunk = upload.file.read(CHUNK)
                if not chunk:
                    break
                if first:
                    if check_content:
                        _check_magic(chunk[:16], ext, what)
                    first = False
                size += len(chunk)
                if size > max_bytes:
                    raise _too_big(max_bytes, what)
                digest.update(chunk)
                out.write(chunk)
        if size == 0:
            raise AppError(f"That {what} is empty.", status=422, code="empty_file",
                           hint="Pick the file again; it may not have finished copying.")
        os.replace(tmp, dest_path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise
    return {"size": size, "sha256": digest.hexdigest()}


def read_upload(upload, *, max_bytes: int, allowed: Optional[Iterable[str]] = None, what: str = "file",
                check_content: bool = True) -> bytes:
    """Read a small upload into memory, stopping at ``max_bytes``."""
    ext = extension_of(upload.filename, allowed, what=what) if allowed is not None else ""
    data = upload.file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise _too_big(max_bytes, what)
    if not data:
        raise AppError(f"That {what} is empty.", status=422, code="empty_file",
                       hint="Pick the file again; it may not have finished copying.")
    if check_content and ext:
        _check_magic(data[:16], ext, what)
    return data


def hash_upload(upload, *, max_bytes: int, what: str = "file") -> tuple[str, int]:
    """SHA-256 of an upload without holding it in memory. Rewinds the file."""
    digest = hashlib.sha256()
    size = 0
    while True:
        chunk = upload.file.read(CHUNK)
        if not chunk:
            break
        size += len(chunk)
        if size > max_bytes:
            raise _too_big(max_bytes, what)
        digest.update(chunk)
    try:
        upload.file.seek(0)
    except Exception:
        pass
    return digest.hexdigest(), size
