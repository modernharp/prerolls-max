"""Outgoing requests for the community libraries, and small file helpers.

Every request names the hosts it may reach. Redirects are followed by hand,
one hop at a time, and each hop is checked with ``net.require_host``, so a
redirect (or a crafted id, or an edited setting) can't send Prerolls Max to
another site.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from typing import Callable, Iterable, Optional
from urllib.parse import urljoin

from backend import brand, net
from backend.errors import AppError

MAX_REDIRECTS = 5


def user_agent(version: str = "") -> str:
    v = f"/{version}" if version else ""
    return f"PrerollsMax{v}{brand.user_agent_comment('self-hosted intro video manager')}"


class Http:
    """A requests-like ``get`` that only reaches allowed hosts.

    ``session`` is a requests.Session or anything with the same ``get``
    (tests pass a fake). Responses are returned as the session gives them.
    """

    def __init__(self, session=None, version: str = ""):
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.user_agent = user_agent(version)

    def get(self, url: str, *, allowed_hosts: Iterable[str], headers: Optional[dict] = None,
            stream: bool = False, timeout: float = 20, max_redirects: int = MAX_REDIRECTS):
        allowed = list(allowed_hosts)
        hdrs = {"User-Agent": self.user_agent}
        hdrs.update(headers or {})
        for _ in range(max_redirects + 1):
            net.require_host(url, allowed)
            resp = self.session.get(url, headers=hdrs, stream=stream, timeout=timeout, allow_redirects=False)
            location = resp.headers.get("Location") if 300 <= resp.status_code < 400 else None
            if not location:
                return resp
            try:
                resp.close()
            except Exception:
                pass
            url = urljoin(url, location)
        raise net.BlockedAddress("Too many redirects.")


class Pacer:
    """Leaves at least ``gap()`` seconds between starts, across threads.

    A caller reserves the next free slot under the lock and sleeps outside
    it, so one waiting download never blocks the others' bookkeeping (or a
    different library's downloads, which have their own Pacer).
    """

    def __init__(self, gap: Callable[[], float], sleep=time.sleep, clock=time.monotonic):
        self._gap = gap
        self._sleep = sleep
        self._clock = clock
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> float:
        with self._lock:
            now = self._clock()
            start = max(now, self._next)
            self._next = start + max(0.0, float(self._gap() or 0))
        delay = start - now
        if delay > 0:
            self._sleep(delay)
        return delay


def atomic_write_bytes(path, data: bytes) -> None:
    """Write next to ``path`` and rename over it: readers never see half a file."""
    path = str(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def atomic_write_json(path, payload) -> None:
    atomic_write_bytes(path, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def network_error(site: str) -> AppError:
    return AppError(f"{site} didn't answer.", status=502, code="community_unreachable",
                    hint="Check this computer's internet connection, then try again in a few minutes.")


def blocked(site: str) -> AppError:
    return AppError(f"{site} sent Prerolls Max to another website, so it stopped.", status=502,
                    code="community_blocked_address",
                    hint="This is usually temporary. Try again later.")


def now_iso(ts: Optional[float] = None) -> Optional[str]:
    if not ts:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
