"""Every Plex, Jellyfin and Emby server Prerolls Max talks to.

Each server is a row in ``media_servers`` (models.MediaServer) with its own
name, address, on/off switch and, for Plex, its own folder mapping. Its token
or API key is kept in the secure store as ``media_server_<id>``.

Prerolls Max began with one server of each type, kept on the settings row
(``plex_url``, ``jellyfin_url``, ``emby_url``, ``path_mappings``) with the
secret under ``plex_token`` / ``jellyfin_api_key`` / ``emby_api_key``. A lot
of code still reads those. So the first *enabled* server of each type is the
"primary" one and is mirrored there (:func:`mirror`), and the old
``/plex/*``, ``/jellyfin/*`` and ``/emby/*`` endpoints keep acting on it.

:func:`sync_from_settings` goes the other way. It runs at startup (turning a
single-server or NeXroll database into rows) and before the server list is
read, and adopts whatever an old endpoint wrote into the settings row: a new
address, token or folder mapping for the primary server, or a first server.
It never removes a row; the old disconnect endpoints call :func:`forget_primary`.
"""
from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlsplit

from backend import models, secure_store
from backend.errors import AppError

logger = logging.getLogger("prerollsmax.servers")

TYPES = ("plex", "jellyfin", "emby")
LABELS = {"plex": "Plex", "jellyfin": "Jellyfin", "emby": "Emby"}
DEFAULT_PORT = {"plex": 32400, "jellyfin": 8096, "emby": 8096}
_URL_COLUMN = {"plex": "plex_url", "jellyfin": "jellyfin_url", "emby": "emby_url"}
_LEGACY_SECRET = {
    "plex": (secure_store.get_plex_token, secure_store.set_plex_token, None),
    "jellyfin": (secure_store.get_jellyfin_api_key, secure_store.set_jellyfin_api_key,
                 secure_store.delete_jellyfin_api_key),
    "emby": (secure_store.get_emby_api_key, secure_store.set_emby_api_key, secure_store.delete_emby_api_key),
}


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def secret_name(server_id: int) -> str:
    return f"media_server_{int(server_id)}"


def get_secret(server) -> Optional[str]:
    server_id = server if isinstance(server, int) else getattr(server, "id", None)
    if not server_id:
        return None
    try:
        return secure_store.get_secret(secret_name(server_id))
    except Exception:
        return None


def set_secret(server, value: str) -> bool:
    try:
        return bool(secure_store.set_secret(secret_name(server.id), value))
    except Exception as exc:
        logger.warning("Couldn't save the key for %s: %s", getattr(server, "name", "?"), exc)
        return False


def delete_secret(server) -> None:
    try:
        secure_store.delete_secret(secret_name(server.id))
    except Exception:
        pass


def legacy_secret(setting, kind: str) -> Optional[str]:
    """The secret the old single-server code uses for this type."""
    getter = _LEGACY_SECRET[kind][0]
    try:
        value = getter()
    except Exception:
        value = None
    if not value and kind == "plex":
        value = getattr(setting, "plex_token", None) if setting is not None else None
    return value or None


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------

def normalize_url(url: Optional[str]) -> str:
    return str(url or "").strip().rstrip("/").lower()


def host_of(url: Optional[str]) -> str:
    try:
        return (urlsplit(str(url or "")).hostname or "").lower()
    except ValueError:
        return ""


def ordered(db, kind: Optional[str] = None) -> list:
    """Servers in the order they were added, optionally of one type."""
    query = db.query(models.MediaServer)
    if kind:
        query = query.filter(models.MediaServer.type == kind)
    return query.order_by(models.MediaServer.id).all()


def enabled(db, kind: Optional[str] = None) -> list:
    return [s for s in ordered(db, kind) if s.enabled]


def find(db, server_id) -> Optional[models.MediaServer]:
    try:
        return db.query(models.MediaServer).filter(models.MediaServer.id == int(server_id)).first()
    except (TypeError, ValueError):
        return None


def label(row) -> str:
    """The server's name, for messages ("Living room Plex")."""
    return (getattr(row, "name", None) or "").strip() or LABELS.get(getattr(row, "type", ""), "Media server")


def mappings(row) -> list:
    from backend import path_mapping
    return path_mapping.load_mappings(getattr(row, "path_mappings", None))


def name_taken(db, name: str, exclude_id: Optional[int] = None) -> bool:
    wanted = " ".join(str(name or "").split()).casefold()
    return any(s.id != exclude_id and (s.name or "").casefold() == wanted for s in ordered(db))


def check_name(db, name: str, exclude_id: Optional[int] = None) -> None:
    if name_taken(db, name, exclude_id):
        message = f"There's already a media server called \"{name}\"."
        raise AppError(message, status=409, code="server_name_taken", fields={"name": message},
                       hint="Give each server its own name, like \"Living room Plex\".")


def default_name(db, kind: str, hint: Optional[str] = None) -> str:
    """"Jellyfin", then "Jellyfin 2", "Jellyfin 3"... (or ``hint`` when it's free)."""
    base = LABELS[kind]
    if hint and str(hint).strip() and not name_taken(db, str(hint).strip()):
        return " ".join(str(hint).split())[:100]
    if not name_taken(db, base):
        return base
    n = 2
    while name_taken(db, f"{base} {n}"):
        n += 1
    return f"{base} {n}"


# ---------------------------------------------------------------------------
# The primary server of each type, mirrored into the settings row
# ---------------------------------------------------------------------------

def _setting(db):
    setting = db.query(models.Setting).first()
    if setting is None:
        setting = models.Setting(plex_url=None, plex_token=None)
        db.add(setting)
        db.flush()
    return setting


def primary(db, kind: str) -> Optional[models.MediaServer]:
    rows = enabled(db, kind)
    return rows[0] if rows else None


def mirror(db, kinds=TYPES) -> None:
    """Make the first enabled server of each type the primary one and copy it
    into the settings row and the old secret slot. The caller commits."""
    setting = _setting(db)
    for kind in kinds:
        first = primary(db, kind)
        for row in ordered(db, kind):
            row.is_primary = row is first
        column = _URL_COLUMN[kind]
        getter, setter, deleter = _LEGACY_SECRET[kind]
        if first is None:
            setattr(setting, column, None)
            if kind == "plex":
                setting.plex_token = None
            elif deleter is not None:
                try:
                    deleter()
                except Exception:
                    pass
            continue
        setattr(setting, column, first.url)
        secret = get_secret(first)
        if secret:
            try:
                if getter() != secret:
                    setter(secret)
            except Exception as exc:
                logger.warning("Couldn't copy the key for %s: %s", first.name, exc)
        if kind == "plex":
            setting.plex_token = None
            setting.path_mappings = json.dumps(mappings(first))
            if first.server_identifier:
                setting.plex_server_machine_id = first.server_identifier


def _adopt(db, setting, kind: str) -> bool:
    """Take in what an old endpoint wrote for this type. True when anything changed."""
    url = (getattr(setting, _URL_COLUMN[kind], None) or "").strip()
    if not url:
        return False
    secret = legacy_secret(setting, kind)
    rows = ordered(db, kind)
    first = next((r for r in rows if r.is_primary), None) or next((r for r in rows if r.enabled), None)
    changed = False
    if first is None or normalize_url(first.url) != normalize_url(url):
        same = next((r for r in rows if normalize_url(r.url) == normalize_url(url)), None)
        if first is not None and same is None:
            first.url = url  # "Change" on the old page: the first server moves
            changed = True
        elif same is not None:
            first = same
            first.enabled = True
            changed = True
        else:
            hint = getattr(setting, "plex_server_name", None) if kind == "plex" else None
            first = models.MediaServer(type=kind, name=default_name(db, kind, hint), url=url, enabled=True)
            if kind == "plex":
                first.server_identifier = getattr(setting, "plex_server_machine_id", None)
            db.add(first)
            db.flush()
            changed = True
            logger.info("Added %s (%s) to the media server list", first.name, kind)
        for row in rows:
            if row is not first and normalize_url(row.url) == normalize_url(url):
                delete_secret(row)
                db.delete(row)
    if secret and get_secret(first) != secret:
        set_secret(first, secret)
        changed = True
    if kind == "plex":
        from backend import path_mapping
        legacy_maps = path_mapping.load_mappings(getattr(setting, "path_mappings", None))
        if legacy_maps != mappings(first):
            first.path_mappings = json.dumps(legacy_maps)
            changed = True
    return changed


def sync_from_settings(db) -> bool:
    """Adopt the settings row's servers (see the module notes), then mirror.

    Idempotent; commits only when something changed. Returns whether it did."""
    setting = db.query(models.Setting).first()
    if setting is None:
        return False
    changed = False
    for kind in TYPES:
        changed = _adopt(db, setting, kind) or changed
    before = _snapshot(setting, db)
    mirror(db)
    changed = changed or _snapshot(setting, db) != before
    db.commit()
    return changed


def _snapshot(setting, db) -> tuple:
    return (setting.plex_url, setting.jellyfin_url, setting.emby_url, setting.path_mappings,
            tuple((r.id, bool(r.is_primary)) for r in ordered(db)))


def forget_primary(db, kind: str) -> Optional[str]:
    """The old ``/<type>/disconnect``: remove the primary server of this type
    and promote the next one. Returns the removed server's name."""
    first = primary(db, kind)
    if first is None:
        return None
    name = first.name
    delete_secret(first)
    db.delete(first)
    db.flush()
    mirror(db, (kind,))
    db.commit()
    return name


# ---------------------------------------------------------------------------
# What other modules need
# ---------------------------------------------------------------------------

@dataclass
class Target:
    """A server to talk to: everything needed to make a request."""
    id: Optional[int]
    type: str
    name: str
    url: str
    token: Optional[str]
    primary: bool = False
    mappings: list = field(default_factory=list)


def target(row) -> Target:
    return Target(id=row.id, type=row.type, name=label(row), url=row.url, token=get_secret(row),
                  primary=bool(row.is_primary), mappings=mappings(row))


def plex_targets(db, setting=None, include_primary: bool = True) -> list:
    """Every enabled Plex server to write the intro list to, the primary first.

    The primary comes from the settings row, which is what the old code paths
    write to; when no server rows exist yet (older tests, a database that
    hasn't been migrated), it is the only one."""
    setting = setting if setting is not None else db.query(models.Setting).first()
    out = []
    try:
        rows = enabled(db, "plex")
    except Exception:
        rows = []
    first = next((r for r in rows if r.is_primary), None)
    if include_primary and setting is not None and getattr(setting, "plex_url", None):
        from backend import path_mapping
        out.append(Target(id=first.id if first else None, type="plex", name=label(first) if first else "Plex",
                          url=setting.plex_url, token=legacy_secret(setting, "plex"), primary=True,
                          mappings=path_mapping.mappings_from_setting(setting)))
    for row in rows:
        if row is not first:
            out.append(target(row))
    return out


def link_plugin(db, kind: str, server_identifier: str = "", key_id: Optional[int] = None,
                address: str = "") -> Optional[models.MediaServer]:
    """The Jellyfin/Emby server a plugin request comes from, or None.

    By the plugin's own API key first, then by the server id the plugin sends,
    then by the address it calls from, then the only server of that type. A
    match fills in what the row didn't know yet, so the next request matches
    by key or id."""
    kind = (kind or "").lower()
    if kind not in ("jellyfin", "emby"):
        return None
    rows = ordered(db, kind)
    if not rows:
        return None
    ident = str(server_identifier or "").replace("-", "").lower()
    found = None
    if key_id:
        found = next((r for r in rows if r.plugin_key_id == key_id), None)
    if found is None and ident:
        found = next((r for r in rows if str(r.server_identifier or "").replace("-", "").lower() == ident), None)
    if found is None and address:
        hits = [r for r in rows if host_of(r.url) == address.lower()]
        found = hits[0] if len(hits) == 1 else None
    if found is None and len(rows) == 1:
        found = rows[0]
    if found is not None:
        changed = False
        if ident and not found.server_identifier:
            found.server_identifier = server_identifier
            changed = True
        if key_id and not found.plugin_key_id:
            found.plugin_key_id = key_id
            changed = True
        if changed:
            try:
                db.commit()
            except Exception:
                db.rollback()
    return found


# The plugin and folder-mapping routes in main.py act on the first server of a
# type; the per-server routes run them inside ``acting_on`` to pick another.
_OVERRIDE: ContextVar = ContextVar("media_server_override", default=None)


@contextmanager
def acting_on(server_target: Target):
    token = _OVERRIDE.set(server_target)
    try:
        yield server_target
    finally:
        _OVERRIDE.reset(token)


def override(kind: str) -> Optional[Target]:
    picked = _OVERRIDE.get()
    return picked if picked is not None and picked.type == kind else None


def lookup(server_id: int) -> Optional[tuple]:
    """(type, name) of a server by id, for "server" playlist rules."""
    from backend.database import SessionLocal
    db = SessionLocal()
    try:
        row = find(db, server_id)
        return (row.type, label(row)) if row is not None else None
    finally:
        db.close()


def names_by_id(db) -> dict:
    try:
        return {r.id: label(r) for r in ordered(db)}
    except Exception:
        return {}


def sensitive_values(db) -> set:
    """Every server's key, for log redaction."""
    out = set()
    for row in ordered(db):
        secret = get_secret(row)
        if secret and secret.strip():
            out.add(secret.strip())
    return out
