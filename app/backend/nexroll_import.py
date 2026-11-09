"""Bring a NeXroll library into Prerolls Max (Settings > Moving from NeXroll).

``preview`` says what a NeXroll backup (nexroll_source.py) holds before
anything changes. ``run_import`` then either

* **replaces** this library with it (the restore Backup > Restore uses), for a
  fresh install, or
* **merges** it in: collections with the same name are joined, videos already
  here (same file or same fingerprint) are reused, and a schedule or playlist
  whose name is taken but whose content differs comes in as "Name (2)".

Either way NeXroll's user accounts and API keys stay behind, and Prerolls
Max's own sign-in settings are kept. Media servers NeXroll was connected to
are added when no server with that address is here yet, with their keys when
the backup has them and the person asked for them.

Videos whose files Prerolls Max can't see (NeXroll kept them in D:\\Prerolls,
Prerolls Max runs in Docker) are listed, kept out of the library clean-up
(``held_ids``) and fixed with ``relink``: "they're in /media/prerolls now".
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import shutil
import threading
from dataclasses import dataclass
from typing import Callable, Optional

from backend import backup_utils, media_servers, models, unique_names, validation
from backend.errors import AppError, bad_input
from backend.nexroll_source import guess_media_folder

logger = logging.getLogger("prerollsmax.nexroll")

STATE_FILE = "nexroll_import.json"
# Prerolls Max keeps its own sign-in and first-run state, whatever NeXroll had.
SETTINGS_KEEP_PREFIXES = ("auth_", "onboarding_")
SERVER_COLUMNS = {
    "plex": ("plex_url", "plex_token"),
    "jellyfin": ("jellyfin_url", "jellyfin_api_key"),
    "emby": ("emby_url", "emby_api_key"),
}
SERVER_SETTING_COLUMNS = {"plex_url", "jellyfin_url", "emby_url", "plex_token", "jellyfin_api_key",
                          "emby_api_key", "path_mappings", "plex_server_machine_id", "plex_server_name"}
SECRET_SETTING_COLUMNS = {"plex_token", "jellyfin_api_key", "emby_api_key", "nexup_radarr_api_key",
                          "nexup_sonarr_api_key", "nexup_tmdb_api_key"}
KEY_LABELS = {"plex_token": "the Plex sign-in", "jellyfin_api_key": "the Jellyfin key",
              "emby_api_key": "the Emby key", "nexup_radarr_api_key": "the Radarr key",
              "nexup_sonarr_api_key": "the Sonarr key", "nexup_tmdb_api_key": "the TMDB key"}


@dataclass
class Deps:
    session: Callable[[], object]
    library_dir: Callable[[], str]
    data_dir: Callable[[], str]
    restore: Callable[..., dict]          # (backup dict, db) -> the restore answer (replaces everything)
    rescan: Callable[..., Optional[dict]]  # (db) -> scanner stats: relinks paths, makes thumbnails
    refresh_schedule: Callable[..., None] = lambda schedule: None
    log: Callable[..., None] = lambda message, level="INFO": None


_deps: Optional[Deps] = None
_state_lock = threading.Lock()


def configure(deps: Deps) -> None:
    global _deps
    _deps = deps


def _need() -> Deps:
    if _deps is None:
        raise RuntimeError("nexroll_import is not configured")
    return _deps


# ---------------------------------------------------------------------------
# Saved state: the last report and the videos waiting for their folder
# ---------------------------------------------------------------------------

def _state_path() -> Optional[str]:
    if _deps is None:
        return None
    try:
        from backend.database import DB_PATH
        return os.path.join(os.path.dirname(DB_PATH), STATE_FILE)
    except Exception:
        return os.path.join(_deps.data_dir(), STATE_FILE)


def load_state() -> dict:
    path = _state_path()
    if not path:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_state(data: dict) -> None:
    path = _state_path()
    if not path:
        return
    with _state_lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, path)


def held_ids() -> set:
    """Imported videos whose files aren't reachable yet. The library clean-up
    (scanner.py) leaves them alone until they are relinked or deleted."""
    try:
        return {int(i) for i in load_state().get("held_ids") or []}
    except (TypeError, ValueError):
        return set()


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def _plural(n: int, one: str, many: Optional[str] = None) -> str:
    return f"{n} {one if n == 1 else (many or one + 's')}"


def _parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _video_label(row: dict) -> str:
    return row.get("display_name") or os.path.splitext(str(row.get("filename") or ""))[0] or "a video"


def _staged_rel(path: str, staged: list) -> Optional[str]:
    """Which extracted ZIP file (``Halloween/Ghost.mp4``) a backed-up path points at."""
    norm = "/" + str(path or "").replace("\\", "/").lstrip("/")
    best = None
    for rel in staged:
        if norm.lower().endswith("/" + rel.lower()) and (best is None or len(rel) > len(best)):
            best = rel
    return best


def file_found(row: dict, staged: list) -> bool:
    path = row.get("path")
    if path and os.path.isfile(path):
        return True
    return bool(staged and _staged_rel(path or "", staged))


def _servers_in(data: dict) -> list:
    """[{type, url, key, mappings}] for the media servers NeXroll was connected to."""
    settings = data.get("settings") or {}
    creds = data.get("credentials") or {}
    out = []
    for kind, (url_col, key_col) in SERVER_COLUMNS.items():
        url = settings.get(url_col)
        if not isinstance(url, str) or not url.strip():
            continue
        try:
            url = validation.clean_server_url(url, service="the server")
        except ValueError:
            continue
        key = creds.get(key_col) or settings.get(key_col) or None
        mappings = []
        if kind == "plex":
            try:
                from backend import path_mapping
                mappings = path_mapping.load_mappings(settings.get("path_mappings"))
            except Exception:
                mappings = []
        out.append({"type": kind, "url": url, "key": key if isinstance(key, str) and key.strip() else None,
                    "mappings": mappings, "name_hint": settings.get("plex_server_name") if kind == "plex" else None})
    return out


def _keys_in(data: dict) -> list:
    settings = data.get("settings") or {}
    creds = data.get("credentials") or {}
    found = []
    for name in KEY_LABELS:
        value = creds.get(name) or settings.get(name)
        if isinstance(value, str) and value.strip():
            found.append(name)
    return found


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

def preview(db, data: dict) -> dict:
    """What would come over, in plain numbers, before anything changes."""
    cleaned, skipped = backup_utils.clean_backup_payload({k: v for k, v in data.items() if k != "_nexroll"})
    extra = data.get("_nexroll") or {}
    staged = extra.get("files") or []
    prerolls = cleaned.get("prerolls") or []
    found = [p for p in prerolls if file_found(p, staged)]
    missing = [p for p in prerolls if not file_found(p, staged)]
    folder = guess_media_folder([p.get("path") for p in missing]) if missing else None
    servers = _servers_in(cleaned | {"credentials": data.get("credentials") or {}})

    have_collections = {unique_names.name_key(n) for (n,) in db.query(models.Category.name).all()}
    taken = {
        "collections": [c["name"] for c in cleaned.get("categories") or []
                        if unique_names.name_key(c.get("name")) in have_collections],
        "schedules": [s["name"] for s in cleaned.get("schedules") or []
                      if unique_names.name_taken(db, "schedule", s["name"])],
        "playlists": [s["name"] for s in cleaned.get("saved_sequences") or []
                      if unique_names.name_taken(db, "playlist", s["name"])],
    }
    library_empty = not (db.query(models.Preroll).count() or db.query(models.Schedule).count()
                         or db.query(models.SavedSequence).count()
                         or db.query(models.Category).filter(models.Category.is_system.isnot(True)).count())
    left_behind = []
    if extra.get("users"):
        left_behind.append(f"{_plural(extra['users'], 'user account')}: Prerolls Max keeps its own sign-in.")
    if extra.get("api_keys"):
        left_behind.append(f"{_plural(extra['api_keys'], 'API key')}: make new ones in Prerolls Max for your "
                           "scripts and dashboards. The Prerolls Max Intros plugin gets its own key when you set it up.")
    keys = _keys_in(cleaned | {"credentials": data.get("credentials") or {}})
    return {
        "source": {"kind": extra.get("source"), "where": extra.get("where"),
                   "exported_by": cleaned.get("exported_by_version"),
                   "keys_left_out": bool(extra.get("keys_left_out"))},
        "counts": {
            "collections": len(cleaned.get("categories") or []),
            "intro_videos": len(prerolls),
            "videos_found": len(found),
            "videos_missing": len(missing),
            "videos_in_zip": len(staged),
            "schedules": len(cleaned.get("schedules") or []),
            "playlists": len(cleaned.get("saved_sequences") or []),
            "holidays": len(cleaned.get("holiday_presets") or []),
            "genre_maps": len(cleaned.get("genre_maps") or []),
            "radarr": len(cleaned.get("radarr_servers") or []),
            "sonarr": len(cleaned.get("sonarr_servers") or []),
            "api_keys": int(extra.get("api_keys") or 0),
            "users": int(extra.get("users") or 0),
        },
        "servers": [{"type": s["type"], "url": s["url"], "has_key": bool(s["key"]),
                     "already_here": _server_here(db, s["type"], s["url"]) is not None} for s in servers],
        "keys": [KEY_LABELS[k] for k in keys],
        "missing": {"count": len(missing), "folder": folder,
                    "examples": [_video_label(p) for p in missing[:5]]},
        "names_taken": taken,
        "library_empty": bool(library_empty),
        "suggested_mode": "replace" if library_empty else "merge",
        "skipped": skipped,
        "left_behind": left_behind,
    }


def _server_here(db, kind: str, url: str):
    key = media_servers.normalize_url(url)
    return next((r for r in media_servers.ordered(db, kind) if media_servers.normalize_url(r.url) == key), None)


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _settings_for_import(settings: dict, include_keys: bool) -> dict:
    out = {}
    for key, value in (settings or {}).items():
        if key.startswith(SETTINGS_KEEP_PREFIXES) or key in SERVER_SETTING_COLUMNS:
            continue
        if key in SECRET_SETTING_COLUMNS and not include_keys:
            continue
        out[key] = value
    return out


def _place_zip_files(data: dict, report: dict) -> None:
    """Copy a full backup's videos into the intro folder and point the rows at them."""
    extra = data.get("_nexroll") or {}
    root, staged = extra.get("files_root"), extra.get("files") or []
    if not root or not staged:
        return
    library = _need().library_dir()
    placed = {}
    for rel in staged:
        src = os.path.join(root, *rel.split("/"))
        if not os.path.isfile(src):
            continue
        dest = os.path.join(library, *rel.split("/"))
        if os.path.exists(dest) and os.path.getsize(dest) != os.path.getsize(src):
            dest = os.path.join(library, "From NeXroll", *rel.split("/"))
        if not os.path.exists(dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(src, dest)
        placed[rel] = dest
    moved = 0
    for row in data.get("prerolls") or []:
        if not isinstance(row, dict):
            continue
        path = row.get("path")
        if path and os.path.isfile(path):
            continue
        rel = _staged_rel(path or "", staged)
        if rel and rel in placed:
            row["path"] = placed[rel]
            moved += 1
    report["videos_copied"] = len(placed)


def _add_servers(db, data: dict, include_keys: bool, report: dict) -> None:
    for found in _servers_in(data):
        kind, url = found["type"], found["url"]
        label = media_servers.LABELS.get(kind, kind)
        if _server_here(db, kind, url) is not None:
            report["notes"].append(f"{label} at {url} was already connected here, so it was left as it is.")
            continue
        row = models.MediaServer(type=kind, name=media_servers.default_name(db, kind, found.get("name_hint")),
                                 url=url, enabled=True)
        if kind == "plex":
            row.path_mappings = json.dumps(found["mappings"] or [])
            row.server_identifier = (data.get("settings") or {}).get("plex_server_machine_id")
        db.add(row)
        db.flush()
        if include_keys and found["key"]:
            media_servers.set_secret(row, found["key"])
            report["added"]["servers"] += 1
            report["notes"].append(f"Added {row.name} ({url}) with NeXroll's key.")
        else:
            report["added"]["servers"] += 1
            report["notes"].append(f"Added {row.name} ({url}) without a key. Add the key on the Media Servers page.")
    media_servers.mirror(db)
    db.commit()


def _add_arr(db, data: dict, include_keys: bool, report: dict) -> None:
    for key, model, label in (("radarr_servers", models.RadarrServer, "Radarr"),
                              ("sonarr_servers", models.SonarrServer, "Sonarr")):
        here = {media_servers.normalize_url(r.url) for r in db.query(model).all()}
        for row in data.get(key) or []:
            url = row.get("url")
            if not url or media_servers.normalize_url(url) in here:
                continue
            api_key = row.get("api_key") if include_keys else None
            if not api_key:
                report["skipped"].append(f"the {label} at {url}: the backup has no key for it")
                continue
            db.add(model(name=row.get("name") or label, url=url, api_key=api_key))
            here.add(media_servers.normalize_url(url))
            report["added"]["arr"] += 1
    db.commit()


def _merge(db, data: dict, report: dict) -> None:
    deps = _need()
    added, matched, renamed = report["added"], report["matched"], report["renamed"]

    # Collections: one with the same name is the same collection.
    by_name = {unique_names.name_key(c.name): c for c in db.query(models.Category).all()}
    cat_map = {}
    for row in data.get("categories") or []:
        key = unique_names.name_key(row.get("name"))
        existing = by_name.get(key)
        if existing is None:
            existing = models.Category(name=row["name"], description=row.get("description"),
                                       plex_mode=row.get("plex_mode") or "shuffle",
                                       apply_to_plex=bool(row.get("apply_to_plex")),
                                       is_system=bool(row.get("is_system")))
            db.add(existing)
            db.flush()
            by_name[key] = existing
            added["collections"] += 1
        else:
            matched["collections"] += 1
        if row.get("id") is not None:
            cat_map[row["id"]] = existing.id
    db.commit()

    for row in data.get("genre_maps") or []:
        cat = cat_map.get(row.get("category_id"))
        if not cat or not row.get("genre"):
            continue
        norm = row.get("genre_norm") or str(row["genre"]).strip().lower()
        exists = db.query(models.GenreMap).filter(models.GenreMap.genre_norm == norm).first()
        if exists is None:
            db.add(models.GenreMap(genre=row["genre"], genre_norm=norm, category_id=cat))
    db.commit()

    # Videos: the same file, or a file with the same fingerprint, is reused.
    by_path = {os.path.normcase(os.path.abspath(p.path)): p for p in db.query(models.Preroll).all() if p.path}
    by_hash = {p.file_hash: p for p in db.query(models.Preroll).all() if p.file_hash}
    cats = {c.id: c for c in db.query(models.Category).all()}
    pre_map = {}
    for row in data.get("prerolls") or []:
        path = row.get("path")
        existing = None
        if path:
            existing = by_path.get(os.path.normcase(os.path.abspath(path)))
        if existing is None and row.get("file_hash"):
            existing = by_hash.get(row["file_hash"])
        links = [cat_map.get(c.get("id")) if isinstance(c, dict) else None for c in row.get("categories") or []]
        if not links and row.get("category_id") is not None:
            links = [cat_map.get(row["category_id"])]
        links = [cats[i] for i in links if i in cats]
        if existing is not None:
            matched["intro_videos"] += 1
            for cat in links:
                if cat not in existing.categories:
                    existing.categories.append(cat)
        else:
            existing = models.Preroll(
                filename=row.get("filename"), display_name=row.get("display_name"), path=path,
                thumbnail=None, tags=row.get("tags"), category_id=links[0].id if links else None,
                description=row.get("description"), duration=row.get("duration"),
                file_size=row.get("file_size"), upload_date=_parse_dt(row.get("upload_date")),
                managed=bool(row.get("managed", True)), enabled=bool(row.get("enabled", True)),
                community_preroll_id=_community_id(row.get("community_preroll_id")),
                exclude_from_matching=bool(row.get("exclude_from_matching", False)),
                file_hash=row.get("file_hash"))
            db.add(existing)
            db.flush()
            existing.categories = links
            added["intro_videos"] += 1
            report["_new_preroll_ids"].append(existing.id)
            if path:
                by_path[os.path.normcase(os.path.abspath(path))] = existing
            if row.get("file_hash"):
                by_hash[row["file_hash"]] = existing
        if row.get("id") is not None:
            pre_map[backup_utils.normalize_preroll_id(row["id"])] = existing.id
    db.commit()

    # Playlists, then schedules (a schedule can name the playlist it came from).
    seq_map = {}
    for row in data.get("saved_sequences") or []:
        blocks = backup_utils.remap_sequence_blocks(row.get("blocks") or [], pre_map, cat_map)
        same = next((s for s in db.query(models.SavedSequence).all()
                     if _same_or_numbered(s.name, row["name"]) and _blocks_equal(s.blocks, blocks)), None)
        if same is not None:
            matched["playlists"] += 1
            seq_map[row.get("id")] = same.id
            continue
        name = unique_names.unique_name(db, "playlist", row["name"])
        if unique_names.name_key(name) != unique_names.name_key(row["name"]):
            renamed.append(unique_names.renamed_note("playlist", row["name"], name))
        seq = models.SavedSequence(name=name, description=row.get("description"), blocks=json.dumps(blocks),
                                   created_at=_parse_dt(row.get("created_at")) or datetime.datetime.utcnow(),
                                   updated_at=_parse_dt(row.get("updated_at")) or datetime.datetime.utcnow())
        db.add(seq)
        db.flush()
        seq_map[row.get("id")] = seq.id
        added["playlists"] += 1
    db.commit()

    for row in data.get("schedules") or []:
        cat = cat_map.get(row.get("category_id"))
        start = _parse_dt(row.get("start_date"))
        sequence = backup_utils.remap_sequence_json(row.get("sequence"), pre_map, cat_map)
        # Start dates aren't compared: yearly schedules store theirs in year 2000.
        same = next((s for s in db.query(models.Schedule).all()
                     if _same_or_numbered(s.name, row["name"])
                     and s.type == row.get("type") and s.category_id == cat
                     and (s.recurrence_pattern or None) == (row.get("recurrence_pattern") or None)
                     and _blocks_equal(s.sequence or "null", json.loads(sequence) if sequence else None)), None)
        if same is not None:
            matched["schedules"] += 1
            continue
        name = unique_names.unique_name(db, "schedule", row["name"])
        if unique_names.name_key(name) != unique_names.name_key(row["name"]):
            renamed.append(unique_names.renamed_note("schedule", row["name"], name))
        sched = models.Schedule(
            name=name, type=row.get("type"), start_date=start, end_date=_parse_dt(row.get("end_date")),
            category_id=cat, fallback_category_id=cat_map.get(row.get("fallback_category_id")),
            playlist=bool(row.get("playlist", False)), is_active=bool(row.get("is_active", True)),
            recurrence_pattern=row.get("recurrence_pattern"),
            preroll_ids=backup_utils.remap_preroll_ids_json(row.get("preroll_ids"), pre_map),
            sequence=sequence,
            color=row.get("color"), blend_enabled=bool(row.get("blend_enabled", False)),
            priority=row.get("priority") if row.get("priority") is not None else 5,
            exclusive=bool(row.get("exclusive", False)), holiday_name=row.get("holiday_name"),
            holiday_country=row.get("holiday_country"),
            source_sequence_id=seq_map.get(row.get("source_sequence_id")))
        try:
            deps.refresh_schedule(sched)
        except Exception:
            pass
        db.add(sched)
        db.flush()
        added["schedules"] += 1
    db.commit()

    have = {unique_names.name_key(h.name) for h in db.query(models.HolidayPreset).all()}
    for row in data.get("holiday_presets") or []:
        if unique_names.name_key(row.get("name")) in have:
            continue
        db.add(models.HolidayPreset(
            name=row["name"], description=row.get("description"), month=row.get("month"), day=row.get("day"),
            start_month=row.get("start_month"), start_day=row.get("start_day"), end_month=row.get("end_month"),
            end_day=row.get("end_day"), is_recurring=bool(row.get("is_recurring", True)),
            category_id=cat_map.get(row.get("category_id"))))
        added["holidays"] += 1
    db.commit()

    have_paths = {r.path_key or r.path for r in db.query(models.IgnoredPath).all()}
    for row in data.get("ignored_paths") or []:
        key = row.get("path_key") or row.get("path")
        if key and key not in have_paths:
            db.add(models.IgnoredPath(path=row["path"], path_key=row.get("path_key"), filename=row.get("filename"),
                                      reason=row.get("reason")))
            have_paths.add(key)
    db.commit()


def _community_id(value):
    try:
        from backend.community import ids as community_ids
        return community_ids.tag_legacy(value)
    except Exception:
        return value


def _same_or_numbered(existing_name, name) -> bool:
    """"Christmas" and "Christmas (2)" are the same item brought in before."""
    have, want = unique_names.name_key(existing_name), unique_names.name_key(name)
    if have == want:
        return True
    return have.startswith(want + " (") and have.endswith(")") and have[len(want) + 2:-1].isdigit()


def _blocks_equal(stored, blocks) -> bool:
    try:
        current = json.loads(stored) if isinstance(stored, str) else stored
    except ValueError:
        return False
    return json.dumps(current, sort_keys=True) == json.dumps(blocks, sort_keys=True)


def run_import(data: dict, *, mode: str, include_keys: bool, progress=None) -> dict:
    """Bring the backup in. ``progress(percent, message)`` is called along the way."""
    deps = _need()
    step = progress or (lambda pct, msg: None)
    if mode not in ("replace", "merge"):
        raise bad_input("Pick Replace or Merge.", field="mode")
    data = json.loads(json.dumps(data, default=str))  # our own copy; the preview stays as it was
    extra = data.get("_nexroll") or {}
    report = {
        "mode": mode,
        "added": {"collections": 0, "intro_videos": 0, "schedules": 0, "playlists": 0, "holidays": 0,
                  "servers": 0, "arr": 0},
        "matched": {"collections": 0, "intro_videos": 0, "schedules": 0, "playlists": 0},
        "renamed": [], "skipped": [], "notes": [], "keys_imported": [], "_new_preroll_ids": [],
        "videos_copied": 0,
    }
    step(5, "Copying the videos from the backup" if extra.get("files") else "Checking the backup")
    _place_zip_files(data, report)

    if not include_keys:
        data["credentials"] = {}
        data["radarr_servers"] = [dict(r, api_key="") for r in data.get("radarr_servers") or []]
        data["sonarr_servers"] = [dict(r, api_key="") for r in data.get("sonarr_servers") or []]
    else:
        report["keys_imported"] = [KEY_LABELS[k] for k in _keys_in(data)]
    servers_source = {"settings": dict(data.get("settings") or {}), "credentials": data.get("credentials") or {}}
    data["settings"] = _settings_for_import(data.get("settings") or {}, include_keys)
    data["credentials"] = {}  # server keys go to the server rows below, not the old single-server slots
    data.pop("_nexroll", None)
    data.pop("media_servers", None)

    cleaned, skipped = backup_utils.clean_backup_payload(data)
    report["skipped"].extend(skipped)
    db = deps.session()
    try:
        if mode == "replace":
            step(25, "Replacing your library with NeXroll's")
            before = {p.id for p in db.query(models.Preroll.id).all()}
            answer = deps.restore(cleaned, db)
            report["skipped"].extend(answer.get("skipped") or [])
            report["renamed"].extend(answer.get("renamed") or [])
            report["added"].update(
                collections=db.query(models.Category).filter(models.Category.is_system.isnot(True)).count(),
                intro_videos=db.query(models.Preroll).count(),
                schedules=db.query(models.Schedule).count(),
                playlists=db.query(models.SavedSequence).count(),
                holidays=db.query(models.HolidayPreset).count())
            report["_new_preroll_ids"] = [p.id for p in db.query(models.Preroll.id).all() if p.id not in before] or \
                [p.id for p in db.query(models.Preroll.id).all()]
            report["settings"] = "replaced"
        else:
            step(25, "Adding NeXroll's collections, videos and schedules")
            _merge(db, cleaned, report)
            _add_arr(db, cleaned, include_keys, report)
            report["settings"] = "kept"
        step(70, "Adding the media servers")
        _add_servers(db, servers_source, include_keys, report)
        step(80, "Finding the video files")
        try:
            deps.rescan(db)
        except Exception as exc:
            deps.log(f"NeXroll import: scan after import failed: {exc}", "WARNING")
        report["missing"] = missing_report(db, report.pop("_new_preroll_ids"))
    finally:
        db.close()
    report["message"] = summary_sentence(report)
    report["finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    state = load_state()
    state.update(last=report, held_ids=report["missing"].get("ids", []))
    _save_state(state)
    step(99, "Done")
    return report


def missing_report(db, ids) -> dict:
    """Imported videos whose files aren't where the database says."""
    ids = list(ids or [])
    rows = db.query(models.Preroll).filter(models.Preroll.id.in_(ids)).all() if ids else []
    missing = [r for r in rows if not (r.path and os.path.isfile(r.path))]
    folder = guess_media_folder([r.path for r in missing]) if missing else None
    return {
        "count": len(missing),
        "ids": [r.id for r in missing],
        "folder": folder,
        "folder_exists_here": bool(folder and os.path.isdir(folder)),
        "examples": [r.display_name or os.path.splitext(r.filename or "")[0] for r in missing[:5]],
    }


def summary_sentence(report: dict) -> str:
    a, m = report["added"], report["matched"]
    bits = []
    if a["collections"]:
        bits.append(_plural(a["collections"], "collection"))
    if a["intro_videos"]:
        bits.append(_plural(a["intro_videos"], "intro video"))
    if a["schedules"]:
        bits.append(_plural(a["schedules"], "schedule"))
    if a["playlists"]:
        bits.append(_plural(a["playlists"], "playlist"))
    if a["servers"]:
        bits.append(_plural(a["servers"], "media server"))
    verb = "Brought over" if report["mode"] == "replace" else "Added"
    text = f"{verb} " + (", ".join(bits[:-1]) + " and " + bits[-1] if len(bits) > 1 else bits[0]) + "." \
        if bits else "Nothing new to add: everything was already here."
    same = sum(m.values())
    if same:
        text += (" 1 thing was already here, so it stayed as it was." if same == 1 else
                 f" {same} things were already here, so they stayed as they were.")
    return text


# ---------------------------------------------------------------------------
# Relink: "NeXroll kept them in D:\\Prerolls; they're in /media/prerolls now"
# ---------------------------------------------------------------------------

def _rest_after(path: str, folder: str) -> Optional[list]:
    """The parts of ``path`` below ``folder``, or None when it isn't inside it."""
    windows = validation.path_style(folder) == "windows" or validation.path_style(path) == "windows"
    p = [x for x in str(path).replace("\\", "/").split("/") if x]
    f = [x for x in str(folder).replace("\\", "/").split("/") if x]
    if len(p) <= len(f):
        return None
    same = (lambda a, b: a.lower() == b.lower()) if windows else (lambda a, b: a == b)
    if all(same(a, b) for a, b in zip(p, f)):
        return p[len(f):]
    return None


def relink(db, from_folder: str, to_folder: str, *, max_files: int = 50000) -> dict:
    """Point videos that NeXroll kept under ``from_folder`` at the same files
    under ``to_folder``. Files not found by their place are looked for by name."""
    try:
        old = validation.clean_folder_path(from_folder, what="folder NeXroll used")
    except ValueError as exc:
        raise bad_input(str(exc), field="from_folder")
    try:
        new = validation.clean_folder_path(to_folder, what="folder")
    except ValueError as exc:
        raise bad_input(str(exc), field="to_folder")
    if not os.path.isdir(new):
        raise bad_input(f"Prerolls Max can't see a folder at {new}.", field="to_folder",
                        hint="In Docker, add the folder as a volume first and use the path inside the container.")
    held = held_ids()
    rows = [r for r in db.query(models.Preroll).all() if r.path and not os.path.isfile(r.path)]
    by_name = None
    relinked, still = [], []
    for row in rows:
        rest = _rest_after(row.path, old)
        candidate = os.path.join(new, *rest) if rest else None
        if not (candidate and os.path.isfile(candidate)):
            if by_name is None:
                by_name = _index_files(new, max_files)
            name = str(row.path).replace("\\", "/").rsplit("/", 1)[-1]
            parent = str(row.path).replace("\\", "/").rsplit("/", 2)[-2] if "/" in str(row.path).replace("\\", "/") else ""
            options = by_name.get(name.lower()) or []
            pick = [o for o in options if os.path.basename(os.path.dirname(o)).lower() == parent.lower()] or options
            candidate = pick[0] if len(pick) == 1 else None
        if candidate and os.path.isfile(candidate):
            row.path = candidate
            relinked.append(row.id)
        else:
            still.append(row)
    db.commit()
    state = load_state()
    state["held_ids"] = sorted(held & {r.id for r in still})
    _save_state(state)
    if relinked:
        try:
            _need().rescan(db)
        except Exception as exc:
            _need().log(f"NeXroll import: scan after relink failed: {exc}", "WARNING")
    return {
        "relinked": len(relinked),
        "still_missing": len(still),
        "examples": [r.display_name or os.path.splitext(r.filename or "")[0] for r in still[:5]],
        "message": (f"Found {_plural(len(relinked), 'video')} in {new}."
                    + (f" {_plural(len(still), 'video is', 'videos are')} still missing." if still else "")),
    }


def _index_files(folder: str, limit: int) -> dict:
    found: dict = {}
    count = 0
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            found.setdefault(f.lower(), []).append(os.path.join(root, f))
            count += 1
            if count >= limit:
                return found
    return found


def status(db) -> dict:
    """The last import and the videos still waiting for their folder."""
    state = load_state()
    held = held_ids()
    rows = db.query(models.Preroll).filter(models.Preroll.id.in_(held)).all() if held else []
    waiting = [r for r in rows if not (r.path and os.path.isfile(r.path))]
    if len(waiting) != len(held):
        state["held_ids"] = [r.id for r in waiting]
        _save_state(state)
    return {
        "last": state.get("last"),
        "waiting": {"count": len(waiting),
                    "folder": guess_media_folder([r.path for r in waiting]) if waiting else None,
                    "examples": [r.display_name or os.path.splitext(r.filename or "")[0] for r in waiting[:5]]},
    }
