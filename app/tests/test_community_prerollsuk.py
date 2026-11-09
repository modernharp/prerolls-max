"""Prerolls.uk (Typical Nerds) provider, against recorded listings. No network."""
import json

import pytest

from backend.community import ids
from backend.community.http import Http, Pacer
from backend.community.prerollsuk import PrerollsUkSource, allowed_server, listed_servers
from backend.errors import AppError
from tests.community_fakes import FakeResponse, FakeSession, load_fixture, md5, prerollsuk_routes, video_bytes

SITE = load_fixture("prerollsuk_site.json")


def make(tmp_path, routes=None, settings=None):
    session = FakeSession(prerollsuk_routes())
    session.routes.update(routes or {})
    settings = {"accepted": True} if settings is None else settings
    source = PrerollsUkSource(tmp_path, http=Http(session), settings=lambda: settings, sleep=lambda s: None)
    return source, session


def built(tmp_path, **kw):
    source, session = make(tmp_path, **kw)
    source.refresh()
    return source, session


def test_only_typical_nerds_servers_are_used():
    assert allowed_server("https://prerolls.uk") and allowed_server("https://home.prerolls.uk/")
    for url in ("http://prerolls.uk", "https://evil.example", "https://prerolls.uk.evil.example",
                "https://prerolls.uk/x", "https://user@prerolls.uk", "https://prerolls.uk:8443",
                "https://169.254.169.254", ""):
        assert not allowed_server(url), url
    servers = SITE["servers"]["servers"] + [{"baseUrl": "https://evil.example", "status": "active"}]
    assert [s["baseUrl"] for s in listed_servers(servers)] == ["https://prerolls.uk", "https://home.prerolls.uk"]


@pytest.mark.parametrize("saved, used, set_aside", [
    (None, "https://prerolls.uk", None),
    ("https://home.prerolls.uk/", "https://home.prerolls.uk", None),
    ("https://usa.prerolls.uk", "https://prerolls.uk", "https://usa.prerolls.uk"),        # gone from the list
    ("http://169.254.169.254/latest", "https://prerolls.uk", "http://169.254.169.254/latest"),  # never used
])
def test_a_saved_server_counts_only_when_listed(tmp_path, saved, used, set_aside):
    source, _ = make(tmp_path)
    assert source.choose_server(saved) == (used, set_aside)


def test_building_the_list_walks_the_folders_and_saves_it_atomically(tmp_path):
    source, session = built(tmp_path)
    data = json.loads(source.index_path.read_text())
    paths = sorted(e["path"] for e in data["prerolls"])
    assert paths == ["/AI/Robot%20Usher.mp4", "/Community/Matrix%20-%20AwesomeAustn/Matrix%20Jellyfin.mp4",
                     "/Community/Matrix%20-%20AwesomeAustn/Matrix%20Plex.mp4", "/Community/_Universal/Neon%20City.mp4",
                     "/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"]
    matrix = next(e for e in data["prerolls"] if e["path"].endswith("Matrix%20Plex.mp4"))
    assert matrix["creator"] == "AwesomeAustn" and matrix["size_bytes"] == 12000111 and matrix["category"] == "Community"
    # Never left the Typical Nerds server, never followed the off-site links.
    assert session.hosts() == {"prerolls.uk"}
    assert not list(tmp_path.glob(".tmp-*"))
    assert source.build_state["building"] is False and source.build_state["progress"] == 100


def test_a_walk_that_finds_nothing_keeps_the_old_list(tmp_path):
    source, session = built(tmp_path)
    before = source.index_path.read_bytes()
    session.routes.clear()
    with pytest.raises(AppError) as raised:
        source.refresh()
    assert raised.value.code == "community_list_failed"
    assert source.index_path.read_bytes() == before
    assert source.status()["error"]["message"].startswith("Prerolls.uk didn't list")
    assert source.build_state["building"] is False


def test_redirects_off_the_server_are_not_followed(tmp_path):
    source, session = make(tmp_path, {
        "https://prerolls.uk/Holidays/": (301, {"Location": "https://evil.example/steal/"}, b"")})
    source.refresh()
    assert "evil.example" not in session.hosts()


def test_the_list_is_read_from_disk_once(tmp_path, monkeypatch):
    source, _ = built(tmp_path)
    from backend.community import prerollsuk
    reads = []
    real = prerollsuk.read_json
    monkeypatch.setattr(prerollsuk, "read_json", lambda *a, **k: reads.append(1) or real(*a, **k))
    source._index = None
    source._index_key = None
    for _ in range(5):
        source.search(q="matrix")
    assert len(reads) == 1


def test_items_group_platform_versions_and_hide_ai_unless_asked(tmp_path):
    source, _ = built(tmp_path)
    items = source.search(sort="az")
    assert [i["title"] for i in items] == ["Matrix", "Neon City", "Snow Globe - Plex"]
    matrix = items[0]
    assert matrix["id"] == "tn:/Community/Matrix%20-%20AwesomeAustn/Matrix%20Plex.mp4"
    assert matrix["platforms"] == ["plex", "jellyfin"]
    assert [v["platform"] for v in matrix["versions"]] == ["plex", "jellyfin"]
    assert matrix["creator"] == {"name": "AwesomeAustn", "url": None}
    assert matrix["downloadable"] is True and matrix["thumbnail_url"] is None
    assert matrix["preview_url"] == "/api/community/preview?id=" + "tn%3A%2FCommunity%2FMatrix%2520-%2520AwesomeAustn%2FMatrix%2520Plex.mp4"
    assert matrix["page_url"] == "https://prerolls.uk/Community/Matrix%20-%20AwesomeAustn/"
    assert items[1]["platforms"] == ["plex", "jellyfin", "emby"]
    assert [i["title"] for i in source.search(category="ai")] == ["Robot Usher"]
    assert len(source.search(include_ai=True)) == 4
    jelly = source.search(prefer=("jellyfin",), q="matrix")[0]
    assert jelly["id"].endswith("Matrix%20Jellyfin.mp4")


def test_search_query_category_duration_and_sort(tmp_path):
    source, _ = built(tmp_path)
    assert [i["title"] for i in source.search(q="snow")] == ["Snow Globe - Plex"]
    assert [i["title"] for i in source.search(category="holidays")] == ["Snow Globe - Plex"]
    assert source.search(duration="lt10") == []          # no lengths read yet
    source.durations.record("/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4", 7000444, 8.5)
    source.durations.record("/Community/_Universal/Neon%20City.mp4", 5000333, 31.0)
    source._rows_cache.clear()
    assert [i["title"] for i in source.search(duration="lt10")] == ["Snow Globe - Plex"]
    assert [i["title"] for i in source.search(sort="shortest")][:2] == ["Snow Globe - Plex", "Neon City"]
    assert [i["title"] for i in source.search()][0] == "Neon City"     # newest first
    assert source.search(downloadable=False) == []
    cats = {c["name"]: c["count"] for c in source.categories()}
    assert cats == {"Community": 2, "Holidays": 1, "AI": 1}


def test_listing_needs_the_fair_use_acceptance_for_refresh_and_download(tmp_path):
    source, session = make(tmp_path, settings={"accepted": False})
    with pytest.raises(AppError) as raised:
        source.refresh()
    assert raised.value.status == 403 and session.calls == []


@pytest.mark.parametrize("path", ["//evil.example/x.mp4", "/a/../../etc/passwd", "/a\\b.mp4", "relative.mp4",
                                  "/x.mp4?u=https://evil.example", "/%2e%2e/secret"])
def test_file_addresses_stay_on_the_server(tmp_path, path):
    source, _ = make(tmp_path)
    with pytest.raises(AppError):
        source.file_url(path)


def test_file_url_is_the_server_in_use_plus_the_path(tmp_path):
    source, _ = make(tmp_path, settings={"accepted": True, "saved_server": "https://home.prerolls.uk"})
    assert source.file_url("/Holidays/Snow.mp4") == "https://home.prerolls.uk/Holidays/Snow.mp4"


def test_download_checks_size_and_type(tmp_path):
    data = video_bytes(7000444)
    url = "https://prerolls.uk/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"
    source, _ = built(tmp_path, routes={url: (200, {"Content-Type": "video/mp4"}, data)})
    item = source.item("/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4")
    out = source.download(item, str(tmp_path / "lib"))
    assert out.size == 7000444 and out.md5 == md5(data)
    source2, _ = built(tmp_path / "b", routes={url: (200, {"Content-Type": "text/html"}, b"<html>")})
    with pytest.raises(AppError):
        source2.download(item, str(tmp_path / "lib2"))


def test_downloads_wait_the_servers_anti_spam_gap(tmp_path):
    source, _ = make(tmp_path, settings={"accepted": True, "saved_server": "https://home.prerolls.uk"})
    assert source.download_gap() == 5.0
    source, _ = make(tmp_path)
    assert source.download_gap() == 2.0


def test_pacer_waits_without_holding_its_lock():
    now = [100.0]
    slept = []

    def sleep(seconds):
        # Another caller can reserve while this one sleeps: the lock is free.
        assert pacer._lock.acquire(blocking=False)
        pacer._lock.release()
        slept.append(seconds)

    pacer = Pacer(lambda: 2.0, sleep=sleep, clock=lambda: now[0])
    assert [pacer.wait(), pacer.wait(), pacer.wait()] == [0.0, 2.0, 4.0]
    assert slept == [2.0, 4.0]


def test_lengths_are_read_from_file_headers_on_the_server(tmp_path):
    from tests.test_community_durations import FTYP, MEDIA, moov, mvhd
    header = FTYP + moov(mvhd(1000, 12_500)) + MEDIA
    url = "https://prerolls.uk/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4"

    def ranged(u, headers):
        start, end = map(int, headers["Range"].split("=")[1].split("-"))
        return FakeResponse(u, 206, {"Content-Type": "video/mp4"}, header[start:end + 1])

    source, session = built(tmp_path, routes={url: ranged})
    out = source.read_lengths()
    assert out["checked"] == 5
    assert source.durations.seconds("/Holidays/Christmas/Snow%20Globe%20-%20Plex.mp4", 7000444) == 12.5
    assert session.hosts() == {"prerolls.uk"}


def test_ids_are_tagged_and_checked():
    assert ids.tag_legacy("/Holidays/Snow.mp4") == "tn:/Holidays/Snow.mp4"
    assert ids.tag_legacy("tn:/Holidays/Snow.mp4") == "tn:/Holidays/Snow.mp4"
    assert ids.tag_legacy("pm:snow") == "pm:snow"
    assert ids.tag_legacy("_Holidays_Snow_mp4") == "_Holidays_Snow_mp4"
    assert ids.tag_legacy("") is None and ids.tag_legacy(None) is None
    assert ids.split("/Holidays/Snow.mp4") == ("prerollsuk", "/Holidays/Snow.mp4")
    assert ids.split("pm:x-logo") == ("prerollsme", "x-logo")
    for bad in ("pm:../x", "pm:X Logo", "zz:/a.mp4", "tn://evil/x.mp4", "https://evil.example/x.mp4", "_mangled"):
        with pytest.raises(AppError):
            ids.split(bad)
