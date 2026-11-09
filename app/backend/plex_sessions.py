"""What Plex is playing: read in one place, shared with everything that needs it.

Only the scheduler's playback-guard probe (``Scheduler.read_plex_sessions``)
asks Plex for ``/status/sessions``. Every answer it gets, and every failure,
is published here. The smart-features loop (automation.py) takes them from
here for play history and the missed-intro check, so Plex isn't asked twice.

The loop asks the probe for a fresh look every 15 seconds while a Plex server
is set up. The probe answers from its own copy when it already looked within
the last 15 seconds (for a schedule change, say), so that costs nothing extra;
with no Plex server set up nothing is asked at all.

The answers are handed over through a small queue rather than a callback: the
probe often runs in the middle of the scheduler writing to the database, and
recording plays from there could wait on its own unfinished write.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

EVERY_SECONDS = 15.0


@dataclass
class Snapshot:
    """One look at Plex's sessions. ``root`` is the parsed answer when ``ok``."""

    ok: bool
    root: Any = None
    message: str = ""
    connector: Any = None
    at: float = field(default_factory=time.time)


class SessionFeed:
    """The latest looks at Plex's sessions, oldest first, until someone reads them."""

    def __init__(self, keep: int = 20):
        self._lock = threading.Lock()
        self._items: deque = deque(maxlen=keep)

    def publish(self, snapshot: Snapshot) -> None:
        with self._lock:
            self._items.append(snapshot)

    def drain(self) -> list:
        with self._lock:
            items = list(self._items)
            self._items.clear()
        return items


FEED = SessionFeed()
