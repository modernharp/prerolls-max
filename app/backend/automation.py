"""The background loop for the smart features.

Runs on its own daemon thread, separate from the scheduler:

- every 15 s, while a Plex server is set up: what Plex is playing (play
  history and the missed-intro check). Plex is asked through the scheduler's
  playback-guard probe, the only reader of /status/sessions, which shares
  each answer through plex_sessions.FEED (see plex_sessions.py);
- every 30 s: Jellyfin/Emby sessions (playbacks that never asked the plugin),
  and the watch folders;
- every 6 h: forget play history older than the retention setting.

Every step is guarded: a slow or failing server never stops the others, and
nothing here can affect the scheduler.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Callable, Optional

import requests

from backend import models, play_history, plex_sessions, smart_settings
from backend.database import SessionLocal
from backend.watch_folders import WATCHER, Deps as WatchDeps

logger = logging.getLogger("prerollsmax.automation")

PLEX_EVERY = plex_sessions.EVERY_SECONDS
SERVERS_EVERY = 30
FOLDERS_EVERY = 30
PRUNE_EVERY = 6 * 3600
INDEX_EVERY = 60

# Which servers' sessions were read successfully, for /api/health/intros.
WATCHING: dict = {}
_watch_lock = threading.Lock()


def _note(server: str, ok: bool, message: str = "") -> None:
    with _watch_lock:
        WATCHING[server] = {"ok": ok, "at": time.time(), "message": message}


def watching_state(now: Optional[float] = None) -> dict:
    now = time.time() if now is None else now
    with _watch_lock:
        return {k: {"ok": v["ok"] and now - v["at"] < 300, "message": v["message"],
                    "seconds_ago": int(now - v["at"])} for k, v in WATCHING.items()}


def _servers() -> dict:
    from backend.routers.capabilities import _configured_servers
    try:
        return _configured_servers()
    except Exception:
        return {}


def _targets(kind: str, conf: Optional[dict] = None) -> list:
    """Every enabled server of this type (media_servers.py); for Plex the first
    one comes first. Falls back to the settings row's one server."""
    from backend import media_servers
    db = SessionLocal()
    try:
        if kind == "plex":
            found = media_servers.plex_targets(db)
        else:
            found = [media_servers.target(r) for r in media_servers.enabled(db, kind)]
    except Exception:
        found = []
    finally:
        db.close()
    conf = conf or {}
    if not found and (conf.get("url") or "").strip():
        found = [media_servers.Target(id=None, type=kind, name=media_servers.LABELS[kind], url=conf["url"],
                                      token=conf.get("token"), primary=True)]
    return found


class Automation:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self.watch_deps: Optional[WatchDeps] = None
        # plex_probe(url, token): the scheduler's session probe (main.py sets it).
        self.plex_probe: Optional[Callable[[str, str], object]] = None
        self._last = {"plex": 0.0, "servers": 0.0, "folders": 0.0, "prune": 0.0, "index": 0.0}
        self._index = None
        self._plex_name = "Plex"
        # One watcher per extra Plex server (the first one uses play_history.PLEX).
        self._plex_watchers: dict = {}

    def start(self, watch_deps: WatchDeps) -> None:
        self.watch_deps = watch_deps
        if self._thread is not None and self._thread.is_alive():
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="smart-features")
        self._thread.start()

    def stop(self) -> None:
        self._running = False

    def _loop(self) -> None:
        # Let startup finish first.
        for _ in range(10):
            if not self._running:
                return
            time.sleep(1)
        while self._running:
            self.tick()
            for _ in range(5):
                if not self._running:
                    return
                time.sleep(1)

    def tick(self, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        settings = smart_settings.get_all()
        servers = None
        if not settings.get("watch_sessions", True):
            plex_sessions.FEED.drain()  # watching is off: the probe's answers aren't wanted
        elif now - self._last["plex"] >= PLEX_EVERY:
            self._last["plex"] = now
            servers = servers or _servers()
            plex = _targets("plex", servers.get("plex"))
            if plex:
                self._plex_name = plex[0].name
            self._guard("Plex sessions", lambda: self.poll_plex(servers.get("plex") or {}, now))
            for target in plex[1:]:
                self._guard(f"{target.name} sessions", lambda t=target: self.poll_other_plex(t, now))
        if settings.get("watch_sessions", True) and now - self._last["servers"] >= SERVERS_EVERY:
            self._last["servers"] = now
            servers = servers or _servers()
            for kind in ("jellyfin", "emby"):
                confs = [{"url": t.url, "token": t.token, "name": t.name}
                         for t in _targets(kind, servers.get(kind))] or [servers.get(kind) or {}]
                for conf in confs:
                    self._guard(f"{conf.get('name') or kind} sessions",
                                lambda kind=kind, conf=conf: self.poll_plugin_server(kind, conf))
        if self.watch_deps is not None and now - self._last["folders"] >= FOLDERS_EVERY:
            self._last["folders"] = now
            self._guard("watch folders", self.scan_folders)
        if now - self._last["prune"] >= PRUNE_EVERY:
            self._last["prune"] = now
            self._guard("history cleanup", lambda: self.prune(int(settings.get("history_retention_days") or 90)))

    @staticmethod
    def _guard(what: str, fn) -> None:
        try:
            fn()
        except Exception as exc:
            logger.info("Smart features: %s skipped this time: %s", what, exc)

    # -- Plex ---------------------------------------------------------------

    def _preroll_index(self, db, now: float):
        if self._index is None or now - self._last["index"] >= INDEX_EVERY:
            from backend import path_mapping
            setting = db.query(models.Setting).first()
            mappings = []
            try:
                data = json.loads(getattr(setting, "path_mappings", None) or "[]")
                mappings = [m for m in data if isinstance(m, dict) and m.get("local") and m.get("plex")]
            except (TypeError, ValueError):
                mappings = []
            rows = db.query(models.Preroll).all()
            self._index = play_history.PrerollIndex(rows, lambda p: path_mapping.translate(p, mappings))
            self._last["index"] = now
        return self._index

    def poll_plex(self, conf: dict, now: float) -> None:
        """Have the scheduler's probe look at Plex, then record what it saw.

        Nothing is asked when no Plex server is set up. The probe reuses its
        answer from the last 15 seconds, so this never adds a second request.
        """
        url, token = (conf.get("url") or "").strip(), conf.get("token")
        if url and token and self.plex_probe is not None:
            self.plex_probe(url, token)
        self.observe_published()

    def observe_published(self) -> int:
        """Record every look at Plex the probe published since last time."""
        snapshots = plex_sessions.FEED.drain()
        for snapshot in snapshots:
            _note("plex", snapshot.ok, snapshot.message)
            if snapshot.ok and snapshot.root is not None:
                self._guard("Plex sessions", lambda s=snapshot: self.observe_plex(s.root, connector=s.connector,
                                                                                  now=s.at))
        return len(snapshots)

    def poll_other_plex(self, target, now: float) -> None:
        """A Plex server after the first: read its sessions directly (no playback guard to share)."""
        import xml.etree.ElementTree as ET
        from backend import path_mapping
        try:
            response = requests.get(f"{target.url.rstrip('/')}/status/sessions",
                                    headers={"X-Plex-Token": target.token or ""}, timeout=6)
        except requests.RequestException:
            return
        if response.status_code != 200 or not response.content:
            return
        db = SessionLocal()
        try:
            rows = db.query(models.Preroll).all()
            index = play_history.PrerollIndex(rows, lambda p: path_mapping.translate(p, target.mappings))
        finally:
            db.close()
        watcher = self._plex_watchers.setdefault(target.id, play_history.PlexWatcher())
        self.observe_plex(ET.fromstring(response.content), now=now, server_name=target.name, watcher=watcher,
                          index=index)

    def observe_plex(self, root, *, connector=None, now: Optional[float] = None, server_name: Optional[str] = None,
                     watcher=None, index=None) -> dict:
        """Feed one /status/sessions answer in (published by the scheduler's probe)."""
        now = time.time() if now is None else now
        server_name = server_name or self._plex_name
        db = SessionLocal()
        try:
            settings = smart_settings.get_all(db)
            index = index or self._preroll_index(db, now)

            def record_play(**fields):
                if settings.get("history_enabled", True):
                    play_history.record_play(db, server_name=server_name, **fields)

            def record_check(**fields):
                play_history.record_check(db, server_name=server_name, **fields)

            def list_is_empty():
                if connector is None:
                    return None
                try:
                    return not str(connector.get_preroll() or "").strip()
                except Exception:
                    return None

            return (watcher or play_history.PLEX).observe(root, index=index, record_play=record_play,
                                                          record_check=record_check,
                                                          list_is_empty=list_is_empty, now=now)
        finally:
            db.close()

    # -- Jellyfin / Emby ----------------------------------------------------

    def poll_plugin_server(self, kind: str, conf: dict) -> None:
        url, token = (conf.get("url") or "").strip(), conf.get("token")
        if not url or not token:
            return
        base = url.rstrip("/")
        if kind == "jellyfin":
            from backend.jellyfin_auth import jellyfin_auth_headers
            endpoint, headers = f"{base}/Sessions?ActiveWithinSeconds=120", jellyfin_auth_headers(token)
        else:
            prefix = "" if base.lower().endswith("/emby") else "/emby"
            endpoint, headers = f"{base}{prefix}/Sessions?ActiveWithinSeconds=120", {"X-Emby-Token": token}
        try:
            response = requests.get(endpoint, headers=headers, timeout=5)
        except requests.RequestException:
            _note(kind, False, f"{kind.capitalize()} didn't answer.")
            return
        if response.status_code != 200:
            _note(kind, False, f"{kind.capitalize()} answered {response.status_code}.")
            return
        _note(kind, True)
        sessions = response.json() if response.content else []
        db = SessionLocal()
        try:
            play_history.PLUGIN_SERVERS.observe(db, kind, sessions if isinstance(sessions, list) else [],
                                                server_name=conf.get("name"))
        finally:
            db.close()

    # -- Watch folders and cleanup -------------------------------------------

    def scan_folders(self) -> list:
        results = []
        db = SessionLocal()
        try:
            for folder in db.query(models.WatchFolder).filter(models.WatchFolder.enabled == True).all():  # noqa: E712
                try:
                    results.append(WATCHER.scan(db, folder, self.watch_deps))
                except Exception as exc:
                    db.rollback()
                    logger.warning("Watch folder %s failed: %s", folder.path, exc)
        finally:
            db.close()
        return results

    def prune(self, days: int) -> int:
        db = SessionLocal()
        try:
            return play_history.prune(db, days)
        finally:
            db.close()


AUTOMATION = Automation()
