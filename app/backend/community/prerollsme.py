"""Prerolls.me: a catalog with an official, keyless JSON API.

https://www.prerolls.me/developers documents ``/api/v1/catalog.json``: every
intro video with its title, description, category, tags, creator, length,
size and links, in one file with an ETag. Prerolls Max keeps a copy on disk,
asks for a new one at most once an hour (with If-None-Match, so an unchanged
catalog costs a 304), and searches the copy locally.

What can be downloaded: only videos Prerolls.me hosts itself
(``download.isDirectFile``, on videos.prerolls.me). The others are on YouTube
or Vimeo; Prerolls Max shows them to watch and links to them, and never
downloads them. A download starts at the item's ``download.url`` (as the
site's fair-use notes ask) and follows redirects only to videos.prerolls.me;
the file must be a video of exactly ``fileSize`` bytes, and its MD5 must match
the storage ETag when the ETag is one.

Credit: every item carries "by {creator} · via Prerolls.me" and its page link.
"""

from __future__ import annotations

import threading
import time
from typing import Iterable, List, Optional
from urllib.parse import quote, urlsplit

from backend import net
from backend.community import base, ids
from backend.community.http import (Http, Pacer, atomic_write_bytes, atomic_write_json, blocked,
                                    network_error, now_iso, read_json)
from backend.errors import AppError

SITE = "Prerolls.me"
SITE_URL = "https://www.prerolls.me"
CATALOG_URL = "https://www.prerolls.me/api/v1/catalog.json"
TERMS_URL = "https://www.prerolls.me/developers"
API_HOSTS = ("www.prerolls.me",)
DOWNLOAD_HOSTS = ("www.prerolls.me", "videos.prerolls.me")
FILE_HOST = "videos.prerolls.me"
THUMB_HOSTS = ("videos.prerolls.me", "i.ytimg.com")
EMBED_HOSTS = ("www.youtube-nocookie.com", "www.youtube.com", "player.vimeo.com")
REFRESH_EVERY = 3600          # seconds; the site asks for at most one catalog check an hour
RETRY_FAILED_AFTER = 300      # a failed check is tried again after this
DOWNLOAD_GAP = 2.0            # seconds between file downloads
MAX_CATALOG_BYTES = 32 * 1024 * 1024
MAX_THUMB_BYTES = 2 * 1024 * 1024

FAIR_USE = (
    "Free to use on your own media server. Keep the credit: the creator and Prerolls.me, "
    "with a link back. Prerolls Max shows it next to every video and saves it with each download. "
    "Videos hosted on YouTube or Vimeo can be watched there but aren't downloaded."
)


def _host(url) -> str:
    return net.host_of(str(url or ""))


def _http_url(url) -> Optional[str]:
    text = str(url or "").strip()
    return text if text.startswith(("https://", "http://")) and _host(text) else None


def attribution(creator: Optional[str]) -> str:
    return f"by {creator} · via Prerolls.me" if creator else "via Prerolls.me"


class PrerollsMeSource(base.CommunitySource):
    id = "prerollsme"
    name = "Prerolls.me"
    site_url = SITE_URL
    description = ("Intro videos collected at Prerolls.me, with titles, tags and creators. "
                   "Videos hosted on Prerolls.me can be downloaded; YouTube and Vimeo ones are to watch.")
    needs_acceptance = False

    def __init__(self, folder, *, http: Optional[Http] = None, clock=time.time, sleep=time.sleep):
        from pathlib import Path
        self.folder = Path(folder)
        self.http = http or Http()
        self._clock = clock
        self._lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self.refreshing = False
        self._items: Optional[List[dict]] = None
        self._by_slug: dict = {}
        self._categories: List[dict] = []
        self._meta: dict = read_json(self.folder / "meta.json", {}) or {}
        self._error: Optional[dict] = None
        self.pacer = Pacer(lambda: DOWNLOAD_GAP, sleep=sleep)

    # ------------------------------------------------------------------ files
    @property
    def catalog_path(self):
        return self.folder / "catalog.json"

    @property
    def thumbs_dir(self):
        return self.folder / "thumbs"

    def _save_meta(self) -> None:
        try:
            atomic_write_json(self.folder / "meta.json", self._meta)
        except OSError:
            pass

    # --------------------------------------------------------------- catalog
    def _load_from_disk(self) -> bool:
        data = read_json(self.catalog_path)
        if not isinstance(data, dict) or not isinstance(data.get("prerolls"), list):
            return False
        self._install(data)
        return True

    def _install(self, data: dict) -> None:
        items = [self._map(raw) for raw in data.get("prerolls") or () if isinstance(raw, dict)]
        items = [i for i in items if i]
        counts: dict = {}
        names: dict = {}
        for item in items:
            cat = item.get("category")
            if cat:
                counts[cat["slug"]] = counts.get(cat["slug"], 0) + 1
                names[cat["slug"]] = cat["name"]
        order = [c.get("slug") for c in data.get("categories") or () if isinstance(c, dict)]
        order += [s for s in counts if s not in order]
        with self._lock:
            self._items = items
            self._by_slug = {i["_slug"]: i for i in items}
            self._categories = [{"slug": s, "name": names[s], "count": counts[s]} for s in order if s in counts]

    def ensure_loaded(self) -> None:
        """Have a catalog in memory: from disk, else fetched now."""
        with self._lock:
            if self._items is not None:
                return
            if self._load_from_disk():
                return
        self.refresh(force=True)

    def has_data(self) -> bool:
        with self._lock:
            if self._items is None:
                self._load_from_disk()
            return bool(self._items)

    def due(self) -> bool:
        checked = float(self._meta.get("checked_at") or 0)
        wait = REFRESH_EVERY if self._meta.get("ok", True) else RETRY_FAILED_AFTER
        return self._clock() - checked >= wait

    def refresh(self, ctx=None, *, force: bool = False) -> dict:
        """Check for a new catalog (at most once an hour). Without a catalog on
        disk it is fetched whatever the time. Network work happens outside the
        state lock, so listing keeps working while a check runs."""
        with self._refresh_lock:
            self.refreshing = True
            try:
                return self._refresh(ctx)
            finally:
                self.refreshing = False

    def _refresh(self, ctx=None) -> dict:
        have = self.catalog_path.exists()
        if have and not self.due():
            minutes = max(1, int((REFRESH_EVERY - (self._clock() - float(self._meta.get("checked_at") or 0))) / 60))
            if self._items is None:
                self._load_from_disk()
            return {"changed": False, "items": len(self._items or ()),
                    "message": f"Prerolls.me was checked less than an hour ago. "
                               f"It asks apps to check at most once an hour, so the next check is in {minutes} min."}
        if ctx:
            ctx.report(progress=10, message="Checking Prerolls.me for new videos")
        headers = {"Accept": "application/json"}
        if have and self._meta.get("etag"):
            headers["If-None-Match"] = self._meta["etag"]
        try:
            resp = self.http.get(CATALOG_URL, allowed_hosts=API_HOSTS, headers=headers, timeout=30)
        except net.BlockedAddress:
            self._fail()
            raise blocked(SITE)
        except Exception:
            self._fail()
            raise network_error(SITE)
        try:
            if resp.status_code == 304 and have:
                self._meta.update(checked_at=self._clock(), ok=True)
                self._save_meta()
                self._error = None
                if self._items is None:
                    self._load_from_disk()
                return {"changed": False, "items": len(self._items or ()), "message": "Prerolls.me has no new videos."}
            if resp.status_code != 200:
                self._fail()
                raise AppError("Prerolls.me couldn't send its list of videos.", status=502,
                               code="community_list_failed", hint="Try again in a few minutes.")
            body = resp.content or b""
            if len(body) > MAX_CATALOG_BYTES:
                self._fail()
                raise AppError("Prerolls.me sent a list that is far too big, so it was ignored.", status=502,
                               code="community_list_failed")
            import json
            try:
                data = json.loads(body.decode("utf-8"))
            except ValueError:
                self._fail()
                raise AppError("Prerolls.me sent a list Prerolls Max couldn't read.", status=502,
                               code="community_list_failed", hint="Try again later.")
            if not isinstance(data, dict) or not isinstance(data.get("prerolls"), list):
                self._fail()
                raise AppError("Prerolls.me sent a list Prerolls Max couldn't read.", status=502,
                               code="community_list_failed", hint="Try again later.")
            if ctx:
                ctx.report(progress=70, message="Saving the list")
            atomic_write_bytes(self.catalog_path, body)
            self._install(data)
            self._meta.update(etag=resp.headers.get("ETag"), checked_at=self._clock(),
                              refreshed_at=self._clock(), ok=True, generated_at=data.get("generatedAt"))
            self._save_meta()
            self._error = None
            return {"changed": True, "items": len(self._items or ()), "message": f"Loaded {len(self._items or ())} videos from Prerolls.me."}
        finally:
            try:
                resp.close()
            except Exception:
                pass

    def _fail(self) -> None:
        self._meta.update(checked_at=self._clock(), ok=False)
        self._save_meta()
        self._error = {"message": "Prerolls.me didn't answer the last time Prerolls Max checked.",
                       "hint": "The list shown may be out of date. Prerolls Max tries again in a few minutes."}

    # ----------------------------------------------------------------- items
    def _map(self, raw: dict) -> Optional[dict]:
        slug = str(raw.get("slug") or "").strip().lower()
        if not ids.valid_slug(slug):
            return None
        video = raw.get("video") if isinstance(raw.get("video"), dict) else {}
        download = raw.get("download") if isinstance(raw.get("download"), dict) else {}
        thumbs = raw.get("thumbnail") if isinstance(raw.get("thumbnail"), dict) else {}
        source = str(raw.get("source") or "").lower()
        direct = _http_url(video.get("directUrl"))
        downloadable = bool(download.get("isDirectFile")) and source == "r2" and _host(direct) == FILE_HOST
        credit = raw.get("credit") if isinstance(raw.get("credit"), dict) else None
        creator = None
        if credit and str(credit.get("name") or "").strip():
            creator = {"name": str(credit["name"]).strip(), "url": _http_url(credit.get("url"))}
        cat = raw.get("category") if isinstance(raw.get("category"), dict) else None
        category = {"slug": str(cat.get("slug") or base.slugify(cat.get("name"))), "name": str(cat.get("name") or "")} if cat else None
        tags = []
        for tag in raw.get("tags") or ():
            if isinstance(tag, dict) and tag.get("name"):
                tags.append(str(tag["name"]))
            elif isinstance(tag, str):
                tags.append(tag)
        tag_slugs = {base.slugify(t) for t in tags}
        for tag in raw.get("tags") or ():
            if isinstance(tag, dict) and tag.get("slug"):
                tag_slugs.add(str(tag["slug"]))
        embed = _http_url(video.get("embedUrl")) if source in ("youtube", "vimeo") else None
        if embed and _host(embed) not in EMBED_HOSTS:
            embed = None
        page = _http_url(raw.get("url"))
        if _host(page) != "www.prerolls.me":
            page = f"{SITE_URL}/preroll/{slug}"
        thumb_src = _http_url(thumbs.get("small")) or _http_url(thumbs.get("large"))
        if _host(thumb_src) not in THUMB_HOSTS:
            thumb_src = None
        seconds = raw.get("durationSeconds")
        seconds = float(seconds) if isinstance(seconds, (int, float)) and seconds > 0 else None
        size = raw.get("fileSize") if isinstance(raw.get("fileSize"), int) and raw.get("fileSize") > 0 else None
        platforms = [p for p in (raw.get("platforms") or ()) if p in base.PLATFORMS] or list(base.PLATFORMS)
        stats = raw.get("stats") if isinstance(raw.get("stats"), dict) else {}
        popularity = sum(int(stats.get(k) or 0) for k in ("downloads", "likes") if isinstance(stats.get(k), (int, float)))
        title = str(raw.get("title") or slug).strip()
        description = str(raw.get("description") or "").strip()
        item_id = ids.make(self.id, slug)
        download_url = _http_url(download.get("url"))
        if _host(download_url) not in DOWNLOAD_HOSTS:
            download_url = None
        return {
            "id": item_id,
            "source": self.id,
            "title": title,
            "description": description,
            "category": category,
            "tags": tags,
            "creator": creator,
            "duration_seconds": seconds,
            "width": raw.get("width") if isinstance(raw.get("width"), int) else None,
            "height": raw.get("height") if isinstance(raw.get("height"), int) else None,
            "size_bytes": size,
            "thumbnail_url": f"/api/community/thumb?id={quote(item_id, safe='')}" if thumb_src else None,
            "preview_url": direct if downloadable else None,
            "embed_url": embed,
            "watch_url": _http_url(video.get("watchUrl")) if source in ("youtube", "vimeo") else None,
            "page_url": page,
            "downloadable": downloadable,
            "hosted_on": {"r2": "Prerolls.me", "youtube": "YouTube", "vimeo": "Vimeo"}.get(source, source or None),
            "platforms": platforms,
            "attribution": attribution(creator["name"] if creator else None),
            "published_at": raw.get("publishedAt") if isinstance(raw.get("publishedAt"), str) else None,
            "in_library": None,
            "_slug": slug,
            "_tag_slugs": tag_slugs,
            "_popularity": popularity,
            "_text_title": " ".join(base.words(title)),
            "_text": " ".join(base.words(" ".join([title, description, " ".join(tags),
                                                   creator["name"] if creator else "",
                                                   category["name"] if category else ""]))),
            "_download_url": download_url if downloadable else None,
            "_direct_url": direct if downloadable else None,
            "_thumb_src": thumb_src,
        }

    def _all(self) -> List[dict]:
        self.ensure_loaded()
        with self._lock:
            return list(self._items or ())

    def item(self, key: str) -> Optional[dict]:
        self.ensure_loaded()
        with self._lock:
            return self._by_slug.get(key)

    def items_by_size(self) -> dict:
        """{fileSize: item} for downloadable items, for matching local files."""
        if not self.has_data():
            return {}
        with self._lock:
            return {i["size_bytes"]: i for i in self._items or () if i["downloadable"] and i["size_bytes"]}

    def categories(self, *, include_ai: bool = False) -> List[dict]:
        self.ensure_loaded()
        with self._lock:
            return [dict(c) for c in self._categories]

    def search(self, *, q: str = "", category: str = "", tag: str = "", duration: str = "",
               downloadable: Optional[bool] = None, sort: str = "", platform: str = "",
               prefer: Iterable[str] = (), include_ai: bool = False) -> List[dict]:
        items = self._all()
        query_words = base.words(q)
        phrase = " ".join(query_words)
        tag_slug = base.slugify(tag) if tag else ""
        cat_slug = (category or "").strip().lower()
        out = []
        for item in items:
            if cat_slug and (not item["category"] or item["category"]["slug"] != cat_slug
                             and base.slugify(item["category"]["name"]) != cat_slug):
                continue
            if tag_slug and tag_slug not in item["_tag_slugs"]:
                continue
            if downloadable is not None and item["downloadable"] != downloadable:
                continue
            if platform and platform not in item["platforms"]:
                continue
            if duration and not base.duration_matches(item["duration_seconds"], duration):
                continue
            rank = 0
            if query_words:
                text = " " + item["_text"] + " "
                if not all(w in item["_text"] for w in query_words):
                    continue
                title = " " + item["_text_title"] + " "
                if f" {phrase} " in title:
                    rank = 0
                elif phrase in item["_text_title"]:
                    rank = 1
                elif all(f" {w} " in text for w in query_words):
                    rank = 2
                else:
                    rank = 3
            out.append((rank, item))
        sort = sort or ("" if query_words else "newest")
        if sort == "newest":
            out.sort(key=lambda r: r[1]["published_at"] or "", reverse=True)
        elif sort == "popular":
            out.sort(key=lambda r: (-r[1]["_popularity"], _neg_text(r[1]["published_at"])))
        elif sort == "shortest":
            out.sort(key=lambda r: (r[1]["duration_seconds"] is None, r[1]["duration_seconds"] or 0, r[1]["title"].casefold()))
        elif sort == "az":
            out.sort(key=lambda r: r[1]["title"].casefold())
        else:
            out.sort(key=lambda r: r[0])
        return [dict(item) for _, item in out]

    # ---------------------------------------------------------------- status
    def status(self) -> dict:
        have = self.has_data()
        with self._lock:
            items = self._items or []
            refreshed = self._meta.get("refreshed_at") or (self.catalog_path.stat().st_mtime if have and self.catalog_path.exists() else None)
            return {
                "item_count": len(items),
                "downloadable_count": sum(1 for i in items if i["downloadable"]),
                "last_refreshed": now_iso(refreshed),
                "error": self._error,
            }

    def terms(self, accepted: bool = True) -> dict:
        return {"summary": FAIR_USE, "url": TERMS_URL, "needs_acceptance": False, "accepted": True}

    # ------------------------------------------------------------- downloads
    def wait_turn(self) -> float:
        return self.pacer.wait()

    def download(self, item: dict, folder: str) -> base.DownloadedFile:
        if not item.get("downloadable"):
            where = item.get("hosted_on") or "another site"
            raise AppError(f"\"{item.get('title')}\" is on {where}, so it can be watched but not downloaded.",
                           status=409, code="watch_only",
                           hint="Open it on Prerolls.me to watch it, or pick a video marked as downloadable.")
        start = item.get("_download_url") or item.get("_direct_url")
        try:
            resp = self.http.get(start, allowed_hosts=DOWNLOAD_HOSTS, stream=True, timeout=60)
        except net.BlockedAddress:
            raise blocked(SITE)
        except Exception:
            raise network_error(SITE)
        # Each hop is its own request, so the response's url is the last one.
        final = getattr(resp, "url", None) or start
        if resp.status_code == 200 and _host(final) != FILE_HOST:
            # The download page answered itself instead of sending the file.
            resp.close()
            raise AppError("Prerolls.me didn't send the video file.", status=502, code="community_download_failed",
                           hint="Try again later.")
        expected_md5 = base.etag_md5(resp)
        name = urlsplit(item.get("_direct_url") or final).path.rsplit("/", 1)[-1]
        result = base.save_stream(resp, folder, site=SITE, expected_size=item.get("size_bytes"),
                                  expected_md5=expected_md5, name_hint=name, accept_types=("video/",))
        self.remember_md5(item["_slug"], result.md5)
        return result

    def known_md5(self, slug: str) -> Optional[str]:
        return (self._meta.get("md5") or {}).get(slug)

    def remember_md5(self, slug: str, md5: str) -> None:
        with self._lock:
            self._meta.setdefault("md5", {})[slug] = md5
            self._save_meta()

    # ------------------------------------------------------------ thumbnails
    def thumbnail(self, key: str):
        """(path, media type) of the item's small thumbnail, cached on disk."""
        item = self.item(key)
        if not item or not item.get("_thumb_src"):
            return None
        src = item["_thumb_src"]
        ext = ".webp" if src.lower().split("?")[0].endswith(".webp") else ".jpg"
        path = self.thumbs_dir / f"{key}{ext}"
        media = "image/webp" if ext == ".webp" else "image/jpeg"
        if path.exists() and path.stat().st_size > 0:
            return path, media
        try:
            resp = self.http.get(src, allowed_hosts=THUMB_HOSTS, timeout=15)
        except Exception:
            return None
        try:
            ctype = str(resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            body = resp.content or b""
            if resp.status_code != 200 or not ctype.startswith("image/") or not body or len(body) > MAX_THUMB_BYTES:
                return None
        finally:
            try:
                resp.close()
            except Exception:
                pass
        atomic_write_bytes(path, body)
        return path, ctype or media


def _neg_text(text: Optional[str]) -> str:
    # Newest first as a secondary key inside an ascending sort.
    return "".join(chr(0x10FFFF - ord(c)) for c in (text or ""))
