"""Pure helpers for preserving database references across JSON restores."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any


def normalize_preroll_id(value: Any) -> int | None:
    """Return a positive integer ID without accepting lossy coercions."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
        try:
            parsed = int(value)
        except ValueError:
            return None
        return parsed if parsed > 0 else None
    return None


def _normalized_id_map(id_map: Mapping[Any, Any] | None) -> dict[int, int]:
    normalized: dict[int, int] = {}
    for old_value, new_value in (id_map or {}).items():
        old_id = normalize_preroll_id(old_value)
        new_id = normalize_preroll_id(new_value)
        if old_id is not None and new_id is not None:
            normalized[old_id] = new_id
    return normalized


def _remap_id_values(values: Any, id_map: Mapping[Any, Any] | None) -> list[int]:
    """Remap a list of old IDs, explicitly dropping invalid/unmapped values."""
    if not isinstance(values, (list, tuple)):
        return []
    normalized_map = _normalized_id_map(id_map)
    remapped: list[int] = []
    for value in values:
        old_id = normalize_preroll_id(value)
        if old_id is not None and old_id in normalized_map:
            remapped.append(normalized_map[old_id])
    return remapped


def remap_preroll_ids_json(raw_value: Any, id_map: Mapping[Any, Any] | None) -> str | None:
    """Remap a schedule's JSON preroll list, returning ``None`` when empty.

    Malformed or unmapped references are removed instead of retained. Retaining
    an old numeric ID is unsafe because SQLite may assign that ID to a different
    preroll while rebuilding the table.
    """
    if raw_value is None or raw_value == "":
        return None
    try:
        values = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    remapped = _remap_id_values(values, id_map)
    return json.dumps(remapped) if remapped else None


def remap_sequence_blocks(
    raw_blocks: Any,
    preroll_id_map: Mapping[Any, Any] | None,
    category_id_map: Mapping[Any, Any] | None = None,
) -> list[Any]:
    """Copy sequence blocks and remap their database-backed references.

    Fixed blocks use preroll IDs. Random and sequential blocks use category
    IDs (including the legacy camelCase spelling). Unknown block types and
    their data are preserved verbatim. A category-backed block with an
    unmapped numeric reference is removed entirely: leaving the block without
    that field would let schedule execution fall back to its top-level category
    and could still play the wrong content.

    ``category_id_map=None`` means category references are outside the caller's
    scope and are left untouched. Passing an empty map explicitly removes all
    numeric category references, which is the safe behavior for a legacy
    restore that supplied no usable category mappings.
    """
    if isinstance(raw_blocks, str):
        try:
            raw_blocks = json.loads(raw_blocks)
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
    if not isinstance(raw_blocks, list):
        return []

    blocks = copy.deepcopy(raw_blocks)
    normalized_preroll_map = _normalized_id_map(preroll_id_map)
    normalized_category_map = (
        _normalized_id_map(category_id_map) if category_id_map is not None else None
    )
    remapped_blocks: list[Any] = []
    for block in blocks:
        if not isinstance(block, dict):
            remapped_blocks.append(block)
            continue
        block_type = str(block.get("type", "")).lower()

        # An Advanced-mode alternative is a block in its own right and carries
        # the same kinds of reference. One that cannot be remapped is dropped,
        # so an unmet condition skips the slot instead of playing the wrong thing.
        otherwise = block.get("otherwise")
        if isinstance(otherwise, dict):
            kept = remap_sequence_blocks([otherwise], preroll_id_map, category_id_map)
            if kept:
                block["otherwise"] = kept[0]
            else:
                block.pop("otherwise", None)

        if block_type == "fixed":
            if "preroll_ids" in block:
                block["preroll_ids"] = _remap_id_values(
                    block.get("preroll_ids"),
                    normalized_preroll_map,
                )

            if "preroll_id" in block:
                old_id = normalize_preroll_id(block.get("preroll_id"))
                new_id = (
                    normalized_preroll_map.get(old_id) if old_id is not None else None
                )
                if new_id is None:
                    block.pop("preroll_id", None)
                else:
                    block["preroll_id"] = new_id

        if block_type in {"random", "sequential"} and normalized_category_map is not None:
            reference_field = (
                "category_id" if "category_id" in block
                else "categoryId" if "categoryId" in block
                else None
            )
            if reference_field is not None:
                old_id = normalize_preroll_id(block.get(reference_field))
                new_id = (
                    normalized_category_map.get(old_id) if old_id is not None else None
                )
                if new_id is None:
                    continue
                block["category_id"] = new_id
                block.pop("categoryId", None)

        remapped_blocks.append(block)

    return remapped_blocks


def remap_fixed_preroll_blocks(
    raw_blocks: Any,
    id_map: Mapping[Any, Any] | None,
) -> list[Any]:
    """Backward-compatible wrapper for callers remapping only fixed blocks."""
    return remap_sequence_blocks(raw_blocks, id_map)


def remap_sequence_json(
    raw_value: Any,
    preroll_id_map: Mapping[Any, Any] | None,
    category_id_map: Mapping[Any, Any] | None = None,
) -> str | None:
    """Remap database-backed references in a schedule's sequence JSON."""
    if raw_value is None or raw_value == "":
        return None
    blocks = remap_sequence_blocks(raw_value, preroll_id_map, category_id_map)
    return json.dumps(blocks)


# ---------------------------------------------------------------------------
# Checking a backup before anything is deleted
# ---------------------------------------------------------------------------

BACKUP_LIST_KEYS = (
    "categories", "genre_maps", "prerolls", "schedules", "holiday_presets",
    "saved_sequences", "ignored_paths", "community_templates", "navigation_favorites",
    "radarr_servers", "sonarr_servers",
    "intro_rules", "intro_exclusions", "watch_folders", "play_history",
)
BACKUP_CONTENT_KEYS = ("categories", "prerolls", "schedules", "saved_sequences", "settings")
RESTORABLE_VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mkv", ".mov", ".avi", ".m4v", ".webm", ".wmv", ".flv", ".ts", ".mpg", ".mpeg",
})


class BackupProblem(ValueError):
    """The upload isn't a backup Prerolls Max can restore; the message says why."""


def _has_bad_chars(text: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in text)


def _has_parent_step(text: str) -> bool:
    return ".." in text.replace("\\", "/").split("/")


def _clean_text(value: Any, max_len: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    if not text or len(text) > max_len or _has_bad_chars(text):
        return None
    return text


def _is_absolute_path(path: str) -> bool:
    return (path.startswith("/") or path.startswith("\\\\")
            or (len(path) > 2 and path[0].isalpha() and path[1] == ":" and path[2] in "\\/"))


def _clean_preroll_row(row: dict) -> tuple[dict | None, str | None]:
    filename = row.get("filename")
    label = filename if isinstance(filename, str) and filename.strip() else "a video with no name"
    if (not isinstance(filename, str) or not filename.strip() or len(filename) > 255
            or _has_bad_chars(filename) or "/" in filename or "\\" in filename):
        return None, f"{label}: the file name isn't valid"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in RESTORABLE_VIDEO_EXTENSIONS:
        return None, f"{filename}: not a video file Prerolls Max can play"
    path = row.get("path")
    if path is not None:
        if (not isinstance(path, str) or not path.strip() or len(path) > 4096 or _has_bad_chars(path)
                or _has_parent_step(path)):
            return None, f"{filename}: its folder path isn't valid"
        if not _is_absolute_path(path):
            return None, f"{filename}: its path isn't a full path"
        if not path.lower().endswith(ext):
            return None, f"{filename}: its path doesn't point at a video file"
    cleaned = dict(row)
    thumb = row.get("thumbnail")
    if thumb is not None and (not isinstance(thumb, str) or _has_bad_chars(thumb) or _has_parent_step(thumb)
                              or len(thumb) > 4096):
        cleaned["thumbnail"] = None
    for key in ("display_name", "description", "tags"):
        value = row.get(key)
        if value is not None and not isinstance(value, str):
            cleaned[key] = None
    return cleaned, None


def clean_backup_payload(data: Any) -> tuple[dict, list[str]]:
    """Check a JSON backup before the restore deletes anything.

    Returns a cleaned copy and a list of plain sentences naming what will be
    left out. Raises :class:`BackupProblem` when the file isn't a backup at all,
    so nothing is deleted. Rows that would put an unusable name or path into
    the database (``..`` steps, control characters, relative paths, files that
    aren't videos) are left out rather than trusted.
    """
    if not isinstance(data, dict):
        raise BackupProblem("That file isn't a Prerolls Max backup.")
    if not any(key in data for key in BACKUP_CONTENT_KEYS):
        raise BackupProblem("That file isn't a Prerolls Max backup: it has no collections, videos, "
                            "schedules or settings.")
    out = dict(data)
    skipped: list[str] = []
    for key in BACKUP_LIST_KEYS:
        if key not in data or data[key] is None:
            continue
        rows = data[key]
        if not isinstance(rows, list):
            raise BackupProblem(f"That backup is damaged: the {key.replace('_', ' ')} part isn't a list.")
        out[key] = [r for r in rows if isinstance(r, dict)]
        if len(out[key]) != len(rows):
            skipped.append(f"{len(rows) - len(out[key])} damaged {key.replace('_', ' ')} entries")
    settings = data.get("settings")
    if settings is not None and not isinstance(settings, dict):
        raise BackupProblem("That backup is damaged: the settings part isn't a group of settings.")

    if "categories" in out:
        categories, seen = [], set()
        for row in out["categories"] or []:
            name = _clean_text(row.get("name"), 100)
            if not name:
                skipped.append("a collection with a missing or unusable name")
                continue
            if name.casefold() in seen:
                skipped.append(f'a second collection called "{name}"')
                continue
            seen.add(name.casefold())
            categories.append({**row, "name": name})
        out["categories"] = categories

    if "prerolls" in out:
        prerolls = []
        for row in out["prerolls"] or []:
            cleaned, problem = _clean_preroll_row(row)
            if cleaned is None:
                skipped.append(problem)
            else:
                prerolls.append(cleaned)
        out["prerolls"] = prerolls

    for key, what in (("schedules", "schedule"), ("saved_sequences", "playlist"), ("holiday_presets", "holiday")):
        if key not in out:
            continue
        kept = []
        for row in out[key] or []:
            name = _clean_text(row.get("name"), 200)
            if not name:
                skipped.append(f"a {what} with a missing or unusable name")
                continue
            kept.append({**row, "name": name})
        out[key] = kept

    if "ignored_paths" in out:
        out["ignored_paths"] = [r for r in out["ignored_paths"] or []
                                if isinstance(r.get("path"), str) and not _has_bad_chars(r["path"])
                                and not _has_parent_step(r["path"])]
    for key in ("radarr_servers", "sonarr_servers"):
        if key not in out:
            continue
        kept = []
        for r in out[key] or []:
            url = r.get("url")
            if isinstance(url, str) and url.lower().startswith(("http://", "https://")) and not _has_bad_chars(url):
                kept.append(r)
            else:
                skipped.append(f"a {key.split('_')[0].title()} server whose address isn't a web address")
        out[key] = kept
    return out, skipped
