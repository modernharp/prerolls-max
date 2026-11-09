"""Community libraries API (docs/dev/CONTRACTS.md section 5).

Two libraries, Prerolls.me first, then Prerolls.uk (Typical Nerds). People
browse either, pick videos from both, and download them together in one job.
"""

from __future__ import annotations

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from backend.community import base, ids, service
from backend.community.prerollsme import PrerollsMeSource
from backend.community.prerollsuk import PREVIEW_HEADERS, PrerollsUkSource
from backend.errors import AppError, not_found

router = APIRouter(tags=["Community"])

SourceId = Literal["prerollsme", "prerollsuk"]


def get_db():
    db = service.state.session_factory()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/community/sources")
def list_sources(db=Depends(get_db)):
    """Both libraries, Prerolls.me first, with counts, terms and any problem."""
    out = []
    for source in service.all_sources():
        if isinstance(source, PrerollsMeSource):
            if source.has_data():
                service.maybe_refresh_in_background(source)
            else:
                try:
                    source.ensure_loaded()   # the first visit: one small request, counts right away
                except AppError:
                    pass                     # shown as the source's error
        out.append(service.source_payload(db, source))
    return out


@router.get("/api/community/items")
def list_items(
    source: SourceId,
    q: str = Query("", max_length=200),
    category: str = Query("", max_length=100),
    tag: str = Query("", max_length=100),
    duration: Optional[Literal["lt10", "10-20", "20-30", "30plus"]] = None,
    downloadable: Optional[bool] = None,
    sort: Optional[Literal["newest", "popular", "shortest", "az"]] = None,
    platform: Optional[Literal["plex", "jellyfin", "emby"]] = None,
    include_ai: bool = False,
    page: int = Query(1, ge=1, le=10000),
    limit: int = Query(24, ge=1, le=100),
    db=Depends(get_db),
):
    src = service.get_source(source)
    items = service.search(db, src, q=q.strip(), category=category.strip(), tag=tag.strip(),
                           duration=duration or "", downloadable=downloadable, sort=sort or "",
                           platform=platform or "", include_ai=include_ai)
    return service.page_of(db, items, page, limit)


@router.get("/api/community/categories")
def list_categories(source: SourceId, include_ai: bool = False, db=Depends(get_db)):
    src = service.get_source(source)
    if src.needs_acceptance and not service.terms_accepted(db, src):
        from backend.community.prerollsuk import terms_needed
        raise terms_needed()
    if isinstance(src, PrerollsUkSource) and not src.has_data():
        return []
    return src.categories(include_ai=include_ai)


@router.get("/api/community/thumb")
def thumbnail(id: str = Query(..., max_length=1100)):
    """A community video's picture, fetched once and kept on disk."""
    source_id, key = ids.split(id)
    source = service.get_source(source_id)
    found = source.thumbnail(key) if isinstance(source, PrerollsMeSource) else None
    if not found:
        raise not_found("The picture for this video", hint="It may not have one.")
    path, media_type = found
    return FileResponse(str(path), media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})


@router.get("/api/community/preview")
def preview(request: Request, id: str = Query(..., max_length=1100), db=Depends(get_db)):
    """Play a Prerolls.uk video in the app (Prerolls.me videos play from their own address)."""
    source_id, key = ids.split(id)
    source = service.get_source(source_id)
    if isinstance(source, PrerollsMeSource):
        item = source.item(key)
        if not item or not item.get("preview_url"):
            raise not_found("A playable copy of this video", hint="Open it on Prerolls.me to watch it.")
        from fastapi.responses import RedirectResponse
        return RedirectResponse(item["preview_url"], status_code=307)
    if not service.terms_accepted(db, source):
        from backend.community.prerollsuk import terms_needed
        raise terms_needed()
    return stream_preview(source, key, request.headers.get("range"))


def stream_preview(source: PrerollsUkSource, path: str, range_header: Optional[str]):
    upstream = source.open_preview(path, range_header)
    headers = {h: upstream.headers[h] for h in PREVIEW_HEADERS if h in upstream.headers}
    headers.setdefault("Accept-Ranges", "bytes")
    headers["Cache-Control"] = "private, max-age=300"
    media = str(upstream.headers.get("Content-Type") or "video/mp4")
    if not media.startswith(("video/", "application/octet-stream")):
        upstream.close()
        raise AppError("Prerolls.uk sent something that isn't a video.", status=502, code="community_not_a_video")

    def body():
        try:
            for chunk in upstream.iter_content(chunk_size=base.CHUNK):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return StreamingResponse(body(), status_code=upstream.status_code, media_type=media, headers=headers)


@router.post("/api/community/sources/{source_id}/refresh")
def refresh_source(source_id: SourceId, db=Depends(get_db)):
    """Check the library for new videos in the background. Returns {job_id}."""
    source = service.get_source(source_id)
    if source.needs_acceptance and not service.terms_accepted(db, source):
        from backend.community.prerollsuk import terms_needed
        raise terms_needed()
    job = service.start_refresh(source)
    return {"job_id": job["id"]}


@router.post("/api/community/sources/{source_id}/accept-terms")
def accept_source_terms(source_id: SourceId, db=Depends(get_db)):
    source = service.get_source(source_id)
    service.accept_terms(db, source)
    return service.source_payload(db, source)


class DownloadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    item_ids: List[str] = Field(..., min_length=1, max_length=service.MAX_ITEMS_PER_DOWNLOAD)
    collection_id: Optional[int] = Field(None, ge=1)
    new_collection_name: Optional[str] = Field(None, max_length=100)


@router.post("/api/community/download")
def download(req: DownloadRequest, db=Depends(get_db)):
    """Download videos from either library, or both, into one collection. Returns {job_id}."""
    job = service.start_download(db, req.item_ids, req.collection_id, req.new_collection_name)
    return {"job_id": job["id"]}
