"""Prerolls.uk (Typical Nerds): a file server with folder listings.

There is no catalog: Prerolls Max walks the folders (Caddy answers JSON
listings with each file's name, size and date) and keeps what it found in
``prerolls_index.json``, then reads each new file's length from its header
(community_durations). Titles, categories and creators come from file and
folder names (community_catalog). Building the list costs about 600 small
requests, so it only happens when someone presses Refresh (or once a week,
if they turned that on), and only after they accepted Typical Nerds' Fair
Use Policy.

Servers: Typical Nerds lists its mirrors in servers.json (community_servers).
Prerolls Max only ever talks to prerolls.uk and its subdomains; a mirror in the
list on any other host is ignored, and a saved server choice that isn't an
active listed mirror is ignored too (it used to be any address, which let a
request make Prerolls Max fetch any URL). Redirects are followed only within
those hosts. Downloads keep the gap the server's "anti-spam" value asks for.

Fixed here compared with NeXroll 2.4.0: Top 5 ids that couldn't be downloaded,
ids from the live folder scrape that downloads refused, the index written in
place (now atomic) and read again for every search (now kept in memory until
the file changes), a progress stream that never ended after a failed build,
and downloads that slept while holding a global lock.
"""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.parse
from typing import Callable, Iterable, List, Optional
from urllib.parse import quote, urljoin

from backend import community_catalog, community_durations, community_servers, net
from backend.community import base, ids
from backend.community.http import (Http, Pacer, atomic_write_json, blocked, network_error, now_iso,
                                    read_json)
from backend.community_filter import filter_ai_prerolls
from backend.community_search import QueryMatcher
from backend.errors import AppError

SITE = "Prerolls.uk"
SITE_URL = "https://prerolls.uk"
OFFICIAL_DOMAIN = "prerolls.uk"
DEFAULT_HOSTS = ("prerolls.uk", "home.prerolls.uk")
SERVER_LIST_TTL = 600         # seconds
SERVER_LIST_RETRY = 60
DIRECTORY_GAP = 0.15          # seconds between folder listings while building the list
LENGTH_GAP = 0.25             # seconds between files while reading lengths
LENGTH_MAX_ERRORS = 5
MAX_AGE = 7 * 24 * 3600       # a list older than this is "refresh recommended"
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".avi", ".mov", ".webm")
SKIP_FOLDERS = ("site-assets", "templates")
PREVIEW_HEADERS = ("Content-Length", "Content-Range", "Accept-Ranges", "Last-Modified", "ETag")

FAIR_USE_SUMMARY = (
    "Typical Nerds share these intro videos for personal, non-commercial use on your own media server. "
    "The videos belong to their creators: don't redistribute, modify or sell them. "
    "Please accept the Fair Use Policy before browsing or downloading."
)

FAIR_USE_POLICY = """------------------------------------------------
Fair Use Policy Disclosure
------------------------------------------------

We appreciate your interest in our community's assets, which are intended for informational and educational purposes only. We encourage their appropriate use within the boundaries of copyright law. Please read the following Fair Use Policy carefully before utilizing our assets:

	1.	Ownership: All assets, including but not limited to text, images, videos, and audio files, available on our platform may be protected by copyright and belong to their respective owners. Ownership rights are not transferred or assigned to users.
	2.	Permissible Use: Users are granted a non-exclusive, non-transferable, revocable license to use the assets provided on our platform for personal, non-commercial purposes, unless otherwise specified. Such use should be in compliance with applicable copyright laws.
	3.	Prohibited Actions: Users must not copy, reproduce, distribute, modify, publicly display, or create derivative works from the assets without obtaining explicit permission from the creator.
	4.	Enforcement: We reserve the right to monitor and enforce compliance with this Fair Use Policy. We may take appropriate action, including but not limited to disabling access, removing content, and pursuing legal remedies against individuals or entities found to be infringing upon copyrights or violating this policy.
	5.	Reporting Infringements: If you believe that any content on our platform infringes upon your copyright or violates this Fair Use Policy, please contact me immediately via email at contact@typicalnerds.uk. We will promptly investigate and take appropriate action.
	6.	Disclaimer: This Fair Use Policy does not override or replace any additional terms or conditions that may apply to specific assets or services offered on our platform. Users are advised to review such terms and conditions in conjunction with this policy.

By accessing and using these assets, you acknowledge that you have read, understood, and agreed to comply with this Fair Use Policy. Failure to adhere to this policy may result in the termination of your access to our assets and potential legal consequences.
"""
FAIR_USE_URL = "https://prerolls.uk/%23%20FAIR%20USE%20POLICY%20-%20READ%20ME.txt"


def allowed_server(url) -> bool:
    """A Typical Nerds server Prerolls Max may talk to: https on prerolls.uk or
    a subdomain, with no path, user name or port games."""
    text = community_servers.normalize(url)
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or parts.query or parts.fragment:
        return False
    if parts.path not in ("", "/"):
        return False
    try:
        if parts.port not in (None, 443):
            return False
    except ValueError:
        return False
    return host == OFFICIAL_DOMAIN or host.endswith("." + OFFICIAL_DOMAIN)


def listed_servers(servers) -> List[dict]:
    """The active servers.json entries Prerolls Max may use, in list order."""
    return [s for s in community_servers.active(servers) if allowed_server(s.get("baseUrl"))]


def creator_of(path_parts: list) -> str:
    """The creator from the nearest folder named "Title - Creator" (a file is
    often one folder further down, in "Plex/" or "Universal/")."""
    for folder in reversed(path_parts[2:-1]):   # [0] is "" and [1] the category
        name = urllib.parse.unquote(folder)
        if " - " in name:
            creator = name.split(" - ")[-1].strip()
            if creator:
                return creator
    return "Typical Nerds"


def _keywords(path_parts: list, title: str) -> list:
    words = []
    for part in path_parts:
        decoded = urllib.parse.unquote(part).lower()
        words.extend(decoded.replace("_", " ").replace("-", " ").replace("/", " ").split())
    words.extend(title.lower().replace("_", " ").replace("-", " ").split())
    return sorted({w for w in words if len(w) > 2})


def parse_mod_time(text):
    """Caddy's RFC 3339 mod_time (often with nanoseconds) -> (timestamp, ISO) or (0.0, None)."""
    if not text:
        return 0.0, None
    try:
        import datetime
        t = str(text).strip().replace("Z", "+00:00")
        if "." in t:
            head, rest = t.split(".", 1)
            digits = ""
            i = 0
            while i < len(rest) and rest[i].isdigit():
                digits += rest[i]
                i += 1
            t = f"{head}.{digits[:6]}{rest[i:]}"
        dt = datetime.datetime.fromisoformat(t)
        return dt.timestamp(), dt.isoformat()
    except Exception:
        return 0.0, None


def make_entry(base_url: str, full_url: str, name: str, *, size=None, mod_time=None) -> dict:
    path = full_url[len(base_url):]
    parts = path.split("/")
    category = parts[1] if len(parts) > 1 and parts[1] else "Community"
    mt, miso = parse_mod_time(mod_time)
    title = name
    for ext in (".mp4", ".mkv"):
        title = title.replace(ext, "")
    return {
        "id": path,
        "title": title.replace("_", " ").replace("-", " ").title(),
        "creator": creator_of(parts),
        "category": category,
        "url": full_url,
        "path": path,
        "keywords": _keywords(parts, name),
        "tags": category.lower(),
        "modified_time": mt,
        "modified_iso": miso,
        "is_ai": category.casefold() == "ai",
        "size_bytes": size if isinstance(size, int) and not isinstance(size, bool) else None,
    }


class PrerollsUkSource(base.CommunitySource):
    id = "prerollsuk"
    name = "Prerolls.uk (Typical Nerds)"
    site_url = SITE_URL
    description = ("The Typical Nerds community library that NeXroll used: about 1,800 intro videos, "
                   "many in Plex, Jellyfin and Emby versions. All of them can be downloaded.")
    needs_acceptance = True

    def __init__(self, folder, *, http: Optional[Http] = None, settings: Callable[[], dict] = lambda: {},
                 log: Callable[..., None] = lambda *a, **k: None, clock=time.time, sleep=time.sleep):
        from pathlib import Path
        self.folder = Path(folder)
        self.http = http or Http()
        self.settings = settings
        self.log = log
        self._clock = clock
        self._sleep = sleep
        self._index_lock = threading.Lock()
        self._index: Optional[dict] = None
        self._index_key = None
        self._rows_cache: dict = {}
        self._servers = {"servers": None, "source": None, "at": 0.0, "ok": False}
        self._servers_lock = threading.Lock()
        self.durations = community_durations.DurationStore(self.folder / "community_durations.json")
        self.pacer = Pacer(self.download_gap, sleep=sleep)
        self.building = False
        self.reading_lengths = False
        self.build_state = {"building": False, "progress": 0, "current_dir": "", "files_found": 0,
                            "dirs_visited": 0, "message": ""}
        self.length_state = {"running": False, "checked": 0, "to_check": 0, "message": "", "finished_at": None}
        self._error: Optional[dict] = None

    @property
    def index_path(self):
        return self.folder / "prerolls_index.json"

    # --------------------------------------------------------------- servers
    def server_list(self) -> Optional[list]:
        """servers.json (cached 10 minutes), only the mirrors Prerolls Max may use."""
        with self._servers_lock:
            cache = self._servers
            ttl = SERVER_LIST_TTL if cache["ok"] else SERVER_LIST_RETRY
            if cache["at"] and self._clock() - cache["at"] < ttl:
                return cache["servers"]

        def get(url, timeout=10, headers=None):
            return self.http.get(url, allowed_hosts=DEFAULT_HOSTS, headers=headers, timeout=timeout)

        servers, source = community_servers.fetch(get, {"Accept": "application/json"})
        servers = listed_servers(servers) or None
        with self._servers_lock:
            if servers:
                self._servers.update(servers=servers, source=source, ok=True, at=self._clock())
            else:
                self.log("Could not fetch the Prerolls.uk server list (servers.json); using the last one or the default")
                self._servers.update(ok=False, at=self._clock())
            return self._servers["servers"]

    def server_list_source(self) -> Optional[str]:
        return self._servers.get("source")

    def choose_server(self, saved=None, servers=None) -> tuple:
        """(URL in use, saved choice set aside or None). Only listed mirrors count."""
        servers = self.server_list() if servers is None else servers
        listed = listed_servers(servers)
        default = community_servers.normalize(listed[0]["baseUrl"]) if listed else community_servers.FALLBACK_URL
        saved = community_servers.normalize(saved)
        if not saved:
            return default, None
        match = next((s for s in listed if community_servers.same_server(s.get("baseUrl"), saved)), None)
        if match:
            return community_servers.normalize(match["baseUrl"]), None
        return default, saved

    def base_url(self) -> str:
        return self.choose_server(self.settings().get("saved_server"))[0]

    def allowed_hosts(self) -> set:
        hosts = set(DEFAULT_HOSTS)
        for server in listed_servers(self._servers.get("servers")):
            hosts.add(net.host_of(server["baseUrl"]))
        return hosts

    def download_gap(self) -> float:
        return community_servers.download_delay(self.base_url(), self.server_list())

    def file_url(self, path: str) -> str:
        """The server in use plus a validated file path; never another host."""
        if not ids.valid_path(path):
            raise AppError("That doesn't look like a Prerolls.uk video.", status=422, code="invalid_input",
                           hint="Pick the video again from the Community page.")
        return self.base_url().rstrip("/") + path

    def _get(self, url, **kwargs):
        return self.http.get(url, allowed_hosts=self.allowed_hosts(), **kwargs)

    # ----------------------------------------------------------------- index
    def load_index(self) -> Optional[dict]:
        """The saved list with titles tidied, kept in memory until the file changes."""
        try:
            st = self.index_path.stat()
        except OSError:
            return None
        key = (st.st_mtime_ns, st.st_size)
        with self._index_lock:
            if self._index_key == key and self._index is not None:
                return self._index
            data = read_json(self.index_path)
            if not isinstance(data, dict) or not isinstance(data.get("prerolls"), list):
                return None
            community_catalog.tidy_titles(data["prerolls"])
            self._index, self._index_key, self._rows_cache = data, key, {}
            return data

    def has_data(self) -> bool:
        return self.load_index() is not None

    def entries(self) -> list:
        data = self.load_index()
        return list(data.get("prerolls") or []) if data else []

    def index_age(self) -> Optional[float]:
        try:
            return max(0.0, self._clock() - self.index_path.stat().st_mtime)
        except OSError:
            return None

    def save_index(self, data: dict) -> None:
        atomic_write_json(self.index_path, data)

    def build_index(self, ctx=None, base_url: Optional[str] = None) -> dict:
        """Walk the server's folders. Raises AppError when nothing was found,
        so a failed walk never replaces a good list."""
        import math
        base_url = (base_url or self.base_url()).rstrip("/")
        headers = {"Accept": "text/html,application/json"}
        visited: set = set()
        found: list = []
        answered = 0
        state = self.build_state
        state.update(building=True, progress=0, current_dir="", files_found=0, dirs_visited=0,
                     message="Reading the folder list")

        def report(path_display: str) -> None:
            pct = int(90 * (1 - math.exp(-len(visited) / 150.0)))
            state.update(current_dir=path_display, dirs_visited=len(visited), files_found=len(found),
                         progress=max(state["progress"], pct))
            if ctx:
                ctx.report(progress=pct, message=f"Reading the library: {len(visited)} {'folder' if len(visited) == 1 else 'folders'} read, {len(found)} {'video' if len(found) == 1 else 'videos'} found so far")

        def add_file(full_url: str, name: str, size=None, mod_time=None) -> None:
            if not full_url.startswith(base_url + "/"):
                return
            path = full_url[len(base_url):]
            if ids.valid_path(path):
                found.append(make_entry(base_url, full_url, name, size=size, mod_time=mod_time))

        def walk(url: str, depth: int = 0) -> None:
            nonlocal answered
            url = url.rstrip("/") + "/"
            if any(skip in url.lower() for skip in SKIP_FOLDERS) or url in visited or depth > 12:
                return
            visited.add(url)
            report(url[len(base_url):] or "/")
            self._sleep(DIRECTORY_GAP)
            try:
                resp = self._get(url, headers=headers, timeout=15)
            except net.BlockedAddress:
                self.log(f"[COMMUNITY] Skipped {url}: it redirects off the Typical Nerds servers")
                return
            except Exception as exc:
                self.log(f"[COMMUNITY] Could not list {url}: {exc}")
                return
            try:
                if resp.status_code != 200:
                    return
                answered += 1
                ctype = str(resp.headers.get("Content-Type") or "")
                text = resp.text
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
            if "application/json" in ctype:
                try:
                    listing = json.loads(text)
                except ValueError:
                    return
                for entry in listing if isinstance(listing, list) else ():
                    if not isinstance(entry, dict):
                        continue
                    name = str(entry.get("name") or "")
                    if not name or name in (".", ".."):
                        continue
                    full_url = urljoin(url, str(entry.get("url") or name))
                    if not full_url.startswith(base_url + "/"):
                        continue
                    if entry.get("is_dir"):
                        walk(full_url, depth + 1)
                    elif name.lower().endswith(VIDEO_EXTENSIONS):
                        add_file(full_url, name, entry.get("size"), entry.get("mod_time"))
            else:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(text, "html.parser")
                for link in soup.find_all("a"):
                    href = link.get("href", "") or ""
                    label = link.get_text().strip()
                    if not href or href.startswith("?") or href in ("../", "./", "..", ".") or label in ("Up", "/", ".."):
                        continue
                    full_url = urljoin(url, href)
                    if not full_url.startswith(base_url + "/"):
                        continue
                    if href.endswith("/"):
                        walk(full_url, depth + 1)
                    elif href.lower().endswith(VIDEO_EXTENSIONS):
                        add_file(full_url, label or href.rsplit("/", 1)[-1])

        try:
            walk(base_url)
            # The landing page may not link every folder; /AI/ is listed on purpose.
            walk(f"{base_url}/AI/")
            if not found:
                raise AppError("Prerolls.uk didn't list any videos, so the saved list was kept.", status=502,
                               code="community_list_failed",
                               hint="The server may be busy or down. Try again later, or pick the other server.")
            if ctx:
                ctx.report(progress=95, message="Saving the list")
            data = {
                "version": "1.1",
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(self._clock())),
                "base_url": base_url,
                "prerolls": found,
                "total_prerolls": len(found),
                "directories_visited": len(visited),
            }
            self.save_index(data)
            state.update(progress=100, files_found=len(found), message=f"Complete! Found {len(found)} prerolls")
            self.log(f"[COMMUNITY] Prerolls.uk list built: {len(found)} videos in {len(visited)} folders "
                     f"({answered} answered)")
            return data
        except AppError as exc:
            state.update(message=exc.message, progress=100)
            raise
        finally:
            state["building"] = False

    def refresh(self, ctx=None, *, force: bool = False) -> dict:
        if not self.settings().get("accepted"):
            raise terms_needed()
        if self.building:
            raise AppError("The Prerolls.uk list is already being refreshed.", status=409, code="refresh_running",
                           hint="Wait for it to finish.")
        self.building = True
        try:
            self.server_list()
            data = self.build_index(ctx)
            self._error = None
            return {"items": len(data["prerolls"]), "message": f"Found {len(data['prerolls'])} videos on Prerolls.uk."}
        except AppError as exc:
            self._error = {"message": exc.message, "hint": exc.hint}
            raise
        finally:
            self.building = False

    # --------------------------------------------------------------- lengths
    def length_status(self, include_ai: bool = True) -> dict:
        entries = filter_ai_prerolls(self.entries(), include_ai=include_ai)
        known = self.durations.durations(entries)
        pending = sum(1 for e in entries
                      if _key(e) not in known and self.durations.needs_reading(_key(e), e.get("size_bytes")))
        st = self.length_state
        return {"total": len(entries), "measured": len(known), "pending": pending,
                "unreadable": max(0, len(entries) - len(known) - pending),
                "running": st["running"], "checked": st["checked"], "to_check": st["to_check"],
                "message": st["message"]}

    def read_lengths(self, ctx=None) -> dict:
        """Read the length of every file that doesn't have one yet, a few KB each."""
        st = self.length_state
        if st["running"]:
            return {"message": "Already reading lengths"}
        st.update(running=True, checked=0, to_check=0, message="Starting", finished_at=None)
        message = ""
        try:
            entries = self.entries()
            if not entries:
                message = "No list yet"
                return {"message": message}
            base_url = self.base_url().rstrip("/")
            self.durations.prune(_key(e) for e in entries)
            todo = [e for e in entries if self.durations.needs_reading(_key(e), e.get("size_bytes"))]
            st.update(to_check=len(todo), message="Reading")
            if ctx:
                ctx.report(total=len(todo), done=0, message=f"Reading the length of {len(todo)} videos")
            if not todo:
                message = "All lengths known"
                return {"message": message}
            source = self

            class _Session:
                def get(self, url, headers=None, stream=False, timeout=15):
                    return source._get(url, headers=headers, stream=stream, timeout=timeout)

            session = _Session()
            errors = 0
            for entry in todo:
                if self.building:
                    message = "Stopped for a list refresh"
                    break
                key = _key(entry)
                if not ids.valid_path(key):
                    continue
                fetch = community_durations.http_range_fetch(session, base_url + key, {})
                try:
                    seconds = community_durations.read_duration(fetch)
                    self.durations.record(key, entry.get("size_bytes"), seconds)
                    errors = 0
                except community_durations.ServerBusy:
                    message = "Prerolls.uk asked Prerolls Max to slow down; the rest are read next time"
                    break
                except (community_durations.FileUnavailable, community_durations.RangeUnsupported,
                        net.BlockedAddress) as exc:
                    self.durations.record(key, entry.get("size_bytes"), None, error=type(exc).__name__)
                    errors = 0
                except Exception:
                    errors += 1
                    if errors >= LENGTH_MAX_ERRORS:
                        message = "Prerolls.uk stopped answering; the rest are read next time"
                        break
                st["checked"] += 1
                if ctx:
                    ctx.advance()
                if st["checked"] % 50 == 0:
                    self.durations.save()
                self._sleep(LENGTH_GAP)
            else:
                message = "Finished"
            return {"message": message, "checked": st["checked"]}
        finally:
            self.durations.save()
            st.update(running=False, message=message, finished_at=self._clock())

    def measure_one(self, path: str, size=None) -> Optional[float]:
        seconds = self.durations.seconds(path, size)
        if seconds:
            return seconds
        source = self

        class _Session:
            def get(self, url, headers=None, stream=False, timeout=15):
                return source._get(url, headers=headers, stream=stream, timeout=timeout)

        try:
            seconds = community_durations.read_duration(
                community_durations.http_range_fetch(_Session(), self.file_url(path), {}))
        except Exception:
            seconds = None
        if seconds:
            self.durations.record(path, size, seconds)
            self.durations.save()
        return seconds

    # ---------------------------------------------------------------- search
    def rows(self, prefer: Iterable[str] = (), include_ai: bool = True) -> list:
        """One row per preroll: copies of a file folded, platform versions grouped."""
        data = self.load_index()
        if not data:
            return []
        cache_key = (tuple(prefer), include_ai)
        with self._index_lock:
            cached = self._rows_cache.get(cache_key)
        if cached is not None:
            return cached
        entries = filter_ai_prerolls(data.get("prerolls", []), include_ai=include_ai)
        durations = self.durations.durations(entries)
        rows = community_catalog.dedupe(entries, durations, key=_key)
        rows = community_catalog.group_versions(rows, prefer=tuple(prefer))
        with self._index_lock:
            self._rows_cache[cache_key] = rows
        return rows

    def _row_seconds(self, row: dict) -> Optional[float]:
        return self.durations.seconds(_key(row), row.get("size_bytes"))

    def search(self, *, q: str = "", category: str = "", tag: str = "", duration: str = "",
               downloadable: Optional[bool] = None, sort: str = "", platform: str = "",
               prefer: Iterable[str] = (), include_ai: bool = False) -> List[dict]:
        if downloadable is False:
            return []
        cat = (category or "").strip().lower()
        wants_ai = include_ai or cat == "ai"
        rows = self.rows(prefer, include_ai=wants_ai)
        matcher = QueryMatcher((q or "").lower())
        tag_word = (tag or "").strip().lower()
        out = []
        for row in rows:
            if cat and base.slugify(row.get("category")) != cat and str(row.get("category") or "").lower() != cat:
                continue
            platforms = _platforms(row)
            if platform and platform not in platforms:
                continue
            if tag_word and tag_word not in (row.get("keywords") or ()):
                continue
            seconds = self._row_seconds(row)
            if duration and not base.duration_matches(seconds, duration):
                continue
            rank = 0
            if q:
                ranks = [matcher.rank(row)] + [matcher.rank(dict(v, keywords=row.get("keywords")))
                                               for v in row.get("versions") or ()]
                ranks = [r for r in ranks if r is not None]
                if not ranks:
                    continue
                rank = min(ranks)
            out.append((rank, seconds, row))
        sort = sort or ("" if q else "newest")
        if sort == "newest":
            out.sort(key=lambda r: r[2].get("modified_time") or 0, reverse=True)
        elif sort == "shortest":
            out.sort(key=lambda r: (r[1] is None, r[1] or 0, str(r[2].get("title") or "").casefold()))
        elif sort == "az":
            out.sort(key=lambda r: str(r[2].get("title") or "").casefold())
        else:  # relevance; "popular" has no numbers here, so it keeps the server's order
            out.sort(key=lambda r: r[0])
        return [self.to_item(row, seconds) for _, seconds, row in out]

    def to_item(self, row: dict, seconds: Optional[float] = None) -> dict:
        path = _key(row)
        item_id = ids.make(self.id, path)
        category = row.get("category") or "Community"
        creator = creator_of(path.split("/")) if path else row.get("creator")
        folder = path.rsplit("/", 1)[0] + "/"
        versions = []
        for v in row.get("versions") or ():
            vpath = v.get("path") or v.get("id")
            versions.append({"id": ids.make(self.id, vpath), "platform": v.get("platform"),
                             "title": v.get("title"), "size_bytes": v.get("size_bytes"),
                             "duration_seconds": self.durations.seconds(vpath, v.get("size_bytes"))})
        return {
            "id": item_id,
            "source": self.id,
            "title": row.get("title") or path.rsplit("/", 1)[-1],
            "description": "",
            "category": {"slug": base.slugify(category), "name": category},
            "tags": [],
            "creator": {"name": creator, "url": None} if creator else None,
            "duration_seconds": seconds if seconds is not None else self._row_seconds(row),
            "width": None,
            "height": None,
            "size_bytes": row.get("size_bytes"),
            "thumbnail_url": None,
            "preview_url": f"/api/community/preview?id={quote(item_id, safe='')}",
            "embed_url": None,
            "page_url": SITE_URL + folder,
            "downloadable": True,
            "platforms": _platforms(row),
            "attribution": f"by {creator} · via Prerolls.uk (Typical Nerds)" if creator else "via Prerolls.uk (Typical Nerds)",
            "published_at": row.get("modified_iso"),
            "versions": versions,
            "in_library": None,
            "_path": path,
            "_also": [ids.make(self.id, d) for d in row.get("duplicate_ids") or ()],
        }

    def item(self, key: str) -> Optional[dict]:
        """The item for a file path, or None when the list doesn't have it."""
        for entry in self.entries():
            if _key(entry) == key:
                return self.to_item(entry)
        return None

    def categories(self, *, include_ai: bool = False) -> List[dict]:
        rows = self.rows((), include_ai=True)
        counts: dict = {}
        for row in rows:
            # AI is listed so people can find it, though "all" leaves it out.
            name = row.get("category") or "Community"
            counts[name] = counts.get(name, 0) + 1
        return [{"slug": base.slugify(n), "name": n, "count": c}
                for n, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        data = self.load_index()
        rows = self.rows((), include_ai=False) if data else []
        age = self.index_age()
        return {"item_count": len(rows), "downloadable_count": len(rows),
                "last_refreshed": now_iso(self._clock() - age) if age is not None else None,
                "error": self._error}

    def terms(self, accepted: bool = False) -> dict:
        return {"summary": FAIR_USE_SUMMARY, "url": FAIR_USE_URL, "needs_acceptance": True,
                "accepted": bool(accepted), "policy": FAIR_USE_POLICY}

    # ------------------------------------------------------------- downloads
    def wait_turn(self) -> float:
        return self.pacer.wait()

    def download(self, item: dict, folder: str) -> base.DownloadedFile:
        if not self.settings().get("accepted"):
            raise terms_needed()
        path = item.get("_path") or ids.split(item.get("id"))[1]
        url = self.file_url(path)
        try:
            resp = self._get(url, stream=True, timeout=60)
        except net.BlockedAddress:
            raise blocked(SITE)
        except Exception:
            raise network_error(SITE)
        return base.save_stream(resp, folder, site=SITE, expected_size=item.get("size_bytes"),
                                name_hint=urllib.parse.unquote(path.rsplit("/", 1)[-1]),
                                accept_types=("video/", "application/octet-stream", "application/mp4"))

    def open_preview(self, path: str, range_header: Optional[str] = None):
        """An upstream response for the in-app player (Range passed through)."""
        url = self.file_url(path)
        headers = {"Range": range_header} if range_header else {}
        try:
            resp = self._get(url, headers=headers, stream=True, timeout=30)
        except net.BlockedAddress:
            raise blocked(SITE)
        except Exception:
            raise network_error(SITE)
        if resp.status_code >= 400:
            resp.close()
            if resp.status_code == 404:
                raise AppError("Prerolls.uk doesn't have this video anymore.", status=404,
                               code="community_item_gone", hint="Refresh the list to see what's there now.")
            raise AppError("Prerolls.uk couldn't play this video right now.", status=502,
                           code="community_preview_failed", hint="Try again in a moment.")
        return resp

    # ---------------------------------------------------------------- health
    def check_server(self) -> dict:
        url = self.base_url()
        started = time.time()
        try:
            resp = self._get(url + "/", timeout=10)
            ok = resp.status_code == 200
            resp.close()
            return {"online": ok, "response_time_ms": int((time.time() - started) * 1000),
                    "error": None if ok else f"The server answered with an error ({resp.status_code})."}
        except Exception:
            return {"online": False, "response_time_ms": None, "error": "The server didn't answer."}


def terms_needed() -> AppError:
    return AppError("Accept the Prerolls.uk Fair Use Policy first.", status=403, code="terms_not_accepted",
                    hint="Open the Prerolls.uk library on the Community page and accept the policy.")


def _key(entry: dict) -> str:
    return str(entry.get("path") or entry.get("id") or "")


def _platforms(row: dict) -> List[str]:
    found = set()
    for v in (row.get("versions") or [row]):
        p = v.get("platform") if "platform" in v else community_catalog.platform_of(v)
        if p in base.PLATFORMS:
            found.add(p)
        else:
            found.update(base.PLATFORMS)
    return [p for p in base.PLATFORMS if p in found]
