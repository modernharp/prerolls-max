"""Adding videos besides a plain upload: duplicates and web links.

    POST /prerolls/upload/staged/{token}   {action: "add" | "skip"}
         A video that matched one already in the library was parked (see
         upload_staging.py); "add" adds that copy, "skip" drops it.
    POST /api/library/from-link            {url, collection_id?}  -> {job_id}
         Download a video file from a web link as a background job
         (GET /api/jobs/{id}). Its result is what an upload answers: the new
         video, or {duplicate: true, token, existing: {name}} to ask about.

Every video still goes through the upload's own checks and steps (main.py
``upload_preroll``), handed in as ``Deps.add_file``.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Callable, Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend import jobs, link_fetch, models, smart_settings, upload_staging
from backend.errors import AppError, not_found

logger = logging.getLogger("prerollsmax.library_add")
router = APIRouter(tags=["Library"])


@dataclass
class Deps:
    staging_root: Callable[[], str]
    add_file: Callable[..., dict]          # (db, path, filename, *, meta, if_duplicate) -> upload answer
    session: Callable[[], object]
    ffprobe: Callable[[], str]
    max_bytes: int
    file_log: Callable[..., None] = lambda message, level="INFO": None


_deps: Optional[Deps] = None


def configure(deps: Deps) -> None:
    global _deps
    _deps = deps


def _need() -> Deps:
    if _deps is None:
        raise RuntimeError("library_add is not configured")
    return _deps


def video_label(preroll) -> str:
    """The name people know a video by."""
    return (getattr(preroll, "display_name", None) or os.path.splitext(preroll.filename or "")[0]
            or "an intro video")


# --- duplicates ---------------------------------------------------------------

def park_duplicate(fileobj, filename: str, existing, file_hash: str, *, meta: dict,
                   move_from: Optional[str] = None) -> dict:
    """Park an exact copy of ``existing`` and return the answer the page shows."""
    deps = _need()
    label = video_label(existing)
    source = move_from if move_from is not None else fileobj
    token = upload_staging.stage(deps.staging_root(), source, filename, meta=meta, existing_name=label,
                                 file_hash=file_hash, move=move_from is not None)
    return {
        "uploaded": False, "duplicate": True, "token": token,
        "filename": filename,
        "existing": {"id": existing.id, "name": label},
        "message": f'Already in your library as "{label}".',
        "keep_minutes": upload_staging.KEEP_SECONDS // 60,
    }


class StagedChoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    action: Literal["add", "skip"]


@router.post("/prerolls/upload/staged/{token}")
def resolve_staged(token: str, choice: StagedChoice):
    deps = _need()
    root = deps.staging_root()
    if choice.action == "skip":
        upload_staging.discard(root, token)
        return {"skipped": True, "uploaded": False, "message": "Skipped. Nothing was added."}
    staged = upload_staging.get(root, token)
    if staged is None:
        raise AppError("That video isn't waiting anymore.", status=410, code="staged_expired",
                       hint=f"Copies are kept for {upload_staging.KEEP_SECONDS // 60} minutes. "
                            "Add the file again to add it anyway.")
    db = deps.session()
    try:
        result = deps.add_file(db, staged["path"], staged["filename"], meta=staged["meta"], if_duplicate="")
    finally:
        db.close()
    upload_staging.discard(root, token)
    return result


# --- filling in missing fingerprints ---------------------------------------------

_backfill_checked = {"at": 0.0}


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def backfill_hashes(ctx, session_factory, *, batch: int = 20, pause: float = 0.02) -> dict:
    """Work out the SHA-256 of library videos that don't have one yet, a few at
    a time, so duplicate checks also know about them. Videos whose file is
    missing are left for a later run."""
    done = missing = 0
    seen: set = set()
    while True:
        db = session_factory()
        try:
            query = db.query(models.Preroll).filter(
                (models.Preroll.file_hash == None) | (models.Preroll.file_hash == ""))  # noqa: E711
            if seen:
                query = query.filter(~models.Preroll.id.in_(seen))
            rows = query.order_by(models.Preroll.id).limit(batch).all()
            if not rows:
                break
            for row in rows:
                seen.add(row.id)
                if not row.path or not os.path.isfile(row.path):
                    missing += 1
                    continue
                try:
                    row.file_hash = _sha256(row.path)
                    done += 1
                except OSError:
                    missing += 1
                if pause:
                    time.sleep(pause)
            db.commit()
        finally:
            db.close()
        if ctx is not None:
            ctx.report(message=f"Checked {done} video(s)", done=done)
    return {"hashed": done, "unreadable": missing}


def backfill_hashes_soon(*, min_gap: float = 60.0) -> None:
    """Start the fingerprint job when some videos lack one (at most once a minute)."""
    deps = _deps
    now = time.monotonic()
    if deps is None or now - _backfill_checked["at"] < min_gap:
        return
    _backfill_checked["at"] = now

    def check():
        db = deps.session()
        try:
            missing = db.query(models.Preroll.id).filter(
                (models.Preroll.file_hash == None) | (models.Preroll.file_hash == "")).first()  # noqa: E711
        finally:
            db.close()
        if missing is not None:
            jobs.runner.submit("hash-backfill", lambda ctx: backfill_hashes(ctx, deps.session),
                               key="hash-backfill", message="Checking videos for duplicates")

    threading.Thread(target=check, daemon=True, name="hash-backfill-check").start()


# --- web links ------------------------------------------------------------------

class LinkIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    url: str = Field(..., max_length=link_fetch.MAX_URL_LENGTH + 100)
    collection_id: Optional[int] = Field(None, ge=1)

    @field_validator("url")
    @classmethod
    def _url(cls, value):
        return link_fetch.check_link(value)


def has_video_stream(ffprobe: str, path: str) -> bool:
    """FFmpeg finds a moving-picture stream. A still picture counts as a
    "video" stream to FFmpeg, so picture formats are refused here too."""
    try:
        out = subprocess.run([ffprobe, "-v", "error", "-select_streams", "v", "-show_entries",
                              "stream=codec_type:format=format_name", "-of", "default=nw=1", path],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    text = out.stdout.lower()
    picture = any(word in text for word in ("image2", "_pipe", "format_name=gif", "format_name=webp"))
    return out.returncode == 0 and "codec_type=video" in text and not picture


def import_link(ctx, url: str, collection_id: Optional[int]) -> dict:
    deps = _need()
    home_network = bool(smart_settings.get("links_allow_home_network"))
    work = tempfile.mkdtemp(prefix="link-", dir=_work_root(deps))
    try:
        ctx.report(message="Downloading", progress=1)

        def progress(size: int, total: Optional[int]):
            if total:
                ctx.report(progress=min(90, 90 * size / total),
                           message=f"Downloading ({size // (1024 * 1024)} of {max(1, total // (1024 * 1024))} MB)")
            else:
                ctx.report(message=f"Downloading ({size // (1024 * 1024)} MB so far)")

        got = link_fetch.fetch(url, work, max_bytes=deps.max_bytes, home_network=home_network, progress=progress)
        ctx.report(message="Checking the video", progress=92)
        if not has_video_stream(deps.ffprobe(), got["path"]):
            raise AppError("That file isn't a video Prerolls Max can play.", status=422, code="not_a_video",
                           hint="Check that the link is for the video file itself.")
        ctx.report(message="Adding it to your library", progress=95)
        db = deps.session()
        try:
            meta = {"category_id": str(collection_id or "")}
            result = deps.add_file(db, got["path"], got["filename"], meta=meta, if_duplicate="ask")
        finally:
            db.close()
        if result.get("duplicate"):
            ctx.report(message=result.get("message") or "Already in your library")
        else:
            ctx.report(message=f'Added "{os.path.splitext(got["filename"])[0]}"')
        return {**result, "source_url": got["final_url"]}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _work_root(deps: Deps) -> str:
    # Next to the parked uploads, not inside: their clean-up would see a
    # download in progress as an old parked file.
    root = os.path.join(os.path.dirname(deps.staging_root().rstrip("/\\")), "link-downloads")
    os.makedirs(root, exist_ok=True)
    return root


@router.post("/api/library/from-link")
def add_from_link(body: LinkIn):
    deps = _need()
    if body.collection_id is not None:
        db = deps.session()
        try:
            if db.query(models.Category.id).filter(models.Category.id == body.collection_id).first() is None:
                raise not_found("That collection", hint="Pick another collection.")
        finally:
            db.close()
    backfill_hashes_soon()
    job = jobs.runner.submit("link-import", lambda ctx: import_link(ctx, body.url, body.collection_id),
                             message="Waiting to start")
    return {"job_id": job.id}
