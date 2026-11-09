"""The smart features in backups: rules, the never-play list, watch folders,
smart settings and (when the setting says so) play history.

Weights and collection cooldowns travel on the intro and collection rows of
the backup itself (``weight``, ``cooldown_hours``); :func:`clean_weight` and
:func:`clean_cooldown` check them on the way back in.

A JSON backup names collections and intros by the ids they had on the old
install. :func:`restore` takes the old-to-new id maps the main restore built
and points every rule and watch folder at the new ids. Anything that can't be
restored safely is left out and described in plain words, for the restore's
``skipped`` list. A system ZIP backup carries the whole database file instead;
:func:`strip_history_from_file` and :func:`check_watch_folders_in_file` work
on that file.
"""
from __future__ import annotations

import datetime
import json
import logging
import sqlite3
from typing import Optional

from pydantic import ValidationError

from backend import models, smart_settings
from backend.validation import clean_folder_path

logger = logging.getLogger("prerollsmax.backup")

LIST_KEYS = ("intro_rules", "intro_exclusions", "watch_folders", "play_history")
MAX_WATCH_FOLDERS = 20
MAX_EXCLUSIONS = 5000
MAX_HISTORY_ROWS = 500_000
MAX_REMEMBERED = 20000
WATCH_MODES = ("link", "copy")
HISTORY_TABLES = ("intro_plays", "playback_checks")
HISTORY_FIELDS = ("name", "path", "server_type", "server_name", "user_name", "client", "device", "item_id",
                  "item_name", "item_type", "source", "rule_name")
_FIELD_LIMITS = {"path": 1000, "client": 100, "device": 200, "item_id": 100, "server_type": 20, "item_type": 20,
                 "source": 20}


def history_in_backups(db=None) -> bool:
    """Whether backups carry play history (Settings; off unless turned on)."""
    return bool(smart_settings.get("backup_includes_history", db))


def _iso(value: Optional[datetime.datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _first_error(error: ValidationError) -> str:
    try:
        message = str(error.errors()[0].get("msg") or "")
    except Exception:
        message = ""
    return message.replace("Value error, ", "").rstrip(".") or "it isn't valid"


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def export(db, *, include_history: Optional[bool] = None) -> dict:
    """The smart-feature part of a JSON backup (merged into its top level)."""
    from backend import intro_rules

    smart_settings.clear_cache()  # read this database's settings, not a cached copy
    if include_history is None:
        include_history = history_in_backups(db)
    rules = db.query(models.IntroRule).order_by(models.IntroRule.position, models.IntroRule.id).all()
    names = {c.id: c.name for c in db.query(models.Category).all()}
    out = {
        "intro_rules": [
            {**{k: v for k, v in intro_rules.rule_dict(r).items() if k != "id"}, "position": index}
            for index, r in enumerate(rules)
        ],
        "intro_exclusions": [
            {"kind": e.kind, "value": e.value, "note": e.note, "created_at": _iso(e.created_at)}
            for e in db.query(models.IntroExclusion).order_by(models.IntroExclusion.id).all()
        ],
        "watch_folders": [
            {"path": f.path, "collection_id": f.collection_id, "collection_name": names.get(f.collection_id),
             "mode": f.mode, "recursive": bool(f.recursive), "enabled": bool(f.enabled),
             "imported_count": f.imported_count or 0, "imported_keys": _keys(f.imported_keys)}
            for f in db.query(models.WatchFolder).order_by(models.WatchFolder.id).all()
        ],
        "smart_settings": _stored_settings(db),
        "play_history_included": bool(include_history),
    }
    if include_history:
        out["play_history"] = [
            {"played_at": _iso(p.played_at), "preroll_id": p.preroll_id,
             **{field: getattr(p, field) for field in HISTORY_FIELDS}}
            for p in db.query(models.PlayEvent).order_by(models.PlayEvent.played_at, models.PlayEvent.id)
            .limit(MAX_HISTORY_ROWS).all()
        ]
    return out


def _keys(text) -> list:
    try:
        value = json.loads(text) if text else []
    except (TypeError, ValueError):
        return []
    return [k for k in value if isinstance(k, str)][-MAX_REMEMBERED:] if isinstance(value, list) else []


def _stored_settings(db) -> dict:
    """The smart settings someone changed; the rest keep following the defaults."""
    out = {}
    for row in db.query(models.FeatureSetting).order_by(models.FeatureSetting.key).all():
        if row.key not in smart_settings.DEFAULTS:
            continue
        try:
            out[row.key] = json.loads(row.value) if row.value is not None else None
        except ValueError:
            continue
    return {k: v for k, v in out.items() if v is not None}


# ---------------------------------------------------------------------------
# Weights and cooldowns (on the intro and collection rows)
# ---------------------------------------------------------------------------

def clean_weight(value, label: str, skipped: list) -> int:
    """A backup row's weight, or 5 (with a note) when it isn't 1 to 10."""
    if value is None:
        return 5
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 10 \
            or int(value) != value:
        skipped.append(f"{label}: its weight wasn't 1 to 10, so it plays normally (5)")
        return 5
    return int(value)


def clean_cooldown(value, label: str, skipped: list) -> int:
    """A backup collection's cooldown in hours, or 0 (with a note) when it isn't 0 to 720."""
    if value is None:
        return 0
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 720 \
            or int(value) != value:
        skipped.append(f'the collection "{label}": its cooldown wasn\'t 0 to 720 hours, so it has none')
        return 0
    return int(value)


# ---------------------------------------------------------------------------
# Restore (JSON backup)
# ---------------------------------------------------------------------------

def restore(db, data: dict, *, category_ids: dict, preroll_ids: dict,
            library_dir: Optional[str] = None) -> dict:
    """Put the smart features back from a cleaned JSON backup.

    Each part is replaced only when the backup has it, so an older backup
    leaves this install's rules, list, folders and settings alone. Returns
    ``{"restored": {part: count}, "skipped": [plain sentences],
    "renamed": [plain sentences]}``.
    """
    category_ids = _int_map(category_ids)
    preroll_ids = _int_map(preroll_ids)
    report = {"restored": {}, "skipped": [], "renamed": []}
    parts = (
        ("smart_settings", _restore_settings),
        ("intro_rules", lambda d, rows, skipped: _restore_rules(d, rows, skipped, category_ids, preroll_ids,
                                                                report["renamed"])),
        ("intro_exclusions", _restore_exclusions),
        ("watch_folders", lambda d, rows, skipped: _restore_watch_folders(d, rows, skipped, category_ids,
                                                                          library_dir)),
        ("play_history", lambda d, rows, skipped: _restore_history(d, rows, skipped, preroll_ids)),
    )
    for key, fn in parts:
        if key not in data or data[key] is None:
            continue
        rows = data[key]
        if key == "smart_settings" and not isinstance(rows, dict):
            report["skipped"].append("the smart settings: that part of the backup is damaged")
            continue
        if key != "smart_settings" and not isinstance(rows, list):
            report["skipped"].append(f"the {key.replace('_', ' ')}: that part of the backup is damaged")
            continue
        try:
            report["restored"][key] = fn(db, rows, report["skipped"])
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("Restoring %s failed", key)
            report["skipped"].append(f"the {key.replace('_', ' ')}: they couldn't be restored (see the log)")
    smart_settings.clear_cache()
    return report


def _int_map(mapping) -> dict:
    out = {}
    for old, new in (mapping or {}).items():
        try:
            out[int(old)] = int(new)
        except (TypeError, ValueError):
            continue
    return out


def _old_id(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _restore_settings(db, values: dict, skipped: list) -> int:
    keep = {}
    for key, value in values.items():
        if key not in smart_settings.DEFAULTS:
            skipped.append(f'the setting "{key}": this version of Prerolls Max doesn\'t have it')
            continue
        try:
            checked = smart_settings.SmartSettingsUpdate.model_validate({key: value})
        except ValidationError as error:
            skipped.append(f'the setting "{key}": {_first_error(error)}')
            continue
        cleaned = checked.model_dump(exclude_none=True)
        if key in cleaned:
            keep[key] = cleaned[key]
    db.query(models.FeatureSetting).delete(synchronize_session=False)
    db.flush()
    smart_settings.save(db, keep)
    return len(keep)


def _restore_rules(db, rows: list, skipped: list, category_ids: dict, preroll_ids: dict,
                   renamed: Optional[list] = None) -> int:
    from backend.routers.rules import MAX_RULES, RuleIn
    from backend import unique_names

    used_names: list = []

    db.query(models.IntroRule).delete(synchronize_session=False)
    ordered = sorted((r for r in rows if isinstance(r, dict)),
                     key=lambda r: (_old_id(r.get("position")) if _old_id(r.get("position")) is not None
                                    else 10 ** 6))
    if len(ordered) != len(rows):
        skipped.append(f"{len(rows) - len(ordered)} damaged rules")
    added = 0
    for row in ordered:
        name = row.get("name") if isinstance(row.get("name"), str) and row.get("name").strip() else "a rule"
        label = f'the rule "{name}"' if name != "a rule" else "a rule with no name"
        if added >= MAX_RULES:
            skipped.append(f"{label}: there can be at most {MAX_RULES} rules")
            continue
        play = dict(row.get("play") or {}) if isinstance(row.get("play"), dict) else {}
        old_collection = _old_id(play.get("collection_id"))
        if old_collection is not None:
            if old_collection not in category_ids:
                skipped.append(f"{label}: its collection isn't in the backup")
                continue
            play["collection_id"] = category_ids[old_collection]
        old_intros = play.get("preroll_ids") or []
        if old_intros:
            if not isinstance(old_intros, list):
                skipped.append(f"{label}: its list of intro videos is damaged")
                continue
            new_intros = [preroll_ids[i] for i in (_old_id(v) for v in old_intros) if i in preroll_ids]
            if not new_intros:
                skipped.append(f"{label}: none of its intro videos are in the backup")
                continue
            if len(new_intros) < len(old_intros):
                skipped.append(f"{label}: {len(old_intros) - len(new_intros)} of its intro videos aren't in "
                               "the backup, so it plays the others")
            play["preroll_ids"] = new_intros
        try:
            rule = RuleIn.model_validate({"name": row.get("name"), "enabled": row.get("enabled", True),
                                          "when": row.get("when") or {}, "play": play})
        except ValidationError as error:
            skipped.append(f"{label}: {_first_error(error)}")
            continue
        name = unique_names.numbered(rule.name, used_names, max_len=100)
        if unique_names.name_key(name) != unique_names.name_key(rule.name) and renamed is not None:
            renamed.append(unique_names.renamed_note("rule", rule.name, name))
        used_names.append(name)
        db.add(models.IntroRule(name=name, enabled=rule.enabled, position=added,
                                when_json=json.dumps(rule.when.model_dump()),
                                play_json=json.dumps(rule.play.model_dump())))
        added += 1
    return added


def _restore_exclusions(db, rows: list, skipped: list) -> int:
    from backend.routers.rules import ExclusionIn

    db.query(models.IntroExclusion).delete(synchronize_session=False)
    seen = set()
    added = 0
    for row in rows:
        if not isinstance(row, dict):
            skipped.append("a damaged never-play entry")
            continue
        try:
            entry = ExclusionIn.model_validate({"kind": row.get("kind"), "value": row.get("value"),
                                                "note": row.get("note")})
        except ValidationError as error:
            shown = row.get("value") if isinstance(row.get("value"), str) else "an entry"
            skipped.append(f'the never-play entry "{str(shown)[:80]}": {_first_error(error)}')
            continue
        key = (entry.kind, entry.value.strip().lower())
        if key in seen:
            continue
        if added >= MAX_EXCLUSIONS:
            skipped.append(f"the never-play list holds at most {MAX_EXCLUSIONS:,} entries; the rest were left out")
            break
        seen.add(key)
        created = _when(row.get("created_at"))
        db.add(models.IntroExclusion(kind=entry.kind, value=entry.value, note=(entry.note or "").strip() or None,
                                     **({"created_at": created} if created else {})))
        added += 1
    return added


def check_watch_folder(row: dict, library_dir: Optional[str] = None) -> tuple:
    """(cleaned path, mode) or raises ValueError with a plain reason."""
    path = clean_folder_path(row.get("path"), what="watch folder")
    mode = row.get("mode") or "link"
    if mode not in WATCH_MODES:
        raise ValueError("its way of adding files isn't one Prerolls Max knows")
    if library_dir:
        from backend.watch_folders import inside
        try:
            if inside(path, library_dir):
                raise ValueError("it's inside the Prerolls Max library, which is checked for new files on its own")
        except (TypeError, OSError):
            pass
    return path, mode


def _restore_watch_folders(db, rows: list, skipped: list, category_ids: dict, library_dir: Optional[str]) -> int:
    from backend.watch_folders import inside

    db.query(models.WatchFolder).delete(synchronize_session=False)
    kept: list = []
    for row in rows:
        if not isinstance(row, dict):
            skipped.append("a damaged watch folder")
            continue
        shown = str(row.get("path") or "a watch folder with no path")[:200]
        try:
            path, mode = check_watch_folder(row, library_dir)
        except ValueError as problem:
            skipped.append(f"the watch folder {shown}: {str(problem).rstrip('.')}")
            continue
        if any(inside(path, other) or inside(other, path) for other in kept):
            skipped.append(f"the watch folder {shown}: it overlaps another watch folder")
            continue
        if len(kept) >= MAX_WATCH_FOLDERS:
            skipped.append(f"the watch folder {shown}: there can be at most {MAX_WATCH_FOLDERS} watch folders")
            continue
        collection_id = None
        old_collection = _old_id(row.get("collection_id"))
        if old_collection is not None:
            collection_id = category_ids.get(old_collection)
            if collection_id is None:
                skipped.append(f"the watch folder {shown}: its collection isn't in the backup, so new files "
                               "are added without one")
        count = row.get("imported_count")
        db.add(models.WatchFolder(
            path=path, mode=mode, collection_id=collection_id,
            recursive=row.get("recursive") is not False, enabled=row.get("enabled") is not False,
            imported_count=count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else 0,
            imported_keys=json.dumps(_keys(json.dumps(row.get("imported_keys") or [])))))
        kept.append(path)
    return len(kept)


def _when(value) -> Optional[datetime.datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def _text(value, limit: int = 200) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, bool)):
        return None
    text = " ".join(str(value).split())
    if any(ord(c) < 32 for c in text):
        return None
    return text[:limit] or None


def _restore_history(db, rows: list, skipped: list, preroll_ids: dict) -> int:
    db.query(models.PlayEvent).delete(synchronize_session=False)
    batch, bad, added = [], 0, 0
    for row in rows[:MAX_HISTORY_ROWS]:
        played_at = _when(row.get("played_at")) if isinstance(row, dict) else None
        if played_at is None:
            bad += 1
            continue
        old = _old_id(row.get("preroll_id"))
        batch.append({"played_at": played_at, "preroll_id": preroll_ids.get(old) if old is not None else None,
                      **{f: _text(row.get(f), _FIELD_LIMITS.get(f, 200)) for f in HISTORY_FIELDS}})
        if len(batch) >= 2000:
            db.bulk_insert_mappings(models.PlayEvent, batch)
            added += len(batch)
            batch = []
    if batch:
        db.bulk_insert_mappings(models.PlayEvent, batch)
        added += len(batch)
    if bad:
        skipped.append(f"{bad} play history entries with no usable time")
    if len(rows) > MAX_HISTORY_ROWS:
        skipped.append(f"the oldest-kept {len(rows) - MAX_HISTORY_ROWS:,} play history entries past the "
                       f"first {MAX_HISTORY_ROWS:,}")
    return added


# ---------------------------------------------------------------------------
# The database file in a system ZIP backup
# ---------------------------------------------------------------------------

def _tables(con) -> set:
    return {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def strip_history_from_file(db_file: str) -> None:
    """Empty the play-history tables in a copy of the database (for a backup)."""
    con = sqlite3.connect(db_file)
    try:
        present = _tables(con)
        for table in HISTORY_TABLES:
            if table in present:
                con.execute(f"DELETE FROM {table}")
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def check_watch_folders_in_file(db_file: str, library_dir: Optional[str] = None) -> list:
    """Remove watch folders with an unusable path from a restored database file.

    Returns plain sentences for the restore's ``skipped`` list. Works on the
    extracted file with sqlite3, before the application opens it.
    """
    skipped: list = []
    con = sqlite3.connect(db_file)
    try:
        if "watch_folders" not in _tables(con):
            return skipped
        for rowid, path, mode in con.execute("SELECT id, path, mode FROM watch_folders").fetchall():
            shown = str(path or "a watch folder with no path")[:200]
            try:
                cleaned, _mode = check_watch_folder({"path": path, "mode": mode}, library_dir)
            except ValueError as problem:
                con.execute("DELETE FROM watch_folders WHERE id = ?", (rowid,))
                skipped.append(f"the watch folder {shown}: {str(problem).rstrip('.')}")
                continue
            if cleaned != path:
                con.execute("UPDATE watch_folders SET path = ? WHERE id = ?", (cleaned, rowid))
        con.commit()
    finally:
        con.close()
    return skipped
