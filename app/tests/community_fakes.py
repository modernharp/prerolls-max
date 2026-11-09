"""Recorded responses for the community library tests: no network is used."""
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

FIXTURES = Path(__file__).parent / "fixtures" / "community"


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeResponse:
    def __init__(self, url, status=200, headers=None, body=b""):
        self.url = url
        self.status_code = status
        self.headers = dict(headers or {})
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")
        self.closed = False

    @property
    def content(self):
        return self._body

    @property
    def text(self):
        return self._body.decode("utf-8")

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return json.loads(self.text)

    def iter_content(self, chunk_size=1024):
        for i in range(0, len(self._body), chunk_size or 1024):
            yield self._body[i:i + chunk_size]

    def close(self):
        self.closed = True


class FakeSession:
    """``routes`` maps a full URL to (status, headers, body) or a callable(url, headers)."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls = []

    def get(self, url, headers=None, stream=False, timeout=None, allow_redirects=True):
        assert allow_redirects is False, "community requests must follow redirects by hand"
        self.calls.append((url, dict(headers or {})))
        route = self.routes.get(url)
        if route is None:
            return FakeResponse(url, 404, {"Content-Type": "text/plain"}, b"not found")
        if callable(route):
            route = route(url, headers or {})
        if isinstance(route, FakeResponse):
            return route
        status, hdrs, body = route
        return FakeResponse(url, status, hdrs, body)

    def urls(self):
        return [u for u, _ in self.calls]

    def hosts(self):
        return {urlsplit(u).hostname for u, _ in self.calls}


def video_bytes(size, seed=b"v"):
    """A fake MP4 of exactly ``size`` bytes."""
    head = b"\x00\x00\x00\x18ftypmp42"
    body = (seed * (size // len(seed) + 1))[: max(0, size - len(head))]
    return (head + body)[:size]


def md5(data):
    return hashlib.md5(data).hexdigest()


def prerollsuk_routes(base="https://prerolls.uk"):
    site = load_fixture("prerollsuk_site.json")
    routes = {
        "https://prerolls.uk/servers.json": (200, {"Content-Type": "application/json"}, json.dumps(site["servers"])),
        base + "/": (200, {"Content-Type": "text/html; charset=utf-8"}, site["root_html"]),
    }
    for path, listing in site["listings"].items():
        routes[base + path] = (200, {"Content-Type": "application/json"}, json.dumps(listing))
    return routes


def no_sleep(_seconds):
    return None
