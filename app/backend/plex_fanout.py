"""Write Plex's intro list to every enabled Plex server, not only the first.

The scheduler builds one list of Prerolls Max's own file paths and writes it
to the primary Plex (the settings row) as it always has. ``after_write`` then
sends the same list to every other enabled Plex server, each through its own
folder mapping, with its own path check and playback guard, and remembers the
outcome per server so the Media Servers page can say "Living room Plex
couldn't see 2 files".

A server that was busy (the playback guard) or didn't answer is retried by
``tick`` on the scheduler's next rounds. Every few minutes ``tick`` also reads
each server's list back and rewrites it when someone changed it, and after a
restart it carries on from the list saved next to the database.
"""
from __future__ import annotations

import datetime
import json
import logging
import os
import threading
import time
import xml.etree.ElementTree as ET
from typing import Optional

import requests

from backend import coexist, media_servers, path_mapping

logger = logging.getLogger("prerollsmax.plex")

VERIFY_EVERY = 300  # seconds between read-backs of the other servers' lists
RETRY_EVERY = 110   # seconds between retries of a server that was busy or down
STATE_FILE = "plex_servers_state.json"


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def _looks_windows(path: str) -> bool:
    return bool(path) and (path.startswith("\\\\") or (len(path) >= 3 and path[1] == ":" and path[2] in "\\/"))


def style_mismatch(paths, platform: str) -> Optional[str]:
    """The first path written for the wrong kind of computer, or None."""
    windows = "win" in (platform or "").lower()
    for path in paths:
        if windows and path.startswith("/") and not _looks_windows(path):
            return path
        if not windows and _looks_windows(path):
            return path
    return None


def unmap(plex_path: str, mappings) -> str:
    """Prerolls Max's own path for a path as Plex sees it (the mapping read backwards)."""
    windows = _looks_windows(plex_path)
    for m in sorted(mappings or [], key=lambda m: -len(str(m.get("plex") or ""))):
        prefix = str(m.get("plex") or "").rstrip("/\\")
        if not prefix:
            continue
        head = plex_path[:len(prefix)]
        same = head.lower() == prefix.lower() if windows else head == prefix
        if same and (len(plex_path) == len(prefix) or plex_path[len(prefix)] in "/\\"):
            rest = plex_path[len(prefix):].lstrip("/\\").replace("\\", "/").split("/")
            return os.path.join(str(m.get("local")), *rest)
    return plex_path


class PlexFanout:
    def __init__(self):
        self._lock = threading.RLock()
        self.last = {"paths": None, "delimiter": ";", "label": ""}
        self.results: dict = {}   # server id -> {state, message, at, value}
        self._pending: set = set()
        self._verified_at = 0.0
        self._tried: dict = {}    # server id -> time of the last retry
        self._path: Optional[str] = None

    # -- persistence ---------------------------------------------------------

    def configure_persistence(self, path: Optional[str]) -> None:
        self._path = path
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data.get("last"), dict):
                self.last.update(data["last"])
            self.results = {int(k): v for k, v in (data.get("results") or {}).items()}
            self._pending = {int(k) for k, v in self.results.items() if v.get("state") != "ok"}
        except Exception as exc:
            logger.warning("Couldn't read the other Plex servers' state: %s", exc)

    def _save(self) -> None:
        if not self._path:
            return
        try:
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump({"last": self.last, "results": {str(k): v for k, v in self.results.items()}}, fh)
            os.replace(tmp, self._path)
        except Exception as exc:
            logger.warning("Couldn't save the other Plex servers' state: %s", exc)

    # -- results ---------------------------------------------------------------

    def note(self, server_id, name: str, state: str, message: str = "", value: Optional[str] = None,
             missing: int = 0) -> None:
        if server_id is None:
            return
        with self._lock:
            self.results[int(server_id)] = {"state": state, "name": name, "message": message, "at": _now_iso(),
                                            "value": value, "missing": missing}
            if state == "ok":
                self._pending.discard(int(server_id))
            else:
                self._pending.add(int(server_id))

    def status(self, server_id) -> Optional[dict]:
        with self._lock:
            got = self.results.get(int(server_id)) if server_id is not None else None
            return {k: v for k, v in got.items() if k != "value"} if got else None

    def forget(self, server_id) -> None:
        with self._lock:
            self.results.pop(int(server_id), None)
            self._pending.discard(int(server_id))
            self._save()

    # -- writing -------------------------------------------------------------

    def after_write(self, scheduler, db, local_paths, delimiter: str, label: str, primary_connector=None,
                    primary_ok: Optional[bool] = None) -> None:
        """The primary was just written (or skipped): note it and write the others."""
        with self._lock:
            self.last = {"paths": [os.path.abspath(p) for p in local_paths or []], "delimiter": delimiter,
                         "label": label}
            targets = media_servers.plex_targets(db)
            if targets and targets[0].primary and primary_ok is not None:
                self._note_connector(targets[0], primary_connector, primary_ok)
            for target in targets[1:]:
                self._write_one(scheduler, db, target)
            self._save()

    def _note_connector(self, target, connector, ok: bool) -> None:
        gate = getattr(connector, "last_visibility", None)
        missing = len(getattr(gate, "missing", None) or []) if gate is not None else 0
        total = len(getattr(gate, "results", None) or []) if gate is not None else 0
        files = "file" if total == 1 else "files"
        if ok:
            message = (f"{target.name} couldn't see {missing} of the {total} intro {files}, so it plays the "
                       f"other {total - missing}. Check its folder mapping." if missing else "")
            self.note(target.id, target.name, "ok", message, missing=missing)
        elif missing and missing == total:
            self.note(target.id, target.name, "failed",
                      f"{target.name} couldn't see any of the {total} intro {files}, so its list wasn't changed. "
                      "Check its folder mapping.", missing=missing)
        else:
            reason = getattr(connector, "last_error", None) or "Plex didn't take the new intro list."
            self.note(target.id, target.name, "failed", f"{target.name}: {reason}", missing=missing)

    def seed_from_primary(self, scheduler, db) -> None:
        """After a restart with no saved list: start from what the first Plex plays."""
        if self.last.get("paths") is not None:
            return
        targets = media_servers.plex_targets(db)
        if not targets or not targets[0].primary:
            return
        from backend import scheduler as scheduler_module
        try:
            value = scheduler_module.PlexConnector(targets[0].url, targets[0].token).get_current_preroll()
        except Exception:
            value = None
        if value is None:
            return
        delimiter = "," if "," in value and ";" not in value else ";"
        paths = [unmap(p.strip(), targets[0].mappings) for p in value.split(delimiter) if p.strip()]
        self.last = {"paths": paths, "delimiter": delimiter, "label": "the first Plex server's list"}

    def _value_for(self, scheduler, target) -> tuple:
        paths = [path_mapping.translate(p, target.mappings) for p in self.last.get("paths") or []]
        return paths, scheduler._join_for_plex(paths, self.last.get("delimiter") or ";")

    def _write_one(self, scheduler, db, target) -> bool:
        from backend import scheduler as scheduler_module
        if coexist.nexroll_manages(target.id):
            self.note(target.id, target.name, "ok",
                      f"NeXroll manages intros on {target.name}, so Prerolls Max leaves its list alone.")
            return True
        connector = scheduler_module.PlexConnector(target.url, target.token)
        paths, value = self._value_for(scheduler, target)
        if paths:
            try:
                info = connector.get_server_info() or {}
            except Exception:
                info = {}
            if not info.get("connected", bool(info)):
                self.note(target.id, target.name, "failed", f"{target.name} didn't answer at {target.url}.")
                return False
            wrong = style_mismatch(paths, str(info.get("platform") or info.get("Platform") or ""))
            if wrong:
                self.note(target.id, target.name, "failed",
                          f"{target.name} runs on a different kind of computer, so it can't use paths like "
                          f"{wrong}. Set up its folder mapping on the Media Servers page.")
                return False
        busy = self.busy(scheduler, db, target)
        if busy:
            self.note(target.id, target.name, "waiting",
                      f"{target.name} is playing intros right now, so its list changes when they finish.")
            return False
        ok = connector.set_preroll(value)
        self._note_connector(target, connector, ok)
        if ok:
            self.results[target.id]["value"] = (connector.get_preroll() if hasattr(connector, "get_preroll")
                                                else value) or value
        scheduler_module._scheduler_log(
            f"{target.name}: {'took' if ok else 'did not take'} the intro list ({self.last.get('label') or 'update'})",
            level="INFO" if ok else "WARNING")
        return ok

    @staticmethod
    def busy(scheduler, db, target) -> bool:
        """Whether this server has a playback still in its intros (the playback guard)."""
        if os.environ.get("PMAX_ALLOW_MIDPLAYBACK_PREROLL_WRITES") == "1":
            return False
        from backend import models
        setting = db.query(models.Setting).first()
        minutes = scheduler._playback_guard_minutes(setting)
        if not minutes:
            return False
        try:
            r = requests.get(f"{target.url.rstrip('/')}/status/sessions", headers={"X-Plex-Token": target.token or ""},
                             timeout=6)
            if r.status_code != 200 or not r.content:
                return False
            if scheduler._preroll_window_seconds != minutes * 60.0:
                scheduler._preroll_window_seconds = minutes * 60.0
            return bool(scheduler._count_sessions_in_preroll_window(ET.fromstring(r.content),
                                                                     datetime.datetime.now()))
        except Exception:
            return False  # an unreachable server must never hold scheduling up

    def send_current(self, scheduler, db, server_id) -> Optional[bool]:
        """Give one server (just added or switched on) the list the others have."""
        with self._lock:
            if self.last.get("paths") is None:
                return None
            target = next((t for t in media_servers.plex_targets(db) if t.id == server_id and not t.primary), None)
            if target is None:
                return None
            ok = self._write_one(scheduler, db, target)
            self._save()
            return ok

    def tick(self, scheduler, db, now: Optional[float] = None) -> None:
        """Retry servers that were busy or down, and every few minutes read each list back."""
        now = time.time() if now is None else now
        if self.last.get("paths") is None:
            if len(media_servers.plex_targets(db)) < 2 or now - self._tried.get(0, 0.0) < RETRY_EVERY:
                return
            self._tried[0] = now
            self.seed_from_primary(scheduler, db)
            if self.last.get("paths") is None:
                return
        with self._lock:
            verify = now - self._verified_at >= VERIFY_EVERY
            if verify:
                self._verified_at = now
            changed = False
            for target in media_servers.plex_targets(db)[1:]:
                if coexist.nexroll_manages(target.id):
                    continue  # left to NeXroll (Settings > Moving from NeXroll)
                due = target.id in self._pending or target.id not in self.results
                if due and now - self._tried.get(target.id, 0.0) < RETRY_EVERY:
                    continue  # a server that is down costs a timeout; don't pay it every round
                if not due and verify:
                    try:
                        from backend import scheduler as scheduler_module
                        actual = scheduler_module.PlexConnector(target.url, target.token).get_preroll()
                    except Exception:
                        actual = None
                    expected = (self.results.get(target.id) or {}).get("value")
                    due = actual is not None and expected is not None and actual.strip() != expected.strip()
                    if due:
                        logger.info("%s's intro list was changed outside Prerolls Max; writing it again", target.name)
                if due:
                    self._tried[target.id] = now
                    self._write_one(scheduler, db, target)
                    changed = True
            if changed:
                self._save()


FANOUT = PlexFanout()
