"""The NeXroll ``/community-prerolls/*`` routes, kept for older pages and scripts.

They answer in the shapes NeXroll 2.4.0 used, but everything goes through the
Prerolls.uk source (community/prerollsuk.py), so they only reach Typical
Nerds' own servers: the server can only be set to a mirror servers.json lists,
previews and downloads only fetch file paths on the server in use, and the
live folder scrape, demo results, Top 5 ids that couldn't be downloaded and
the poster lookups on other sites are gone. Downloads also accept Prerolls.me
ids (``pm:<slug>``).

The matching routes (downloaded-ids, match-existing, clear-matches,
migrate-legacy) stay in main.py with the rest of the matching code.
"""

from __future__ import annotations

import asyncio
import base64
import json
import random
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from backend import community_catalog, community_servers, models
from backend.community import ids, service
from backend.community.prerollsuk import (FAIR_USE_POLICY, MAX_AGE, PrerollsUkSource, listed_servers,
                                          terms_needed)
from backend.community_filter import filter_ai_prerolls
from backend.errors import AppError, bad_input, conflict
from backend.routers.community import get_db, stream_preview

router = APIRouter(tags=["Community (old routes)"])

BUILD_COOLDOWN = 600          # seconds between manual list rebuilds
HEALTH_TTL = 300
_build = {"last_manual": 0.0, "job_id": None}
_health: dict = {}


def uk() -> PrerollsUkSource:
    return service.get_source("prerollsuk")


def require_terms(db) -> None:
    if not service.terms_accepted(db, uk()):
        raise terms_needed()


def _setting(db, create: bool = False):
    s = db.query(models.Setting).first()
    if not s and create:
        s = models.Setting()
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


# ------------------------------------------------------------------ servers

@router.get("/community-prerolls/health")
def health(db=Depends(get_db)):
    source = uk()
    url = source.base_url()
    listed = community_servers.find(url, source.server_list())
    server = {"server_url": url, "server_name": listed.get("name") if listed else None}
    cached = _health.get(url)
    now = time.time()
    if cached and now - cached["at"] < HEALTH_TTL:
        return dict(cached["body"], cached=True, **server)
    result = source.check_server()
    body = dict(result, last_checked=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)))
    _health[url] = {"at": now, "body": body}
    return dict(body, cached=False, **server)


@router.get("/community-prerolls/servers")
def servers():
    source = uk()
    listed = source.server_list()
    if not listed:
        return {"servers": [], "error": "Prerolls Max couldn't get the server list from Prerolls.uk."}
    return {"servers": listed, "source": source.server_list_source(),
            "default_url": community_servers.default_url(listed)}


def _server_payload(db) -> dict:
    source = uk()
    s = _setting(db)
    saved = community_servers.normalize(getattr(s, "community_server_url", None) if s else None) or None
    listed = source.server_list()
    url, set_aside = source.choose_server(saved, listed)
    entry = community_servers.find(url, listed)
    return {"server_url": url,
            "is_custom": bool(saved) and not set_aside,
            "default_url": community_servers.default_url(listed) or community_servers.FALLBACK_URL,
            "server_name": entry.get("name") if entry else None,
            "set_aside_url": set_aside,
            "download_delay_seconds": community_servers.download_delay(url, listed)}


@router.get("/community-prerolls/server-url")
def get_server_url(db=Depends(get_db)):
    return _server_payload(db)


@router.put("/community-prerolls/server-url")
def set_server_url(url: Optional[str] = Body(None, embed=True), db=Depends(get_db)):
    """Pick one of the servers servers.json lists; null or "" goes back to the default."""
    source = uk()
    clean = community_servers.normalize(url) or None
    listed = listed_servers(source.server_list())
    if clean and not any(community_servers.same_server(clean, s.get("baseUrl")) for s in listed):
        raise bad_input("Pick one of the Prerolls.uk servers in the list.", field="url",
                        hint="Prerolls Max only downloads from the servers Typical Nerds list.")
    if clean and listed and community_servers.same_server(clean, listed[0].get("baseUrl")):
        clean = None
    s = _setting(db, create=True)
    s.community_server_url = clean
    db.commit()
    return _server_payload(db)


# ------------------------------------------------------------------ fair use

@router.get("/community-prerolls/fair-use-policy")
def fair_use_policy():
    return {"policy": FAIR_USE_POLICY, "source": community_servers.FALLBACK_URL + "/",
            "credit": "https://typicalnerds.uk/"}


@router.post("/community-prerolls/fair-use/accept")
def fair_use_accept(db=Depends(get_db)):
    service.accept_terms(db, uk())
    s = _setting(db)
    at = getattr(s, "community_fair_use_accepted_at", None)
    return {"accepted": True, "accepted_at": at.isoformat() + "Z" if at else None,
            "message": "Fair Use Policy accepted"}


@router.get("/community-prerolls/fair-use/status")
def fair_use_status(db=Depends(get_db)):
    s = _setting(db)
    at = getattr(s, "community_fair_use_accepted_at", None) if s else None
    return {"accepted": bool(s and getattr(s, "community_fair_use_accepted", False)),
            "accepted_at": at.isoformat() + "Z" if at else None}


# --------------------------------------------------------------------- index

class AutoRefreshRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    enabled: bool


@router.put("/community-prerolls/auto-refresh")
def set_auto_refresh(req: AutoRefreshRequest, db=Depends(get_db)):
    s = _setting(db, create=True)
    s.community_auto_refresh = bool(req.enabled)
    db.commit()
    return {"auto_refresh": bool(req.enabled)}


@router.get("/community-prerolls/build-index")
def build_index(db=Depends(get_db)):
    """Start rebuilding the Prerolls.uk list (at most once every 10 minutes)."""
    require_terms(db)
    source = uk()
    if service.state.runner.active(service.refresh_key(source.id)) or source.building:
        raise AppError("The list is already being rebuilt. Wait for it to finish.", status=429,
                       code="refresh_running")
    wait = BUILD_COOLDOWN - (time.time() - _build["last_manual"])
    if wait > 0:
        raise AppError(f"Wait {int(wait) // 60} min {int(wait) % 60} s before rebuilding the list again.",
                       status=429, code="too_many_requests",
                       hint="Rebuilding reads hundreds of folders on Prerolls.uk, so it's limited.")
    _build["last_manual"] = time.time()
    job = service.start_refresh(source)
    _build["job_id"] = job["id"]
    return {"status": "started", "job_id": job["id"],
            "message": "Started rebuilding the list. Follow it with the build-progress stream."}


@router.get("/community-prerolls/build-progress")
async def build_progress():
    """Server-sent events with the rebuild's progress. Ends when the build ends,
    whether it worked or not."""
    source = uk()

    async def events():
        while True:
            job = service.state.runner.latest(service.refresh_key(source.id))
            state = dict(source.build_state)
            running = bool(job and job["state"] in ("queued", "running")) or source.building
            state["building"] = running
            if job and job["state"] == "failed":
                state["message"] = job["message"]
                state["failed"] = True
            if not running:
                state["progress"] = 100
            yield f"data: {json.dumps(state)}\n\n"
            if not running:
                return
            await asyncio.sleep(0.5)

    return StreamingResponse(events(), media_type="text/event-stream")


@router.get("/community-prerolls/index-status")
def index_status(db=Depends(get_db)):
    source = uk()
    s = _setting(db)
    auto = bool(getattr(s, "community_auto_refresh", False)) if s else False
    data = source.load_index()
    if not data:
        return {"exists": False, "auto_refresh": auto,
                "message": "No list yet. Build it to browse Prerolls.uk."}
    age = source.index_age() or 0
    stale = age > MAX_AGE
    try:
        size_mb = round(source.index_path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        size_mb = None
    return {"exists": True, "is_stale": stale, "age_days": age / 86400, "max_age_days": MAX_AGE / 86400,
            "auto_refresh": auto, "size_mb": size_mb, "total_prerolls": data.get("total_prerolls", 0),
            "created_at": data.get("created_at"),
            "message": "The list is over a week old. Refresh recommended." if stale else "The list is up to date."}


@router.get("/community-prerolls/facets")
def facets(include_ai: bool = False):
    source = uk()
    data = source.load_index()
    if not data:
        return {"available": False, "categories": [], "creators": [], "platforms": [], "total": 0,
                "has_dates": False, "message": "Build the community list to browse."}
    entries = filter_ai_prerolls(data.get("prerolls", []), include_ai=include_ai)
    durations = source.durations.durations(entries)
    groups = {"categories": {}, "creators": {}, "platforms": {}}
    has_dates = False
    for e in entries:
        groups["categories"].setdefault(e.get("category") or "Other", []).append(e)
        groups["creators"].setdefault(e.get("creator") or "Unknown", []).append(e)
        platform = community_catalog.platform_of(e)
        name = platform.capitalize() if platform in ("plex", "jellyfin", "emby") else "Universal"
        groups["platforms"].setdefault(name, []).append(e)
        has_dates = has_dates or bool(e.get("modified_time"))

    def count(rows, versions=True):
        rows = community_catalog.dedupe(rows, durations, key=lambda x: x.get("path") or x.get("id"))
        return len(community_catalog.group_versions(rows) if versions else rows)

    def as_list(group, versions=True):
        counts = {k: count(v, versions) for k, v in group.items()}
        return [{"name": k, "count": v} for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))]

    return {"available": True, "total": count(entries), "categories": as_list(groups["categories"]),
            "platforms": as_list(groups["platforms"], versions=False), "creators": as_list(groups["creators"]),
            "has_dates": has_dates, "created_at": data.get("created_at"), "include_ai": include_ai}


@router.get("/community-prerolls/durations")
def durations(include_ai: bool = False):
    status = uk().length_status(include_ai=include_ai)
    status["available"] = status["total"] > 0
    return status


@router.post("/community-prerolls/durations/measure")
def measure(include_ai: bool = False, db=Depends(get_db)):
    require_terms(db)
    source = uk()
    if not source.has_data():
        raise conflict("Build the community list first.", code="needs_refresh")
    if source.building:
        raise conflict("The list is being rebuilt; lengths are read when it finishes.", code="refresh_running")
    status = source.length_status()
    started = False
    if status["pending"] and not status["running"]:
        started = bool(service.start_lengths(source))
    return {"started": started, "available": True, **source.length_status(include_ai=include_ai)}


# -------------------------------------------------------------------- search

def _legacy_row(source: PrerollsUkSource, row: dict, base: str) -> dict:
    """An index row as NeXroll returned it, with its length and a url on the server in use."""
    base = base.rstrip("/")
    key = row.get("path") or row.get("id")
    out = dict(row, duration=source.durations.seconds(key, row.get("size_bytes")), url=base + key)
    if row.get("versions"):
        out["versions"] = [dict(v, duration=source.durations.seconds(v.get("path") or v.get("id"), v.get("size_bytes")),
                                url=base + (v.get("path") or v.get("id")))
                           for v in row["versions"]]
    return out


@router.get("/community-prerolls/search")
def search(query: str = "", category: str = "", platform: str = "", creator: str = "", sort: str = "relevance",
           limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), include_ai: bool = False,
           min_duration: Optional[float] = Query(None, ge=0), max_duration: Optional[float] = Query(None, ge=0),
           servers: str = "", db=Depends(get_db)):
    """Search the saved Prerolls.uk list (no list, no results: nothing is scraped live)."""
    require_terms(db)
    source = uk()
    data = source.load_index()
    if not data:
        return {"found": 0, "results": [], "total": 0, "offset": offset, "limit": limit, "query": query,
                "source": "none", "needs_index": True,
                "message": "Build the community list first (Refresh), then search it."}
    from backend import community_durations
    from backend.community_search import QueryMatcher
    prefer = tuple(s.strip().lower() for s in servers.split(",") if s.strip()) or service.preferred_platforms(db)
    rows = source.rows(prefer, include_ai=include_ai)
    matcher = QueryMatcher(query.lower())
    results, ranks, unmeasured = [], {}, 0
    for row in rows:
        if query:
            found = [matcher.rank(row)] + [matcher.rank(dict(v, keywords=row.get("keywords"))) for v in row.get("versions") or ()]
            found = [r for r in found if r is not None]
            if not found:
                continue
            ranks[id(row)] = min(found)
        if category and category.lower() not in str(row.get("category") or "").lower():
            continue
        if platform:
            blob = (str(row.get("path") or "") + " " + str(row.get("title") or "")).lower()
            versions = " ".join(str(v.get("platform") or "") for v in row.get("versions") or ())
            if platform.lower() not in blob and platform.lower() not in versions:
                continue
        if creator and creator.lower() not in str(row.get("creator") or "").lower():
            continue
        if min_duration is not None or max_duration is not None:
            seconds = source.durations.seconds(row.get("path") or row.get("id"), row.get("size_bytes"))
            if seconds is None:
                unmeasured += 1
                continue
            if not community_durations.length_matches(seconds, min_duration, max_duration):
                continue
        results.append(row)
    key = lambda r: r.get("path") or r.get("id")
    if sort == "newest":
        results.sort(key=lambda r: r.get("modified_time") or 0, reverse=True)
    elif sort == "oldest":
        results.sort(key=lambda r: r.get("modified_time") or 0)
    elif sort == "name":
        results.sort(key=lambda r: str(r.get("title") or "").lower())
    elif sort in ("shortest", "longest"):
        results.sort(key=lambda r: (community_durations.length_sort_key(
            source.durations.seconds(key(r), r.get("size_bytes")), longest=sort == "longest"),
            str(r.get("title") or "").lower()))
    elif ranks:
        results.sort(key=lambda r: ranks[id(r)])
    base = source.base_url()
    page = [_legacy_row(source, r, base) for r in results[offset:offset + limit]]
    return {"found": len(page), "results": page, "total": len(results), "offset": offset, "limit": limit,
            "query": query, "category": category, "creator": creator, "sort": sort,
            "min_duration": min_duration, "max_duration": max_duration, "unmeasured": unmeasured,
            "include_ai": include_ai, "source": "local_index", "index_created": data.get("created_at"),
            "message": f"Searched {data.get('total_prerolls', 0)} prerolls from the saved list"}


def _pick(db, include_ai: bool, platform: str = "", category: str = "") -> list:
    source = uk()
    rows = source.rows((), include_ai=include_ai)
    out = []
    for row in rows:
        if platform and platform.lower() not in str(row.get("title") or "").lower() \
                and platform.lower() not in " ".join(str(v.get("platform")) for v in row.get("versions") or ()):
            continue
        if category and category.lower() not in str(row.get("category") or "").lower():
            continue
        out.append(row)
    return out


@router.get("/community-prerolls/random")
def random_pick(platform: str = "", category: str = "", include_ai: bool = False, db=Depends(get_db)):
    require_terms(db)
    if not uk().has_data():
        return {"found": False, "result": None, "needs_index": True,
                "message": "Build the community list first."}
    rows = _pick(db, include_ai, platform, category)
    if not rows:
        return {"found": False, "result": None, "message": "No prerolls found matching filters"}
    return {"found": True, "result": _legacy_row(uk(), random.choice(rows), uk().base_url()), "source": "local_index"}


@router.get("/community-prerolls/top5")
def top5(platform: str = "", db=Depends(get_db)):
    """The five newest prerolls in the saved list, with real, downloadable ids."""
    require_terms(db)
    rows = _pick(db, False, platform)
    rows.sort(key=lambda r: r.get("modified_time") or 0, reverse=True)
    base = uk().base_url()
    results = [dict(_legacy_row(uk(), r, base), featured=True) for r in rows[:5]]
    return {"found": len(results), "results": results}


_GRADIENTS = [("#667eea", "#764ba2"), ("#f093fb", "#f5576c"), ("#4facfe", "#00f2fe"),
              ("#43e97b", "#38f9d7"), ("#fa709a", "#fee140"), ("#30cfd0", "#330867")]


def _tile(n: int) -> str:
    a, b = _GRADIENTS[n % len(_GRADIENTS)]
    svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='300' height='180'><defs>"
           f"<linearGradient id='g{n}' x1='0%' y1='0%' x2='100%' y2='100%'>"
           f"<stop offset='0%' stop-color='{a}'/><stop offset='100%' stop-color='{b}'/></linearGradient></defs>"
           f"<rect width='300' height='180' fill='url(#g{n})'/>"
           f"<text x='150' y='100' text-anchor='middle' fill='#fff' font-size='16' font-weight='bold'>NEW</text></svg>")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


@router.get("/community-prerolls/latest")
def latest(limit: int = Query(6, ge=1, le=50), platform: str = "", include_ai: bool = False, db=Depends(get_db)):
    require_terms(db)
    if not uk().has_data():
        return {"found": False, "results": [], "message": "Build the community list to see the newest prerolls",
                "needs_index": True}
    rows = _pick(db, include_ai, platform)
    rows.sort(key=lambda r: r.get("modified_time") or 0, reverse=True)
    base = uk().base_url()
    results = [dict(_legacy_row(uk(), r, base), thumbnail=_tile(n)) for n, r in enumerate(rows[:limit])]
    return {"found": True, "results": results, "total": len(results),
            "message": f"Showing {len(results)} latest prerolls", "source": "local_index"}


# ------------------------------------------------------------ one preroll

@router.get("/community-prerolls/metadata")
def metadata(preroll_id: str = Query(..., max_length=1100), db=Depends(get_db)):
    require_terms(db)
    source_id, key = ids.split(preroll_id, field="preroll_id")
    if source_id != "prerollsuk":
        source, item = service.find_item(preroll_id)
        return {"preroll_id": preroll_id, "duration": item.get("duration_seconds") if item else None,
                "size_bytes": item.get("size_bytes") if item else None}
    source = uk()
    entry = next((e for e in source.entries() if (e.get("path") or e.get("id")) == key), None)
    size = entry.get("size_bytes") if entry else None
    seconds = source.measure_one(key, size)
    return {"preroll_id": preroll_id, "duration": round(seconds, 1) if seconds else None, "size_bytes": size}


@router.get("/community-prerolls/preview")
def preview(request: Request, preroll_id: str = Query(..., max_length=1100), db=Depends(get_db)):
    require_terms(db)
    source_id, key = ids.split(preroll_id, field="preroll_id")
    if source_id != "prerollsuk":
        raise bad_input("This route only plays Prerolls.uk videos.", field="preroll_id",
                        hint="Use /api/community/preview for Prerolls.me.")
    return stream_preview(uk(), key, request.headers.get("range"))


class LegacyDownloadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    preroll_id: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    category_id: Optional[int] = None
    add_to_category: bool = False


@router.post("/community-prerolls/download")
def download(req: LegacyDownloadRequest, db=Depends(get_db)):
    """Download one video and wait for it. ``url`` only supplies a path on the
    Prerolls.uk server in use; its host is ignored."""
    item_id = req.preroll_id
    if not item_id and req.url:
        from urllib.parse import urlsplit
        item_id = urlsplit(str(req.url)).path or None
    if not item_id:
        raise bad_input("Pick an intro video to download.", field="preroll_id")
    out = service.download_now(db, item_id, req.category_id)
    category = out["category"]
    preroll = out.get("preroll")
    if out["status"] == "skipped":
        preroll = db.query(models.Preroll).filter(models.Preroll.id == out["preroll_id"]).first()
    return {
        "downloaded": out["status"] == "added",
        "already_in_library": out["status"] == "skipped",
        "id": preroll.id if preroll else out["preroll_id"],
        "filename": preroll.filename if preroll else None,
        "display_name": preroll.display_name if preroll else out["name"],
        "category_id": preroll.category_id if preroll else category.id,
        "category": {"id": category.id, "name": category.name},
        "thumbnail": preroll.thumbnail if preroll else None,
        "duration": preroll.duration if preroll else None,
        "file_size": preroll.file_size if preroll else None,
        "community_preroll_id": out["item_id"],
        "source": "community_prerolls",
        "credit": "https://typicalnerds.uk/" if out["item_id"].startswith("tn:") else "https://www.prerolls.me/",
        "auto_applied": out.get("applied", False),
    }
