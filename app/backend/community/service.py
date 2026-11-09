"""The community libraries as one feature: sources, settings, jobs.

main.py calls :func:`configure` once with what the feature needs from the app
(database sessions, the library folder, ffmpeg helpers, logging). The routers
and main.py's matching code then use the functions here.
"""

from __future__ import annotations

import random
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional

from backend import jobs, models
from backend.community import ids, library, matching
from backend.community.base import CommunitySource, public
from backend.community.http import Http
from backend.community.prerollsme import PrerollsMeSource
from backend.community.prerollsuk import MAX_AGE as UK_MAX_AGE, PrerollsUkSource, terms_needed
from backend.errors import AppError, bad_input, conflict, not_found

MAX_ITEMS_PER_DOWNLOAD = 100


class _State:
    session_factory: Optional[Callable] = None
    host: Optional[library.Host] = None
    log: Callable[..., None] = staticmethod(lambda *a, **k: None)
    log_event: Callable[..., None] = staticmethod(lambda *a, **k: None)
    sources: Dict[str, CommunitySource] = {}
    runner: jobs.JobRunner = jobs.runner


state = _State()


def configure(*, session_factory, data_dir, host: library.Host, version: str = "",
              log: Optional[Callable] = None, log_event: Optional[Callable] = None,
              runner: Optional[jobs.JobRunner] = None, sources: Optional[List[CommunitySource]] = None) -> None:
    state.session_factory = session_factory
    state.host = host
    if log:
        state.log = log
    if log_event:
        state.log_event = log_event
    if runner:
        state.runner = runner
    if sources is None:
        data_dir = Path(data_dir)
        sources = [
            PrerollsMeSource(data_dir / "community" / "prerollsme", http=Http(version=version)),
            PrerollsUkSource(data_dir, http=Http(version=version), settings=uk_settings, log=state.log),
        ]
    state.sources = {s.id: s for s in sources}


# ---------------------------------------------------------------- settings

def _setting(db):
    return db.query(models.Setting).first()


def _with_db(fn):
    db = state.session_factory()
    try:
        return fn(db)
    finally:
        db.close()


def uk_settings() -> dict:
    """What the Prerolls.uk source needs from the saved settings."""
    if state.session_factory is None:
        return {}

    def read(db):
        s = _setting(db)
        if not s:
            return {}
        return {"accepted": bool(getattr(s, "community_fair_use_accepted", False)),
                "saved_server": getattr(s, "community_server_url", None),
                "auto_refresh": bool(getattr(s, "community_auto_refresh", False))}
    try:
        return _with_db(read)
    except Exception:
        return {}


def terms_accepted(db, source: CommunitySource) -> bool:
    if not source.needs_acceptance:
        return True
    s = _setting(db)
    return bool(s and getattr(s, "community_fair_use_accepted", False))


def accept_terms(db, source: CommunitySource) -> None:
    if not source.needs_acceptance:
        return
    from backend.timeutil import utcnow
    if not _setting(db):
        db.add(models.Setting())
        db.flush()
    # Every row: a duplicate settings row (a known first-start race, merged at
    # the next start) must not lose the acceptance.
    db.query(models.Setting).update({models.Setting.community_fair_use_accepted: True,
                                     models.Setting.community_fair_use_accepted_at: utcnow()},
                                    synchronize_session=False)
    db.commit()


def preferred_platforms(db) -> tuple:
    """The user's media servers, so a preroll with versions leads with theirs."""
    s = _setting(db)
    if not s:
        return ()
    pairs = (("plex", getattr(s, "plex_url", None)), ("jellyfin", getattr(s, "jellyfin_url", None)),
             ("emby", getattr(s, "emby_url", None)))
    return tuple(name for name, url in pairs if url)


# ----------------------------------------------------------------- sources

def all_sources() -> List[CommunitySource]:
    return list(state.sources.values())


def get_source(source_id: str) -> CommunitySource:
    source = state.sources.get(source_id)
    if not source:
        raise not_found("That community library", hint="Pick Prerolls.me or Prerolls.uk.")
    return source


def refresh_key(source_id: str) -> str:
    return f"community.refresh:{source_id}"


def source_payload(db, source: CommunitySource) -> dict:
    status = {"item_count": 0, "downloadable_count": 0, "last_refreshed": None, "error": None}
    try:
        status.update(source.status())
    except AppError as exc:
        status["error"] = {"message": exc.message, "hint": exc.hint}
    except Exception as exc:
        state.log(f"[COMMUNITY] Status of {source.id} failed: {exc}", "WARNING")
        status["error"] = {"message": f"{source.name} couldn't be read right now.", "hint": "Try again in a moment."}
    accepted = terms_accepted(db, source)
    terms = source.terms(accepted)
    terms = {k: terms[k] for k in ("summary", "url", "needs_acceptance", "accepted")}
    refreshing = bool(state.runner.active(refresh_key(source.id))) or bool(getattr(source, "refreshing", False)) \
        or bool(getattr(source, "building", False))
    return {
        "id": source.id, "name": source.name, "site_url": source.site_url, "description": source.description,
        "item_count": status["item_count"], "downloadable_count": status["downloadable_count"],
        "last_refreshed": status["last_refreshed"], "refreshing": refreshing,
        "terms": terms, "error": status["error"],
    }


def maybe_refresh_in_background(source: CommunitySource) -> None:
    """Prerolls.me: check for a new catalog when the hour is up (on use only)."""
    if isinstance(source, PrerollsMeSource) and source.catalog_path.exists() and source.due():
        start_refresh(source)


def start_refresh(source: CommunitySource) -> dict:
    def run(ctx):
        result = source.refresh(ctx)
        if isinstance(source, PrerollsUkSource):
            lengths = start_lengths(source)
            result["lengths_job_id"] = lengths["id"] if lengths else None
        ctx.report(message=result.get("message") or "Finished")
        return result
    job = state.runner.submit("community.refresh", run, key=refresh_key(source.id),
                              message=f"Refreshing {source.name}")
    return job.to_dict()


def start_lengths(source: PrerollsUkSource) -> Optional[dict]:
    if source.length_state.get("running"):
        return state.runner.active(f"community.lengths:{source.id}")
    job = state.runner.submit("community.lengths", lambda ctx: source.read_lengths(ctx),
                              key=f"community.lengths:{source.id}", message="Reading video lengths")
    return job.to_dict()


def search(db, source: CommunitySource, **params) -> List[dict]:
    if source.needs_acceptance and not terms_accepted(db, source):
        raise terms_needed()
    if not source.has_data():
        if isinstance(source, PrerollsUkSource):
            raise AppError("The Prerolls.uk list hasn't been loaded yet.", status=409, code="needs_refresh",
                           hint="Press Refresh to load it. The first time takes a few minutes.")
    else:
        maybe_refresh_in_background(source)
    return source.search(prefer=preferred_platforms(db), **params)


def page_of(db, items: List[dict], page: int, limit: int) -> dict:
    total = len(items)
    pages = max(1, -(-total // limit))
    chunk = items[(page - 1) * limit: page * limit]
    me = state.sources.get("prerollsme")
    matching.annotate(db, chunk, known_md5=lambda item: me.known_md5(item["id"][3:]) if me else None)
    return {"items": [public(i) for i in chunk], "page": page, "limit": limit, "total": total,
            "total_pages": pages}


def find_item(item_id: str):
    """(source, item) for a tagged or legacy id; item None when the list lacks it."""
    source_id, key = ids.split(item_id)
    source = get_source(source_id)
    try:
        return source, source.item(key)
    except AppError:
        return source, None


def item_exists(item_id) -> Optional[bool]:
    """True/False when the source's list can say, None when it has no list."""
    try:
        source_id, key = ids.split(item_id)
    except AppError:
        return False
    source = state.sources.get(source_id)
    if not source:
        return False
    try:
        if not source.has_data():
            return None
        return source.item(key) is not None
    except Exception:
        return None


# --------------------------------------------------------------- downloads

def check_download_request(db, item_ids: List[str]) -> List[str]:
    """Clean the id list (tagged, no repeats) and refuse up front what can't work."""
    if not item_ids:
        raise bad_input("Pick at least one intro video.", field="item_ids")
    cleaned: List[str] = []
    for n, raw in enumerate(item_ids):
        source_id, key = ids.split(raw, field=f"item_ids.{n}")
        tagged = ids.make(source_id, key)
        if tagged not in cleaned:
            cleaned.append(tagged)
    if len(cleaned) > MAX_ITEMS_PER_DOWNLOAD:
        raise bad_input(f"Pick {MAX_ITEMS_PER_DOWNLOAD} videos or fewer at a time.", field="item_ids")
    for source_id in {i.split(":", 1)[0] for i in cleaned}:
        source = get_source(ids.PREFIXES[source_id])
        if source.needs_acceptance and not terms_accepted(db, source):
            raise terms_needed()
    return cleaned


def _interleave(item_ids: List[str]) -> List[str]:
    """Alternate libraries so one's download gap is spent on the other."""
    queues: Dict[str, List[str]] = {}
    for item_id in item_ids:
        queues.setdefault(item_id[:3], []).append(item_id)
    out = []
    while any(queues.values()):
        for q in queues.values():
            if q:
                out.append(q.pop(0))
    return out


def _existing(db, item_id: str):
    legacy = item_id[3:] if item_id.startswith("tn:") else item_id
    return db.query(models.Preroll).filter(
        models.Preroll.community_preroll_id.in_([item_id, legacy])).first()


def download_one(db, item_id: str, category, *, skip_existing: bool = True) -> dict:
    """Download one item into ``category``. Returns {"status": "added"|"skipped", ...}.
    Raises AppError with a plain message when it can't."""
    source, item = find_item(item_id)
    if item is None:
        raise AppError(f"This video isn't in the {source.name} list anymore.", status=404,
                       code="community_item_gone", hint="Refresh the list and pick it again.")
    if skip_existing:
        existing = _existing(db, item["id"])
        if existing:
            return {"status": "skipped", "item_id": item["id"], "preroll_id": existing.id,
                    "name": existing.display_name or existing.filename, "title": item["title"]}
    if not item.get("downloadable"):
        source.download(item, "")   # raises the plain "watch only" message
    source.wait_turn()
    folder = library.collection_folder(state.host.library_dir(), category)
    downloaded = source.download(item, folder)
    preroll = library.add_to_library(db, state.host, item, downloaded, category, source.name)
    state.log(f"[COMMUNITY] Downloaded '{item['title']}' ({item['id']}) {item.get('attribution') or ''} "
              f"into '{category.name}'")
    return {"status": "added", "item_id": item["id"], "preroll_id": preroll.id,
            "name": preroll.display_name or preroll.filename, "title": item["title"], "preroll": preroll}


def _apply_if_needed(db, category) -> bool:
    try:
        if library.should_apply(db, category):
            return bool(state.host.apply_collection(db, category.id))
    except Exception as exc:
        state.log(f"[COMMUNITY] Applying '{category.name}' after download failed: {exc}", "WARNING")
    return False


def start_download(db, item_ids: List[str], collection_id: Optional[int] = None,
                   new_collection_name: Optional[str] = None) -> dict:
    cleaned = check_download_request(db, item_ids)
    category = library.resolve_collection(db, collection_id, new_collection_name)
    category_id, category_name = category.id, category.name
    order = _interleave(cleaned)

    def run(ctx):
        db = state.session_factory()
        added, skipped = [], []
        try:
            category = db.query(models.Category).filter(models.Category.id == category_id).first()
            if category is None:
                raise AppError("The collection was deleted before the downloads started.", status=409,
                               code="collection_gone", hint="Pick another collection and try again.")
            ctx.report(total=len(order), done=0, message=f"Downloading {len(order)} intro videos")
            for n, item_id in enumerate(order, 1):
                ctx.report(message=f"Downloading {n} of {len(order)}")
                try:
                    out = download_one(db, item_id, category)
                    out.pop("preroll", None)
                    (added if out["status"] == "added" else skipped).append(out)
                except AppError as exc:
                    ctx.error(item_id, exc.message)
                except Exception as exc:
                    state.log(f"[COMMUNITY] Download of {item_id} failed: {type(exc).__name__}: {exc}", "ERROR")
                    ctx.error(item_id, "This video couldn't be saved. The log has the details.")
                ctx.advance()
            applied = _apply_if_needed(db, category) if added else False
            failed = len(order) - len(added) - len(skipped)
            if added:
                message = f"Added {len(added)} intro video{'s' if len(added) != 1 else ''} to {category.name}."
            elif skipped and not failed:
                message = "These intro videos are already in your library."
            else:
                message = "Nothing was added."
            if skipped and added:
                message += f" {len(skipped)} {'was' if len(skipped) == 1 else 'were'} already in your library."
            if failed and (added or skipped):
                message += f" {failed} couldn't be downloaded."
            if added:
                state.log_event("INFO", "user", f"Community download: {message}", source="community_download",
                                details={"added": [a["item_id"] for a in added]})
            if failed and not added and not skipped:
                raise AppError("None of the intro videos could be downloaded.", status=502,
                               code="community_download_failed", hint="See the reason next to each video.")
            ctx.report(message=message)
            return {"added": added, "skipped": skipped, "collection": {"id": category.id, "name": category.name},
                    "applied": applied}
        finally:
            db.close()

    job = state.runner.submit("community.download", run, total=len(order),
                              message=f"Waiting to download {len(order)} intro videos into {category_name}")
    return job.to_dict()


def download_now(db, item_id: str, collection_id: Optional[int] = None, *, skip_existing: bool = True) -> dict:
    """The same download, done before returning (old routes, sequence import)."""
    cleaned = check_download_request(db, [item_id])
    category = library.resolve_collection(db, collection_id, None)
    out = download_one(db, cleaned[0], category, skip_existing=skip_existing)
    out["category"] = category
    out["applied"] = _apply_if_needed(db, category) if out["status"] == "added" else False
    return out


# ---------------------------------------------------------------- matching

def matcher():
    """Everything matching needs, or None when neither library has a list."""
    from backend import community_match
    uk: Optional[PrerollsUkSource] = state.sources.get("prerollsuk")
    me: Optional[PrerollsMeSource] = state.sources.get("prerollsme")
    uk_matcher = None
    if uk is not None:
        uk_matcher = _uk_matcher(uk, community_match)
    me_by_size = me.items_by_size() if me is not None else {}
    if uk_matcher is None and not me_by_size:
        return None
    return matching.SourceAwareMatcher(uk_matcher, me_by_size,
                                       lambda item: me.known_md5(item["id"][3:]) if me else None)


_uk_matcher_cache = {"key": None, "matcher": None}


def _uk_matcher(uk: PrerollsUkSource, community_match):
    data = uk.load_index()
    if not data:
        return None
    try:
        lengths = (uk.folder / "community_durations.json").stat().st_mtime_ns
    except OSError:
        lengths = None
    key = (uk._index_key, lengths)
    if _uk_matcher_cache["key"] != key:
        entries = data.get("prerolls", [])
        tagged = [dict(e, id=ids.make("prerollsuk", e.get("path") or e.get("id"))) for e in entries
                  if ids.valid_path(e.get("path") or e.get("id") or "")]
        _uk_matcher_cache.update(key=key, matcher=community_match.Matcher(tagged, uk.durations.durations(entries)))
    return _uk_matcher_cache["matcher"]


def tag_legacy_ids(db) -> int:
    return matching.tag_legacy_ids(db)


# ------------------------------------------------------------ auto refresh

AUTO_REFRESH_CHECK = 3600
AUTO_REFRESH_RETRY = 24 * 3600
_auto = {"last_attempt": 0.0}


def auto_refresh_tick(jitter: float) -> bool:
    """Weekly Prerolls.uk refresh when the user turned it on. True if started."""
    uk = state.sources.get("prerollsuk")
    if uk is None:
        return False
    settings = uk_settings()
    if not settings.get("auto_refresh") or not settings.get("accepted"):
        return False
    age = uk.index_age()
    if age is None or age < UK_MAX_AGE + jitter:
        return False
    if time.time() - _auto["last_attempt"] < AUTO_REFRESH_RETRY:
        return False
    _auto["last_attempt"] = time.time()
    start_refresh(uk)
    state.log("[COMMUNITY] Weekly Prerolls.uk refresh started")
    return True


def auto_refresh_loop() -> None:
    # Not right at startup: a restart loop must not turn into a refresh loop.
    time.sleep(random.uniform(600, 1800))
    jitter = random.uniform(0, 12 * 3600)
    while True:
        try:
            auto_refresh_tick(jitter)
        except Exception as exc:
            state.log(f"[COMMUNITY] Auto-refresh check failed: {exc}", "WARNING")
        time.sleep(AUTO_REFRESH_CHECK)


def ensure_not_running(source: CommunitySource) -> None:
    if state.runner.active(refresh_key(source.id)):
        raise conflict(f"{source.name} is already being refreshed.", hint="Wait for it to finish.",
                       code="refresh_running")
