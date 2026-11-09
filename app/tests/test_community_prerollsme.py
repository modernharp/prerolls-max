"""Prerolls.me provider, against a recorded catalog. No network."""
import json

import pytest

from backend.community import prerollsme
from backend.community.http import Http
from backend.community.prerollsme import CATALOG_URL, PrerollsMeSource
from backend.errors import AppError
from tests.community_fakes import FIXTURES, FakeResponse, FakeSession, md5, video_bytes

CATALOG = (FIXTURES / "prerollsme_catalog.json").read_bytes()
ETAG = '"5f95a08e58cfe0a4cbcef68f2646197c"'


class Clock:
    def __init__(self, now=1_800_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


def make(tmp_path, routes=None, clock=None):
    session = FakeSession({CATALOG_URL: (200, {"Content-Type": "application/json", "ETag": ETAG}, CATALOG)})
    session.routes.update(routes or {})
    source = PrerollsMeSource(tmp_path / "pm", http=Http(session), clock=clock or Clock(), sleep=lambda s: None)
    return source, session


def test_items_follow_the_contract_and_keep_the_credit(tmp_path):
    source, _ = make(tmp_path)
    items = {i["id"]: i for i in source.search(sort="az")}
    assert len(items) == 6
    hosted = items["pm:x-logo-emby-pre-roll"]
    assert hosted["source"] == "prerollsme" and hosted["downloadable"] is True
    assert hosted["size_bytes"] == 3273811 and hosted["duration_seconds"] == 5.4
    assert hosted["thumbnail_url"] == "/api/community/thumb?id=pm%3Ax-logo-emby-pre-roll"
    assert hosted["preview_url"].startswith("https://videos.prerolls.me/")
    assert hosted["embed_url"] is None and hosted["platforms"] == ["emby"]
    assert hosted["page_url"] == "https://www.prerolls.me/preroll/x-logo-emby-pre-roll"
    assert hosted["attribution"] == "via Prerolls.me"
    youtube = items["pm:blockbuster-feature-presentation"]
    assert youtube["downloadable"] is False and youtube["preview_url"] is None
    assert youtube["embed_url"] == "https://www.youtube-nocookie.com/embed/bbvq75JD9pM"
    assert youtube["creator"] == {"name": "Jonathan M", "url": "https://www.youtube.com/@Redrum215_"}
    assert youtube["attribution"] == "by Jonathan M · via Prerolls.me"
    assert youtube["hosted_on"] == "YouTube"
    assert items["pm:marvel-studios-jellyfin-preroll"]["hosted_on"] == "Vimeo"
    for item in items.values():
        assert set(item) >= {"id", "source", "title", "description", "category", "tags", "creator",
                             "duration_seconds", "width", "height", "size_bytes", "thumbnail_url", "preview_url",
                             "embed_url", "page_url", "downloadable", "platforms", "in_library"}


def test_the_catalog_is_saved_whole_and_checked_at_most_hourly(tmp_path):
    clock = Clock()
    source, session = make(tmp_path, clock=clock)
    source.ensure_loaded()
    assert json.loads(source.catalog_path.read_bytes()) == json.loads(CATALOG)
    assert not list(source.catalog_path.parent.glob(".tmp-*"))
    out = source.refresh()
    assert out["changed"] is False and "once an hour" in out["message"]
    assert session.urls() == [CATALOG_URL]

    clock.now += 3601
    session.routes[CATALOG_URL] = lambda url, headers: FakeResponse(url, 304, {"ETag": ETAG})
    out = source.refresh()
    assert out["changed"] is False
    assert session.calls[-1][1]["If-None-Match"] == ETAG
    assert "PrerollsMax" in session.calls[-1][1]["User-Agent"]

    # A new process reads the saved copy without asking the site.
    again, session2 = make(tmp_path, clock=clock)
    assert len(again.search()) == 6 and session2.calls == []


def test_a_failed_check_keeps_the_list_and_says_so(tmp_path):
    clock = Clock()
    source, session = make(tmp_path, clock=clock)
    source.ensure_loaded()
    clock.now += 3601
    session.routes[CATALOG_URL] = (500, {}, b"oops")
    with pytest.raises(AppError):
        source.refresh()
    assert len(source.search()) == 6
    assert source.status()["error"]["message"].startswith("Prerolls.me didn't answer")


@pytest.mark.parametrize("params, expected", [
    ({"q": "disney"}, ["pm:walt-disney-pictures-emby-preroll", "pm:marvel-studios-jellyfin-preroll"]),
    ({"q": "jonathan"}, ["pm:blockbuster-feature-presentation"]),        # creator
    ({"q": "video store"}, ["pm:blockbuster-feature-presentation"]),     # tag
    ({"q": "metallic"}, ["pm:x-logo-emby-pre-roll"]),                   # description
    ({"category": "theater", "sort": "az"}, ["pm:blockbuster-feature-presentation",
                                             "pm:regency-theaters-feature-presentation"]),
    ({"tag": "marvel"}, ["pm:marvel-studios-jellyfin-preroll"]),
    ({"duration": "lt10", "sort": "shortest"}, ["pm:x-logo-emby-pre-roll", "pm:blockbuster-feature-presentation"]),
    ({"duration": "30plus"}, ["pm:marvel-studios-jellyfin-preroll"]),
    ({"duration": "10-20", "sort": "az"}, ["pm:regency-theaters-feature-presentation", "pm:water-droplets-emby-pre-roll"]),
    ({"downloadable": True, "sort": "az"}, ["pm:walt-disney-pictures-emby-preroll", "pm:water-droplets-emby-pre-roll",
                                            "pm:x-logo-emby-pre-roll"]),
    ({"platform": "jellyfin", "downloadable": False, "sort": "newest"},
     ["pm:blockbuster-feature-presentation", "pm:regency-theaters-feature-presentation",
      "pm:marvel-studios-jellyfin-preroll"]),
])
def test_search_filters_and_sorts_locally(tmp_path, params, expected):
    source, session = make(tmp_path)
    assert [i["id"] for i in source.search(**params)] == expected
    assert session.urls() == [CATALOG_URL]


def test_popular_puts_downloaded_ones_first(tmp_path):
    source, _ = make(tmp_path)
    top = [i["id"] for i in source.search(sort="popular")][:2]
    assert top == ["pm:x-logo-emby-pre-roll", "pm:water-droplets-emby-pre-roll"]


def file_routes(data, *, final="https://videos.prerolls.me/X%20Logo%20Emby%20Pre-roll.mp4?dl=1",
                ctype="video/mp4", etag=None):
    return {
        "https://www.prerolls.me/download/x-logo-emby-pre-roll": (302, {"Location": final}, b""),
        final: (200, {"Content-Type": ctype, "Content-Length": str(len(data)), "ETag": f'"{etag or md5(data)}"'}, data),
    }


def x_logo(source):
    return source.item("x-logo-emby-pre-roll")


def test_a_download_follows_the_site_link_and_checks_the_file(tmp_path):
    data = video_bytes(3273811)
    source, session = make(tmp_path, file_routes(data))
    out = source.download(x_logo(source), str(tmp_path / "lib"))
    assert out.size == 3273811 and out.md5 == md5(data) and out.extension == ".mp4"
    assert open(out.path, "rb").read() == data
    assert session.urls()[-2:] == ["https://www.prerolls.me/download/x-logo-emby-pre-roll",
                                   "https://videos.prerolls.me/X%20Logo%20Emby%20Pre-roll.mp4?dl=1"]
    assert source.known_md5("x-logo-emby-pre-roll") == md5(data)


@pytest.mark.parametrize("change, code", [
    ({"final": "https://ssyoutube.com/x.mp4"}, "community_blocked_address"),
    ({"final": "http://videos.prerolls.me/x.mp4"}, "community_blocked_address"),
    ({"ctype": "text/html"}, "community_not_a_video"),
    ({"etag": "0" * 32}, "community_checksum_mismatch"),
])
def test_a_download_that_goes_wrong_leaves_nothing(tmp_path, change, code):
    data = video_bytes(3273811)
    source, session = make(tmp_path, file_routes(data, **change))
    with pytest.raises(AppError) as raised:
        source.download(x_logo(source), str(tmp_path / "lib"))
    assert raised.value.code == code
    assert "ssyoutube.com" not in session.hosts()
    assert not list((tmp_path / "lib").glob("*")) if (tmp_path / "lib").exists() else True


def test_a_short_file_is_refused(tmp_path):
    data = video_bytes(1000)
    source, _ = make(tmp_path, file_routes(data))
    with pytest.raises(AppError) as raised:
        source.download(x_logo(source), str(tmp_path / "lib"))
    assert raised.value.code == "community_size_mismatch"


def test_youtube_and_vimeo_items_are_never_downloaded(tmp_path):
    source, session = make(tmp_path)
    item = source.item("blockbuster-feature-presentation")
    with pytest.raises(AppError) as raised:
        source.download(item, str(tmp_path / "lib"))
    assert raised.value.code == "watch_only" and "YouTube" in raised.value.message
    assert session.urls() == [CATALOG_URL]


def test_thumbnails_are_fetched_once_from_allowed_hosts(tmp_path):
    thumb = "https://videos.prerolls.me/thumbs/kYJ9gXbEky7O-480.webp"
    source, session = make(tmp_path, {thumb: (200, {"Content-Type": "image/webp"}, b"RIFF....WEBP")})
    path, media = source.thumbnail("x-logo-emby-pre-roll")
    assert media == "image/webp" and path.read_bytes() == b"RIFF....WEBP"
    assert source.thumbnail("x-logo-emby-pre-roll")[0] == path
    assert session.urls().count(thumb) == 1


def test_a_catalog_cannot_point_downloads_or_pictures_elsewhere(tmp_path):
    raw = json.loads(CATALOG)
    first = raw["prerolls"][0]
    first["video"]["directUrl"] = "https://evil.example/x.mp4"
    first["thumbnail"]["small"] = first["thumbnail"]["large"] = "http://169.254.169.254/latest"
    first["download"]["url"] = "https://evil.example/download"
    session = FakeSession({CATALOG_URL: (200, {"Content-Type": "application/json"}, json.dumps(raw))})
    source = PrerollsMeSource(tmp_path / "pm", http=Http(session), sleep=lambda s: None)
    item = source.item(first["slug"])
    assert item["downloadable"] is False and item["thumbnail_url"] is None
    assert source.thumbnail(first["slug"]) is None
    assert session.hosts() == {"www.prerolls.me"}


def test_terms_need_no_acceptance(tmp_path):
    terms = prerollsme.PrerollsMeSource(tmp_path).terms()
    assert terms["needs_acceptance"] is False and terms["accepted"] is True
    assert "credit" in terms["summary"] and terms["url"].startswith("https://www.prerolls.me/")
