"""Read a NeXroll install's data, wherever it is, as one NeXroll backup.

Three places it can come from (Settings > Moving from NeXroll):

* a ``nexroll.db`` on this computer (``backup_from_db``). The file is copied
  with SQLite's backup API from a read-only connection first; NeXroll's own
  file is never written to.
* a backup file from NeXroll's Settings > Backup & Restore (``backup_from_upload``): the
  JSON settings backup, or the full ZIP with the videos.
* a NeXroll that's running (``fetch_backup``): its own ``GET /backup/database``,
  with an ``X-Api-Key`` header when its login is on.

Each gives the same shape NeXroll's ``GET /backup/database`` returns
(schema_version 5), plus ``_nexroll``: what stays behind (user accounts, API
keys) and where the videos were. nexroll_import.py takes it from there.
"""
from __future__ import annotations

import base64
import json
import os
import posixpath
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from typing import Optional

import requests

from backend import validation
from backend.brand import LEGACY_DB_FILENAME
from backend.errors import AppError, bad_input, rejected_credentials, unreachable

# A settings backup is small (a big NeXroll library is a few MB). Anything far
# bigger isn't one.
MAX_JSON_BYTES = 64 * 1024 * 1024
FETCH_TIMEOUT = (5, 60)
SECRET_NAMES = ("plex_token", "jellyfin_api_key", "emby_api_key")
BOOL_COLUMNS = {"managed", "enabled", "exclude_from_matching", "apply_to_plex", "is_system", "playlist",
                "is_active", "blend_enabled", "exclusive", "is_recurring", "is_public"}
LIST_TABLES = ("categories", "schedules", "holiday_presets", "genre_maps", "ignored_paths",
               "community_templates", "radarr_servers", "sonarr_servers")


class Source(dict):
    """A backup dict; ``_nexroll`` holds the extra facts."""


# ---------------------------------------------------------------------------
# Where NeXroll keeps its data
# ---------------------------------------------------------------------------

def known_locations(platform: Optional[str] = None, environ=None, own_dir: Optional[str] = None) -> list:
    """Folders where a NeXroll database usually is, most likely first.

    Windows: %ProgramData%\\NeXroll, %LOCALAPPDATA%\\NeXroll, %APPDATA%\\NeXroll.
    Everywhere: Prerolls Max's own data folder (Docker people often keep the
    old /data volume), and the NeXroll folders NEXROLL_DB_DIR names.
    """
    platform = platform if platform is not None else sys.platform
    env = os.environ if environ is None else environ
    out = []
    if platform.startswith("win"):
        for var in ("ProgramData", "LOCALAPPDATA", "APPDATA"):
            base = env.get(var)
            if base:
                out.append(os.path.join(base, "NeXroll"))
    for var in ("NEXROLL_DB_DIR",):
        value = (env.get(var) or "").strip()
        if value:
            out.append(value)
    if own_dir:
        out.append(own_dir)
    if not platform.startswith("win"):
        out += ["/nexroll", "/nexroll-data", "/data/nexroll"]
    seen, unique = set(), []
    for p in out:
        key = os.path.normcase(os.path.abspath(p))
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def find_databases(platform: Optional[str] = None, environ=None, own_dir: Optional[str] = None) -> list:
    """[{path, folder, size, modified}] for every nexroll.db found."""
    found = []
    for folder in known_locations(platform, environ, own_dir):
        path = os.path.join(folder, LEGACY_DB_FILENAME)
        try:
            if os.path.isfile(path):
                st = os.stat(path)
                found.append({"path": path, "folder": folder, "size": st.st_size, "modified": st.st_mtime})
        except OSError:
            continue
    return found


def database_in(folder_text: str) -> str:
    """The nexroll.db in a folder the person typed (or the file itself).

    Raises a 422 with a plain message for the ``path`` field."""
    text = (folder_text or "").strip().strip('"').strip("'")
    if text.lower().endswith(".db"):
        text = os.path.dirname(text) or text
    try:
        folder = validation.clean_folder_path(text, what="folder")
    except ValueError as exc:
        raise bad_input(str(exc), field="path")
    if not os.path.isdir(folder):
        raise bad_input(f"Prerolls Max can't see a folder at {folder}.", field="path",
                        hint="In Docker, add the old NeXroll data folder as a volume first, "
                             "for example /nexroll, and enter that path here.")
    path = os.path.join(folder, LEGACY_DB_FILENAME)
    if not os.path.isfile(path):
        raise bad_input(f"There's no {LEGACY_DB_FILENAME} in {folder}.", field="path",
                        hint="Pick the folder NeXroll kept its data in: the one with nexroll.db in it.")
    return path


# ---------------------------------------------------------------------------
# From a nexroll.db
# ---------------------------------------------------------------------------

def snapshot(src: str, dest: str) -> None:
    """Copy a SQLite database (with whatever is still in its -wal file)
    through a read-only connection. The source is never written."""
    try:
        source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10)
        source.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.Error:
        # A folder we may not write to (no -shm next to it): read the file as it is.
        source = sqlite3.connect(f"file:{src}?mode=ro&immutable=1", uri=True, timeout=10)
    try:
        target = sqlite3.connect(dest)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def _tables(con) -> set:
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _rows(con, table: str, tables: set) -> list:
    if table not in tables:
        return []
    con.row_factory = sqlite3.Row
    try:
        out = []
        for row in con.execute(f'SELECT * FROM "{table}"'):
            item = dict(row)
            for key in BOOL_COLUMNS & item.keys():
                if item[key] is not None:
                    item[key] = bool(item[key])
            out.append(item)
        return out
    finally:
        con.row_factory = None


def _count(con, table: str, tables: set) -> int:
    if table not in tables:
        return 0
    try:
        return int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
    except sqlite3.Error:
        return 0


def read_secrets_file(folder: str) -> dict:
    """NeXroll's keys from its secrets.json (Docker and Linux keep them there,
    base64 encoded). Windows keeps them in Credential Manager, which Prerolls
    Max reads by itself, or DPAPI-encrypted, which only that machine can open."""
    path = os.path.join(folder, "secrets.json")
    out = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return out
    if not isinstance(data, dict):
        return out
    for name in SECRET_NAMES:
        entry = data.get(name)
        if isinstance(entry, dict):
            entry = entry.get("b64")
        if not isinstance(entry, str) or not entry.strip():
            continue
        try:
            value = base64.b64decode(entry, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if value.strip() and value.isprintable():
            out[name] = value.strip()
    return out


def backup_from_db(path: str, *, read_secrets: bool = True) -> Source:
    """A NeXroll backup built from its database file (copied first)."""
    fd, copy = tempfile.mkstemp(prefix="nexroll-import-", suffix=".db")
    os.close(fd)
    try:
        try:
            snapshot(path, copy)
        except sqlite3.Error as exc:
            raise AppError("Prerolls Max couldn't read that NeXroll database.", status=422,
                           code="nexroll_db_unreadable",
                           hint="Stop NeXroll and try again. If it still fails, make a backup in NeXroll "
                                "(Settings > Backup & Restore) and upload that instead.") from exc
        con = sqlite3.connect(copy)
        try:
            tables = _tables(con)
            if "prerolls" not in tables or "categories" not in tables:
                raise AppError("That file isn't a NeXroll database.", status=422, code="not_nexroll",
                               hint="Pick the nexroll.db from NeXroll's data folder.")
            data = _from_tables(con, tables)
        finally:
            con.close()
    finally:
        for p in (copy, copy + "-wal", copy + "-shm"):
            try:
                os.unlink(p)
            except OSError:
                pass
    if read_secrets:
        data["credentials"] = read_secrets_file(os.path.dirname(path))
    data["_nexroll"]["source"] = "database"
    data["_nexroll"]["where"] = path
    return data


def _from_tables(con, tables: set) -> Source:
    categories = _rows(con, "categories", tables)
    names = {c.get("id"): c.get("name") for c in categories}
    links = {}
    for row in _rows(con, "preroll_categories", tables):
        links.setdefault(row.get("preroll_id"), []).append(row.get("category_id"))
    prerolls = []
    for row in _rows(con, "prerolls", tables):
        ids = links.get(row.get("id")) or ([row["category_id"]] if row.get("category_id") else [])
        row["categories"] = [{"id": i, "name": names.get(i)} for i in ids if names.get(i)]
        prerolls.append(row)
    sequences = []
    for row in _rows(con, "saved_sequences", tables):
        try:
            row["blocks"] = json.loads(row.get("blocks") or "[]")
        except (TypeError, ValueError):
            row["blocks"] = []
        sequences.append(row)
    favorites = [{"page": r.get("page")} for r in _rows(con, "navigation_favorites", tables)
                 if r.get("page") and (r.get("scope") in (None, "local"))]
    settings_rows = _rows(con, "settings", tables)
    settings = dict(settings_rows[0]) if settings_rows else {}
    settings.pop("id", None)
    data = Source({
        "schema_version": 5,
        "categories": categories,
        "prerolls": prerolls,
        "saved_sequences": sequences,
        "navigation_favorites": favorites,
        "settings": settings,
        "credentials": {},
        "exported_by_version": "NeXroll database",
    })
    for table in LIST_TABLES:
        if table != "categories":
            data[table] = _rows(con, table, tables)
    data["_nexroll"] = {"users": _count(con, "users", tables), "api_keys": _count(con, "api_keys", tables)}
    return data


# ---------------------------------------------------------------------------
# From an uploaded backup
# ---------------------------------------------------------------------------

def _safe_member(name: str) -> Optional[str]:
    """A ZIP entry's path when it's safe to extract, else None."""
    norm = name.replace("\\", "/")
    if not norm or norm.startswith("/") or (len(norm) > 1 and norm[1] == ":"):
        return None
    parts = [p for p in norm.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _check_backup_json(data) -> Source:
    if not isinstance(data, dict) or not any(k in data for k in ("prerolls", "categories", "schedules", "settings")):
        raise AppError("That file isn't a NeXroll backup.", status=422, code="not_a_backup",
                       hint="In NeXroll, open Settings > Backup & Restore, press Download Database Backup "
                            "(or Download System Backup for the videos too), then pick that file.")
    out = Source(data)
    out.setdefault("_nexroll", {})
    return out


def backup_from_json_bytes(raw: bytes) -> Source:
    if len(raw) > MAX_JSON_BYTES:
        raise AppError("That file is too big to be a NeXroll settings backup.", status=413, code="file_too_large",
                       hint="Pick the .json or .zip file NeXroll's Settings > Backup & Restore made.")
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        raise AppError("That file isn't a NeXroll backup.", status=422, code="not_a_backup",
                       hint="Pick the .json or .zip file NeXroll's Settings > Backup & Restore made.")
    return _check_backup_json(data)


def backup_from_upload(path: str, filename: str, staging: str) -> Source:
    """A NeXroll backup from an uploaded .json or .zip. A ZIP's videos are
    extracted into ``staging/prerolls`` and noted in ``_nexroll.files_root``."""
    lower = (filename or "").lower()
    if lower.endswith(".json"):
        with open(path, "rb") as fh:
            raw = fh.read(MAX_JSON_BYTES + 1)
        data = backup_from_json_bytes(raw)
        data["_nexroll"].update(source="upload", where=filename)
        return data
    if not zipfile.is_zipfile(path):
        raise AppError("That file isn't a NeXroll backup.", status=422, code="not_a_backup",
                       hint="Pick the .json or .zip file NeXroll's Settings > Backup & Restore made.")
    with zipfile.ZipFile(path) as zf:
        members = {}
        for info in zf.infolist():
            safe = _safe_member(info.filename)
            if safe and not info.is_dir():
                members[safe] = info
        data = None
        if "database/nexroll_data.json" in members:
            info = members["database/nexroll_data.json"]
            if info.file_size > MAX_JSON_BYTES:
                raise AppError("The settings inside that ZIP are too big to be NeXroll's.", status=413,
                               code="file_too_large")
            data = backup_from_json_bytes(zf.read(info))
        elif "database/nexroll.db" in members:
            fd, db_copy = tempfile.mkstemp(prefix="nexroll-zip-", suffix=".db")
            os.close(fd)
            try:
                with zf.open(members["database/nexroll.db"]) as src, open(db_copy, "wb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                data = backup_from_db(db_copy, read_secrets=False)
            finally:
                try:
                    os.unlink(db_copy)
                except OSError:
                    pass
        if data is None:
            raise AppError("That ZIP isn't a NeXroll full backup.", status=422, code="not_a_backup",
                           hint="It has no database folder. Pick the ZIP NeXroll's Settings > Backup & Restore made.")
        videos = [m for m in members if m.startswith("prerolls/")]
        root = os.path.join(staging, "prerolls")
        extracted = []
        for name in videos:
            rel = name[len("prerolls/"):]
            target = os.path.join(root, *rel.split("/"))
            if not os.path.abspath(target).startswith(os.path.abspath(root) + os.sep):
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(members[name]) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
            extracted.append(rel)
    data["_nexroll"].update(source="upload", where=filename, files_root=root if extracted else None,
                            files=extracted)
    return data


# ---------------------------------------------------------------------------
# From a NeXroll that's running
# ---------------------------------------------------------------------------

def _get(url: str, headers: dict, timeout=FETCH_TIMEOUT, max_bytes: int = MAX_JSON_BYTES):
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=False, stream=True)
    body = b""
    try:
        for chunk in r.iter_content(64 * 1024):
            body += chunk
            if len(body) > max_bytes:
                raise AppError("NeXroll sent more than a settings backup should be.", status=502,
                               code="nexroll_reply_too_large")
    finally:
        r.close()
    return r.status_code, body


def _signin_problem(key: str) -> AppError:
    if not key:
        return AppError("NeXroll asks for a sign-in.", status=422, code="nexroll_key_required",
                        fields={"api_key": "Enter a NeXroll API key."},
                        hint="In NeXroll, open Settings > API Keys, make a key with read access, "
                             "and paste it here.")
    err = rejected_credentials("NeXroll", what="API key",
                               hint="Check the key in NeXroll's Settings > API Keys. It needs read access "
                                    "and must be switched on.")
    err.fields = {"api_key": "NeXroll turned this key down."}
    return err


def check_running(address: str, api_key: Optional[str] = None) -> tuple:
    """Is NeXroll at this address, and does it let us in? (base, headers).

    Quick: its health check, its page title, and its small backup status
    (behind NeXroll's sign-in like the backup itself). Problems are field
    messages for ``url`` or ``api_key``."""
    try:
        base = validation.clean_server_url(address, service="NeXroll", default_port=9393)
    except ValueError as exc:
        raise bad_input(str(exc), field="url")
    headers = {"Accept": "application/json", "User-Agent": "Prerolls Max (moving from NeXroll)"}
    key = (api_key or "").strip()
    if key:
        if len(key) > 512 or any(c.isspace() for c in key) or not key.isprintable():
            raise bad_input("That doesn't look like a NeXroll API key.", field="api_key",
                            hint="NeXroll's keys start with nx_. Copy it again from NeXroll's Settings > API Keys.")
        headers["X-Api-Key"] = key
    try:
        status, _body = _get(base + "/health", {"Accept": "application/json"}, timeout=(5, 10), max_bytes=4096)
        _page_status, page = _get(base + "/", {"Accept": "text/html"}, timeout=(5, 10), max_bytes=256 * 1024)
    except requests.exceptions.SSLError:
        raise unreachable("NeXroll", base, code="nexroll_unreachable",
                          hint="Try the address with http:// instead of https://.")
    except requests.RequestException:
        raise unreachable("NeXroll", base, code="nexroll_unreachable",
                          hint="Check that NeXroll is running and the address and port are right (NeXroll uses "
                               "9393). If Prerolls Max runs in Docker, use the computer's IP address, not localhost.")
    text = page.decode("utf-8", "replace").lower()
    if status != 200 or "<title>nexroll" not in text:
        if "prerolls max" in text:
            raise bad_input("That's Prerolls Max, not NeXroll.", field="url",
                            hint="Enter the address NeXroll runs on. If it ran on the same port before, "
                                 "use one of the other two ways instead.")
        raise bad_input(f"Something answered at {base}, but it isn't NeXroll.", field="url",
                        hint="Check the port: NeXroll uses 9393 unless you changed it.")
    try:
        status, _body = _get(base + "/backup/status", headers, timeout=(5, 10), max_bytes=4096)
    except requests.RequestException:
        status = 200  # an older NeXroll without it: the backup itself will tell
    if status == 401:
        raise _signin_problem(key)
    return base, headers


def fetch_backup(address: str, api_key: Optional[str] = None) -> Source:
    """NeXroll's own settings backup, through its API."""
    base, headers = check_running(address, api_key)
    key = headers.get("X-Api-Key", "")
    try:
        status, body = _get(base + "/backup/database", headers)
    except AppError:
        raise
    except requests.RequestException:
        raise unreachable("NeXroll", base, code="nexroll_unreachable",
                          hint="NeXroll stopped answering while it made the backup. Try again.")
    if status == 401:
        raise _signin_problem(key)
    if status != 200:
        raise AppError(f"NeXroll couldn't make a backup (it answered {status}).", status=502,
                       code="nexroll_backup_failed",
                       hint="Make a backup in NeXroll's Settings > Backup & Restore and upload the file instead.")
    data = backup_from_json_bytes(body)
    data["_nexroll"].update(source="running", where=base, keys_left_out=bool(key))
    return data


def guess_media_folder(paths) -> Optional[str]:
    """The folder most of these video paths share, in their own style."""
    paths = [p for p in paths if isinstance(p, str) and p.strip()]
    if not paths:
        return None
    windows = validation.path_style(paths[0]) == "windows"
    split = [p.replace("\\", "/").split("/")[:-1] for p in paths]
    common = []
    for parts in zip(*split):
        if all(x.lower() == parts[0].lower() if windows else x == parts[0] for x in parts):
            common.append(parts[0])
        else:
            break
    if not common or common == [""]:
        return None
    folder = "/".join(common)
    if windows:
        folder = folder.replace("/", "\\")
        if len(folder) == 2 and folder.endswith(":"):
            folder += "\\"
    return folder or posixpath.sep
