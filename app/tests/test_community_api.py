"""The community API (CONTRACTS section 5) and the old /community-prerolls routes,
through FastAPI's TestClient with recorded responses. No network."""
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend import errors, jobs, models
from backend.community import base, library, matching, service
from backend.community.http import Http
from backend.community.prerollsme import CATALOG_URL, PrerollsMeSource
from backend.community.prerollsuk import PrerollsUkSource
from backend.routers import community as community_routes
from backend.routers import community_legacy
from tests.community_fakes import FIXTURES, FakeSession, md5, prerollsuk_routes, video_bytes

CATALOG = (FIXTURES / "prerollsme_catalog.json").read_bytes()
X_LOGO = video_bytes(3273811)
DISNEY = video_bytes(1263470, b"d")
SNOW = video_bytes(7000444, b"s")
X_FINAL = "https://videos.prerolls.me/X%20Logo%20Emby%20Pre-roll.mp4?dl=1"
DISNEY_FINAL = "https://videos.prerolls.me/Walt%20Disney%20Pictures%20Emby%20Preroll.mp4?dl=1"
SNOW_URL = "https://prerolls.uk/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"


@pytest.fixture
def app_env(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'app.db'}", connect_args={"check_same_thread": False})
    models.Base.metadata.create_all(engine)
    make_session = sessionmaker(bind=engine)
    db = make_session()
    db.add(models.Setting())
    db.commit()
    db.close()

    me_session = FakeSession({
        CATALOG_URL: (200, {"Content-Type": "application/json", "ETag": '"abc"'}, CATALOG),
        "https://www.prerolls.me/download/x-logo-emby-pre-roll": (302, {"Location": X_FINAL}, b""),
        X_FINAL: (200, {"Content-Type": "video/mp4", "ETag": f'"{md5(X_LOGO)}"'}, X_LOGO),
        "https://www.prerolls.me/download/walt-disney-pictures-emby-preroll": (302, {"Location": DISNEY_FINAL}, b""),
        DISNEY_FINAL: (200, {"Content-Type": "video/mp4"}, DISNEY),
        "https://videos.prerolls.me/thumbs/kYJ9gXbEky7O-480.webp": (200, {"Content-Type": "image/webp"}, b"WEBP"),
    })
    uk_session = FakeSession(prerollsuk_routes())
    uk_session.routes[SNOW_URL] = (200, {"Content-Type": "video/mp4"}, SNOW)
    me = PrerollsMeSource(tmp_path / "data" / "community" / "prerollsme", http=Http(me_session), sleep=lambda s: None)
    uk = PrerollsUkSource(tmp_path / "data", http=Http(uk_session), settings=service.uk_settings, sleep=lambda s: None)
    runner = jobs.JobRunner(max_workers=2)
    applied = []
    thumbs = []

    def make_thumbnail(preroll, path, folder):
        thumbs.append((preroll.id, folder))
        return f"prerolls/thumbnails/{folder}/{preroll.id}.jpg"

    lib_dir = tmp_path / "library"
    service.configure(
        session_factory=make_session, data_dir=tmp_path / "data", runner=runner, sources=[me, uk],
        host=library.Host(library_dir=lambda: str(lib_dir), make_thumbnail=make_thumbnail,
                          measure_seconds=lambda path: None,
                          apply_collection=lambda db, cid: applied.append(cid) or True),
    )
    monkey_runner = jobs.runner
    jobs.runner = runner
    app = FastAPI()
    errors.install(app)
    app.include_router(jobs.router)
    app.include_router(community_routes.router)
    app.include_router(community_legacy.router)
    client = TestClient(app)
    env = type("Env", (), dict(client=client, db=make_session, me=me, uk=uk, me_session=me_session,
                               uk_session=uk_session, lib=lib_dir, applied=applied, thumbs=thumbs, runner=runner))
    yield env
    jobs.runner = monkey_runner
    client.close()
    engine.dispose()


def wait(env, job_id):
    for _ in range(500):
        body = env.client.get(f"/api/jobs/{job_id}").json()
        if body["state"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    raise AssertionError("job did not finish")


def accept_uk(env):
    assert env.client.post("/api/community/sources/prerollsuk/accept-terms").status_code == 200


def build_uk(env):
    accept_uk(env)
    job = env.client.post("/api/community/sources/prerollsuk/refresh").json()["job_id"]
    assert wait(env, job)["state"] == "done"


def test_sources_list_prerolls_me_first_with_terms(app_env):
    body = app_env.client.get("/api/community/sources").json()
    assert [s["id"] for s in body] == ["prerollsme", "prerollsuk"]
    me, uk = body
    assert me["name"] == "Prerolls.me" and me["item_count"] == 6 and me["downloadable_count"] == 3
    assert me["terms"] == {"summary": me["terms"]["summary"], "url": "https://www.prerolls.me/developers",
                           "needs_acceptance": False, "accepted": True}
    assert me["last_refreshed"] and me["error"] is None and me["refreshing"] is False
    assert uk["name"] == "Prerolls.uk (Typical Nerds)" and uk["item_count"] == 0 and uk["last_refreshed"] is None
    assert uk["terms"]["needs_acceptance"] is True and uk["terms"]["accepted"] is False
    accepted = app_env.client.post("/api/community/sources/prerollsuk/accept-terms").json()
    assert accepted["terms"]["accepted"] is True


def test_acceptance_survives_a_duplicate_settings_row(app_env):
    db = app_env.db()
    db.add(models.Setting())      # the first-start race; the next start keeps the newest row
    db.commit()
    accept_uk(app_env)
    assert [s.community_fair_use_accepted for s in db.query(models.Setting).all()] == [True, True]
    db.close()


def test_prerolls_uk_waits_for_the_fair_use_acceptance(app_env):
    c = app_env.client
    for call in (lambda: c.get("/api/community/items", params={"source": "prerollsuk"}),
                 lambda: c.post("/api/community/sources/prerollsuk/refresh"),
                 lambda: c.post("/api/community/download", json={"item_ids": ["tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"]})):
        res = call()
        assert res.status_code == 403 and res.json()["error"]["code"] == "terms_not_accepted"
    assert app_env.uk_session.calls == []
    accept_uk(app_env)
    res = c.get("/api/community/items", params={"source": "prerollsuk"})
    assert res.status_code == 409 and res.json()["error"]["code"] == "needs_refresh"
    assert res.json()["error"]["hint"]


def test_items_page_and_validate(app_env):
    c = app_env.client
    body = c.get("/api/community/items", params={"source": "prerollsme", "limit": 4, "page": 2, "sort": "az"}).json()
    assert (body["page"], body["limit"], body["total"], body["total_pages"]) == (2, 4, 6, 2)
    assert len(body["items"]) == 2
    assert all(not k.startswith("_") for item in body["items"] for k in item)
    res = c.get("/api/community/items", params={"source": "elsewhere"})
    assert res.status_code == 422 and "source" in res.json()["error"]["fields"]
    res = c.get("/api/community/items", params={"source": "prerollsme", "limit": 500})
    assert res.status_code == 422 and res.json()["error"]["fields"]["limit"] == "Use 100 or less."
    res = c.get("/api/community/items", params={"source": "prerollsme", "duration": "long"})
    assert res.status_code == 422
    cats = c.get("/api/community/categories", params={"source": "prerollsme"}).json()
    assert {"slug": "theater", "name": "Theater & PSA", "count": 2} in cats


def test_thumbnails_come_from_this_server(app_env):
    c = app_env.client
    res = c.get("/api/community/thumb", params={"id": "pm:x-logo-emby-pre-roll"})
    assert res.status_code == 200 and res.content == b"WEBP" and res.headers["content-type"] == "image/webp"
    assert c.get("/api/community/thumb", params={"id": "pm:not-there"}).status_code == 404
    assert c.get("/api/community/thumb", params={"id": "https://evil.example/x.png"}).status_code == 422


def test_one_job_downloads_from_both_libraries_into_one_collection(app_env):
    c = app_env.client
    build_uk(app_env)
    res = c.post("/api/community/download", json={
        "item_ids": ["pm:x-logo-emby-pre-roll", "tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4",
                     "pm:blockbuster-feature-presentation", "pm:x-logo-emby-pre-roll"],
        "new_collection_name": "Holiday Mix"})
    assert res.status_code == 200
    job = wait(app_env, res.json()["job_id"])
    assert job["kind"] == "community.download" and job["state"] == "done" and job["progress"] == 100
    assert (job["done"], job["total"]) == (3, 3)
    assert job["errors"] == [{"item_id": "pm:blockbuster-feature-presentation",
                              "message": "\"Blockbuster Feature Presentation\" is on YouTube, so it can be watched but not downloaded."}]
    assert job["result"]["collection"]["name"] == "Holiday Mix"
    assert job["message"] == "Added 2 intro videos to Holiday Mix. 1 couldn't be downloaded."
    db = app_env.db()
    rows = {p.community_preroll_id: p for p in db.query(models.Preroll).all()}
    assert set(rows) == {"pm:x-logo-emby-pre-roll", "tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"}
    x = rows["pm:x-logo-emby-pre-roll"]
    assert x.filename == "X Logo.mp4" and x.display_name == "X Logo" and x.file_size == 3273811
    assert x.category.name == "Holiday Mix" and [c.name for c in x.categories] == ["Holiday Mix"]
    assert "via Prerolls.me" in x.description and x.description.startswith("Downloaded from Community Prerolls")
    assert x.thumbnail == f"prerolls/thumbnails/Holiday Mix/{x.id}.jpg"
    assert open(x.path, "rb").read() == X_LOGO and x.path.startswith(str(app_env.lib / "Holiday Mix"))
    assert os.stat(x.path).st_mode & 0o777 == base.FILE_MODE   # readable by the media server, not owner-only
    snow = rows["tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"]
    assert snow.filename == "Snow Globe - Plex.mp4" and "Typical Nerds" in snow.description
    assert not [f for f in os.listdir(app_env.lib / "Holiday Mix") if f.endswith(".part")]
    db.close()

    # Both now show as in the library, and asking again adds nothing.
    items = c.get("/api/community/items", params={"source": "prerollsme", "q": "x logo"}).json()["items"]
    assert items[0]["in_library"]["name"] == "X Logo"
    again = wait(app_env, c.post("/api/community/download", json={
        "item_ids": ["pm:x-logo-emby-pre-roll", "pm:walt-disney-pictures-emby-preroll"]}).json()["job_id"])
    assert again["message"] == "Added 1 intro video to Default. 1 was already in your library."
    again = wait(app_env, c.post("/api/community/download", json={"item_ids": ["pm:x-logo-emby-pre-roll"]}).json()["job_id"])
    assert again["state"] == "done" and again["result"]["skipped"][0]["item_id"] == "pm:x-logo-emby-pre-roll"
    assert again["message"] == "These intro videos are already in your library."


def test_file_names_are_safe_for_plex_and_unique(tmp_path):
    assert library.file_name_for("Fire, Ice; and: More?", ".mp4") == "Fire - Ice - and More.mp4"
    assert library.file_name_for("...", ".mp4") == "Community intro.mp4"
    assert library.file_name_for("CON", ".mp4") == "Community intro.mp4"
    (tmp_path / "Snow.mp4").write_bytes(b"x")
    (tmp_path / "Snow (2).mp4").write_bytes(b"x")
    assert library.unique_path(str(tmp_path), "Snow.mp4").endswith("Snow (3).mp4")


def test_a_download_into_an_existing_collection_applies_it_when_active(app_env):
    db = app_env.db()
    cat = models.Category(name="Fall", apply_to_plex=True)
    db.add(cat)
    db.commit()
    cid = cat.id
    db.close()
    job = wait(app_env, app_env.client.post("/api/community/download", json={
        "item_ids": ["pm:walt-disney-pictures-emby-preroll"], "collection_id": cid}).json()["job_id"])
    assert job["state"] == "done" and job["result"]["applied"] is True and app_env.applied == [cid]


def test_download_requests_are_checked_before_starting(app_env):
    c = app_env.client
    for body, field in (({"item_ids": []}, "item_ids"), ({"item_ids": ["https://evil.example/x.mp4"]}, "item_ids.0"),
                        ({"item_ids": ["pm:x-logo-emby-pre-roll"], "new_collection_name": "a/b"}, "new_collection_name")):
        res = c.post("/api/community/download", json=body)
        assert res.status_code == 422, body
        assert field in res.json()["error"]["fields"]
    res = c.post("/api/community/download", json={"item_ids": ["pm:x-logo-emby-pre-roll"], "collection_id": 999})
    assert res.status_code == 404
    assert app_env.me_session.urls() == []


def test_a_job_where_nothing_worked_fails_with_reasons(app_env):
    app_env.me_session.routes[X_FINAL] = (200, {"Content-Type": "text/html"}, b"<html>")
    job = wait(app_env, app_env.client.post("/api/community/download", json={
        "item_ids": ["pm:x-logo-emby-pre-roll", "pm:no-such-video"]}).json()["job_id"])
    assert job["state"] == "failed" and job["message"] == "None of the intro videos could be downloaded."
    assert [e["item_id"] for e in job["errors"]] == ["pm:x-logo-emby-pre-roll", "pm:no-such-video"]
    assert "isn't a video" in job["errors"][0]["message"]
    assert "isn't in the Prerolls.me list anymore" in job["errors"][1]["message"]


def test_in_library_matches_by_id_then_exact_size_and_md5(app_env, tmp_path):
    db = app_env.db()
    same = tmp_path / "renamed.mp4"
    same.write_bytes(DISNEY)
    db.add_all([
        models.Preroll(filename="a.mp4", display_name="Old NeXroll download", path="/x/a.mp4",
                       community_preroll_id="/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"),
        models.Preroll(filename="renamed.mp4", path=str(same), file_size=len(DISNEY)),
        models.Preroll(filename="other.mp4", path="/x/other.mp4", file_size=3273811),
    ])
    db.commit()
    items = [app_env.me.item("walt-disney-pictures-emby-preroll"), app_env.me.item("x-logo-emby-pre-roll")]
    items = [dict(i) for i in items]
    app_env.me.remember_md5("x-logo-emby-pre-roll", md5(X_LOGO))   # the local file's MD5 differs
    matching.annotate(db, items, known_md5=lambda i: app_env.me.known_md5(i["id"][3:]))
    assert items[0]["in_library"]["name"] == "renamed.mp4"
    assert items[1]["in_library"] is None
    uk_item = {"id": "tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4", "source": "prerollsuk",
               "size_bytes": 1, "downloadable": True, "in_library": None}
    matching.annotate(db, [uk_item])
    assert uk_item["in_library"]["name"] == "Old NeXroll download"   # untagged row still found
    db.close()


def test_matcher_tags_ids_and_tries_prerolls_me_first(app_env):
    assert service.matcher() is None              # no list from either library yet, and no network
    build_uk(app_env)
    app_env.client.get("/api/community/sources")  # loads the Prerolls.me catalog
    m = service.matcher()
    out = m.match(["whatever.mp4"], size=1263470)
    assert out["id"] == "pm:walt-disney-pictures-emby-preroll" and out["how"] == "file"
    out = m.match(["Snow Globe Plex.mp4"], size=7000444)
    assert out["id"] == "tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"


def test_jobs_report_unknown_ids_plainly(app_env):
    res = app_env.client.get("/api/jobs/nope")
    assert res.status_code == 404
    assert res.json()["error"]["message"] == "That task doesn't exist anymore. It may have been deleted."


def test_refresh_jobs_respect_the_hourly_limit(app_env):
    app_env.client.get("/api/community/sources")
    first = app_env.client.post("/api/community/sources/prerollsme/refresh").json()["job_id"]
    body = wait(app_env, first)
    assert body["kind"] == "community.refresh" and body["state"] == "done"
    assert "once an hour" in body["result"]["message"]


# --------------------------------------------------------- the old routes

def test_old_server_route_only_takes_listed_mirrors(app_env):
    c = app_env.client
    for url in ("http://169.254.169.254/latest/meta-data", "https://evil.example", "http://127.0.0.1:9393"):
        res = c.put("/community-prerolls/server-url", json={"url": url})
        assert res.status_code == 422, url
        assert res.json()["error"]["fields"]["url"] == "Pick one of the Prerolls.uk servers in the list."
    body = c.put("/community-prerolls/server-url", json={"url": "https://home.prerolls.uk"}).json()
    assert body["server_url"] == "https://home.prerolls.uk" and body["download_delay_seconds"] == 5.0
    body = c.put("/community-prerolls/server-url", json={"url": None}).json()
    assert body["server_url"] == "https://prerolls.uk" and body["is_custom"] is False


def test_a_crafted_server_setting_is_never_fetched(app_env):
    db = app_env.db()
    db.query(models.Setting).first().community_server_url = "http://169.254.169.254"
    db.commit()
    db.close()
    accept_uk(app_env)
    res = app_env.client.get("/community-prerolls/preview", params={"preroll_id": "/latest/meta-data"})
    assert app_env.uk_session.hosts() <= {"prerolls.uk"}
    assert res.status_code in (404, 502)


@pytest.mark.parametrize("preroll_id", ["//evil.example/x.mp4", "/../etc/passwd", "https://evil.example/x.mp4",
                                        "\\\\evil\\share"])
def test_old_preview_refuses_other_addresses(app_env, preroll_id):
    accept_uk(app_env)
    res = app_env.client.get("/community-prerolls/preview", params={"preroll_id": preroll_id})
    assert res.status_code == 422
    assert app_env.uk_session.calls == []


def test_old_preview_streams_from_the_server(app_env):
    build_uk(app_env)
    res = app_env.client.get("/community-prerolls/preview",
                             params={"preroll_id": "/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"})
    assert res.status_code == 200 and res.content == SNOW
    res = app_env.client.get("/api/community/preview",
                             params={"id": "tn:/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"})
    assert res.status_code == 200 and res.content == SNOW


def test_old_download_uses_only_the_path_of_a_sent_url(app_env):
    build_uk(app_env)
    res = app_env.client.post("/community-prerolls/download", json={
        "url": "https://evil.example/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4", "title": "ignored"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["downloaded"] is True and body["community_preroll_id"].startswith("tn:/Holidays/")
    assert "evil.example" not in app_env.uk_session.hosts()


def test_old_search_and_status_use_the_saved_list_only(app_env):
    c = app_env.client
    accept_uk(app_env)
    body = c.get("/community-prerolls/search", params={"query": "snow"}).json()
    assert body["results"] == [] and body["needs_index"] is True
    assert app_env.uk_session.calls == []                       # no live scraping
    build_uk(app_env)
    body = c.get("/community-prerolls/search", params={"query": "matrix", "servers": "jellyfin"}).json()
    assert body["total"] == 1 and body["results"][0]["path"].endswith("Matrix%20Jellyfin.mp4")
    top = c.get("/community-prerolls/top5").json()["results"]
    assert top and all(r["id"].startswith("/") for r in top)    # real ids, not top_0
    latest = c.get("/community-prerolls/latest").json()["results"]
    assert latest[0]["thumbnail"].startswith("data:image/svg+xml")
    status = c.get("/community-prerolls/index-status").json()
    assert status["exists"] is True and status["total_prerolls"] == 5
    assert c.get("/community-prerolls/facets").json()["total"] == 3
    assert app_env.uk_session.hosts() == {"prerolls.uk"}


def test_build_progress_ends_after_a_failed_build(app_env):
    accept_uk(app_env)
    app_env.uk_session.routes.clear()
    community_legacy._build["last_manual"] = 0.0
    job = app_env.client.get("/community-prerolls/build-index").json()["job_id"]
    assert wait(app_env, job)["state"] == "failed"
    with app_env.client.stream("GET", "/community-prerolls/build-progress") as res:
        events = [line for line in res.iter_lines() if line.startswith("data:")]
    assert len(events) == 1 and '"building": false' in events[0] and '"failed": true' in events[0]
    again = app_env.client.get("/community-prerolls/build-index")
    assert again.status_code == 429


def test_tagging_old_ids_is_idempotent(app_env):
    db = app_env.db()
    db.add_all([models.Preroll(filename="a.mp4", community_preroll_id="/A/a.mp4"),
                models.Preroll(filename="b.mp4", community_preroll_id="tn:/B/b.mp4"),
                models.Preroll(filename="c.mp4", community_preroll_id="pm:c")])
    db.commit()
    assert service.tag_legacy_ids(db) == 1
    assert service.tag_legacy_ids(db) == 0
    assert sorted(p.community_preroll_id for p in db.query(models.Preroll).all()) == ["pm:c", "tn:/A/a.mp4", "tn:/B/b.mp4"]
    db.close()
