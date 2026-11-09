"""Media tools: loudness, matching versions and combined files (background jobs).

    GET  /api/media/status                 -> {ffmpeg, tonemap, profiles, frame_rates}
    GET  /api/media/info/{preroll_id}      -> format, whether it already matches 1080p SDR, its versions
    GET  /api/media/loudness               -> every intro's loudness with a plain status, and outliers
    POST /api/media/loudness/check         {preroll_ids?: [..], only_unchecked?: bool} -> {job_id}
    POST /api/media/loudness/normalize     {preroll_ids, target_lufs?, mode: new_version|replace,
                                            use_instead?: bool} -> {job_id}
    POST /api/media/versions               {preroll_ids, profiles: ["1080p", "720p", "2160p"],
                                            frame_rate?, use_instead?: bool} -> {job_id}
    POST /api/media/combine                {preroll_ids? | sequence_id?, name, profile?, frame_rate?,
                                            match_loudness?: bool, collection_id?} -> {job_id}

Normalizing with ``mode: "replace"`` (originals go to the Trash) is for
admins; the other jobs only add new files, so any signed-in person may start them.

Progress: GET /api/jobs/{job_id} (jobs.py). Outputs never overwrite anything:
a new version is a new library item; "replace" moves the original to the
Trash first, so it can be restored from Library > Trash.
"""
from __future__ import annotations

import datetime
import logging
import os
from dataclasses import dataclass
from typing import Callable, List, Literal, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend import media_tools as mt
from backend import admin_guard, models, preroll_trash, smart_settings
from backend.database import SessionLocal
from backend.errors import AppError, bad_input, not_found
from backend.jobs import runner
from backend.preroll_files import validate_storage_component
from backend.timeutil import utcnow
from backend.validation import Name, clean_filename, plex_safe_filename

logger = logging.getLogger("prerollsmax.media_tools")

router = APIRouter(tags=["Media tools"])


@dataclass
class Deps:
    library_dir: Callable[[], str]
    data_dir: Callable[[], Optional[str]] = lambda: None
    make_thumbnail: Optional[Callable] = None


_deps: Optional[Deps] = None


def configure(deps: Optional[Deps]) -> None:
    global _deps
    _deps = deps


def _need_deps() -> Deps:
    if _deps is None:
        raise AppError("Prerolls Max is still starting.", status=503, code="starting", hint="Try again in a moment.")
    return _deps


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def label(preroll) -> str:
    return (getattr(preroll, "display_name", None) or os.path.splitext(preroll.filename or "")[0]
            or f"Intro {preroll.id}")


def _iso(value):
    return value.replace(microsecond=0).isoformat() + "Z" if value else None


def _within(path: str, folder: Optional[str]) -> bool:
    if not path or not folder:
        return False
    a = os.path.normcase(os.path.abspath(path))
    b = os.path.normcase(os.path.abspath(folder))
    return a == b or a.startswith(b + os.sep)


def _load(db, ids: List[int]) -> list:
    rows = {p.id: p for p in db.query(models.Preroll).filter(models.Preroll.id.in_(ids)).all()}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise bad_input("Some of those intro videos don't exist anymore.", field="preroll_ids",
                        hint="Refresh the page and choose them again.")
    return [rows[i] for i in ids]


def _version_folder(original) -> str:
    library = _need_deps().library_dir()
    folder = os.path.dirname(os.path.abspath(original.path))
    if _within(folder, library):
        return folder
    return os.path.join(library, "Versions")


def _thumbnail(row, path: str) -> None:
    deps = _need_deps()
    if not deps.make_thumbnail:
        return
    try:
        category = row.categories[0].name if row.categories else (row.category.name if row.category else None)
        thumb = deps.make_thumbnail(row, path, category)
        if thumb:
            row.thumbnail = thumb
    except Exception as exc:
        logger.info("No thumbnail for %s: %s", path, exc)


def _add_version(db, original, path: str, version_label: str, *, use_instead: bool,
                 loudness: Optional[dict] = None, duration: Optional[float] = None):
    """A new library item for a version of ``original``."""
    library = _need_deps().library_dir()
    row = models.Preroll(
        filename=os.path.basename(path), display_name=f"{label(original)} ({version_label})", path=path,
        tags=original.tags, description=f"{version_label} version of '{label(original)}', made by Prerolls Max.",
        duration=duration if duration is not None else original.duration, file_size=os.path.getsize(path),
        managed=_within(path, library), version_of=original.id, version_label=version_label,
        weight=getattr(original, "weight", None) or 5, enabled=True,
    )
    if loudness:
        row.loudness_lufs = loudness.get("lufs")
        row.loudness_peak = loudness.get("peak")
        row.loudness_lra = loudness.get("lra")
        row.loudness_checked_at = utcnow()
    if use_instead:
        row.categories = list(original.categories or [])
        row.category_id = original.category_id
        original.enabled = False
    db.add(row)
    db.commit()
    db.refresh(row)
    _thumbnail(row, path)
    db.commit()
    return row


def _progress(ctx, index: int, total: int, name: str, verb: str):
    def report(fraction: float):
        ctx.report(progress=100 * (index + fraction) / max(1, total), message=f"{verb} '{name}'")
    return report


def _session():
    """A database session for a job that holds the media lock (released if this fails)."""
    try:
        return SessionLocal()
    except Exception:
        mt.media_lock.release()
        raise


def _waiting(ctx):
    if not mt.media_lock.acquire(blocking=False):
        ctx.report(message="Waiting for another media task to finish")
        mt.media_lock.acquire()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class CheckIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_ids: List[int] = Field(default_factory=list, max_length=5000)
    only_unchecked: bool = False


class NormalizeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_ids: List[int] = Field(..., min_length=1, max_length=500)
    target_lufs: Optional[float] = Field(None, ge=-31, le=-10)
    mode: Literal["new_version", "replace"] = "new_version"
    use_instead: bool = True


class VersionsIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_ids: List[int] = Field(..., min_length=1, max_length=500)
    profiles: List[Literal["720p", "1080p", "2160p"]] = Field(default_factory=lambda: ["1080p"], min_length=1,
                                                               max_length=3)
    frame_rate: Literal["source", "23.976", "24", "25", "29.97", "30", "50", "59.94", "60"] = "source"
    use_instead: bool = True
    skip_matching: bool = True

    @model_validator(mode="after")
    def _one_replacement(self):
        if self.use_instead and len(set(self.profiles)) > 1:
            raise ValueError("Only one size can take the original's place. Choose one size, or turn off "
                             "\"use instead of the original\".")
        return self


class CombineIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_ids: List[int] = Field(default_factory=list, max_length=50)
    sequence_id: Optional[int] = Field(None, ge=1)
    name: Name
    profile: Literal["720p", "1080p", "2160p"] = "1080p"
    frame_rate: Literal["source", "23.976", "24", "25", "29.97", "30", "50", "59.94", "60"] = "source"
    match_loudness: bool = True
    collection_id: Optional[int] = Field(None, ge=1)

    @model_validator(mode="after")
    def _source(self):
        if bool(self.preroll_ids) == bool(self.sequence_id):
            raise ValueError("Choose intro videos or a playlist to combine (one of the two).")
        if self.preroll_ids and len(self.preroll_ids) < 2:
            raise ValueError("Choose at least two intro videos to combine.")
        return self


# ---------------------------------------------------------------------------
# Status and info
# ---------------------------------------------------------------------------

@router.get("/api/media/status")
def media_status():
    ok = mt.available()
    return {"ffmpeg": ok, "tonemap": ok and mt.has_zscale(),
            "profiles": [{"id": k, "label": mt.PROFILE_LABELS[k], "width": v[0], "height": v[1]}
                         for k, v in mt.PROFILES.items()],
            "frame_rates": ["source", *mt.FRAME_RATES.keys()],
            "note": None if ok else "ffmpeg isn't installed, so the media tools can't run."}


@router.get("/api/media/info/{preroll_id}")
def media_info(preroll_id: int, db=Depends(get_db)):
    preroll = db.query(models.Preroll).filter(models.Preroll.id == preroll_id).first()
    if preroll is None:
        raise not_found("That intro video")
    if not preroll.path or not os.path.isfile(preroll.path):
        raise AppError(f"The file for '{label(preroll)}' is missing.", status=404, code="file_missing",
                       hint="Rescan the library, or upload it again.")
    info = mt.probe(preroll.path)
    versions = db.query(models.Preroll).filter(models.Preroll.version_of == preroll.id).all()
    original = None
    if preroll.version_of:
        source = db.query(models.Preroll).filter(models.Preroll.id == preroll.version_of).first()
        original = {"id": source.id, "name": label(source)} if source else None
    matches = mt.matches_profile(info, "1080p")
    return {"preroll_id": preroll.id, "name": label(preroll), "format": mt.describe_format(info), **info,
            "matches_1080p_sdr": matches,
            "advice": ("Already plays everywhere without converting." if matches else
                       "HDR intros switch TVs into HDR mode and make players convert them; a 1080p SDR version "
                       "avoids both." if info.get("hdr") else
                       "A 1080p SDR H.264 version would play on every app without converting."),
            "versions": [{"id": v.id, "name": label(v), "label": v.version_label, "enabled": v.enabled is not False}
                         for v in versions],
            "version_of": original}


@router.get("/api/media/loudness")
def loudness_overview(db=Depends(get_db)):
    settings = smart_settings.get_all(db)
    target = float(settings.get("loudness_target_lufs") or mt.DEFAULT_TARGET_LUFS)
    tolerance = float(settings.get("loudness_tolerance_lu") or 2.0)
    items = []
    counts: dict = {}
    for p in db.query(models.Preroll).order_by(models.Preroll.id).all():
        checked = p.loudness_checked_at is not None
        status, text = mt.loudness_status(p.loudness_lufs, p.loudness_peak, checked, target, tolerance)
        counts[status] = counts.get(status, 0) + 1
        items.append({"preroll_id": p.id, "name": label(p), "lufs": p.loudness_lufs, "peak": p.loudness_peak,
                      "lra": p.loudness_lra, "checked_at": _iso(p.loudness_checked_at), "status": status,
                      "label": text, "version_of": p.version_of})
    measured = sorted(i["lufs"] for i in items if i["lufs"] is not None)
    median = measured[len(measured) // 2] if measured else None
    return {"target_lufs": target, "tolerance_lu": tolerance, "true_peak_limit": mt.TRUE_PEAK_LIMIT,
            "median_lufs": median, "counts": counts,
            "outliers": [i for i in items if i["status"] in ("loud", "quiet", "peaks")],
            "items": items,
            "note": f"Your target is {target:g} LUFS. Intros within {tolerance:g} LU of it sound even with each "
                    "other and with the movie that follows."}


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def _store_loudness(row, measured: Optional[dict]) -> None:
    row.loudness_lufs = (measured or {}).get("lufs")
    row.loudness_peak = (measured or {}).get("peak")
    row.loudness_lra = (measured or {}).get("lra")
    row.loudness_checked_at = utcnow()


@router.post("/api/media/loudness/check")
def start_loudness_check(body: CheckIn, db=Depends(get_db)):
    query = db.query(models.Preroll)
    if body.preroll_ids:
        ids = [p.id for p in _load(db, body.preroll_ids)]
    else:
        if body.only_unchecked:
            query = query.filter(models.Preroll.loudness_checked_at.is_(None))
        ids = [p.id for p in query.order_by(models.Preroll.id).all()]
    if not ids:
        raise AppError("There's nothing to check: every intro has been checked already.", status=409,
                       code="nothing_to_do")
    target = float(smart_settings.get("loudness_target_lufs", db) or mt.DEFAULT_TARGET_LUFS)

    def job(ctx):
        _waiting(ctx)
        session = _session()
        try:
            checked = 0
            ctx.set_total(len(ids))
            for preroll_id in ids:
                row = session.query(models.Preroll).filter(models.Preroll.id == preroll_id).first()
                if row is None:
                    ctx.advance(1)
                    continue
                if not row.path or not os.path.isfile(row.path):
                    ctx.error(str(preroll_id), f"The file for '{label(row)}' is missing.")
                    ctx.advance(1)
                    continue
                try:
                    measured = mt.measure_loudness(row.path, target)
                except AppError as exc:
                    ctx.error(str(preroll_id), exc.message)
                    ctx.advance(1)
                    continue
                _store_loudness(row, measured)
                session.commit()
                checked += 1
                ctx.advance(1, f"Checked '{label(row)}'")
            ctx.report(message=f"Checked {checked} intro video(s).")
            return {"checked": checked}
        finally:
            session.close()
            mt.media_lock.release()

    job_state = runner.submit("loudness_check", job, total=len(ids), message="Waiting to start")
    return {"job_id": job_state.id}


@router.post("/api/media/loudness/normalize")
def start_normalize(body: NormalizeIn, request: Request, db=Depends(get_db)):
    if body.mode == "replace":
        # Replacing moves the originals to the Trash: admins only.
        admin_guard.require(request, "replace the original files")
    rows = _load(db, body.preroll_ids)
    for row in rows:
        if not row.path or not os.path.isfile(row.path):
            raise AppError(f"The file for '{label(row)}' is missing.", status=404, code="file_missing",
                           hint="Rescan the library, or leave it out.")
    ids = [r.id for r in rows]
    target = body.target_lufs if body.target_lufs is not None else float(
        smart_settings.get("loudness_target_lufs", db) or mt.DEFAULT_TARGET_LUFS)
    deps = _need_deps()

    def job(ctx):
        _waiting(ctx)
        session = _session()
        done = []
        try:
            for index, preroll_id in enumerate(ids):
                row = session.query(models.Preroll).filter(models.Preroll.id == preroll_id).first()
                if row is None:
                    continue
                name = label(row)
                source = row.path
                report = _progress(ctx, index, len(ids), name, "Evening out")
                try:
                    measured = mt.measure_loudness(source, target)
                    if not measured or measured.get("lufs") is None:
                        ctx.error(str(preroll_id), f"'{name}' has no sound, so there's nothing to even out.")
                        continue
                    stem, _ext = os.path.splitext(os.path.basename(source))
                    ext = mt.output_extension(source)
                    if body.mode == "new_version":
                        out = mt.unique_path(_version_folder(row), f"{stem} (normalized){ext}")
                        result = mt.normalize_loudness(source, out, target=target, measured=measured,
                                                       on_progress=report)
                        new = _add_version(session, row, out, f"Loudness {target:g} LUFS",
                                           use_instead=body.use_instead, loudness=result)
                        done.append({"preroll_id": row.id, "name": name, "new_preroll_id": new.id,
                                     "before_lufs": measured["lufs"], "after_lufs": result.get("lufs")})
                    else:
                        folder = os.path.dirname(os.path.abspath(source))
                        final = os.path.join(folder, stem + ext)
                        staged = mt.unique_path(folder, f"{stem} (normalized){ext}")
                        result = mt.normalize_loudness(source, staged, target=target, measured=measured,
                                                       on_progress=report)
                        manifest = preroll_trash.move_to_trash(
                            source, deps.library_dir(), deps.data_dir(),
                            metadata={"preroll_id": row.id, "reason": "Replaced by its loudness-normalized version"})
                        try:
                            os.replace(staged, final)
                        except OSError:
                            if manifest and manifest.get("trashed_path"):
                                os.replace(manifest["trashed_path"], source)
                            raise
                        row.path = final
                        row.filename = os.path.basename(final)
                        row.file_size = os.path.getsize(final)
                        row.file_hash = None
                        _store_loudness(row, result)
                        session.commit()
                        done.append({"preroll_id": row.id, "name": name, "new_preroll_id": None,
                                     "before_lufs": measured["lufs"], "after_lufs": result.get("lufs"),
                                     "original_in_trash": bool(manifest)})
                except AppError as exc:
                    ctx.error(str(preroll_id), f"'{name}': {exc.message}")
                ctx.report(progress=100 * (index + 1) / len(ids), message=f"Finished '{name}'")
            ctx.report(message=f"Evened out {len(done)} intro video(s) to {target:g} LUFS.")
            return {"target_lufs": target, "mode": body.mode, "items": done}
        finally:
            session.close()
            mt.media_lock.release()

    job_state = runner.submit("loudness_normalize", job, total=len(ids))
    return {"job_id": job_state.id}


@router.post("/api/media/versions")
def start_versions(body: VersionsIn, db=Depends(get_db)):
    rows = _load(db, body.preroll_ids)
    for row in rows:
        if not row.path or not os.path.isfile(row.path):
            raise AppError(f"The file for '{label(row)}' is missing.", status=404, code="file_missing",
                           hint="Rescan the library, or leave it out.")
    ids = [r.id for r in rows]
    profiles = list(dict.fromkeys(body.profiles))
    total = len(ids) * len(profiles)

    def job(ctx):
        _waiting(ctx)
        session = _session()
        made, skipped = [], []
        try:
            step = 0
            for preroll_id in ids:
                row = session.query(models.Preroll).filter(models.Preroll.id == preroll_id).first()
                if row is None:
                    continue
                name = label(row)
                for profile in profiles:
                    report = _progress(ctx, step, total, name, f"Making a {mt.PROFILE_LABELS[profile]} version of")
                    step += 1
                    try:
                        info = mt.probe(row.path)
                        if body.skip_matching and mt.matches_profile(info, profile):
                            skipped.append({"preroll_id": row.id, "name": name, "profile": profile,
                                            "why": f"Already {mt.PROFILE_LABELS[profile]} H.264 with AAC sound."})
                            continue
                        stem = os.path.splitext(os.path.basename(row.path))[0]
                        out = mt.unique_path(_version_folder(row), f"{stem} ({profile}).mp4")
                        new_info = mt.make_version(row.path, out, profile=profile, frame_rate=body.frame_rate,
                                                   on_progress=report)
                        new = _add_version(session, row, out, mt.PROFILE_LABELS[profile],
                                           use_instead=body.use_instead, duration=new_info.get("duration"))
                        made.append({"preroll_id": row.id, "name": name, "profile": profile,
                                     "new_preroll_id": new.id, "format": mt.describe_format(new_info),
                                     "was": mt.describe_format(info), "tone_mapped": bool(info.get("hdr"))})
                    except AppError as exc:
                        ctx.error(str(preroll_id), f"'{name}': {exc.message}")
            note = None
            if body.use_instead and made:
                note = ("Each new version took its original's place in its collections; the originals are "
                        "switched off, not deleted. Playlists that name an original directly still play it.")
            made_text = "1 new version" if len(made) == 1 else f"{len(made)} new versions"
            ctx.report(message=f"Made {made_text}." + (f" {len(skipped)} already matched." if skipped else ""))
            return {"made": made, "skipped": skipped, "note": note}
        finally:
            session.close()
            mt.media_lock.release()

    job_state = runner.submit("matching_versions", job, total=total)
    return {"job_id": job_state.id}


def _sequence_paths(db, sequence_id: int) -> tuple:
    from backend.scheduler import resolve_sequence_paths
    sequence = db.query(models.SavedSequence).filter(models.SavedSequence.id == sequence_id).first()
    if sequence is None:
        raise not_found("That playlist")
    blocks = sequence.get_blocks()
    paths = resolve_sequence_paths(blocks, db, ("combine", sequence_id, utcnow().isoformat()),
                                   log_prefix="[COMBINE]")
    return [p for p in paths if os.path.isfile(p)], sequence.name


@router.post("/api/media/combine")
def start_combine(body: CombineIn, db=Depends(get_db)):
    deps = _need_deps()
    collection = None
    if body.collection_id:
        collection = db.query(models.Category).filter(models.Category.id == body.collection_id).first()
        if collection is None:
            raise bad_input("That collection doesn't exist anymore.", field="collection_id")
    if body.preroll_ids:
        rows = _load(db, body.preroll_ids)
        missing = [label(r) for r in rows if not r.path or not os.path.isfile(r.path)]
        if missing:
            raise AppError(f"The file for '{missing[0]}' is missing.", status=404, code="file_missing",
                           hint="Rescan the library, or leave it out.")
        sources = [os.path.abspath(r.path) for r in rows]
        part_names = [label(r) for r in rows]
        source_note = None
    else:
        sources, playlist_name = _sequence_paths(db, body.sequence_id)
        if len(sources) < 2:
            raise AppError(f"'{playlist_name}' has fewer than two videos to combine right now.", status=422,
                           code="nothing_to_combine",
                           hint="Random parts are picked once when the file is made; conditions that depend on "
                                "the title can't be known ahead, so their Otherwise plays.")
        known = {os.path.abspath(p.path): p for p in db.query(models.Preroll).filter(models.Preroll.path.in_(sources))}
        part_names = [label(known[s]) if s in known else os.path.splitext(os.path.basename(s))[0] for s in sources]
        source_note = (f"Made from '{playlist_name}'. Random parts were picked once, now; make it again for "
                       "a new mix.")
    try:
        filename = clean_filename(plex_safe_filename(body.name) + ".mp4")
    except ValueError as exc:
        raise bad_input(str(exc), field="name")
    folder_name = collection.name if collection is not None else "Combined"
    try:
        folder = os.path.join(deps.library_dir(), validate_storage_component(folder_name))
    except Exception:
        folder = os.path.join(deps.library_dir(), "Combined")
    collection_id = collection.id if collection is not None else None

    def job(ctx):
        _waiting(ctx)
        session = _session()
        try:
            out = mt.unique_path(folder, filename)
            ctx.report(message=f"Combining {len(sources)} videos")
            target = float(smart_settings.get("loudness_target_lufs", session) or mt.DEFAULT_TARGET_LUFS)
            info = mt.combine(sources, out, profile=body.profile, frame_rate=body.frame_rate,
                              match_loudness=body.match_loudness, target=target,
                              on_progress=lambda f: ctx.report(progress=100 * f, message="Combining"))
            row = models.Preroll(filename=os.path.basename(out), display_name=body.name, path=out,
                                 description=f"One file made from: {', '.join(part_names)}.",
                                 duration=info.get("duration"), file_size=os.path.getsize(out), managed=True,
                                 version_label="Combined", enabled=True)
            if collection_id:
                target_collection = session.query(models.Category).filter(models.Category.id == collection_id).first()
                if target_collection is not None:
                    row.categories = [target_collection]
                    row.category_id = target_collection.id
            session.add(row)
            session.commit()
            session.refresh(row)
            _thumbnail(row, out)
            session.commit()
            ctx.report(message=f"Made '{body.name}' ({len(sources)} videos, {info.get('duration', 0):.0f} s).")
            return {"preroll_id": row.id, "name": body.name, "path": out, "duration_seconds": info.get("duration"),
                    "format": mt.describe_format(info), "parts": part_names, "note": source_note}
        finally:
            session.close()
            mt.media_lock.release()

    job_state = runner.submit("combine", job, total=len(sources))
    return {"job_id": job_state.id}
