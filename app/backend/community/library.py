"""Putting a downloaded community video into the user's library.

The file goes to ``<library>/<collection>/<title>.mp4`` (Plex reads "," and
";" as separators in its preroll list, so they never appear in the name; a
name already taken gets " (2)", " (3)"...). A Preroll row records where it
came from in ``community_preroll_id`` (``pm:...`` / ``tn:...``) and the
credit in its description. The thumbnail and length come from the app's own
ffmpeg/ffprobe helpers.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Optional

from backend import models
from backend.community.base import DownloadedFile
from backend.errors import bad_input, not_found
from backend.preroll_files import validate_storage_component
from backend.validation import clean_filename, clean_name, plex_safe_filename

# Kept in descriptions so older matching ("Downloaded from Community Prerolls")
# still recognises downloads made here.
DESCRIPTION_PREFIX = "Downloaded from Community Prerolls"


@dataclass
class Host:
    """What the library import needs from the app (main.py fills it in)."""
    library_dir: Callable[[], str]
    make_thumbnail: Callable  # (preroll, video_path, category_name) -> relative path or None
    measure_seconds: Callable[[str], Optional[float]]
    apply_collection: Callable  # (db, category_id) -> bool
    log: Callable[..., None] = lambda *a, **k: None


def resolve_collection(db, collection_id: Optional[int], new_name: Optional[str]):
    """The collection (category) to put downloads in: an existing one by id,
    a new or existing one by name, else "Default"."""
    if collection_id:
        category = db.query(models.Category).filter(models.Category.id == collection_id).first()
        if not category:
            raise not_found("That collection", hint="Pick another collection, or type a name for a new one.")
        return category
    if new_name is not None and str(new_name).strip():
        try:
            name = clean_name(new_name, what="collection name")
            validate_storage_component(name)
        except ValueError as exc:
            message = str(exc)
            if "storage folder" in message:
                message = "Collection names can't contain \\ / : * ? \" < > | or end with a dot."
            raise bad_input(message, field="new_collection_name")
        existing = db.query(models.Category).filter(models.Category.name == name).first()
        if existing:
            return existing
        category = models.Category(name=name, description="Intro videos from the Community libraries")
        db.add(category)
        db.commit()
        db.refresh(category)
        return category
    category = db.query(models.Category).filter(models.Category.name == "Default").first()
    if not category:
        category = models.Category(name="Default", description="Default category")
        db.add(category)
        db.commit()
        db.refresh(category)
    return category


def collection_folder(library_dir: str, category) -> str:
    try:
        name = validate_storage_component(category.name)
    except ValueError:
        name = "Default"
    return os.path.join(library_dir, name)


def file_name_for(title: str, extension: str) -> str:
    """A file name from a title that Windows, Linux and Plex all accept."""
    text = plex_safe_filename(str(title or ""))
    text = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]+', " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .-") or "Community intro"
    text = text[:120].rstrip(" .")
    try:
        name = clean_filename(text + extension)
    except ValueError:
        name = clean_filename("Community intro" + extension)
    return name


def unique_path(folder: str, file_name: str) -> str:
    stem, ext = os.path.splitext(file_name)
    path = os.path.join(folder, file_name)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, f"{stem} ({n}){ext}")
        n += 1
    return path


def describe(item: dict, source_name: str) -> str:
    parts = [f"{DESCRIPTION_PREFIX} ({source_name})"]
    if item.get("attribution"):
        parts.append(item["attribution"])
    if item.get("page_url"):
        parts.append(item["page_url"])
    return " — ".join(parts)


def add_to_library(db, host: Host, item: dict, downloaded: DownloadedFile, category, source_name: str):
    """Move the checked file into the collection's folder and add its row.

    On failure nothing is left behind: the file is removed and the row rolled back.
    """
    folder = collection_folder(host.library_dir(), category)
    os.makedirs(folder, exist_ok=True)
    target = unique_path(folder, file_name_for(item.get("title"), downloaded.extension))
    os.replace(downloaded.path, target)
    try:
        seconds = item.get("duration_seconds") or None
        measured = host.measure_seconds(target)
        if measured:
            seconds = round(float(measured), 3)
        preroll = models.Preroll(
            filename=os.path.basename(target),
            display_name=item.get("title") or os.path.splitext(os.path.basename(target))[0],
            path=target,
            thumbnail=None,
            tags=None,
            category_id=category.id,
            description=describe(item, source_name),
            duration=seconds,
            file_size=downloaded.size,
            file_hash=downloaded.sha256,
            managed=True,
            community_preroll_id=item["id"],
        )
        db.add(preroll)
        db.flush()
        if category not in (preroll.categories or []):
            preroll.categories = list(preroll.categories or []) + [category]
        db.commit()
        db.refresh(preroll)
    except Exception:
        db.rollback()
        try:
            os.remove(target)
        except OSError:
            pass
        raise
    try:
        thumb = host.make_thumbnail(preroll, target, os.path.basename(folder))
        if thumb:
            preroll.thumbnail = thumb
            db.commit()
    except Exception as exc:  # a missing thumbnail is not worth failing the download for
        db.rollback()
        host.log(f"[COMMUNITY] Thumbnail for {target} failed: {exc}", "WARNING")
    return preroll


def should_apply(db, category) -> bool:
    if getattr(category, "apply_to_plex", False):
        return True
    setting = db.query(models.Setting).first()
    return bool(setting and getattr(setting, "active_category", None) == category.id)
