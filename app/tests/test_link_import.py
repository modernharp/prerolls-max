"""Add from a web link: a direct video file is downloaded safely and added
like an upload; pages, streams, private addresses and fakes are refused in
plain words (backend/link_fetch.py, backend/routers/library_add.py)."""
import http.server
import ipaddress
import os
import shutil
import socket
import subprocess
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from backend import jobs, link_fetch, main, models, smart_settings
from backend.database import SessionLocal
from backend.errors import AppError
from tests.test_first_run_and_roles import _wipe_accounts

HAVE_FFMPEG = shutil.which("ffmpeg") is not None


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    if not HAVE_FFMPEG:
        pytest.skip("FFmpeg isn't installed")
    path = tmp_path_factory.mktemp("media") / "intro.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10",
                    "-metadata", f"comment={uuid.uuid4().hex}", "-pix_fmt", "yuv420p", str(path)], check=True)
    return path.read_bytes()


@pytest.fixture(scope="module")
def server(video):
    routes = {
        "/intro.mp4": (200, {"Content-Type": "video/mp4"}, video),
        "/download": (200, {"Content-Type": "application/octet-stream",
                            "Content-Disposition": 'attachment; filename="Pumpkin: Intro?.mp4"'}, video),
        "/missing.mp4": (404, {"Content-Type": "text/plain"}, b"not here"),
        "/big.mp4": (200, {"Content-Type": "video/mp4"}, video * 4),
        "/page": (200, {"Content-Type": "text/html"}, b"<!doctype html><html><body>hi</body></html>"),
        "/sneaky.mp4": (200, {"Content-Type": "video/mp4"}, b"<!DOCTYPE html><html><body>login</body></html>"),
        "/picture.mp4": (200, {"Content-Type": "video/mp4"}, b"\x89PNG\r\n\x1a\n" + b"\x00" * 600),
        "/playlist": (200, {"Content-Type": "application/vnd.apple.mpegurl"}, b"#EXTM3U\n"),
        "/to-private": (302, {"Location": "http://10.0.0.5/intro.mp4"}, b""),
        "/to-intro": (301, {"Location": "/intro.mp4"}, b""),
        "/loop": (302, {"Location": "/loop"}, b""),
    }

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            status, headers, body = routes.get(self.path, (404, {}, b""))
            self.send_response(status)
            for key, value in headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def home(monkeypatch):
    """The test server runs on this machine: no proxy in between."""
    monkeypatch.setattr(link_fetch, "_proxy_for", lambda url: None)


def fetch(url, tmp_path, **kw):
    return link_fetch.fetch(url, str(tmp_path), max_bytes=kw.pop("max_bytes", 50 * 1024 * 1024),
                            home_network=kw.pop("home_network", True), **kw)


def refused(fn):
    with pytest.raises(AppError) as err:
        fn()
    return err.value


# --- the link itself -------------------------------------------------------------------

@pytest.mark.parametrize("url,words", [
    ("", "Paste a link to a video file."),
    ("ftp://example.com/a.mp4", "starts with http:// or https://"),
    ("example.com/a.mp4", "starts with http:// or https://"),
    ("https://user:pw@example.com/a.mp4", "user name or password"),
    ("https://www.youtube.com/watch?v=abc", "That's a video page, not a video file. Prerolls Max can't download from YouTube"),
    ("https://youtu.be/abc", "YouTube"),
    ("https://vimeo.com/123", "Vimeo"),
    ("https://www.tiktok.com/@a/video/1", "TikTok"),
    ("https://example.com/live/index.m3u8", "That's a stream, not a file."),
    ("https://example.com/manifest.mpd", "That's a stream, not a file."),
])
def test_links_that_arent_video_files_are_refused_in_plain_words(url, words):
    err = refused(lambda: link_fetch.check_link(url))
    assert words in err.message and err.status == 422 and "url" in err.fields


def test_a_good_link_is_kept():
    assert link_fetch.check_link("  https://example.com/intro.mp4 ") == "https://example.com/intro.mp4"


# --- addresses ----------------------------------------------------------------------

def resolver(*addresses):
    return lambda host, port, type=0: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, port)) for a in addresses]


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "192.168.1.20", "172.16.0.9", "169.254.169.254",
                                     "224.0.0.1", "0.0.0.0", "100.64.0.1"])
def test_private_and_special_addresses_are_refused(address):
    err = refused(lambda: link_fetch.pick_address("files.example", 80, home_network=False, resolve=resolver(address)))
    assert err.code == "link_private_address" and "your own network" in err.message
    assert "Allow links to my home network" in err.hint


def test_the_home_network_setting_allows_a_nas_but_never_cloud_metadata():
    assert link_fetch.pick_address("nas.example", 80, home_network=True, resolve=resolver("192.168.1.20")) == "192.168.1.20"
    assert link_fetch.pick_address("nas.example", 80, home_network=True, resolve=resolver("127.0.0.1")) == "127.0.0.1"
    for address in ("169.254.169.254", "224.0.0.1"):
        refused(lambda: link_fetch.pick_address("x.example", 80, home_network=True, resolve=resolver(address)))


def test_a_name_that_also_points_inside_is_refused_and_the_checked_address_is_used():
    refused(lambda: link_fetch.pick_address("mixed.example", 80, home_network=False,
                                            resolve=resolver("93.184.216.34", "10.0.0.1")))
    assert link_fetch.pick_address("ok.example", 80, home_network=False,
                                   resolve=resolver("93.184.216.34")) == "93.184.216.34"
    refused(lambda: link_fetch.pick_address("[::ffff:127.0.0.1]", 80, home_network=False))
    refused(lambda: link_fetch.pick_address("localhost", 80, home_network=False, resolve=resolver("93.184.216.34")))


def test_an_unknown_name_says_so_unless_a_proxy_looks_it_up():
    def fail(*a, **k):
        raise socket.gaierror("nope")
    err = refused(lambda: link_fetch.pick_address("nowhere.example", 80, home_network=False, resolve=fail))
    assert err.message == "Prerolls Max couldn't find the site nowhere.example."
    assert link_fetch.pick_address("nowhere.example", 80, home_network=False, resolve=fail, via_proxy=True) is None


# --- downloading ----------------------------------------------------------------------

def test_a_video_file_is_downloaded_with_its_name(server, tmp_path, home, video):
    got = fetch(f"{server}/intro.mp4", tmp_path)
    assert got["filename"] == "intro.mp4" and open(got["path"], "rb").read() == video
    named = fetch(f"{server}/download", tmp_path)
    assert named["filename"] == "Pumpkin Intro.mp4"  # ":" and "?" can't be in file names
    moved = fetch(f"{server}/to-intro", tmp_path)
    assert moved["final_url"].endswith("/intro.mp4")
    assert not [n for n in os.listdir(tmp_path) if n.endswith(".part")]


def test_progress_is_reported(server, tmp_path, home):
    seen = []
    fetch(f"{server}/intro.mp4", tmp_path, progress=lambda size, total: seen.append((size, total)))
    assert seen and seen[-1][0] == seen[-1][1]


@pytest.mark.parametrize("path,code,words", [
    ("/missing.mp4", "link_failed", "There's no file at that link"),
    ("/page", "link_web_page", "That link opens a web page, not a video file."),
    ("/sneaky.mp4", "link_web_page", "That link opens a web page, not a video file."),
    ("/playlist", "link_stream", "That's a stream, not a file."),
    ("/loop", "link_redirects", "too many times"),
])
def test_failures_are_plain(server, tmp_path, home, path, code, words):
    err = refused(lambda: fetch(f"{server}{path}", tmp_path))
    assert err.code == code and words in err.message
    assert not [n for n in os.listdir(tmp_path)]


def test_a_redirect_to_a_private_address_is_refused_even_when_the_first_hop_is_public(server, tmp_path, home,
                                                                                         monkeypatch):
    real = link_fetch._allowed
    monkeypatch.setattr(link_fetch, "_allowed",
                        lambda ip, home_network: ip == ipaddress.ip_address("127.0.0.1") or real(ip, home_network))
    err = refused(lambda: fetch(f"{server}/to-private", tmp_path, home_network=False))
    assert err.code == "link_private_address" and "10.0.0.5" in err.message


def test_too_big_stops_before_or_while_downloading(server, tmp_path, home, video):
    err = refused(lambda: fetch(f"{server}/big.mp4", tmp_path, max_bytes=len(video)))
    assert err.status == 413 and "too big" in err.message
    assert not os.listdir(tmp_path)


def test_ffmpeg_must_find_moving_pictures_not_a_still_image(tmp_path, video):
    from backend.routers.library_add import has_video_stream
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(video)
    picture = tmp_path / "picture.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=64x64", "-frames:v", "1",
                    "-f", "image2", "-c:v", "png", str(picture)], check=True)
    assert has_video_stream("ffprobe", str(clip)) is True
    assert has_video_stream("ffprobe", str(picture)) is False
    assert has_video_stream("ffprobe", str(tmp_path / "missing.mp4")) is False


# --- the whole job ------------------------------------------------------------------

@pytest.fixture
def admin():
    _wipe_accounts()
    client = TestClient(main.app, raise_server_exceptions=False)
    assert client.post("/auth/setup", json={"username": "admin", "password": "admin pass 1"}).status_code == 200
    yield client
    db = SessionLocal()
    try:
        smart_settings.save(db, {"links_allow_home_network": False})
        db.commit()
    finally:
        db.close()
    smart_settings.clear_cache()
    _wipe_accounts()


def run_job(client, body):
    r = client.post("/api/library/from-link", json=body)
    assert r.status_code == 200, r.text
    return jobs.runner.wait(r.json()["job_id"], timeout=60)


def test_a_link_is_added_like_an_upload_and_a_second_copy_is_asked_about(admin, server):
    # Off: this machine's own address is refused.
    job = run_job(admin, {"url": f"{server}/intro.mp4"})
    assert job["state"] == "failed" and "your own network" in job["message"]
    assert admin.put("/api/smart-settings", json={"links_allow_home_network": True}).status_code == 200
    smart_settings.clear_cache()

    job = run_job(admin, {"url": f"{server}/intro.mp4"})
    assert job["state"] == "done", job
    added = job["result"]
    assert added["uploaded"] is True and added["filename"].startswith("intro")
    try:
        again = run_job(admin, {"url": f"{server}/to-intro"})["result"]
        assert again["duplicate"] is True and again["token"]
        assert again["message"].startswith("Already in your library as ")
        assert admin.post(f"/prerolls/upload/staged/{again['token']}", json={"action": "skip"}).json()["skipped"]

        fake = run_job(admin, {"url": f"{server}/picture.mp4"})
        assert fake["state"] == "failed" and "isn't a video" in fake["message"]
    finally:
        db = SessionLocal()
        row = db.query(models.Preroll).filter(models.Preroll.id == added["id"]).first()
        if row is not None:
            if row.path and os.path.exists(row.path):
                os.remove(row.path)
            db.delete(row)
            db.commit()
        db.close()


def test_the_link_and_collection_are_checked_before_starting(admin):
    r = admin.post("/api/library/from-link", json={"url": "https://youtu.be/x"})
    assert r.status_code == 422 and "YouTube" in r.json()["error"]["fields"]["url"]
    r = admin.post("/api/library/from-link", json={"url": "https://example.com/a.mp4", "collection_id": 999999})
    assert r.status_code == 404


@pytest.mark.skipif(shutil.which("openssl") is None, reason="needs openssl to make a test certificate")
def test_https_connects_to_the_checked_address_but_checks_the_certificate_for_the_name(tmp_path, home, monkeypatch,
                                                                                         video):
    import ssl
    key, cert = tmp_path / "key.pem", tmp_path / "cert.pem"
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", str(key), "-out", str(cert),
                    "-days", "1", "-subj", "/CN=videos.test", "-addext", "subjectAltName=DNS:videos.test"],
                   check=True, capture_output=True)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(video)))
            self.end_headers()
            self.wfile.write(video)

        def log_message(self, *args):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(cert))
    try:
        # "videos.test" is looked up once (to this machine) and the certificate
        # is checked against that name.
        got = link_fetch.fetch(f"https://videos.test:{port}/intro.mp4", str(tmp_path / "out"), max_bytes=10 ** 8,
                               home_network=True, resolve=resolver("127.0.0.1"))
        assert open(got["path"], "rb").read() == video
        # Another name for the same address doesn't match the certificate.
        err = refused(lambda: link_fetch.fetch(f"https://other.test:{port}/intro.mp4", str(tmp_path / "out2"),
                                               max_bytes=10 ** 8, home_network=True, resolve=resolver("127.0.0.1")))
        assert err.code == "link_tls"
    finally:
        httpd.shutdown()
